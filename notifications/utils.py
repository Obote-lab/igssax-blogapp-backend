from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Notification


def create_notification(
    recipient,
    sender=None,
    notification_type=Notification.NotificationType.SYSTEM,
    title="Notification",
    message="",
    instance=None,
    extra_data=None,
):
    if not recipient or (sender and sender == recipient):
        return None

    # ENFORCE PUSH PREFERENCES
    if hasattr(recipient, "notification_preferences"):
        prefs = recipient.notification_preferences
        if (
            notification_type == Notification.NotificationType.MESSAGE
            and not prefs.push_messages
        ):
            return None

    content_type = None
    object_id = None
    if instance is not None:
        content_type = ContentType.objects.get_for_model(instance)
        object_id = instance.pk

    with transaction.atomic():
        notification = Notification.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type=notification_type,
            title=title,
            message=message,
            content_type=content_type,
            object_id=object_id,
            extra_data=extra_data or {},
            created_at=timezone.now(),
        )

    # WebSocket push
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{recipient.id}",
        {
            "type": "send_notification",
            "content": {
                "id": notification.id,
                "title": notification.title,
                "message": notification.message,
                "type": notification.notification_type,
                "sender": getattr(sender, "username", None),
                "created_at": notification.created_at.isoformat(),
            },
        },
    )

    # Email notifications
    if hasattr(recipient, "notification_preferences"):
        prefs = recipient.notification_preferences
        if (
            notification_type == Notification.NotificationType.MESSAGE
            and prefs.email_messages
        ) or (
            notification_type == Notification.NotificationType.FRIEND_REQUEST
            and prefs.email_friend_requests
        ):
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=True,
            )

    return notification
