"""
ASGI config for igssax_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

import django
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import livestream.routing
import notifications.routing
import posts.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "igssax_backend.settings")
django.setup()

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(
            URLRouter(
                notifications.routing.websocket_urlpatterns
                + livestream.routing.websocket_urlpatterns
                + posts.routing.websocket_urlpatterns
            )
        ),
    }
)
