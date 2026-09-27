import unicodedata
import uuid

from django import forms


SCENARIOS = (
    ("success", "Deliver / recover"),
    ("fail_before_delivery", "Fail before delivery"),
    ("lost_ack", "Lost acknowledgement"),
)


def normalize_submission(value):
    # Keep the idempotency contract intentionally narrower than ML normalization.
    # NFC and line-ending normalization preserve case and meaningful whitespace.
    return unicodedata.normalize("NFC", str(value).replace("\r\n", "\n").replace("\r", "\n")).strip()


class SubmissionForm(forms.Form):
    text = forms.CharField(
        label="Technical discussion", min_length=3, max_length=1500,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 1500, "placeholder": "The export button returns an error after I choose a date range."}),
    )
    idempotency_key = forms.UUIDField(label="Idempotency key", initial=uuid.uuid4)

    def clean_text(self):
        value = normalize_submission(self.cleaned_data["text"])
        if any(unicodedata.category(char).startswith("C") and char not in "\n\t" for char in value):
            raise forms.ValidationError("Use plain text without control characters.")
        if len(value) < 3:
            raise forms.ValidationError("Write at least 3 characters.")
        if len(value) > 1500:
            raise forms.ValidationError("Use at most 1,500 characters after Unicode normalization.")
        return value


class DeliveryForm(forms.Form):
    event_id = forms.UUIDField(widget=forms.HiddenInput)
    scenario = forms.ChoiceField(choices=SCENARIOS, label="Delivery scenario")
