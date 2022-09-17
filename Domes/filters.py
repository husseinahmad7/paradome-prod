from dataclasses import fields
import django_filters
from .models import Dome
from django.db.models import Q
from django.contrib.auth.models import User

class DomeFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method='title_description_search', label='search')
    date = django_filters.DateFromToRangeFilter(field_name='date',label='Date d/m/y')
    class Meta:
        model = Dome
        fields = ['q','date']
    def title_description_search(self, queryset, name, value):
        return queryset.filter(Q(title__icontains=value) | Q(description__icontains=value))
    
class MembersFilter(django_filters.FilterSet):
    u = django_filters.CharFilter(field_name='username', lookup_expr='icontains',label='username')
    class Meta:
        model = User
        fields = ['u']