from rest_framework.routers import DefaultRouter

from posts.api.viewsets import (
    PostViewSet, StoryViewSet, 
    TagViewSet,PostShareViewSet
    )

router = DefaultRouter()
router.register("posts", PostViewSet, basename="post")
router.register("stories", StoryViewSet, basename="story")
router.register("tags", TagViewSet, basename="tag")
router.register(r"shares", PostShareViewSet, basename="postshare")

urlpatterns = router.urls
