from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from comments.models import Comment
from posts.models import Post

from ..models import Reaction
from .serializers import ReactionSerializer


class ReactionViewSet(viewsets.ModelViewSet):
    queryset = Reaction.objects.all().select_related("user")
    serializer_class = ReactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        post_id = self.request.query_params.get("post")
        comment_id = self.request.query_params.get("comment")

        if post_id:
            ct = ContentType.objects.get_for_model(Post)
            return qs.filter(content_type=ct, object_id=post_id)
        if comment_id:
            ct = ContentType.objects.get_for_model(Comment)
            return qs.filter(content_type=ct, object_id=comment_id)
        return qs

    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError("You have already reacted to this item.")

    @action(detail=False, methods=["post"])
    def toggle(self, request):
        """
        Toggle reaction (like/unlike) for a post or comment.
        """
        post_id = request.data.get("post")
        comment_id = request.data.get("comment")
        reaction_type = request.data.get("reaction_type", "like")

        if not post_id and not comment_id:
            return Response(
                {"detail": "Provide either 'post' or 'comment'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if post_id:
            ct = ContentType.objects.get_for_model(Post)
            obj_id = int(post_id)
        else:
            ct = ContentType.objects.get_for_model(Comment)
            obj_id = int(comment_id)

        # Find existing reaction
        existing = Reaction.objects.filter(
            user=request.user, content_type=ct, object_id=obj_id
        ).first()

        if existing:
            # If same reaction type, remove it (toggle off)
            if existing.reaction_type == reaction_type:
                existing.delete()
                return Response(
                    {
                        "action": "removed",
                        "reaction_type": reaction_type,
                        "object_id": obj_id,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                # Different reaction type, update it
                existing.reaction_type = reaction_type
                existing.save()
                serializer = self.get_serializer(existing)
                return Response(
                    {"action": "updated", "reaction": serializer.data},
                    status=status.HTTP_200_OK,
                )

        # Create new reaction
        reaction = Reaction.objects.create(
            user=request.user,
            reaction_type=reaction_type,
            content_type=ct,
            object_id=obj_id,
        )
        serializer = self.get_serializer(reaction)
        return Response(
            {"action": "created", "reaction": serializer.data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"])
    def my_reactions(self, request):
        """Get all reactions by the current user"""
        reactions = self.get_queryset().filter(user=request.user)
        serializer = self.get_serializer(reactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get reaction summary for a post or comment"""
        post_id = request.query_params.get("post")
        comment_id = request.query_params.get("comment")

        if not post_id and not comment_id:
            return Response({"error": "Provide post or comment ID"}, status=400)

        if post_id:
            ct = ContentType.objects.get_for_model(Post)
            obj_id = post_id
        else:
            ct = ContentType.objects.get_for_model(Comment)
            obj_id = comment_id

        reactions = Reaction.objects.filter(content_type=ct, object_id=obj_id)
        summary = {}
        for reaction in reactions:
            summary[reaction.reaction_type] = summary.get(reaction.reaction_type, 0) + 1

        # Check if current user has reacted
        user_reacted = None
        if request.user.is_authenticated:
            user_reaction = reactions.filter(user=request.user).first()
            if user_reaction:
                user_reacted = user_reaction.reaction_type

        return Response(
            {
                "summary": summary,
                "total": sum(summary.values()),
                "user_reacted": user_reacted,
            }
        )
