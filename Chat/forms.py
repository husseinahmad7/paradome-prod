from django import forms
from .models import ChatMessage, ChatChannel
class ChatMessageCreation(forms.ModelForm):
    body = forms.CharField(max_length=250, label='reply',widget=forms.TextInput(attrs={'class': 'input is-small','autofocus':True}))
    # file = forms.FileField(allow_empty_file=True, required=False)
    class Meta:
        model = ChatMessage
        fields = ['body']
        
class ChatChannelCreation(forms.ModelForm):
    class Meta:
        model = ChatChannel
        fields = ['title', 'topic']