import copy
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from . import search, services
from .models import LabRun, SearchObservation


@override_settings(ENGINEERING_SEMANTIC_ENABLED=True)
class RetrievalTests(SimpleTestCase):
    def setUp(self):
        search.semantic_artifacts.cache_clear()

    def test_pinned_compatible_artifacts_and_reproducible_ranking(self):
        self.assertTrue(search.artifact_health()["healthy"])
        vector = search.semantic_artifacts()[0][0]
        self.assertEqual(search.cosine_rank(vector)[0][0]["id"], search.corpus()[0]['documents'][0]['id'])
        self.assertAlmostEqual(search.cosine_rank(vector)[0][1], 1.0)
        self.assertEqual(search.cosine_rank(vector), search.cosine_rank(vector))

    def test_bm25_exact_identifiers_and_empty_query(self):
        self.assertIn("csrf", search.keyword_rank("CSRF")[0][0]["group"])
        self.assertEqual(search.keyword_rank("and the a"), [])

    def test_invalid_vectors_never_reach_cosine(self):
        for values in ([], [0] * 384, [True] * 384, [float("nan")] * 384, [float("inf")] * 384, [0] * 383, "vector", [101] * 384):
            with self.subTest(values=str(values)[:30]):
                result = search.retrieve("CSRF token", {**search.embedding_contract(), "values": values}, experimental=True)
                self.assertEqual(result["fallback_reason"], "embedding_invalid")
                self.assertEqual(result["mode"], "keyword")

    def test_every_contract_mismatch_falls_back(self):
        embedding = {**search.embedding_contract(), "values": search.semantic_artifacts()[0][0]}
        for key in search.embedding_contract():
            with self.subTest(key=key):
                wrong = dict(embedding, **{key: "wrong"})
                self.assertEqual(search.retrieve("CSRF token", wrong, experimental=True)["fallback_reason"], "artifact_mismatch")

    def test_missing_or_mismatched_index_disables_semantic(self):
        original = Path.read_bytes
        def changed(path):
            if path.name == "search-index-v2.json":
                artifact = json.loads(original(path)); artifact["contract"]["revision"] = "wrong"
                return json.dumps(artifact).encode()
            return original(path)
        with patch.object(Path, "read_bytes", changed):
            search.semantic_artifacts.cache_clear()
            self.assertEqual(search.artifact_health()["reason"], "artifact_mismatch")
        search.semantic_artifacts.cache_clear()
        with patch.object(Path, "read_bytes", side_effect=FileNotFoundError):
            self.assertEqual(search.semantic_artifacts()[3], "artifact_unavailable")
        search.semantic_artifacts.cache_clear()

    def test_frozen_gate_keeps_keyword_default_and_opt_in_is_labelled(self):
        embedding = {**search.embedding_contract(), "values": search.semantic_artifacts()[0][0]}
        self.assertFalse(search.semantic_artifacts('v1')[2]['gate']['passed'])
        vectors,calibrator,report,reason=search.semantic_artifacts()
        failed_report=copy.deepcopy(report); failed_report['gate']['passed']=False
        with patch('engineering.search.semantic_artifacts',return_value=(vectors,calibrator,failed_report,reason)):
            self.assertEqual(search.retrieve("A lost reply", embedding)["fallback_reason"], "evaluation_gate")
            preview = search.retrieve("A lost reply", embedding, experimental=True)
        self.assertTrue(preview["experimental"])
        self.assertEqual(preview["mode"], "semantic")
        self.assertGreater(preview["semantic_assessment"]["estimated_relevance"], 0)
        self.assertIsNone(preview["results"][1]["confidence"])

    def test_low_confidence_and_simulated_outage(self):
        embedding = {**search.embedding_contract(), "values": search.semantic_artifacts()[0][0]}
        with patch("engineering.search.relevance_confidence", return_value=0.01):
            result = search.retrieve("lost acknowledgement", embedding, experimental=True)
            self.assertEqual(result["fallback_reason"], "low_confidence")
            self.assertEqual(result["semantic_assessment"]["estimated_relevance"], .01)
        self.assertEqual(search.retrieve("lost acknowledgement", embedding, fallback="model_unavailable_demo", experimental=True)["fallback_reason"], "model_unavailable_demo")

    def test_semantic_feature_off_cannot_be_bypassed_by_preview(self):
        embedding = {**search.embedding_contract(), "values": search.semantic_artifacts()[0][0]}
        with override_settings(ENGINEERING_SEMANTIC_ENABLED=False):
            self.assertEqual(search.retrieve("lost acknowledgement", embedding, experimental=True)["fallback_reason"], "semantic_disabled")

    def test_calibrator_is_fit_and_selected_on_separate_groups(self):
        calibrator = search.semantic_artifacts()[1]
        self.assertEqual(calibrator["fit_split"], "development")
        self.assertEqual(calibrator["threshold_split"], "calibration")
        groups = search.evaluation_report()["frozen"]["groups"]
        self.assertFalse(set(groups["development"]) & set(groups["test"]))
        self.assertFalse(set(groups["calibration"]) & set(groups["test"]))
        self.assertLess(search.relevance_confidence(.2, 0, calibrator), search.relevance_confidence(.9, .2, calibrator))

    def test_fresh_holdout_and_related_retrieval_pass_gate(self):
        report=search.evaluation_report()
        self.assertTrue(report['gate']['passed'])
        self.assertGreaterEqual(report['splits']['test']['semantic']['recall_at_5'],.85)
        self.assertGreater(report['splits']['test']['semantic']['recall_at_5'],report['splits']['test']['cosine']['recall_at_5'])
        legacy=search.semantic_artifacts('v1')[2]['frozen']['groups']
        for split in ('calibration','test'):
            self.assertFalse(set(report['frozen']['groups'][split])&set(sum(legacy.values(),[])))
        vector=search.semantic_artifacts()[0][0]
        result=search.retrieve('A related technical discussion',{**search.embedding_contract(),'values':vector})
        first=search.corpus()[0]['documents'][0]
        self.assertEqual(result['results'][1]['id'],first['related_ids'][0])
        self.assertEqual(result['results'][1]['retrieval_reason'],'related_thread')
        self.assertIsNone(result['results'][1]['confidence'])


@override_settings(ENGINEERING_LAB_ENABLED=True, ENGINEERING_CONTROL_ROOM_ENABLED=True, ENGINEERING_SEMANTIC_ENABLED=True)
class SearchApiTests(TestCase):
    def setUp(self):
        self.client.post("/engineering/runs/")
        self.run = LabRun.objects.get()
        self.url = f"/engineering/runs/{self.run.id}/search/"
        self.metrics_url = f"/engineering/runs/{self.run.id}/metrics/"

    def post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

    def test_keyword_json_and_no_javascript_form_work_without_model(self):
        response = self.post({"text": "private attachment authorization"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "keyword")
        self.assertEqual(response["Cache-Control"], "no-store")
        html = self.client.post(self.url, {"text": "unique receipt acknowledgement"})
        self.assertEqual(html.status_code, 200)
        self.assertContains(html, "BM25 keyword score")
        self.assertContains(html, "Inspect discussion")
        self.assertContains(html, "Search by meaning")

    def test_session_isolation_expiry_and_logout(self):
        other = Client()
        self.assertEqual(other.post(self.url, {"text": "hello world"}, HTTP_ACCEPT="application/json").status_code, 404)
        self.assertEqual(other.get(self.metrics_url, HTTP_ACCEPT="application/json").status_code, 404)
        LabRun.objects.filter(pk=self.run.id).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post({"text": "hello world"}).status_code, 404)
        self.assertEqual(SearchObservation.objects.count(), 0)

    def test_csrf_and_method_contracts(self):
        guarded = Client(enforce_csrf_checks=True)
        guarded.cookies = self.client.cookies
        self.assertEqual(guarded.post(self.url, data='{"text":"test csrf"}', content_type="application/json").status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.metrics_url).status_code, 405)

    def test_malformed_json_text_and_body_bounds(self):
        for raw in ('[1,2]', '{bad', '{"text":true}', '{"text":"ab"}', '{"text":"a\\u0000b"}', '{"text":"hello","experimental":"yes"}', '{"text":"hello","browser":[]}', '{"text":"' + 'x' * 13000 + '"}', '{"text":"hello","embedding":NaN}'):
            with self.subTest(raw=raw[:40]):
                self.assertEqual(self.client.post(self.url, raw, content_type="application/json").status_code, 400)
        self.assertEqual(SearchObservation.objects.count(), 0)

    def test_observation_bound_and_data_minimization(self):
        result = search.retrieve("This raw query must not be saved")
        for _ in range(45):
            search.record_observation(self.run, result, {"embedding_ms": float("inf"), "model_load_ms": 900000})
        self.assertEqual(SearchObservation.objects.count(), 40)
        observation = SearchObservation.objects.first()
        self.assertIsNone(observation.browser_embedding_ms)
        self.assertIsNone(observation.browser_model_load_ms)
        names = {f.name for f in SearchObservation._meta.get_fields()}
        self.assertFalse(names & {"text", "query", "embedding", "values"})
        self.assertTrue(all(doc_id.startswith("discussion-") for doc_id in observation.result_ids))
        self.assertEqual(self.client.get(self.metrics_url).json()["window"]["retained"], 40)

    def test_rate_limit_is_json_and_foreign_run_stays_unavailable(self):
        for _ in range(40):
            self.assertEqual(self.post({"text": "csrf token"}).status_code, 200)
        response = self.post({"text": "csrf token"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertIn("error", response.json())
        self.assertEqual(Client().post(self.url, {"text": "csrf token"}, HTTP_ACCEPT="application/json").status_code, 404)

    def test_disabled_interface_routes_and_public_evaluation(self):
        self.assertEqual(Client().get("/engineering/evaluation/", HTTP_ACCEPT="application/json").json()["status"], "frozen")
        with override_settings(ENGINEERING_CONTROL_ROOM_ENABLED=False):
            self.assertEqual(self.post({"text": "csrf token"}).status_code, 404)
            self.assertEqual(self.client.get(self.metrics_url).status_code, 404)
            self.assertEqual(self.client.get("/engineering/evaluation/").status_code, 404)
            self.assertNotContains(self.client.get(f"/engineering/runs/{self.run.id}/"), "room-search")

    def test_public_asset_allowlist_and_worker_csp(self):
        # Built assets are not needed for keyword use or the production test suite.
        self.assertEqual(self.client.get("/engineering/assets/minilm-q8-v1/../../private-media/test").status_code, 404)
        asset = Path(__file__).parent / "static/engineering/search-assets/minilm-q8-v1/worker.mjs"
        if asset.exists():
            response = self.client.get("/engineering/assets/minilm-q8-v1/worker.mjs")
            self.assertEqual(response.status_code, 200)
            self.assertIn("immutable", response["Cache-Control"])
            self.assertIn("'wasm-unsafe-eval'", response["Content-Security-Policy"])
            self.assertNotIn("'unsafe-eval'", response["Content-Security-Policy"])
            etag = response["ETag"]
            # Exhaust Django's test-client iterator so it suppresses the real
            # request-finished connection cleanup inside TestCase's transaction.
            # Direct FileResponse.close() breaks that transaction on MySQL.
            self.assertTrue(b"".join(response.streaming_content))
            head = self.client.head("/engineering/assets/minilm-q8-v1/worker.mjs")
            self.assertEqual(head.status_code, 200)
            self.assertEqual(head.content, b"")
            self.assertEqual(head["ETag"], etag)
            cached = self.client.get("/engineering/assets/minilm-q8-v1/worker.mjs", HTTP_IF_NONE_MATCH=etag)
            self.assertEqual(cached.status_code, 304)
            self.assertIn("immutable", cached["Cache-Control"])

    def test_no_js_discussion_selection_is_public_id_only(self):
        response = self.client.get(f"/engineering/runs/{self.run.id}/?discussion=discussion-001-a")
        self.assertContains(response, "Our fictional billing relay")
        self.assertEqual(self.run.submissions.count(), 0)
        self.assertEqual(self.run.search_observations.count(), 0)
