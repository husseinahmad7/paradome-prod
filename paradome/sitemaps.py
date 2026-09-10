from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticSitemap(Sitemap):
    changefreq = "monthly"
    priority = 1.0

    def items(self):
        return ("HusseinAh:home",)

    def location(self, item):
        return reverse(item)
