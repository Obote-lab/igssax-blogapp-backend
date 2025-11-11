# notifications/asgi.py
import os

import django
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import notifications.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "igssax_backend.settings")
django.setup()

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(
            URLRouter(notifications.routing.websocket_urlpatterns)
        ),
    }
)
