from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/posts/$", consumers.PostConsumer.as_asgi()),
    re_path(r"ws/stories/$", consumers.StoryConsumer.as_asgi()),
]
