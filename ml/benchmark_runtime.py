"""Measure full standard-library inference locally; never a production claim.

Run: python ml/benchmark_runtime.py
Prints measured JSON to stdout without modifying the model, corpus, or evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engineering.triage import classify  # noqa: E402


def benchmark(count=500):
    corpus = json.loads((ROOT / "ml/data/triage-corpus.json").read_text(encoding="utf-8"))
    texts = [text for group in corpus["groups"] if group["split"] == "test"
             for text in group["texts"]]
    classify(texts[0])  # Artifact load and validation are excluded from warm timing.
    samples = []
    outcomes = set()
    for iteration in range(count):
        started = time.perf_counter()
        result = classify(texts[iteration % len(texts)])
        samples.append((time.perf_counter() - started) * 1000)
        outcomes.add(result["status"])
    if "unavailable" in outcomes:
        raise RuntimeError("Cannot benchmark successful triage with an unavailable artifact.")
    ordered = sorted(samples)
    return {
        "scope": "Complete warm classify calls, including artifact stat/cache, inference, abstention, contribution sorting and result timing; excludes first load, Django and network",
        "python": platform.python_version(), "platform": platform.platform(),
        "sample_count": count, "p50_ms": statistics.median(samples),
        "p95_ms": ordered[math.ceil(count * 0.95) - 1], "max_ms": max(samples),
        "training_libraries_present": {
            name: importlib.util.find_spec(name) is not None
            for name in ("sklearn", "numpy", "scipy")
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=500)
    args = parser.parse_args()
    if not 100 <= args.samples <= 10000:
        parser.error("--samples must be between 100 and 10000")
    print(json.dumps(benchmark(args.samples), indent=2))
