# livestream/asgi.py
import asyncio
import os

import django
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import livestream.routing
from livestream.redis_listener import redis_event_listener

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "igssax_backend.settings")
django.setup()

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(
            URLRouter(livestream.routing.websocket_urlpatterns)
        ),
    }
)

# Start Redis listener when ASGI loads
asyncio.ensure_future(redis_event_listener())
