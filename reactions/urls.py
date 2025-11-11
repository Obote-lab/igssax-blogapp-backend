from rest_framework.routers import DefaultRouter
from .api.viewsets import ReactionViewSet

router = DefaultRouter()
router.register("reactions", ReactionViewSet, basename="reaction")

urlpatterns = router.urls