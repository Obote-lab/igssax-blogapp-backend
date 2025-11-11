from django.db import models
from django.db.models import Q
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from ..models import DirectMessage
from .serializers import DirectMessageSerializer


class DirectMessageViewSet(viewsets.ModelViewSet):
    """
    DM API:
    - GET /messages/ -> list messages involving current user (paginated)
    - POST /messages/ -> create message (recipient_id required)
    - GET /messages/conversation/?recipient_id= -> fetch conversation between current user and recipient
    - POST /messages/{id}/mark_read/ -> mark a message as read (or use bulk)
    - GET /messages/unread_count/ -> unread counts aggregated by conversation
    """
    serializer_class = DirectMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        # Only return messages where the user is sender or recipient and not soft-deleted
        return DirectMessage.objects.filter(
            (Q(sender=user) & Q(deleted_by_sender=False)) |
            (Q(recipient=user) & Q(deleted_by_recipient=False))
        ).select_related("sender", "recipient").order_by("-created_at")

    def perform_create(self, serializer):
        # serializer.create handles recipient resolution; sender is request.user
        dm = serializer.save()
        # mark delivered = True when created (simple model for 1-1 DM)
        dm.delivered = True
        dm.save(update_fields=["delivered"])

    @action(detail=False, methods=["get"])
    def conversation(self, request):
        recipient_id = request.query_params.get("recipient_id")
        if not recipient_id:
            return Response({"error": "recipient_id is required"}, status=400)

        user = request.user
        # conversation_key ensures both directions share same key
        low, high = (min(int(user.id), int(recipient_id)), max(int(user.id), int(recipient_id)))
        conv_key = f"dm_{low}_{high}"

        messages = self.get_queryset().filter(conversation_key=conv_key).order_by("created_at")
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark a single message as read by the recipient."""
        dm = self.get_object()
        user = request.user
        if dm.recipient != user:
            return Response({"error": "Only the recipient can mark the message as read."}, status=403)
        if not dm.read:
            dm.read = True
            dm.save(update_fields=["read"])
        return Response({"success": "Marked as read"}, status=200)

    @action(detail=False, methods=["post"])
    def bulk_mark_read(self, request):
        """
        Mark all messages in a conversation as read.
        POST body: {"recipient_id": <id>} where recipient_id is the other user in the conversation.
        """
        recipient_id = request.data.get("recipient_id")
        if not recipient_id:
            return Response({"error": "recipient_id is required"}, status=400)
        user = request.user
        low, high = (min(int(user.id), int(recipient_id)), max(int(user.id), int(recipient_id)))
        conv_key = f"dm_{low}_{high}"

        updated = self.get_queryset().filter(conversation_key=conv_key, recipient=user, read=False).update(read=True)
        return Response({"marked": updated})

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Return the total unread messages for the current user and breakdown by conversation."""
        user = request.user
        total_unread = DirectMessage.objects.filter(recipient=user, read=False, deleted_by_recipient=False).count()

        # breakdown by conversation_key
        from django.db.models import Count
        breakdown_qs = DirectMessage.objects.filter(recipient=user, read=False, deleted_by_recipient=False).values("conversation_key").annotate(count=Count("id"))
        breakdown = {item["conversation_key"]: item["count"] for item in breakdown_qs}

        return Response({"total_unread": total_unread, "by_conversation": breakdown})

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete: mark deleted_by_sender/recipient depending on who calls.
        Actual DB delete can be scheduled later via retention policy.
        """
        dm = self.get_object()
        user = request.user
        if dm.sender == user:
            dm.deleted_by_sender = True
            dm.save(update_fields=["deleted_by_sender"])
            return Response({"success": "Message deleted for sender (soft)."})
        if dm.recipient == user:
            dm.deleted_by_recipient = True
            dm.save(update_fields=["deleted_by_recipient"])
            return Response({"success": "Message deleted for recipient (soft)."})
        return Response({"error": "Not allowed"}, status=403)
