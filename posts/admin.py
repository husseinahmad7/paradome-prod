from django.contrib import admin

from .models import Post, Comment, Tag, Follow,Stream

class CommentsInline(admin.TabularInline):
    model = Comment
    extra = 3

admin.AdminSite.site_header = 'Posts'
admin.AdminSite.site_title = 'Posts admin'
class PostsAdmin(admin.ModelAdmin):
    date_hierarchy = 'posted_date'
    fields = ('user','picture','question_text','content', 'tags','dome', 'likes')
    inlines = [CommentsInline]
    list_display = ('question_text', 'user', 'posted_date', 'was_posted_recently')
    list_filter = ['posted_date']
    search_fields = ['question_text','content']
    #list_per_page
admin.site.register(Post, PostsAdmin)
admin.site.register(Tag)
admin.site.register(Follow)
admin.site.register(Stream)
admin.site.register(Comment)

