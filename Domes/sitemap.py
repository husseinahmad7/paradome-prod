from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q

from .models import Dome

class DomesSitemap(Sitemap):
    def items(self):
        return (
            Dome.objects.filter(privacy=1)
            .exclude(user__groups__name="Demo")
            .order_by("pk")
        )

    def location(self, obj):
        return reverse('domes:dome-detail', kwargs={'pk':obj.pk})
