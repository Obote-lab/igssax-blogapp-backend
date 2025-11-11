from rest_framework.routers import DefaultRouter

from .api.viewsets import NotificationPreferenceViewSet, NotificationViewSet

router = DefaultRouter()


router.register(r"notifications", NotificationViewSet, basename="notifications")
router.register(
    r"preferences", NotificationPreferenceViewSet, basename="notification-preferences"
)

# Export router URLs
urlpatterns = router.urls
