from django import forms

from .models import ChatChannel, ChatMessage


class ChatMessageCreation(forms.ModelForm):
    body = forms.CharField(
        max_length=250,
        label="Message",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "autocomplete": "off",
                "maxlength": "250",
                "placeholder": "Write a short message…",
                "aria-describedby": "chat-message-hint",
            }
        ),
    )

    class Meta:
        model = ChatMessage
        fields = ["body"]

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Message cannot be empty.")
        return body


class ChatChannelCreation(forms.ModelForm):
    def __init__(self, *args, category=None, **kwargs):
        self.category = category
        super().__init__(*args, **kwargs)

    class Meta:
        model = ChatChannel
        fields = ["title", "topic"]

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if self.category and ChatChannel.objects.filter(
            category=self.category, title__iexact=title
        ).exists():
            raise forms.ValidationError("This category already has a channel with that title.")
        return title
