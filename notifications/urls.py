from rest_framework.routers import DefaultRouter

from .api.viewsets import NotificationPreferenceViewSet, NotificationViewSet

router = DefaultRouter()
router.register('notifications', NotificationViewSet, basename='notification')
router.register('preferences', NotificationPreferenceViewSet, basename='notificationpreference')

urlpatterns = router.urls