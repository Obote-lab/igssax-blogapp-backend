# reactions/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Live reaction updates per post
    re_path(r"ws/reactions/(?P<post_id>\d+)/$", consumers.ReactionConsumer.as_asgi()),
]
