# livestream/urls.py
import time

from django.http import JsonResponse
from django.urls import include, path
from django.utils import timezone
from rest_framework.routers import DefaultRouter

from .api.viewsets import (LiveStreamViewSet, StreamAnalyticsViewSet,
                           StreamBanViewSet, StreamMessageViewSet,
                           StreamReactionViewSet)

app_name = "livestream"

# Initialize router for CRUD endpoints
router = DefaultRouter()
router.register(r"streams", LiveStreamViewSet, basename="livestream")
router.register(r"messages", StreamMessageViewSet, basename="streammessage")
router.register(r"reactions", StreamReactionViewSet, basename="streamreaction")
router.register(r"bans", StreamBanViewSet, basename="streamban")
router.register(r"analytics", StreamAnalyticsViewSet, basename="streamanalytics")


# --- Health Check ---
def health_check(request):
    return JsonResponse(
        {
            "status": "healthy",
            "service": "livestream",
            "timestamp": timezone.now().isoformat(),
        }
    )


# --- URL Patterns ---
urlpatterns = [
    # Authenticated API (default CRUD routes)
    path("", include(router.urls)),
    # Public API (unauthenticated)
    path(
        "public/v1/",
        include(
            [
                path("health/", health_check, name="health-check"),
                path(
                    "streams/live/",
                    LiveStreamViewSet.as_view({"get": "live_now"}),
                    name="public-live-streams",
                ),
                path(
                    "streams/",
                    LiveStreamViewSet.as_view({"get": "list"}),
                    name="public-streams-list",
                ),
            ]
        ),
    ),
    # Additional versioned endpoints
    path(
        "v1/streams/",
        include(
            [
                path(
                    "categories/",
                    LiveStreamViewSet.as_view({"get": "categories"}),
                    name="stream-categories",
                ),
                path(
                    "featured/",
                    LiveStreamViewSet.as_view({"get": "featured"}),
                    name="featured-streams",
                ),
            ]
        ),
    ),
]
