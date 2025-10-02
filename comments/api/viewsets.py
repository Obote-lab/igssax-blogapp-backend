from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from ..models import Comment, Conversation, ConversationMessage
from .serializers import (CommentSerializer, ConversationMessageSerializer,
                          ConversationSerializer)


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            obj.author == request.user or getattr(obj, "sender", None) == request.user
        )


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        queryset = Comment.objects.select_related(
            "author", "post", "parent"
        ).prefetch_related("replies__author")
        post_id = self.request.query_params.get("post")

        if post_id:
            # Return top-level comments for that post
            queryset = queryset.filter(post_id=post_id, parent__isnull=True)
        return queryset

    def perform_create(self, serializer):
        parent = serializer.validated_data.get("parent")

        # Ensure parent belongs to the same post
        if parent and parent.post_id != serializer.validated_data["post"].id:
            raise ValidationError("Parent comment must belong to the same post.")

        # Ensure nesting does not exceed 4 levels
        depth = 0
        current_parent = parent
        while current_parent:
            depth += 1
            current_parent = current_parent.parent
            if depth >= 4:
                raise ValidationError("Maximum comment nesting (4 levels) reached.")

        serializer.save(author=self.request.user)

    @action(detail=True, methods=["get"])
    def replies(self, request, pk=None):
        """Get all replies for a specific comment"""
        comment = self.get_object()
        replies = comment.replies.all().select_related("author")
        serializer = self.get_serializer(replies, many=True)
        return Response(serializer.data)


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only see conversations they're part of
        return Conversation.objects.filter(
            participants=self.request.user
        ).prefetch_related("participants", "messages__sender")

    def perform_create(self, serializer):
        conversation = serializer.save(created_by=self.request.user)
        # Creator automatically joins the conversation
        conversation.participants.add(self.request.user)

    @action(detail=True, methods=["post"])
    def add_participant(self, request, pk=None):
        conversation = self.get_object()
        user_id = request.data.get("user_id")

        if not user_id:
            return Response(
                {"error": "user_id required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user exists and is not already a participant
        from django.contrib.auth import get_user_model

        User = get_user_model()

        try:
            user = User.objects.get(id=user_id)
            if conversation.participants.filter(id=user_id).exists():
                return Response(
                    {"error": "User is already a participant"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            conversation.participants.add(user)
            return Response({"success": f"User {user.email} added to conversation"})

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """Leave a conversation"""
        conversation = self.get_object()
        conversation.participants.remove(request.user)

        # If no participants left, delete the conversation
        if conversation.participants.count() == 0:
            conversation.delete()
            return Response({"success": "Left and deleted conversation"})

        return Response({"success": "Left conversation"})


class ConversationMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only see messages from conversations they're part of
        return ConversationMessage.objects.filter(
            conversation__participants=self.request.user
        ).select_related("conversation", "sender")

    def perform_create(self, serializer):
        conversation = serializer.validated_data["conversation"]

        # Check if user is a participant in the conversation
        if not conversation.participants.filter(id=self.request.user.id).exists():
            raise ValidationError("You are not a participant in this conversation")

        serializer.save(sender=self.request.user)

    @action(detail=False, methods=["get"])
    def conversation_messages(self, request):
        """Get messages for a specific conversation"""
        conversation_id = request.query_params.get("conversation_id")
        if not conversation_id:
            return Response(
                {"error": "conversation_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        messages = self.get_queryset().filter(conversation_id=conversation_id)
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)
