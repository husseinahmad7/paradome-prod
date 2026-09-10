from django import template
from django.utils.safestring import mark_safe

from posts.sanitizers import sanitize_rich_text


register = template.Library()


@register.filter(name="safe_rich_text")
def safe_rich_text(value):
    """Sanitize again at render time until all historical rows are normalized."""

    return mark_safe(sanitize_rich_text(value))
