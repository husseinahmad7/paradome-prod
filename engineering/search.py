"""Fixed public retrieval: stdlib BM25, cosine ranking and frozen calibration.

Visitor queries are processed in memory. Only record_observation may persist
search metadata; its schema deliberately has no text or embedding field.
"""

from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from time import perf_counter

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum

from . import services
from .models import ConsumerReceipt, OutboxEvent, SearchObservation

MODEL_ID = "Xenova/all-MiniLM-L6-v2"
REVISION = "751bff37182d3f1213fa05d7196b954e230abad9"
RUNTIME = "4.3.1"
INDEX_VERSION = "minilm-q8-discussions-v1"
DIMENSION = 384
POOLING = "mean-l2"
ROOT = Path(__file__).resolve().parents[1] / "ml" / "search"
ARTIFACT_ROOT = Path(__file__).resolve().parent / "ml_artifacts"
MAX_OBSERVATIONS = 40
FALLBACK_REASONS = {
    "keyword_requested": "Keyword search selected.",
    "javascript_unavailable": "Browser embeddings are unavailable; keyword search is ready.",
    "model_loading": "The browser model is still loading. These are keyword results.",
    "model_unavailable": "The browser model could not load. Keyword search remains available.",
    "model_unavailable_demo": "Simulated model outage. These are keyword results.",
    "embedding_invalid": "The embedding is invalid. These are keyword results.",
    "artifact_mismatch": "Model and index versions do not match. These are keyword results.",
    "artifact_unavailable": "The evaluated semantic index is unavailable. These are keyword results.",
    "semantic_disabled": "Semantic retrieval is disabled for this release.",
    "evaluation_gate": "The semantic release gate is not met. Keyword search is the default.",
    "low_confidence": "No confident semantic match. These keyword suggestions may be unrelated.",
}
STOP_WORDS = frozenset("a an the is are was were be been being to of in on at by for with and or as it its this that these those my our we you i how what do does can should from when which have has if then than into not".split())


def tokens(text):
    return [term for term in re.findall(r"[a-z0-9]+", text.lower()) if term not in STOP_WORDS]


@lru_cache(maxsize=1)
def corpus():
    raw = ROOT.joinpath("data/corpus-v1.json").read_bytes()
    content = json.loads(raw)
    documents = content["documents"]
    if len(documents) != 120 or len({doc["id"] for doc in documents}) != 120:
        raise ValueError("Invalid public corpus")
    return content, hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=1)
def keyword_index():
    documents = corpus()[0]["documents"]
    counts = [Counter(tokens(doc["title"] + " " + doc["text"])) for doc in documents]
    lengths = [sum(count.values()) for count in counts]
    frequencies = Counter(term for count in counts for term in count)
    return counts, lengths, sum(lengths) / len(lengths), frequencies


def keyword_rank(text, *, limit=5):
    """BM25 k1=1.2, b=.75; query terms count once; positive matches only."""
    counts, lengths, average, frequencies = keyword_index()
    terms = set(tokens(text))
    size = len(counts)
    scored = []
    for document, count, length in zip(corpus()[0]["documents"], counts, lengths):
        score = 0.0
        for term in terms:
            tf = count[term]
            if not tf:
                continue
            df = frequencies[term]
            idf = math.log(1 + (size - df + .5) / (df + .5))
            score += idf * (tf * 2.2) / (tf + 1.2 * (.25 + .75 * length / average))
        if score > 0:
            scored.append((document, score))
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]["id"]))[:limit]


def normalize_vector(values):
    if not isinstance(values, list) or len(values) != DIMENSION:
        raise ValueError("embedding_invalid")
    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100 for v in values):
        raise ValueError("embedding_invalid")
    norm = math.sqrt(sum(v * v for v in values))
    if norm < 1e-8:
        raise ValueError("embedding_invalid")
    return [v / norm for v in values]


def embedding_contract():
    return {"model_id": MODEL_ID, "revision": REVISION, "runtime_version": RUNTIME,
            "index_version": INDEX_VERSION, "dimension": DIMENSION, "pooling": POOLING, "dtype": "q8"}


def validate_embedding(embedding):
    if not isinstance(embedding, dict):
        raise ValueError("embedding_invalid")
    if any(embedding.get(key) != value for key, value in embedding_contract().items()):
        raise ValueError("artifact_mismatch")
    return normalize_vector(embedding.get("values"))


@lru_cache(maxsize=1)
def semantic_artifacts():
    try:
        index = json.loads(ARTIFACT_ROOT.joinpath("search-index-v1.json").read_bytes())
        report = json.loads(ROOT.joinpath("evaluation-v1.json").read_bytes())
        calibrator = json.loads(ARTIFACT_ROOT.joinpath("search-calibration-v1.json").read_bytes())
        contract = embedding_contract()
        for artifact in (index, calibrator, report):
            if artifact["contract"] != contract or artifact["corpus_sha256"] != corpus()[1]:
                raise ValueError("artifact_mismatch")
        ids = [doc["id"] for doc in corpus()[0]["documents"]]
        if index["document_ids"] != ids or len(index["vectors"]) != len(ids):
            raise ValueError("artifact_mismatch")
        # Digest binds the report and calibration to the precise exported index.
        digest = hashlib.sha256(ARTIFACT_ROOT.joinpath("search-index-v1.json").read_bytes()).hexdigest()
        if calibrator["index_sha256"] != digest or report["index_sha256"] != digest:
            raise ValueError("artifact_mismatch")
        vectors = [normalize_vector(v) for v in index["vectors"]]
        if len(calibrator["weights"]) != 2 or not all(math.isfinite(v) for v in calibrator["weights"] + [calibrator["intercept"], calibrator["threshold"]]):
            raise ValueError("artifact_mismatch")
        if not 0 <= calibrator["threshold"] <= 1:
            raise ValueError("artifact_mismatch")
        return vectors, calibrator, report, ""
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        reason = "artifact_mismatch" if isinstance(exc, ValueError) and str(exc) == "artifact_mismatch" else "artifact_unavailable"
        return None, None, None, reason


def cosine_rank(vector, *, limit=5):
    vectors, _, _, reason = semantic_artifacts()
    if reason:
        raise ValueError(reason)
    scored = [(doc, max(-1.0, min(1.0, sum(a * b for a, b in zip(vector, encoded))))) for doc, encoded in zip(corpus()[0]["documents"], vectors)]
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]["id"]))[:limit]


def relevance_confidence(top_score, margin, calibrator):
    logit = calibrator["intercept"] + calibrator["weights"][0] * top_score + calibrator["weights"][1] * margin
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, logit))))


def artifact_health():
    _, calibrator, report, reason = semantic_artifacts()
    return {**embedding_contract(), "healthy": not reason, "reason": reason or None,
            "semantic_enabled": settings.ENGINEERING_SEMANTIC_ENABLED,
            "gate_passed": bool(report and report["gate"]["passed"]),
            "threshold": calibrator["threshold"] if calibrator else None,
            "corpus_version": corpus()[0]["provenance"]["version"], "documents": 120}


def evaluation_report():
    _, _, report, reason = semantic_artifacts()
    return report if report else {"status": "unavailable", "reason": reason, "contract": embedding_contract(), "gate": {"passed": False}}


def retrieve(text, embedding=None, *, fallback="javascript_unavailable", experimental=False):
    started = perf_counter()
    reason = fallback if fallback in FALLBACK_REASONS else "javascript_unavailable"
    ranked, semantic_candidates, confidence = None, [], None
    top_score = None
    vectors, calibrator, report, artifact_reason = semantic_artifacts()
    if embedding is not None and fallback != "model_unavailable_demo":
        try:
            vector = validate_embedding(embedding)
        except ValueError as exc:
            reason = str(exc)
        else:
            if not settings.ENGINEERING_SEMANTIC_ENABLED:
                reason = "semantic_disabled"
            elif artifact_reason:
                reason = artifact_reason
            elif not report["gate"]["passed"] and not experimental:
                reason = "evaluation_gate"
            else:
                semantic_candidates = cosine_rank(vector)
                top_score = semantic_candidates[0][1]
                margin = top_score - semantic_candidates[1][1]
                confidence = relevance_confidence(top_score, margin, calibrator)
                if confidence >= calibrator["threshold"]:
                    ranked, reason = semantic_candidates, ""
                else:
                    reason = "low_confidence"
    semantic_ms = (perf_counter() - started) * 1000
    keyword_ms = 0.0
    if ranked is None:
        keyword_started = perf_counter()
        ranked = keyword_rank(text)
        keyword_ms = (perf_counter() - keyword_started) * 1000
    mode = "keyword" if reason else "semantic"
    return {
        "experimental": bool(experimental and report and not report["gate"]["passed"]),
        "mode": mode, "fallback_reason": reason or None, "notice": FALLBACK_REASONS.get(reason, "Semantic results from the evaluated public corpus."),
        "results": [{"id": doc["id"], "title": doc["title"], "text": doc["text"], "score": round(score, 6),
                     "score_kind": "bm25" if reason else "cosine", "confidence": round(confidence, 6) if not reason and i == 0 else None} for i, (doc, score) in enumerate(ranked)],
        "semantic_assessment": {"top_similarity": round(top_score, 6) if top_score is not None else None,
                                "estimated_relevance": round(confidence, 6) if confidence is not None else None,
                                "threshold": calibrator["threshold"] if calibrator else None},
        "timings": {"server_ranking_ms": round((perf_counter() - started) * 1000, 3), "semantic_ms": round(semantic_ms, 3), "keyword_ms": round(keyword_ms, 3)},
        "artifact": artifact_health(),
    }


def browser_timing(value):
    # Browser timings are assertions from an untrusted client, not server facts.
    if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 600_000:
        return round(value, 3)
    return None


def record_observation(run, result, browser):
    with transaction.atomic():
        locked = services._lock_run(run.id)
        assessment = result["semantic_assessment"]
        SearchObservation.objects.create(
            run=locked, mode=result["mode"], fallback_reason=result["fallback_reason"] or "",
            top_score=assessment["top_similarity"], confidence=assessment["estimated_relevance"],
            result_ids=[item["id"] for item in result["results"]],
            server_ranking_ms=result["timings"]["server_ranking_ms"],
            browser_embedding_ms=browser_timing(browser.get("embedding_ms")),
            browser_model_load_ms=browser_timing(browser.get("model_load_ms")), index_version=INDEX_VERSION,
        )
        stale = list(locked.search_observations.order_by("-id").values_list("id", flat=True)[MAX_OBSERVATIONS:])
        if stale:
            SearchObservation.objects.filter(pk__in=stale).delete()


def timing_summary(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"count": 0, "median_ms": None, "p95_ms": None}
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return {"count": len(values), "median_ms": round(median, 3), "p95_ms": round(values[math.ceil(.95 * len(values)) - 1], 3)}


def metrics(run):
    # Consistent snapshot: submit, delivery and observation writers lock this root.
    with transaction.atomic():
        locked = services._lock_run(run.id)
        observations = list(locked.search_observations.order_by("id"))
        trace_counts = dict(locked.traces.values("stage").annotate(count=Count("id")).values_list("stage", "count"))
        attempts = OutboxEvent.objects.filter(submission__run=locked).aggregate(total=Sum("attempt_count"))["total"] or 0
        receipts = ConsumerReceipt.objects.filter(event__submission__run=locked).count()
        submissions = locked.submissions.count()
    scored = [o for o in observations if o.top_score is not None]
    distribution = [{"label": label, "count": sum(low <= o.top_score < high for o in scored)} for label, low, high in [("below 0.4", -1.01, .4), ("0.4–0.6", .4, .6), ("0.6–0.8", .6, .8), ("0.8–1.0", .8, 1.01)]]
    assessed = [o for o in observations if o.confidence is not None]
    threshold = artifact_health()["threshold"]
    low = sum(o.confidence < threshold for o in assessed) if threshold is not None else 0
    return {
        "artifact": artifact_health(), "window": {"retained": len(observations), "maximum": MAX_OBSERVATIONS, "scope": "This browser-owned run; newest observations only, not global analytics."},
        "search": {"semantic": sum(o.mode == "semantic" for o in observations), "keyword": sum(o.mode == "keyword" for o in observations),
                   "fallbacks": dict(Counter(o.fallback_reason for o in observations if o.fallback_reason)),
                   "score_distribution": distribution, "assessed": len(assessed), "low_confidence": low, "low_confidence_rate": low / len(assessed) if assessed else None},
        "latency": {"server_ranking": timing_summary([o.server_ranking_ms for o in observations]),
                    "browser_embedding": timing_summary([o.browser_embedding_ms for o in observations]),
                    "browser_model_load": timing_summary([o.browser_model_load_ms for o in observations])},
        "delivery": {"submissions": submissions, "attempts": attempts, "inbox_effects": receipts,
                     "duplicate_preventions_in_trace_window": trace_counts.get("duplicate_prevented", 0), "replays_in_trace_window": trace_counts.get("replay", 0), "trace_window_maximum": services.MAX_TRACES},
    }
