# asgi.py
import comments.routing as comments_routing
import reactions.routing as reactions_routing
import livestream.routing as livestream_routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            livestream_routing.websocket_urlpatterns +
            comments_routing.websocket_urlpatterns +
            reactions_routing.websocket_urlpatterns
        )
    ),
})
