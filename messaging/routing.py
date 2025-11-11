from django.urls import re_path
from .consumers import DMConsumer

websocket_urlpatterns = [
    re_path(r"ws/dm/(?P<other_user_id>\d+)/$", DMConsumer.as_asgi()),
]
