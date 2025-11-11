from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import Notification, NotificationPreference
from ..utils import create_notification
from .serializers import (NotificationCountSerializer,
                          NotificationPreferenceSerializer,
                          NotificationSerializer)


class NotificationViewSet(viewsets.ModelViewSet):
    """
    Handles all user notifications — listing, marking read, counting, etc.
    """

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return notifications for the authenticated user,
        ordered by newest first.
        """
        return (
            Notification.objects.filter(recipient=self.request.user)
            .select_related("sender", "sender__profile")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(recipient=self.request.user)

    @action(detail=False, methods=["get"])
    def unread(self, request):
        """
        Fetch all unread notifications.
        """
        unread = self.get_queryset().filter(is_read=False)
        page = self.paginate_queryset(unread)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(unread, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """
        Mark all notifications as read for the authenticated user.
        """
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response(
            {
                "message": f"Marked {updated} notifications as read.",
                "marked_read": updated,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """
        Mark a single notification as read.
        """
        notification = self.get_object()
        notification.mark_as_read()
        return Response(
            {"message": "Notification marked as read."}, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["get"])
    def count(self, request):
        """
        Return total and unread notification counts.
        """
        total = self.get_queryset().count()
        unread = self.get_queryset().filter(is_read=False).count()
        serializer = NotificationCountSerializer(
            {"unread_count": unread, "total_count": total}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    Allows users to view and update their notification preferences.
    A NotificationPreference object is auto-created on user creation (see signals.py).
    """

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Each user should have only their own preferences
        return NotificationPreference.objects.filter(user=self.request.user)

    def get_object(self):
        # Always ensure a preference exists for the user
        obj, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return obj

    def list(self, request):
        """
        Since each user has one preference, return that object directly.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve the single preference for the user.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        """
        Update the user's notification preferences.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Override create to behave like update (idempotent).
        """
        return self.update(request, *args, **kwargs)
