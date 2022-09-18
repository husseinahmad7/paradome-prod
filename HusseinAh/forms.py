import email
from django import forms

class ContactMe(forms.Form):
    subject = forms.CharField(max_length=100)
    email = forms.EmailField()
    content = forms.CharField(widget=forms.Textarea)
    