from django import forms


class ContactMe(forms.Form):
    subject = forms.CharField(
        max_length=100,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "autocomplete": "off",
                "placeholder": "What would you like to discuss?",
            }
        ),
    )
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "input",
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )
    content = forms.CharField(
        label="Message",
        max_length=5000,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "class": "textarea",
                "rows": 8,
                "placeholder": "Share the role, project, or problem you are working on.",
            }
        ),
    )
    website = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.HiddenInput(attrs={"autocomplete": "off", "tabindex": "-1"}),
    )

    def clean_subject(self):
        subject = self.cleaned_data["subject"]
        if "\r" in subject or "\n" in subject:
            raise forms.ValidationError("Enter a subject without line breaks.")
        return subject
