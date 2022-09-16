from django import forms
from .models import Post, Comment,Tag
# from ckeditor.widgets import CKEditorWidget
from django.core.exceptions import ValidationError

class PostCreation(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(Tag.objects.all().order_by('title'))
    class Meta:
        model = Post
        fields=['picture','question_text','content','tags']
    
    def clean_picture(self):
        image = self.cleaned_data.get('picture', False)
        if image:
            if image.size > 4*1024*1024:
                raise ValidationError("Image file too large ( > 4mb )")
            return image
        else:
            raise ValidationError("Couldn't read uploaded image")
    
class CommentCreation(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['comment']

class CommentReplyCreation(forms.ModelForm):
    comment = forms.CharField(widget=forms.Textarea(attrs={'cols':30, 'rows':3,'class':'textarea is-small'}))
    class Meta:
        model = Comment
        fields = ['comment']
class TagCreation(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['title']
        
    def clean(self):
        data = self.cleaned_data
        title = data.get("title")
        qs = Tag.objects.filter(title__exact=title)
        if qs.exists():
            self.add_error("Tag", f"\"{title}\" is already in use. Please pick another title.")
            # raise forms.ValidationError("Office is not allowed")
            
        return data