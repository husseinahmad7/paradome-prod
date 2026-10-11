"""Fit development, select calibration threshold, then evaluate test once.

Only stdlib + existing Django code. Running again refuses to overwrite a frozen
report. --verify recomputes rankings/metrics without refitting or revising policy.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paradome.settings.test")
import django
django.setup()
from engineering import search


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def rank_metrics(ranked, relevance):
    relevant = set(relevance)
    if not relevant:
        return None
    recall = len(relevant.intersection(ranked[:5])) / len(relevant)
    dcg = sum((2 ** relevance.get(doc_id, 0) - 1) / math.log2(i + 2) for i, doc_id in enumerate(ranked[:5]))
    ideal = sum((2 ** grade - 1) / math.log2(i + 2) for i, grade in enumerate(sorted(relevance.values(), reverse=True)[:5]))
    return {"recall_at_5": recall, "ndcg_at_5": dcg / ideal}


def fit(rows):
    # Fit the probability that the top retrieved item is judged relevant.
    means = [statistics.mean(r["features"][j] for r in rows) for j in range(2)]
    scales = [max(.01, statistics.pstdev(r["features"][j] for r in rows)) for j in range(2)]
    weights, intercept = [0.0, 0.0], 0.0
    for _ in range(4000):
        gradients, bias = [0.0, 0.0], 0.0
        for row in rows:
            x = [(row["features"][j] - means[j]) / scales[j] for j in range(2)]
            p = search.relevance_confidence(x[0], x[1], {"weights": weights, "intercept": intercept})
            error = p - row["top_relevant"]
            bias += error
            for j in range(2):
                gradients[j] += error * x[j]
        intercept -= .07 * bias / len(rows)
        weights = [weights[j] - .07 * (gradients[j] / len(rows) + .02 * weights[j]) for j in range(2)]
    unscaled = [weights[j] / scales[j] for j in range(2)]
    return {"weights": unscaled, "intercept": intercept - sum(unscaled[j] * means[j] for j in range(2))}


def confidence(row, calibrator):
    return search.relevance_confidence(*row["features"], calibrator)


def operating_point(rows, calibrator, threshold):
    accepted = [r for r in rows if confidence(r, calibrator) >= threshold]
    correct = sum(r["top_relevant"] for r in accepted)
    positive = sum(r["top_relevant"] for r in rows)
    precision = correct / len(accepted) if accepted else None
    recall = correct / positive if positive else 0
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0
    absent = [r for r in rows if not r["query"]["relevance"]]
    return {"precision": precision, "accepted": len(accepted), "coverage": len(accepted) / len(rows),
            "f1": f1, "no_answer_count": len(absent),
            "no_answer_rejection_rate": sum(confidence(r, calibrator) < threshold for r in absent) / len(absent) if absent else None}


def reliability(rows, calibrator):
    bins, ece, brier = [], 0.0, 0.0
    for i in range(10):
        selected = [r for r in rows if i / 10 <= confidence(r, calibrator) < (i + 1) / 10 or (i == 9 and confidence(r, calibrator) == 1)]
        if not selected:
            bins.append({"lower": i / 10, "count": 0, "mean_confidence": None, "relevance_rate": None})
            continue
        mean = statistics.mean(confidence(r, calibrator) for r in selected)
        rate = statistics.mean(r["top_relevant"] for r in selected)
        ece += len(selected) / len(rows) * abs(mean - rate)
        bins.append({"lower": i / 10, "count": len(selected), "mean_confidence": mean, "relevance_rate": rate})
    brier = statistics.mean((confidence(r, calibrator) - r["top_relevant"]) ** 2 for r in rows)
    return {"expected_calibration_error": ece, "brier_score": brier, "bins": bins}


def aggregate(rows, mode):
    eligible = [r[mode] for r in rows if r[mode] is not None]
    return {"answerable_queries": len(eligible), **{metric: statistics.mean(r[metric] for r in eligible) if eligible else None for metric in ("recall_at_5", "ndcg_at_5")}}


def main(verify=False):
    frozen = read(ROOT / "frozen-v1.json")
    for name, digest in frozen["sha256"].items():
        if hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Frozen corpus changed; author a fresh holdout for a new experiment.")
    report_path = ROOT / "evaluation-v1.json"
    if report_path.exists() and not verify:
        raise RuntimeError("v1 test already inspected. Use --verify or author a new independent holdout; do not refit v1.")
    documents = search.corpus("v1")[0]["documents"]
    if verify:
        # Verification works from a clean clone, without the ignored encoder output.
        evidence = json.loads(gzip.decompress((search.ARTIFACT_ROOT / "evaluation-vectors-v1.json.gz").read_bytes()))
        index_path = search.ARTIFACT_ROOT / "search-index-v1.json"
        index = read(index_path)
        previous = read(report_path)
        assert evidence["contract"] == previous["contract"] == index["contract"]
        assert evidence["index_sha256"] == previous["index_sha256"] == hashlib.sha256(index_path.read_bytes()).hexdigest()
        assert evidence["query_sha256"] == frozen["sha256"]["queries-v1.json"]
        assert index["document_ids"] == [d["id"] for d in documents]
        vectors = index["vectors"]  # Already normalized by the original encoder run.
        query_vectors = {q["id"]: q["vector"] for q in evidence["queries"]}
    else:
        encoded = read(ROOT / "encoded-v1.json")
        vectors = [search.normalize_vector(doc["vector"]) for doc in encoded["documents"]]
        assert [d["id"] for d in encoded["documents"]] == [d["id"] for d in documents]
        query_vectors = {q["id"]: search.normalize_vector(q["vector"]) for q in encoded["queries"]}
    rows = []
    for query in read(ROOT / "data/queries-v1.json")["queries"]:
        started = perf_counter()
        vector = query_vectors[query["id"]]
        scored = sorted([(doc["id"], sum(a * b for a, b in zip(vector, v))) for doc, v in zip(documents, vectors)], key=lambda p: (-p[1], p[0]))
        semantic_ms = (perf_counter() - started) * 1000
        started = perf_counter()
        bm25 = [doc["id"] for doc, _ in search.keyword_rank(query["text"], version="v1")]
        keyword_ms = (perf_counter() - started) * 1000
        ids = [doc_id for doc_id, _ in scored[:5]]
        rows.append({"query": query, "features": [scored[0][1], scored[0][1] - scored[1][1]],
                     "top_relevant": int(ids[0] in query["relevance"]), "semantic_ids": ids, "bm25_ids": bm25,
                     "semantic": rank_metrics(ids, query["relevance"]), "bm25": rank_metrics(bm25, query["relevance"]),
                     "semantic_ms": semantic_ms, "keyword_ms": keyword_ms})
    split_rows = {split: [r for r in rows if r["query"]["split"] == split] for split in ("development", "calibration", "test")}
    contract, corpus_hash = search.embedding_contract("v1"), search.corpus("v1")[1]
    calibration_path = search.ARTIFACT_ROOT / "search-calibration-v1.json"
    if verify:
        calibrator = read(calibration_path)
    else:
        calibrator = fit(split_rows["development"])
        candidates = [(t / 1000, operating_point(split_rows["calibration"], calibrator, t / 1000)) for t in range(1, 1001)]
        qualified = [(t, point) for t, point in candidates if point["precision"] is not None and point["precision"] >= .90 and point["coverage"] >= .50]
        threshold, point = max(qualified, key=lambda p: (p[1]["f1"], p[1]["coverage"], p[0])) if qualified else (1.0, operating_point(split_rows["calibration"], calibrator, 1.0))
        calibrator.update({"threshold": threshold, "contract": contract, "corpus_sha256": corpus_hash,
                           "fit_split": "development", "threshold_split": "calibration", "regularization": .02,
                           "selection": "Max F1 at precision >= .90 and coverage >= .50 on calibration; ties prefer higher threshold. Otherwise reject all."})
    summary = {split: {"queries": len(part), "semantic": aggregate(part, "semantic"), "bm25": aggregate(part, "bm25"),
                       "operating_point": operating_point(part, calibrator, calibrator["threshold"]),
                       **reliability(part, calibrator)} for split, part in split_rows.items()}
    test = split_rows["test"]
    slices = {kind: {"semantic": aggregate([r for r in test if r["query"]["slice"] == kind], "semantic"),
                     "bm25": aggregate([r for r in test if r["query"]["slice"] == kind], "bm25")} for kind in ("literal", "paraphrase", "distractor")}
    passed = summary["test"]["semantic"]["recall_at_5"] >= .85 and slices["paraphrase"]["semantic"]["recall_at_5"] > slices["paraphrase"]["bm25"]["recall_at_5"]
    if verify:
        previous = read(report_path)
        def rounded(value):
            if isinstance(value, float):
                return round(value, 12)
            if isinstance(value, dict):
                return {key: rounded(item) for key, item in value.items()}
            if isinstance(value, list):
                return [rounded(item) for item in value]
            return value
        if rounded(summary) != rounded(previous["splits"]) or rounded(slices) != rounded(previous["test_slices"]) or passed != previous["gate"]["passed"]:
            raise RuntimeError("Frozen metrics do not reproduce")
        print("Frozen evaluation and calibration reproduce.")
        return
    index_path = search.ARTIFACT_ROOT / "search-index-v1.json"
    write(index_path, {"contract": contract, "corpus_sha256": corpus_hash, "document_ids": [d["id"] for d in documents], "vectors": vectors})
    index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    calibrator["index_sha256"] = index_hash
    write(calibration_path, calibrator)
    write(search.ARTIFACT_ROOT / "search-golden-v1.json", {"contract": contract, "assets": read(ROOT / "assets-lock-v1.json"), "goldens": encoded["goldens"], "tolerance": {"maximum_absolute_difference": .001, "minimum_cosine": .999}})
    failures = [r for r in test if (r["semantic"] and r["semantic"]["recall_at_5"] < 1) or (confidence(r, calibrator) >= calibrator["threshold"] and not r["top_relevant"])]
    report = {"status": "frozen", "version": "search-evaluation-v1", "contract": contract, "corpus_sha256": corpus_hash, "index_sha256": index_hash,
              "provenance": search.corpus("v1")[0]["provenance"], "frozen": frozen,
              "policy": "Rank raw semantic candidates for Recall/nDCG; report acceptance and fallback separately. No-answer queries excluded from ranking averages. Test evaluated once after policy freeze.",
              "splits": summary, "test_slices": slices, "threshold": calibrator["threshold"],
              "gate": {"passed": passed, "minimum_recall_at_5": .85, "requires_paraphrase_improvement": True},
              "latency": {"scope": "Offline host measurements, not browser or Wasmer latency; no network, CPU q8 encoder.", "encoder_runtime": encoded["runtime"],
                          "model_load_ms": encoded["model_load_ms"], "query_embedding": search.timing_summary([q["duration_ms"] for q in encoded["queries"]]),
                          "semantic_rank": search.timing_summary([r["semantic_ms"] for r in rows]), "bm25_rank": search.timing_summary([r["keyword_ms"] for r in rows])},
              "failure_examples": [{"query_id": r["query"]["id"], "query": r["query"]["text"], "relevance": r["query"]["relevance"], "semantic_ids": r["semantic_ids"], "bm25_ids": r["bm25_ids"], "confidence": confidence(r, calibrator), "accepted": confidence(r, calibrator) >= calibrator["threshold"]} for r in failures[:10]],
              "test_predictions": [{"query_id": r["query"]["id"], "semantic_ids": r["semantic_ids"], "bm25_ids": r["bm25_ids"], "confidence": confidence(r, calibrator)} for r in test]}
    write(report_path, report)
    print(json.dumps({"test": summary["test"], "paraphrase": slices["paraphrase"], "gate_passed": passed}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    main(parser.parse_args().verify)
