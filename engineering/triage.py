"""Small, non-executable JSON classifier; no training dependency at runtime.

This is a lab suggestion, never an authorization or moderation decision. Missing
or invalid artifacts intentionally disable triage without disabling the lab.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import time
import unicodedata

LABELS = ("bug report", "idea", "question")
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_FEATURES = 5000
MAX_TEXT_LENGTH = 1500
ARTIFACT_PATH = Path(__file__).with_name("ml_artifacts") / "triage-v1.json"
TOKEN_PATTERN = r"(?u)\b\w\w+\b"
TOKEN_RE = re.compile(TOKEN_PATTERN)
CONTRACT = {
    "normalization": "NFKC",
    "lowercase": True,
    "token_pattern": TOKEN_PATTERN,
    "ngram_range": [1, 2],
    "term_frequency": "raw-count",
    "idf": "log((1+n_documents)/(1+document_frequency))+1",
    "norm": "l2",
    "classifier": "multinomial-logistic-regression",
    "probabilities": "stable-softmax",
    "label_order": list(LABELS),
}

EXPLANATIONS = {
    None: "Suggested category from a small English text model. The score is not calibrated confidence.",
    "unsupported_script": "This English-only model does not support this script. No category was selected.",
    "insufficient_vocabulary": "Too little familiar vocabulary to make a useful suggestion. No category was selected.",
    "below_threshold": "The strongest score is below the validation-selected threshold. No category was selected.",
    "input_too_long": "Use plain text of at most 1,500 characters for a suggestion.",
    "model_unavailable": "Triage is temporarily unavailable. Submission and delivery still work.",
}


class ArtifactError(ValueError):
    """An artifact cannot safely satisfy the frozen inference contract."""


def normalize_text(text):
    return unicodedata.normalize("NFKC", text).lower()


def supported_script(text):
    """Reject non-Latin letters; this deliberately is not language detection."""
    return all(
        not character.isalpha() or "LATIN" in unicodedata.name(character, "")
        for character in normalize_text(text)
    )


def _numbers(values, count, *, positive=False):
    if not isinstance(values, list) or len(values) != count:
        raise ArtifactError("Invalid numeric dimensions.")
    for value in values:
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or abs(value) > 1_000_000
            or (positive and value <= 0)
        ):
            raise ArtifactError("Invalid numeric parameter.")


def validate_artifact(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ArtifactError("Unsupported artifact schema.")
    if data.get("contract") != CONTRACT or data.get("labels") != list(LABELS):
        raise ArtifactError("Inference contract mismatch.")
    if not isinstance(data.get("version"), str) or not 1 <= len(data["version"]) <= 80:
        raise ArtifactError("Invalid model version.")
    features = data.get("features")
    if (
        not isinstance(features, list)
        or not 1 <= len(features) <= MAX_FEATURES
        or any(not isinstance(term, str) or not 1 <= len(term) <= 100 for term in features)
        or len(set(features)) != len(features)
    ):
        raise ArtifactError("Invalid vocabulary.")
    _numbers(data.get("idf"), len(features), positive=True)
    _numbers(data.get("intercepts"), len(LABELS))
    coefficients = data.get("coefficients")
    if not isinstance(coefficients, list) or len(coefficients) != len(LABELS):
        raise ArtifactError("Invalid coefficient dimensions.")
    for row in coefficients:
        _numbers(row, len(features))
    threshold = data.get("threshold")
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 1 / 3 <= threshold <= 1:
        raise ArtifactError("Invalid abstention threshold.")
    if type(data.get("min_recognized_words")) is not int or not 1 <= data["min_recognized_words"] <= 20:
        raise ArtifactError("Invalid vocabulary floor.")
    ratio = data.get("min_recognized_ratio")
    if type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
        raise ArtifactError("Invalid vocabulary coverage floor.")
    if not isinstance(data.get("evidence"), dict) or not isinstance(data.get("limitations"), list):
        raise ArtifactError("Missing model evidence.")
    if any(not isinstance(item, str) for item in data["limitations"]):
        raise ArtifactError("Invalid model limitations.")
    return data


@lru_cache(maxsize=2)
def _read_artifact(path, modified_ns, size):
    del modified_ns  # Part of the cache key so atomic replacements are revalidated.
    if not 1 <= size <= MAX_ARTIFACT_BYTES:
        raise ArtifactError("Artifact exceeds the byte budget.")
    with Path(path).open("rb") as source:
        raw = source.read(MAX_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ArtifactError("Artifact exceeds the byte budget.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ArtifactError("Invalid artifact JSON.") from error
    validate_artifact(data)
    data["_vocabulary"] = {term: index for index, term in enumerate(data["features"])}
    data["_artifact_bytes"] = len(raw)
    return data


def load_model(path=None):
    target = Path(path) if path is not None else ARTIFACT_PATH
    stat = target.stat()
    return _read_artifact(str(target), stat.st_mtime_ns, stat.st_size)


def vectorize(model, text):
    """Return sparse L2-normalized raw-TF * smoothed-IDF and vocabulary evidence."""
    tokens = TOKEN_RE.findall(normalize_text(text))
    vocabulary = model.get("_vocabulary")
    if vocabulary is None:
        vocabulary = {term: index for index, term in enumerate(model["features"])}
    terms = tokens + [left + " " + right for left, right in zip(tokens, tokens[1:])]
    counts = Counter(vocabulary[term] for term in terms if term in vocabulary)
    values = {index: count * model["idf"][index] for index, count in counts.items()}
    norm = math.sqrt(math.fsum(value * value for value in values.values()))
    if norm:
        values = {index: value / norm for index, value in values.items()}
    recognized = {token for token in tokens if token in vocabulary}
    unique_tokens = set(tokens)
    return values, len(recognized), len(recognized) / len(unique_tokens) if unique_tokens else 0.0


def predict_scores(model, text):
    """Unthresholded scores for parity/evaluation, including all held-out rows."""
    features, recognized_words, recognized_ratio = vectorize(model, text)
    logits = [
        intercept + math.fsum(features[index] * row[index] for index in features)
        for intercept, row in zip(model["intercepts"], model["coefficients"])
    ]
    highest = max(logits)
    exponentials = [math.exp(value - highest) for value in logits]
    denominator = math.fsum(exponentials)
    scores = [value / denominator for value in exponentials]
    winner = max(range(len(scores)), key=scores.__getitem__)
    contributions = [
        {
            "name": model["features"][index],
            "contribution": value * model["coefficients"][winner][index],
        }
        for index, value in features.items()
    ]
    contributions.sort(key=lambda item: (-abs(item["contribution"]), item["name"]))
    return {
        "label": LABELS[winner],
        "score": scores[winner],
        "scores": scores,
        "logits": logits,
        "terms": contributions,
        "intercept": model["intercepts"][winner],
        "recognized_words": recognized_words,
        "recognized_ratio": recognized_ratio,
    }


def abstention_reason(model, text, prediction):
    if not supported_script(text):
        return "unsupported_script"
    if (
        prediction["recognized_words"] < model["min_recognized_words"]
        or prediction["recognized_ratio"] < model["min_recognized_ratio"]
    ):
        return "insufficient_vocabulary"
    if prediction["score"] < model["threshold"]:
        return "below_threshold"
    return None


def classify(text):
    started = time.perf_counter()
    result = {
        "status": "unavailable",
        "label": None,
        "score": None,
        "terms": [],
        "version": None,
        "latency_ms": 0.0,
        "reason": "model_unavailable",
    }
    try:
        model = load_model()
        result["version"] = model["version"]
        if not isinstance(text, str) or len(text) > MAX_TEXT_LENGTH:
            result.update(status="uncertain", reason="input_too_long")
        else:
            prediction = predict_scores(model, text)
            reason = abstention_reason(model, text, prediction)
            result.update(
                status="uncertain" if reason else "suggested",
                label=None if reason else prediction["label"],
                score=prediction["score"],
                terms=prediction["terms"][:6],
                reason=reason,
            )
    except (OSError, ArtifactError, UnicodeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        # Do not leak paths, parameters, exceptions, or input text to the UI.
        pass
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 4)
    result["explanation"] = EXPLANATIONS[result["reason"]]
    return result


def model_card():
    try:
        model = load_model()
        return {
            "status": "available",
            "version": model["version"],
            "labels": list(LABELS),
            "threshold": model["threshold"],
            "min_recognized_words": model["min_recognized_words"],
            "min_recognized_ratio": model["min_recognized_ratio"],
            "feature_count": len(model["features"]),
            "artifact_bytes": model["_artifact_bytes"],
            "metrics": model["evidence"],
            "limitations": model["limitations"],
        }
    except (OSError, ArtifactError, UnicodeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {
            "status": "unavailable",
            "version": None,
            "labels": list(LABELS),
            "metrics": {},
            "limitations": ["Triage is unavailable. Submission and delivery still work."],
        }
