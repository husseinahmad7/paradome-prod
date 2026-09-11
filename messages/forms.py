from django import forms


class DirectMessageForm(forms.Form):
    body = forms.CharField(
        max_length=1000,
        strip=True,
        widget=forms.Textarea(
            attrs={"class": "input is-medium", "rows": 6, "placeholder": "Reply"}
        ),
    )
