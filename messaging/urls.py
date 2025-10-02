from rest_framework.routers import DefaultRouter

from .api.viewsets import DirectMessageViewSet

router = DefaultRouter()
router.register("messages", DirectMessageViewSet, basename="messages")

urlpatterns = router.urls
