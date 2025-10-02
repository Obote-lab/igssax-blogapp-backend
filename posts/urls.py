from rest_framework.routers import DefaultRouter

from posts.api.viewsets import PostViewSet, StoryViewSet, TagViewSet

router = DefaultRouter()
router.register("posts", PostViewSet, basename="post")
router.register("stories", StoryViewSet, basename="story")
router.register("tags", TagViewSet, basename="tag")

urlpatterns = router.urls
