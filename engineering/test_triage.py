"""Runtime, held-out evidence, and export-contract tests (no training libraries)."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engineering import triage

ROOT = Path(__file__).resolve().parents[1]


class ExportedTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = triage.load_model()
        cls.golden = json.loads((ROOT / "engineering/ml_artifacts/golden-v1.json").read_text(encoding="utf-8"))
        cls.corpus = json.loads((ROOT / "ml/data/triage-corpus.json").read_text(encoding="utf-8"))

    def test_artifact_budget_and_contract(self):
        self.assertLessEqual(triage.ARTIFACT_PATH.stat().st_size, 1024 * 1024)
        self.assertLessEqual(len(self.model["features"]), 5000)
        self.assertEqual(self.model["contract"], triage.CONTRACT)
        self.assertEqual(self.model["labels"], list(triage.LABELS))

    def test_export_matches_training_golden_scores_and_logits(self):
        self.assertGreaterEqual(len(self.golden["examples"]), 72)
        for example in self.golden["examples"]:
            with self.subTest(text=example["text"]):
                result = triage.predict_scores(self.model, example["text"])
                self.assertEqual(result["label"], example["label"])
                for field in ("scores", "logits"):
                    for expected, actual in zip(example[field], result[field]):
                        self.assertLessEqual(abs(expected - actual), 1e-6)
                self.assertAlmostEqual(sum(result["scores"]), 1.0, places=12)

    def test_all_feature_contributions_reconstruct_winning_logit(self):
        result = triage.predict_scores(self.model, "The upload fails after login and saving a message crashes.")
        winner = triage.LABELS.index(result["label"])
        reconstructed = result["intercept"] + math.fsum(term["contribution"] for term in result["terms"])
        self.assertAlmostEqual(reconstructed, result["logits"][winner], places=12)
        self.assertTrue(any(abs(term["contribution"]) > 0 for term in result["terms"]))

    def test_raw_counts_idf_l2_and_bigrams(self):
        model = {"features": ["save", "save save", "now", "save now"], "idf": [2.0, 3.0, 4.0, 5.0]}
        values, recognized, ratio = triage.vectorize(model, "save save now")
        expected = [4.0, 3.0, 4.0, 5.0]
        norm = math.sqrt(sum(value * value for value in expected))
        for index, value in enumerate(expected):
            self.assertAlmostEqual(values[index], value / norm)
        self.assertEqual(recognized, 2)
        self.assertEqual(ratio, 1.0)

    def test_nfkc_lowercase_punctuation_contract(self):
        self.assertEqual(triage.normalize_text("ＦＩＬＥ ﬁle"), "file file")
        first = triage.predict_scores(self.model, "THE MESSAGE FAILS")
        second = triage.predict_scores(self.model, "the message fails")
        self.assertEqual(first["scores"], second["scores"])
        self.assertEqual(triage.TOKEN_RE.findall("x A 1 ab aa_ab"), ["ab", "aa_ab"])

    def test_supported_script_is_not_language_detection(self):
        self.assertTrue(triage.supported_script("café question"))
        self.assertTrue(triage.supported_script("Ｆｕｌｌｗｉｄｔｈ letters"))
        self.assertFalse(triage.supported_script("English العربية"))
        self.assertFalse(triage.supported_script("не работает"))

    def test_low_vocabulary_and_empty_inputs_abstain(self):
        for text in ("", "?!", "flerm snorf quux", "save"):
            with self.subTest(text=text):
                result = triage.classify(text)
                self.assertEqual(result["status"], "uncertain")
                self.assertIsNone(result["label"])
                self.assertEqual(result["reason"], "insufficient_vocabulary")
                self.assertTrue(result["explanation"])

    def test_unsupported_script_abstains_even_with_familiar_words(self):
        result = triage.classify("the application fails after login العربية")
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["reason"], "unsupported_script")
        self.assertIsNone(result["label"])

    def test_validation_threshold_is_enforced(self):
        model = dict(self.model, threshold=1.0)
        with patch.object(triage, "load_model", return_value=model):
            result = triage.classify("The message fails to save after login.")
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["reason"], "below_threshold")

    def test_excessive_input_is_bounded_before_vectorization(self):
        with patch.object(triage, "predict_scores") as predictor:
            result = triage.classify("a" * 1501)
        predictor.assert_not_called()
        self.assertEqual(result["reason"], "input_too_long")
        self.assertIsNone(result["label"])

    def test_suggestion_shape_and_measured_latency(self):
        result = triage.classify("The message fails to save after login.")
        self.assertIn(result["status"], ("suggested", "uncertain"))
        self.assertEqual(result["version"], "triage-en-v1")
        self.assertGreaterEqual(result["latency_ms"], 0)
        self.assertLessEqual(len(result["terms"]), 6)
        self.assertIsInstance(result["explanation"], str)
        for term in result["terms"]:
            self.assertEqual(set(term), {"name", "contribution"})
            self.assertTrue(math.isfinite(term["contribution"]))

    def test_split_integrity_and_provenance(self):
        self.assertIn("synthetic", self.corpus["provenance"])
        seen_groups, seen_texts = set(), set()
        counts, groups = {}, {}
        for group in self.corpus["groups"]:
            self.assertNotIn(group["id"], seen_groups)
            seen_groups.add(group["id"])
            self.assertTrue(group["provenance"])
            self.assertEqual(len(group["texts"]), 4)
            groups.setdefault(group["split"], set()).add(group["id"])
            counts[group["split"]] = counts.get(group["split"], 0) + len(group["texts"])
            for text in group["texts"]:
                normalized = triage.normalize_text(text)
                self.assertNotIn(normalized, seen_texts)
                seen_texts.add(normalized)
        self.assertEqual(counts, {"train": 216, "validation": 72, "test": 72})
        self.assertEqual(len(seen_groups), 90)
        for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
            self.assertFalse(groups[left] & groups[right])

    def test_challenges_are_separate_and_unsupported_scripts_rejected(self):
        data = json.loads((ROOT / "ml/data/challenges.json").read_text(encoding="utf-8"))
        corpus_texts = {text for group in self.corpus["groups"] for text in group["texts"]}
        self.assertEqual({row["kind"] for row in data["examples"]},
                         {"ambiguous", "unfamiliar", "unsupported_script"})
        for row in data["examples"]:
            self.assertNotIn(row["text"], corpus_texts)
            if row["kind"] == "unsupported_script":
                self.assertEqual(triage.classify(row["text"])["reason"], "unsupported_script")

    def test_frozen_threshold_and_dataset_hash_match(self):
        freeze = json.loads((ROOT / "ml/frozen-v1.json").read_text(encoding="utf-8"))
        expected_hash = hashlib.sha256((ROOT / "ml/data/triage-corpus.json").read_bytes()).hexdigest()
        self.assertEqual(freeze["dataset_sha256"], expected_hash)
        self.assertEqual(self.model["evidence"]["dataset_sha256"], expected_hash)
        self.assertEqual(freeze["threshold"], self.model["threshold"])
        qualified = [item for item in freeze["validation_candidates"]
                     if (item["accepted_precision"] or 0) >= 0.85]
        chosen = max(qualified, key=lambda item: (
            item["coverage"], item["accepted_precision"], -item["threshold"]))
        self.assertEqual(chosen["threshold"], self.model["threshold"])

    def test_published_test_metrics_recompute_without_training_dependencies(self):
        rows = [(group["label"], text) for group in self.corpus["groups"]
                if group["split"] == "test" for text in group["texts"]]
        results = [triage.predict_scores(self.model, text) for _, text in rows]
        accepted = [i for i, (_, text) in enumerate(rows)
                    if triage.abstention_reason(self.model, text, results[i]) is None]
        report = self.model["evidence"]["test"]
        self.assertEqual(report["count"], len(rows))
        self.assertAlmostEqual(report["coverage"], len(accepted) / len(rows))
        self.assertAlmostEqual(report["accepted_precision"],
                               sum(rows[i][0] == results[i]["label"] for i in accepted) / len(accepted))
        f1s = []
        for label in triage.LABELS:
            true_positive = sum(expected == label and result["label"] == label
                                for (expected, _), result in zip(rows, results))
            false_positive = sum(expected != label and result["label"] == label
                                 for (expected, _), result in zip(rows, results))
            false_negative = sum(expected == label and result["label"] != label
                                 for (expected, _), result in zip(rows, results))
            f1 = 2 * true_positive / (2 * true_positive + false_positive + false_negative)
            self.assertAlmostEqual(report["per_class"][label]["f1"], f1)
            f1s.append(f1)
        self.assertAlmostEqual(report["macro_f1"], sum(f1s) / len(f1s))

    def test_evaluation_artifact_fingerprint_matches(self):
        report = json.loads((ROOT / "ml/evaluation-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(report["artifact_sha256"], hashlib.sha256(triage.ARTIFACT_PATH.read_bytes()).hexdigest())
        self.assertEqual(report["artifact_bytes"], triage.ARTIFACT_PATH.stat().st_size)
        self.assertEqual(report["feature_count"], len(self.model["features"]))

    def test_model_card_has_evidence_and_qualified_limitations(self):
        card = triage.model_card()
        self.assertEqual(card["status"], "available")
        self.assertEqual(card["metrics"]["test"]["count"], 72)
        self.assertTrue(any("synthetic" in item for item in card["limitations"]))
        self.assertTrue(any("calibrated" in item for item in card["limitations"]))


class TriageFallbackTests(unittest.TestCase):
    def _unavailable_for_file(self, content):
        with tempfile.TemporaryDirectory(prefix="paradome-triage-") as temporary:
            target = Path(temporary) / "model.json"
            if content is not None:
                target.write_bytes(content)
            with patch.object(triage, "ARTIFACT_PATH", target):
                result = triage.classify("The message fails to save after login.")
                card = triage.model_card()
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["reason"], "model_unavailable")
            self.assertIsNone(result["label"])
            self.assertEqual(result["terms"], [])
            self.assertNotIn(temporary, json.dumps(result))
            self.assertEqual(card["status"], "unavailable")

    def test_missing_artifact_is_nonfatal(self):
        self._unavailable_for_file(None)

    def test_invalid_json_and_oversize_artifacts_are_nonfatal(self):
        for data in (b"not json", b"\x00" * 100, b" " * (1024 * 1024 + 1), b"[]", b"{}"):
            with self.subTest(size=len(data)):
                self._unavailable_for_file(data)

    def test_invalid_contract_dimensions_and_numbers_are_nonfatal(self):
        original = json.loads(triage.ARTIFACT_PATH.read_text(encoding="utf-8"))
        mutations = [
            lambda data: data.update(labels=["question", "idea", "bug report"]),
            lambda data: data["contract"].update(normalization="none"),
            lambda data: data["features"].__setitem__(0, data["features"][1]),
            lambda data: data.update(intercepts=[0]),
            lambda data: data["coefficients"][0].pop(),
            lambda data: data["coefficients"][0].__setitem__(0, float("nan")),
            lambda data: data["idf"].__setitem__(0, -1),
            lambda data: data.update(threshold=float("inf")),
            lambda data: data.update(min_recognized_words=0),
        ]
        for mutation in mutations:
            data = copy.deepcopy(original)
            mutation(data)
            self._unavailable_for_file(json.dumps(data).encode("utf-8"))

    def test_artifact_cache_revalidates_changed_file(self):
        raw = triage.ARTIFACT_PATH.read_bytes()
        with tempfile.TemporaryDirectory(prefix="paradome-triage-") as temporary:
            target = Path(temporary) / "model.json"
            target.write_bytes(raw)
            with patch.object(triage, "ARTIFACT_PATH", target):
                self.assertNotEqual(triage.classify("A message fails after login.")["status"], "unavailable")
                target.write_bytes(b"invalid")
                self.assertEqual(triage.classify("A message fails after login.")["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
