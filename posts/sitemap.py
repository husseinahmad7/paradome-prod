from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q

from .models import Post

class PostsSitemap(Sitemap):
    def items(self):
        return Post.objects.filter(Q(posted_date__lte=timezone.now()), Q(dome__isnull=True) | Q(dome__privacy__exact=1))

    def location(self, obj):
        return reverse('posts:post-detail', kwargs={'pk':obj.pk})