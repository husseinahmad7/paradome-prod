"""Server-side HTML sanitization for user-authored rich text.

The allow-list intentionally matches the small, semantic subset needed by a
ProseMirror/django-prose-editor document. nh3 must be installed by the project
dependency owner; importing this module fails closed when it is absent.
"""

import nh3


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


def sanitize_rich_text(value):
    if not value:
        return ""
    return nh3.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        clean_content_tags=CLEAN_CONTENT_TAGS,
        link_rel="noopener noreferrer nofollow ugc",
        strip_comments=True,
    )
