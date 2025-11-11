from django.db.models import Count, OuterRef, Subquery, IntegerField
from django.core.cache import cache
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model

from ..models import Comment, CommentAttachment, Conversation, ConversationMessage
from .serializers import (
    CommentSerializer,
    ConversationSerializer,
    ConversationMessageSerializer,
)
from reactions.models import Reaction
from posts.models import Post


# --- PAGINATION ---
from rest_framework.pagination import PageNumberPagination
class MessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


# --- PERMISSIONS ---
class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            obj.author == request.user or getattr(obj, "sender", None) == request.user
        )


# --- COMMENT VIEWSET ---
class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser] 

    def get_queryset(self):
        """Fetch all top-level comments for a post, with cached nested prefetching."""
        post_id = self.request.query_params.get("post") or self.kwargs.get("post_id")
        if not post_id:
            return Comment.objects.none()

        cache_key = f"comments_post_{post_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        queryset = (
            Comment.objects.filter(post_id=post_id, parent__isnull=True)
            .select_related("author", "author__profile")
            .prefetch_related(
                "attachments",
                "replies__attachments",
                "replies__replies__attachments",
                "replies__replies__replies__attachments",
                "replies__replies__replies__replies__attachments",
                "replies__author__profile",
                "replies__replies__author__profile",
                "replies__replies__replies__author__profile",
                "replies__replies__replies__replies__author__profile",
            )
            .order_by("-created_at")
        )

        cache.set(cache_key, queryset, timeout=60)
        return queryset

    def create(self, request, *args, **kwargs):
        """
        Override create to handle multipart form data properly
        """
        print("🎯 CommentViewSet.create() called")
        print("📦 Request data:", dict(request.data))
        print("📎 Request FILES:", dict(request.FILES))
        
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print(f"❌ Error in CommentViewSet.create(): {str(e)}")
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    def perform_create(self, serializer):
        """
        Handles creation of a comment, including attachments (files & GIFs)
        and max depth validation for nested replies.
        """
        parent = serializer.validated_data.get("parent")

        # Enforce nesting limit
        depth = 0
        current_parent = parent
        while current_parent:
            depth += 1
            current_parent = current_parent.parent
            if depth >= 4:
                raise ValidationError("Maximum comment nesting (4 levels) reached.")

        # Create comment (serializer handles attachments)
        # Note: The author is now set in the serializer's create method
        comment = serializer.save()

        # 🔄 Invalidate cache for this post
        if comment.post_id:
            cache_key = f"comments_post_{comment.post_id}"
            cache.delete(cache_key)

        return comment

    @action(detail=True, methods=["get"])
    def replies(self, request, pk=None):
        """Return replies for a specific comment, annotated with reactions."""
        comment = self.get_object()
        comment_ct = ContentType.objects.get_for_model(Comment)

        def reaction_count_subquery(reaction_type):
            return Subquery(
                Reaction.objects.filter(
                    content_type=comment_ct,
                    object_id=OuterRef("pk"),
                    reaction_type=reaction_type,
                )
                .values("object_id")
                .annotate(count=Count("id"))
                .values("count"),
                output_field=IntegerField(),
            )

        replies = (
            comment.replies.all()
            .select_related("author", "author__profile")
            .prefetch_related("attachments")
            .annotate(
                likes=reaction_count_subquery("like"),
                loves=reaction_count_subquery("love"),
                wows=reaction_count_subquery("wow"),
                sads=reaction_count_subquery("sad"),
                angrys=reaction_count_subquery("angry"),
            )
            .order_by("created_at")
        )

        serializer = self.get_serializer(replies, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="react")
    def react(self, request, pk=None):
        """Toggle or update a reaction on a comment."""
        comment = self.get_object()
        reaction_type = request.data.get("reaction_type")

        valid_types = [r[0] for r in Reaction._meta.get_field("reaction_type").choices]
        if reaction_type not in valid_types:
            return Response({"error": "Invalid reaction type"}, status=400)

        ctype = ContentType.objects.get_for_model(Comment)

        reaction, created = Reaction.objects.update_or_create(
            user=request.user,
            content_type=ctype,
            object_id=comment.id,
            defaults={"reaction_type": reaction_type},
        )

        summary = Reaction.compute_summary(ctype, comment.id)
        return Response(
            {
                "message": "Reaction added" if created else "Reaction updated",
                "summary": summary,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["delete"], url_path="react")
    def remove_reaction(self, request, pk=None):
        """Remove a user's reaction from a comment."""
        comment = self.get_object()
        ctype = ContentType.objects.get_for_model(Comment)

        Reaction.objects.filter(
            user=request.user,
            content_type=ctype,
            object_id=comment.id,
        ).delete()

        summary = Reaction.compute_summary(ctype, comment.id)
        return Response(
            {"message": "Reaction removed", "summary": summary},
            status=status.HTTP_200_OK,
        )

# --- CONVERSATION VIEWSET ---
class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(
            participants=self.request.user
        ).prefetch_related("participants", "messages__sender", "messages__sender__profile")

    def perform_create(self, serializer):
        conversation = serializer.save(created_by=self.request.user)
        conversation.participants.add(self.request.user)

    @action(detail=True, methods=["post"])
    def add_participant(self, request, pk=None):
        conversation = self.get_object()
        user_id = request.data.get("user_id")

        if not user_id:
            return Response({"error": "user_id required"}, status=400)

        User = get_user_model()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        if conversation.participants.filter(id=user_id).exists():
            return Response({"error": "User already a participant"}, status=400)

        conversation.participants.add(user)
        return Response({
            "success": True,
            "message": f"User {user.username} added",
            "user": {"id": user.id, "username": user.username}
        })

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        conversation = self.get_object()
        conversation.participants.remove(request.user)

        if conversation.participants.count() == 0:
            conversation.delete()
            return Response({"success": "Left and deleted conversation"})
        return Response({"success": "Left conversation"})


# --- MESSAGE VIEWSET ---
class ConversationMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = MessagePagination

    def get_queryset(self):
        return (
            ConversationMessage.objects.filter(
                conversation__participants=self.request.user
            )
            .select_related("conversation", "sender", "sender__profile")
            .prefetch_related("conversation__participants")
        )

    def perform_create(self, serializer):
        conversation = serializer.validated_data["conversation"]
        if not conversation.participants.filter(id=self.request.user.id).exists():
            raise ValidationError("You are not a participant in this conversation")
        serializer.save(sender=self.request.user)

    @action(detail=False, methods=["get"])
    def conversation_messages(self, request):
        conversation_id = request.query_params.get("conversation_id")
        if not conversation_id:
            return Response({"error": "conversation_id required"}, status=400)

        messages = self.get_queryset().filter(conversation_id=conversation_id)
        messages.update(delivered_to=request.user)
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)
