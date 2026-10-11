from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from deployment.wasmer import deploy


class WasmerActivationTests(SimpleTestCase):
    def options(self):
        return SimpleNamespace(app_id="demo-app", version_id="retained-version",
                               revision="a" * 40, owner="confirmed-owner", features=False)

    def replies(self):
        names = ("ENGINEERING_CONTROL_ROOM_ENABLED", "ENGINEERING_SEMANTIC_ENABLED", "ENGINEERING_SOURCE_REVISION")
        return [
            {"node": {"id": "retained-version", "app": {"id": "demo-app"}}},
            {"node": {"envVars": {"edges": [{"node": {"id": str(i), "name": name}} for i, name in enumerate(names)]}}},
            {"updateEnvVars": {"success": True}},
            {"markAppVersionAsActive": {"app": {"id": "demo-app", "activeVersion": {"id": "retained-version"}}}},
            {"redeployActiveAppVersion": {"app": {"id": "demo-app", "activeVersion": {"id": "fresh-runtime"}}}},
        ]

    @patch.object(deploy, "preflight", return_value="confirmed-owner")
    def test_rollback_restores_only_release_flags_and_restarts_retained_package(self, _):
        with patch.object(deploy, "graphql", side_effect=self.replies()) as api, patch.object(deploy, "ROOT") as root:
            deploy.activate(self.options())
        lookup = api.call_args_list[1]
        self.assertNotIn("value", lookup.args[0])
        self.assertEqual(set(lookup.args[1]["names"]), {"ENGINEERING_CONTROL_ROOM_ENABLED", "ENGINEERING_SEMANTIC_ENABLED", "ENGINEERING_SOURCE_REVISION"})
        update = api.call_args_list[2].args[1]["input"]["envVars"]
        self.assertEqual(update, [{"id": "0", "value": "false"}, {"id": "1", "value": "false"}, {"id": "2", "value": "a" * 40}])
        self.assertIn("markAppVersionAsActive", api.call_args_list[3].args[0])
        self.assertIn("redeployActiveAppVersion", api.call_args_list[4].args[0])
        root.__truediv__.return_value.write_text.assert_called_once()

    @patch.object(deploy, "preflight", return_value="confirmed-owner")
    def test_other_app_version_is_rejected_before_any_mutation(self, _):
        with patch.object(deploy, "graphql", return_value={"node": {"app": {"id": "other-app"}}}) as api:
            with self.assertRaisesMessage(RuntimeError, "does not belong"):
                deploy.activate(self.options())
        self.assertEqual(api.call_count, 1)

    @patch.object(deploy, "preflight", return_value="confirmed-owner")
    def test_failed_flag_update_does_not_select_or_restart_a_version(self, _):
        replies = self.replies()[:3]
        replies[-1] = {"updateEnvVars": {"success": False}}
        with patch.object(deploy, "graphql", side_effect=replies) as api:
            with self.assertRaisesMessage(RuntimeError, "no version was activated"):
                deploy.activate(self.options())
        self.assertEqual(api.call_count, 3)
