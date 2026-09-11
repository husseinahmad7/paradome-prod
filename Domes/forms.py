from django import forms
from .models import Dome, Category

class DomeCreation(forms.ModelForm):
    PRIVACY_CHOICES = ((1,'Public'), (0,'Private'),)
    
    privacy = forms.ChoiceField(choices=PRIVACY_CHOICES)
    description = forms.CharField(max_length=144,widget=forms.Textarea())
    
    class Meta:
        model = Dome
        fields=['icon','banner','title','description','privacy']

class CategoryCreation(forms.ModelForm):
    def __init__(self, *args, dome=None, **kwargs):
        self.dome = dome
        super().__init__(*args, **kwargs)

    class Meta:
        model = Category
        fields = ['title']

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if self.dome and Category.objects.filter(
            Dome=self.dome, title__iexact=title
        ).exists():
            raise forms.ValidationError("This Dome already has a category with that title.")
        return title
