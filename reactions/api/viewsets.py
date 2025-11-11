from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from comments.models import Comment
from posts.models import Post
from notifications.utils import create_notification
from ..models import Reaction
from .serializers import ReactionSerializer
from ..utils.cache_utils import get_reaction_summary_cached, invalidate_reaction_cache


class ReactionViewSet(viewsets.ModelViewSet):
    """
    Robust Reaction API:
      • Toggle, summary, and my reactions
      • Redis-cached summaries
      • Auto invalidation on change
      • Safe notification system
    """

    serializer_class = ReactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Reaction.objects.select_related("user")

    def get_queryset(self):
        """Filter by post or comment, optionally user."""
        post_id = self.request.query_params.get("post")
        comment_id = self.request.query_params.get("comment")
        user_id = self.request.query_params.get("user")

        qs = self.queryset

        if post_id:
            ct = ContentType.objects.get_for_model(Post)
            qs = qs.filter(content_type=ct, object_id=post_id)
        elif comment_id:
            ct = ContentType.objects.get_for_model(Comment)
            qs = qs.filter(content_type=ct, object_id=comment_id)

        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs

    def perform_create(self, serializer):
        """Create reaction safely with automatic cache invalidation."""
        try:
            reaction = serializer.save(user=self.request.user)
            self._after_reaction_change(reaction)
        except IntegrityError:
            raise ValidationError("You have already reacted to this item.")

    # ------------------------------------------------
    # 🔁 Core Utility Methods
    # ------------------------------------------------
    def _after_reaction_change(self, reaction):
        """Handle cache invalidation and notifications after a reaction event."""
        target = reaction.content_object
        model_class = target.__class__
        invalidate_reaction_cache(model_class, target.id)
        self._send_reaction_notification(reaction)

    def _send_reaction_notification(self, reaction):
        """Send reaction notification (post or comment)."""
        target = reaction.content_object
        recipient = getattr(target, "author", None) or getattr(target, "user", None)
        if not recipient or recipient == reaction.user:
            return

        notif_type = (
            "post_reaction"
            if reaction.content_type.model == "post"
            else "comment_reaction"
        )
        create_notification(
            recipient=recipient,
            sender=reaction.user,
            notification_type=notif_type,
            title=f"{reaction.user.username} reacted to your {reaction.content_type.model}",
            message=f"{reaction.user.username} reacted '{reaction.reaction_type}' on your {reaction.content_type.model}.",
        )

    # ------------------------------------------------
    # ⚙️ Custom Endpoints
    # ------------------------------------------------

    @action(detail=False, methods=["post"])
    def toggle(self, request):
        """
        Toggle a reaction (create/update/remove).
        Idempotent — clicking same reaction twice removes it.
        """
        user = request.user
        post_id = request.data.get("post")
        comment_id = request.data.get("comment")
        reaction_type = request.data.get("reaction_type", "like")

        if not post_id and not comment_id:
            return Response(
                {"detail": "Provide either 'post' or 'comment'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_class = Post if post_id else Comment
        obj_id = int(post_id or comment_id)
        ct = ContentType.objects.get_for_model(model_class)

        existing = Reaction.objects.filter(
            user=user, content_type=ct, object_id=obj_id
        ).first()

        if existing:
            if existing.reaction_type == reaction_type:
                existing.delete()
                invalidate_reaction_cache(model_class, obj_id)
                return Response({"action": "removed", "reaction_type": reaction_type})
            existing.reaction_type = reaction_type
            existing.save()
            self._after_reaction_change(existing)
            serializer = self.get_serializer(existing)
            return Response({"action": "updated", "reaction": serializer.data})

        # Create new reaction
        reaction = Reaction.objects.create(
            user=user,
            reaction_type=reaction_type,
            content_type=ct,
            object_id=obj_id,
        )
        self._after_reaction_change(reaction)
        serializer = self.get_serializer(reaction)
        return Response({"action": "created", "reaction": serializer.data}, status=201)

    @action(detail=False, methods=["get"])
    def my_reactions(self, request):
        """List all reactions made by the current user."""
        reactions = self.get_queryset().filter(user=request.user)
        serializer = self.get_serializer(reactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get cached summary (with total + user's reaction)."""
        post_id = request.query_params.get("post")
        comment_id = request.query_params.get("comment")

        if not post_id and not comment_id:
            return Response({"error": "Provide post or comment ID"}, status=400)

        model_class = Post if post_id else Comment
        obj_id = int(post_id or comment_id)

        summary = get_reaction_summary_cached(model_class, obj_id)
        user_reacted = None

        if request.user.is_authenticated:
            ct = ContentType.objects.get_for_model(model_class)
            user_reaction = Reaction.objects.filter(
                content_type=ct, object_id=obj_id, user=request.user
            ).first()
            if user_reaction:
                user_reacted = user_reaction.reaction_type

        return Response(
            {
                "summary": summary,
                "total": sum(summary.values()),
                "user_reacted": user_reacted,
                "cached": True,
            }
        )

    @action(detail=False, methods=["get"])
    def summary_for_post_comments(self, request):
        """Return cached reaction summaries for all comments in a post."""
        post_id = request.query_params.get("post")
        if not post_id:
            return Response({"error": "Provide post ID"}, status=400)

        comment_ids = Comment.objects.filter(post_id=post_id).values_list("id", flat=True)
        summaries = {
            cid: get_reaction_summary_cached(Comment, cid) for cid in comment_ids
        }

        return Response(summaries)
