"""Server-side HTML sanitization for user-authored rich text.

The allow-list intentionally matches the small, semantic subset needed by a
ProseMirror/django-prose-editor document. Conventional runtimes use nh3. Wasmer
uses the same current Ammonia engine and policy in a hash-checked WASI executable.
Neither backend accepts unsanitized content when its dependency is unavailable.
"""

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import subprocess

from django.conf import settings
from django.core.exceptions import ValidationError


ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "h4",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "u",
    "ul",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}
CLEAN_CONTENT_TAGS = {"embed", "iframe", "object", "script", "style", "template"}


@lru_cache(maxsize=1)
def _wasm_binary(root):
    directory = Path(root) / "deployment/wasmer/sanitizer"
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("policy") != "prose-v1" or manifest.get("ammonia") != "4.1.4":
        raise ValueError("Incompatible sanitizer policy")
    binary = directory / "bin/paradome-sanitizer.wasm"
    content = binary.read_bytes()
    if content[:4] != b"\x00asm" or hashlib.sha256(content).hexdigest() != manifest["sha256"]:
        raise ValueError("Sanitizer digest mismatch")
    return binary


def _sanitize_wasm(value):
    try:
        encoded = value.encode("utf-8")
        if len(encoded) > 2_621_440:
            raise ValueError("Input too large")
        # Fixed executable, no shell, no user-controlled arguments or filename.
        result = subprocess.run([str(_wasm_binary(str(settings.BASE_DIR)))],
                                input=encoded, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=5, check=True)
        if len(result.stdout) > 16_777_216:
            raise ValueError("Output too large")
        return result.stdout.decode("utf-8")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        raise ValidationError("Rich-text sanitization is temporarily unavailable. Please try again later.") from error


def sanitize_rich_text(value):
    if not value:
        return ""
    value = str(value)
    backend = getattr(settings, "RICH_TEXT_SANITIZER", "nh3")
    if backend == "ammonia-wasi":
        return _sanitize_wasm(value)
    if backend != "nh3":
        raise ValidationError("Rich-text sanitization is unavailable.")
    import nh3
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        clean_content_tags=CLEAN_CONTENT_TAGS,
        link_rel="noopener noreferrer nofollow ugc",
        strip_comments=True,
    )


def sanitize_prose_field(value):
    """Keep the editor's existing empty-document validation with either backend."""
    cleaned = sanitize_rich_text(value)
    return "" if re.fullmatch(r"<(?P<tag>\w+)></(?P=tag)>", cleaned) else cleaned
