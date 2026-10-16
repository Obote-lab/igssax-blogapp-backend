from django.urls import include, path
from rest_framework_nested import routers
from posts.api.viewsets import (
    PostShareViewSet, 
    PostViewSet, StoryViewSet,TagViewSet,
    StoryReactionViewSet,
    StoryCommentViewSet,ContentModerationViewSet, PostInsightViewSet 
)

# Main router
router = routers.DefaultRouter()
router.register("posts", PostViewSet, basename="post")
router.register("stories", StoryViewSet, basename="story")
router.register("tags", TagViewSet, basename="tag")
router.register("shares", PostShareViewSet, basename="postshare")
router.register("moderation", ContentModerationViewSet, basename="moderation")
router.register("insights", PostInsightViewSet, basename="insights") 

# Nested router for stories
stories_router = routers.NestedDefaultRouter(router, r'stories', lookup='story')
stories_router.register(r'reactions', StoryReactionViewSet, basename='story-reactions')
stories_router.register(r'comments', StoryCommentViewSet, basename='story-comments')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(stories_router.urls)),
]
