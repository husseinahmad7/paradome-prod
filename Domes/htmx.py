from django.utils.cache import patch_vary_headers


class HtmxTemplateResponseMixin:
    """Render a fragment for HTMX and a complete, refreshable page otherwise."""

    partial_template_name = None
    page_template_name = None

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return [self.partial_template_name]
        return [self.page_template_name]

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        patch_vary_headers(response, ("HX-Request",))
        return response
