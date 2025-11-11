from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from .models import Notification


def create_notification(
    recipient,
    sender=None,
    notification_type="general",
    title="Notification",
    message="",
    instance=None,
    extra_data=None,
):
    if not recipient or (sender and sender == recipient):
        return None  # Skip self-notifications

    content_type = None
    object_id = None
    if instance is not None:
        try:
            content_type = ContentType.objects.get_for_model(instance)
            object_id = instance.pk
        except Exception:
            pass

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
            timestamp=timezone.now(),
        )

    # Send real-time update
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
                "created_at": notification.timestamp.isoformat(),
            },
        },
    )

    # Optional email notification
    if hasattr(recipient, "notification_preferences"):
        prefs = recipient.notification_preferences
        if (
            notification_type == "message"
            and prefs.email_messages
        ) or (
            notification_type == "friend_request"
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











# from asgiref.sync import async_to_sync
# from channels.layers import get_channel_layer
# from django.contrib.contenttypes.models import ContentType
# from django.db import transaction
# from django.utils import timezone

# from .models import Notification


# def create_notification(
#     recipient,
#     sender=None,
#     notification_type=None,
#     title="",
#     message="",
#     instance=None,
#     extra_data=None,
# ):
#     """
#     Creates a Notification instance and sends it via WebSocket to the recipient.

#     Args:
#         recipient (User): The user receiving the notification.
#         sender (User, optional): The user who triggered the notification.
#         notification_type (str, optional): Category or type label for this notification.
#         title (str, optional): Title text for the notification.
#         message (str, optional): Body text for the notification.
#         instance (Model, optional): A related object (e.g., Comment, Post).
#         extra_data (dict, optional): JSON-serializable data for flexible payloads.

#     Returns:
#         Notification: The created notification instance.
#     """
#     content_type = None
#     object_id = None

#     # Handle instance linking if provided
#     if instance is not None:
#         try:
#             content_type = ContentType.objects.get_for_model(instance)
#             object_id = instance.pk
#         except Exception:
#             content_type = None
#             object_id = None

#     # Default notification type
#     if not notification_type:
#         notification_type = "general"

#     # Save and broadcast atomically
#     with transaction.atomic():
#         notification = Notification.objects.create(
#             recipient=recipient,
#             sender=sender,
#             notification_type=notification_type,
#             title=title or "Notification",
#             message=message or "",
#             content_type=content_type,
#             object_id=object_id,
#             extra_data=extra_data or {},
#             timestamp=timezone.now(),
#         )

#     # Send real-time WebSocket event
#     channel_layer = get_channel_layer()
#     group_name = f"user_{recipient.id}"

#     async_to_sync(channel_layer.group_send)(
#         group_name,
#         {
#             "type": "send_notification",
#             "content": {
#                 "id": notification.id,
#                 "title": notification.title,
#                 "message": notification.message,
#                 "notification_type": notification.notification_type,
#                 "sender": notification.sender.username if notification.sender else None,
#                 "created_at": notification.timestamp.isoformat(),
#             },
#         },
#     )

#     return notification
