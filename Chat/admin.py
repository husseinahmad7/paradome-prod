from django.contrib import admin
from .models import ChatChannel, ChatMessage
admin.site.register(ChatMessage)
admin.site.register(ChatChannel)