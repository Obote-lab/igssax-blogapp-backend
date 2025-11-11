# livestream/signals/moderation_signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import StreamModerationLog


@receiver(post_save, sender=StreamModerationLog)
def handle_moderation_log(sender, instance, created, **kwargs):
    """Hook for additional moderation actions (future use)."""
    if created:
        # Example: send notification to admins or audit service
        print(
            f"[Moderation Log] {instance.action} | Stream: {instance.stream.title} | User: {instance.target_user}"
        )
