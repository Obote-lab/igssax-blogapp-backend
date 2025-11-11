# livestream/signals/message_signals.py
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from ..models import StreamMessage, StreamAnalytics, StreamModerationLog


@receiver(post_save, sender=StreamMessage)
def handle_new_message(sender, instance, created, **kwargs):
    """Handle message creation."""
    if created and hasattr(instance.stream, "analytics"):
        with transaction.atomic():
            analytics = instance.stream.analytics
            analytics.total_messages = StreamMessage.objects.filter(
                stream=instance.stream
            ).count()
            analytics.save(update_fields=["total_messages", "updated_at"])

        # Auto-flag messages with suspicious content
        suspicious_keywords = ["spam", "http://", "https://", "buy now", "click here"]
        msg_lower = instance.content.lower()
        if any(keyword in msg_lower for keyword in suspicious_keywords):
            instance.is_flagged = True
            instance.flag_count += 1
            instance.save(update_fields=["is_flagged", "flag_count"])

            StreamModerationLog.objects.create(
                stream=instance.stream,
                action="Message auto-flagged",
                performed_by=None,
                target_user=instance.user,
                notes=f"Auto-flagged for suspicious keywords",
            )


@receiver(post_save, sender=StreamMessage)
def handle_flagged_message(sender, instance, **kwargs):
    """Auto-moderate heavily flagged messages."""
    if instance.is_flagged and instance.flag_count >= 3:
        instance.is_moderated = True
        instance.save(update_fields=["is_moderated"])

        StreamModerationLog.objects.create(
            stream=instance.stream,
            action="Message auto-moderated",
            performed_by=None,
            target_user=instance.user,
            notes=f"Message moderated after {instance.flag_count} flags",
        )


@receiver(post_delete, sender=StreamMessage)
def handle_message_delete(sender, instance, **kwargs):
    """Update analytics when messages are deleted."""
    if hasattr(instance.stream, "analytics"):
        with transaction.atomic():
            analytics = instance.stream.analytics
            analytics.total_messages = StreamMessage.objects.filter(
                stream=instance.stream
            ).count()
            analytics.save(update_fields=["total_messages", "updated_at"])
