import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from . import sanitizers


class SanitizerBackendTests(SimpleTestCase):
    def test_empty_prose_document_keeps_editor_validation(self):
        self.assertEqual(sanitizers.sanitize_prose_field("<p></p>"), "")
        self.assertEqual(sanitizers.sanitize_prose_field("<p>text</p>"), "<p>text</p>")

    @override_settings(RICH_TEXT_SANITIZER="unknown")
    def test_unknown_backend_never_returns_raw_html(self):
        with self.assertRaises(ValidationError):
            sanitizers.sanitize_rich_text("<script>unsafe</script>")

    @override_settings(RICH_TEXT_SANITIZER="ammonia-wasi")
    def test_fixed_binary_receives_only_stdin_and_no_shell(self):
        with patch.object(sanitizers, "_wasm_binary", return_value=Path("/app/sanitizer.wasm")), patch.object(sanitizers.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"<p>safe</p>")) as run:
            self.assertEqual(sanitizers.sanitize_rich_text("<p>safe</p>"), "<p>safe</p>")
        args, options = run.call_args
        self.assertEqual(args, ([str(Path("/app/sanitizer.wasm"))],))
        self.assertNotIn("shell", options)
        self.assertEqual(options["input"], b"<p>safe</p>")
        self.assertEqual(options["timeout"], 5)

    @override_settings(RICH_TEXT_SANITIZER="ammonia-wasi")
    def test_missing_failed_timed_out_or_invalid_output_fails_closed(self):
        errors = [FileNotFoundError(), ValueError("bad digest"), subprocess.TimeoutExpired("sanitizer", 5), subprocess.CalledProcessError(2, "sanitizer")]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch.object(sanitizers, "_wasm_binary", return_value=Path("/fixed")), patch.object(sanitizers.subprocess, "run", side_effect=error), self.assertRaises(ValidationError):
                sanitizers.sanitize_rich_text("<script>unsafe</script>")
        with patch.object(sanitizers, "_wasm_binary", return_value=Path("/fixed")), patch.object(sanitizers.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"\xff")), self.assertRaises(ValidationError):
            sanitizers.sanitize_rich_text("unsafe")

    @override_settings(RICH_TEXT_SANITIZER="ammonia-wasi")
    def test_input_limit_rejects_before_process_creation(self):
        with patch.object(sanitizers.subprocess, "run") as run, self.assertRaises(ValidationError):
            sanitizers.sanitize_rich_text("x" * 2_621_441)
        run.assert_not_called()

    def test_wasm_artifact_digest_is_verified(self):
        with TemporaryDirectory() as root:
            directory = Path(root) / "deployment/wasmer/sanitizer"
            (directory / "bin").mkdir(parents=True)
            content = b"\x00asmfixture"
            binary = directory / "bin/paradome-sanitizer.wasm"
            binary.write_bytes(content)
            (directory / "manifest.json").write_text(json.dumps({"policy":"prose-v1", "ammonia":"4.1.4", "sha256":hashlib.sha256(content).hexdigest()}))
            sanitizers._wasm_binary.cache_clear()
            self.assertEqual(sanitizers._wasm_binary(root), binary)
            binary.write_bytes(b"changed")
            sanitizers._wasm_binary.cache_clear()
            with self.assertRaises(ValueError):
                sanitizers._wasm_binary(root)
        sanitizers._wasm_binary.cache_clear()
