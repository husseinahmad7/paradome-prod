from django import forms
from .models import Dome, Category

class DomeCreation(forms.ModelForm):
    PRIVACY_CHOICES = ((1,'Public'), (0,'Private'),)
    
    privacy = forms.ChoiceField(choices=PRIVACY_CHOICES)
    description = forms.CharField(max_length=144,widget=forms.Textarea())
    
    class Meta:
        model = Dome
        fields=['picture','banner','title','description','privacy']

class CategoryCreation(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['title']