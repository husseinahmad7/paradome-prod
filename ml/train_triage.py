"""Reproducible, two-phase offline training. See README before changing v1.

Training/validation produces a frozen candidate. Only a subsequent evaluate
invocation opens the held-out predictions. Training libraries are never imported
by the Django application.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score

from engineering.triage import (
    CONTRACT, LABELS, MAX_ARTIFACT_BYTES, abstention_reason, normalize_text,
    predict_scores, validate_artifact, vectorize,
)

CORPUS = ROOT / "ml/data/triage-corpus.json"
CHALLENGES = ROOT / "ml/data/challenges.json"
BUILD = ROOT / ".gstack/ml-training"
ARTIFACT = ROOT / "engineering/ml_artifacts/triage-v1.json"
GOLDEN = ROOT / "engineering/ml_artifacts/golden-v1.json"
REPORT = ROOT / "ml/evaluation-v1.json"
FREEZE = ROOT / "ml/frozen-v1.json"
VERSION = "triage-en-v1"
# Frozen before any held-out evaluation; intentionally no test-driven search.
CONFIG = {
    "max_features": 4000,
    "C": 5.0,
    "solver": "lbfgs",
    "max_iter": 2000,
    "tol": 1e-9,
    "random_state": 1729,
    "min_recognized_words": 3,
    "min_recognized_ratio": 0.25,
    "threshold_candidates": [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90],
    "validation_precision_floor": 0.85,
}
LIMITATIONS = [
    "360 LLM-authored synthetic English examples, not independent human labels or production traffic.",
    "Paraphrases stay together in 90 scenario groups. Wording style is still shared across groups.",
    "A score is the model's softmax output, not a calibrated probability of correctness.",
    "Latin-script checks do not identify English. Unfamiliar English and other Latin-script languages can be misclassified confidently.",
    "The small bag-of-words model does not reliably reason about negation, intent, or mixed requests.",
    "Observed malfunction takes precedence over a proposed capability, then requests for guidance.",
    "Suggestions never change permissions, delivery, or real application content. Visitors retain the final decision.",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data, *, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":") if compact else None,
                         indent=None if compact else 2) + "\n"
    payload = encoded.encode("utf-8")
    with path.open("wb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    if path.read_bytes() != payload:
        raise OSError(f"Generated JSON did not survive read-back verification: {path.name}")
    return len(payload)


def dataset():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows = {"train": [], "validation": [], "test": []}
    seen_groups, seen_texts = set(), set()
    for group in corpus["groups"]:
        if group["id"] in seen_groups or group["label"] not in LABELS:
            raise ValueError("Duplicate group or unsupported label.")
        seen_groups.add(group["id"])
        for index, text in enumerate(group["texts"]):
            normalized = normalize_text(text)
            if normalized in seen_texts:
                raise ValueError("Exact duplicate text in authored corpus.")
            seen_texts.add(normalized)
            rows[group["split"]].append({
                "id": f'{group["id"]}-{index + 1}',
                "group": group["id"], "text": text, "label": group["label"],
            })
    if sum(map(len, rows.values())) < 300:
        raise ValueError("At least 300 authored examples are required.")
    return corpus, rows


def fit(rows):
    train = rows["train"]
    vectorizer = TfidfVectorizer(
        preprocessor=normalize_text, lowercase=False,
        token_pattern=CONTRACT["token_pattern"], ngram_range=(1, 2),
        binary=False, sublinear_tf=False, use_idf=True, smooth_idf=True,
        norm="l2", dtype=np.float64, max_features=CONFIG["max_features"],
    )
    matrix = vectorizer.fit_transform([row["text"] for row in train])
    classifier = LogisticRegression(
        C=CONFIG["C"], solver=CONFIG["solver"], max_iter=CONFIG["max_iter"],
        tol=CONFIG["tol"], random_state=CONFIG["random_state"],
    ).fit(matrix, [row["label"] for row in train])
    assert classifier.classes_.tolist() == list(LABELS)
    return vectorizer, classifier


def metrics(model, rows):
    predictions = [predict_scores(model, row["text"]) for row in rows]
    expected = [row["label"] for row in rows]
    actual = [row["label"] for row in predictions]
    accepted = [
        index for index, row in enumerate(rows)
        if abstention_reason(model, row["text"], predictions[index]) is None
    ]
    report = classification_report(expected, actual, labels=list(LABELS),
                                   output_dict=True, zero_division=0)
    per_class = {}
    for label in LABELS:
        item = report[label]
        class_rows = [i for i, expected_label in enumerate(expected) if expected_label == label]
        class_accepted = [i for i in accepted if actual[i] == label]
        per_class[label] = {
            "precision": item["precision"], "recall": item["recall"],
            "f1": item["f1-score"], "support": int(item["support"]),
            "accepted_precision": (
                sum(expected[i] == actual[i] for i in class_accepted) / len(class_accepted)
                if class_accepted else None
            ),
            "coverage": sum(i in accepted for i in class_rows) / len(class_rows),
        }
    majority = LABELS[0]  # Training counts tie; fixed lexical tie-break, never test-selected.
    return {
        "count": len(rows),
        "macro_f1": f1_score(expected, actual, labels=list(LABELS), average="macro"),
        "accuracy": accuracy_score(expected, actual),
        "per_class": per_class,
        "accepted_precision": (
            sum(expected[i] == actual[i] for i in accepted) / len(accepted)
            if accepted else None
        ),
        "coverage": len(accepted) / len(rows),
        "accepted_count": len(accepted),
        "baseline": {
            "name": "training-majority (lexical tie-break)",
            "label": majority,
            "macro_f1": f1_score(expected, [majority] * len(rows),
                                labels=list(LABELS), average="macro"),
            "accuracy": accuracy_score(expected, [majority] * len(rows)),
        },
    }


def parity(model, vectorizer, classifier, texts):
    expected_matrix = vectorizer.transform(texts)
    expected_scores = classifier.predict_proba(expected_matrix)
    expected_logits = classifier.decision_function(expected_matrix)
    maximum = 0.0
    golden = []
    for index, text in enumerate(texts):
        result = predict_scores(model, text)
        sparse, _, _ = vectorize(model, text)
        dense = np.zeros(len(model["features"]))
        for column, value in sparse.items():
            dense[column] = value
        feature_error = float(np.max(np.abs(dense - expected_matrix[index].toarray()[0])))
        score_error = float(np.max(np.abs(np.array(result["scores"]) - expected_scores[index])))
        logit_error = float(np.max(np.abs(np.array(result["logits"]) - expected_logits[index])))
        maximum = max(maximum, feature_error, score_error, logit_error)
        if maximum > 1e-6:
            raise AssertionError(f"Runtime/training parity exceeded tolerance: {maximum}")
        golden.append({
            "text": text,
            "scores": expected_scores[index].tolist(),
            "logits": expected_logits[index].tolist(),
            "label": result["label"],
        })
    return maximum, golden


def train(*, reproduce=False):
    if REPORT.exists() and not reproduce:
        raise SystemExit(
            "v1 has already seen its holdout. Use --phase reproduce to verify it. "
            "A revised model needs a new version and a fresh untouched holdout."
        )
    corpus, rows = dataset()
    vectorizer, classifier = fit(rows)
    model = {
        "schema_version": 1, "version": VERSION, "contract": CONTRACT,
        "labels": list(LABELS), "features": vectorizer.get_feature_names_out().tolist(),
        "idf": vectorizer.idf_.tolist(), "coefficients": classifier.coef_.tolist(),
        "intercepts": classifier.intercept_.tolist(),
        "min_recognized_words": CONFIG["min_recognized_words"],
        "min_recognized_ratio": CONFIG["min_recognized_ratio"],
        "threshold": 1.0, "evidence": {}, "limitations": LIMITATIONS,
    }
    candidates = []
    for threshold in CONFIG["threshold_candidates"]:
        model["threshold"] = threshold
        result = metrics(model, rows["validation"])
        candidates.append({"threshold": threshold, **result})
    qualified = [
        item for item in candidates
        if item["accepted_precision"] is not None
        and item["accepted_precision"] >= CONFIG["validation_precision_floor"]
    ]
    # Maximize validation coverage, then precision; lower threshold breaks exact ties.
    chosen = max(qualified, key=lambda item: (
        item["coverage"], item["accepted_precision"], -item["threshold"]
    )) if qualified else None
    model["threshold"] = chosen["threshold"] if chosen else 1.0
    validation = metrics(model, rows["validation"])
    model["evidence"] = {
        "dataset_version": corpus["dataset_version"],
        "dataset_sha256": digest(CORPUS),
        "split_counts": {split: len(items) for split, items in rows.items()},
        "scenario_groups": len(corpus["groups"]),
        "validation": validation,
        "threshold_selection": "Validation-only maximum coverage at accepted precision >= 0.85; tie-break precision then lower threshold.",
    }
    validate_artifact(model)
    parity_error, _ = parity(model, vectorizer, classifier,
                            [row["text"] for row in rows["validation"]])
    freeze = {
        "version": VERSION, "dataset_sha256": digest(CORPUS),
        "configuration": CONFIG, "threshold": model["threshold"],
        "validation_candidates": candidates, "validation_parity_max_error": parity_error,
        "procedure": "Written by train phase before the evaluate phase. No test predictions used.",
        "training_versions": {name: importlib.metadata.version(name) for name in
                              ("scikit-learn", "numpy", "scipy", "joblib", "threadpoolctl")},
    }
    if reproduce:
        original = json.loads(FREEZE.read_text(encoding="utf-8"))
        deployed = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        assert original["dataset_sha256"] == freeze["dataset_sha256"]
        assert original["configuration"] == freeze["configuration"]
        assert original["threshold"] == freeze["threshold"]
        for name in ("coefficients", "intercepts", "idf"):
            assert np.max(np.abs(np.asarray(model[name]) - np.asarray(deployed[name]))) < 1e-6
        assert model["features"] == deployed["features"]
        heldout = metrics(model, rows["test"])
        assert abs(heldout["macro_f1"] - deployed["evidence"]["test"]["macro_f1"]) < 1e-12
        print(json.dumps({"reproduced": True, "test": heldout}, indent=2))
        return
    write_json(BUILD / "candidate.json", model, compact=True)
    write_json(FREEZE, freeze)
    print(json.dumps({"frozen_threshold": model["threshold"], "validation": validation,
                      "test_evaluated": False}, indent=2))


def evaluate():
    if REPORT.exists():
        raise SystemExit("v1 was already evaluated. Run --phase reproduce, not another evaluation.")
    _, rows = dataset()
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze["dataset_sha256"] != digest(CORPUS) or freeze["configuration"] != CONFIG:
        raise SystemExit("Dataset or configuration changed after freezing.")
    model = validate_artifact(json.loads((BUILD / "candidate.json").read_text(encoding="utf-8")))
    if model["threshold"] != freeze["threshold"]:
        raise SystemExit("Candidate threshold differs from the frozen threshold.")
    heldout = metrics(model, rows["test"])
    vectorizer, classifier = fit(rows)
    contract_texts = [
        "THE message FAILS after login.", "Ｆｕｌｌｗｉｄｔｈ login fails.",
        "A ﬁle fails to save.", "save save save", "x a 1 _ aa_ab",
        "Could we add a preview?", "", "موضوع جديد", "unknownword flerm snorf",
        "How does a database transaction work?",
    ]
    parity_error, golden = parity(model, vectorizer, classifier,
                                 [row["text"] for row in rows["test"]] + contract_texts)
    challenge_rows = json.loads(CHALLENGES.read_text(encoding="utf-8"))["examples"]
    challenges = []
    for row in challenge_rows:
        prediction = predict_scores(model, row["text"])
        reason = abstention_reason(model, row["text"], prediction)
        challenges.append({
            **row, "predicted_label": prediction["label"], "score": prediction["score"],
            "accepted": reason is None, "reason": reason,
            "correct": prediction["label"] == row["label"] if row["label"] else None,
        })
    promotion = (
        heldout["macro_f1"] >= 0.80
        and (heldout["accepted_precision"] or 0) >= 0.85
        and heldout["coverage"] >= 0.50
    )
    model["evidence"].update({
        "test": heldout, "promotion_passed": promotion,
        "promotion_targets": {"macro_f1": 0.80, "accepted_precision": 0.85, "coverage": 0.50},
        "parity_max_absolute_error": parity_error,
        "test_policy": "Threshold frozen before test. No model revision was made from these test findings.",
    })
    artifact_bytes = write_json(ARTIFACT, model, compact=True)
    if artifact_bytes > MAX_ARTIFACT_BYTES:
        raise AssertionError("Artifact exceeds 1 MiB.")
    write_json(GOLDEN, {"version": VERSION, "tolerance": 1e-6, "examples": golden})
    # A local CPU measurement, not a production latency guarantee.
    for row in rows["test"]:
        predict_scores(model, row["text"])
    samples = []
    for iteration in range(500):
        text = rows["test"][iteration % len(rows["test"])]["text"]
        started = time.perf_counter()
        prediction = predict_scores(model, text)
        abstention_reason(model, text, prediction)
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    benchmark = {
        "scope": "500 warm local predict_scores + abstention calls; excludes disk loading, Django and network",
        "python": platform.python_version(), "platform": platform.platform(),
        "sample_count": len(samples), "p50_ms": statistics.median(samples),
        "p95_ms": ordered[int(len(samples) * 0.95) - 1], "max_ms": max(samples),
    }
    report = {
        "version": VERSION, "dataset_sha256": digest(CORPUS),
        "artifact_sha256": digest(ARTIFACT), "artifact_bytes": artifact_bytes,
        "feature_count": len(model["features"]), "threshold": model["threshold"],
        "test": heldout, "promotion_passed": promotion,
        "parity_max_absolute_error": parity_error, "benchmark": benchmark,
        "challenges": challenges, "limitations": LIMITATIONS,
    }
    write_json(REPORT, report)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("challenges", "limitations")}, indent=2))
    if not promotion:
        print("Promotion targets not met. Do not advertise this model as promoted.", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("train", "evaluate", "reproduce"), required=True)
    args = parser.parse_args()
    if args.phase == "evaluate":
        evaluate()
    else:
        train(reproduce=args.phase == "reproduce")
