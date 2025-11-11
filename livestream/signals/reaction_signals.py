# livestream/signals/reaction_signals.py
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from ..models import StreamReaction


@receiver(post_save, sender=StreamReaction)
def handle_new_reaction(sender, instance, created, **kwargs):
    """Track reactions on streams."""
    if created and hasattr(instance.stream, "analytics"):
        with transaction.atomic():
            analytics = instance.stream.analytics
            analytics.total_reactions = StreamReaction.objects.filter(
                stream=instance.stream
            ).count()
            analytics.save(update_fields=["total_reactions", "updated_at"])


@receiver(post_delete, sender=StreamReaction)
def handle_deleted_reaction(sender, instance, **kwargs):
    """Recalculate total reactions when one is removed."""
    if hasattr(instance.stream, "analytics"):
        with transaction.atomic():
            analytics = instance.stream.analytics
            analytics.total_reactions = StreamReaction.objects.filter(
                stream=instance.stream
            ).count()
            analytics.save(update_fields=["total_reactions", "updated_at"])
