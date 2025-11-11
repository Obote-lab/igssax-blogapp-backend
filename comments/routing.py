from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # For conversations (already working)
    re_path(r"ws/chat/(?P<conversation_id>\d+)/$", consumers.ChatConsumer.as_asgi()),

    # 🆕 For live comments per post
    re_path(r"ws/comments/(?P<post_id>\d+)/$", consumers.CommentConsumer.as_asgi()),
]
