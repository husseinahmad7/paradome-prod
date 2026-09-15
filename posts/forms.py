from django.core.exceptions import ValidationError
from django import forms
from django.utils.html import strip_tags

from Domes.access import is_demo_user
from .models import Post, Comment, Tag, validate_image
from .sanitizers import sanitize_rich_text

class PostCreation(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        Tag.objects.all().order_by('title'), required=False
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if is_demo_user(self.user):
            self.fields.pop("picture", None)

    class Meta:
        model = Post
        fields=['picture','question_text','content','tags']

    def clean_content(self):
        content = sanitize_rich_text(self.cleaned_data.get("content"))
        if not strip_tags(content).strip():
            raise ValidationError("Post content cannot be empty.")
        return content

    def clean(self):
        cleaned_data = super().clean()
        if is_demo_user(self.user) and self.files:
            raise ValidationError("Demo accounts cannot upload files.")
        return cleaned_data
    
    def clean_picture(self):
        image = self.cleaned_data.get('picture')
        if image and is_demo_user(self.user):
            raise ValidationError("Demo accounts cannot upload files.")
        if image:
            validate_image(image)
        return image
    
class CommentCreation(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['comment']

    def clean_comment(self):
        comment = sanitize_rich_text(self.cleaned_data.get("comment"))
        if not strip_tags(comment).strip():
            raise ValidationError("Comment cannot be empty.")
        return comment

class CommentReplyCreation(forms.ModelForm):
    comment = forms.CharField(widget=forms.Textarea(attrs={'cols':30, 'rows':3,'class':'textarea is-small'}))
    class Meta:
        model = Comment
        fields = ['comment']

    def clean_comment(self):
        comment = sanitize_rich_text(self.cleaned_data.get("comment"))
        if not strip_tags(comment).strip():
            raise ValidationError("Reply cannot be empty.")
        return comment
class TagCreation(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['title']
        
    def clean(self):
        data = self.cleaned_data
        title = data.get("title")
        qs = Tag.objects.filter(title__exact=title)
        if qs.exists():
            self.add_error("title", f"\"{title}\" is already in use. Please pick another title.")
            # raise forms.ValidationError("Office is not allowed")
            
        return data
