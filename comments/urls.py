from rest_framework.routers import DefaultRouter

from comments.api.viewsets import (CommentViewSet, ConversationMessageViewSet,
                                   ConversationViewSet)

router = DefaultRouter()
router.register("comments", CommentViewSet, basename="comment")
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", ConversationMessageViewSet, basename="conversationmessage")

urlpatterns = router.urls
