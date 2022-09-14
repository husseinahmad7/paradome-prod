import django_filters
from .models import Post, Tag
from django import forms
class PostFilter(django_filters.FilterSet):
    question_text = django_filters.CharFilter(field_name='question_text', lookup_expr='icontains', label='the question')
    tags = django_filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all(), 
                                                    widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = Post
        fields = ['question_text', 'tags']
    