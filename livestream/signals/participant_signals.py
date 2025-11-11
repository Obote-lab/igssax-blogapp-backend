# livestream/signals/participant_signals.py
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from ..models import StreamParticipant, StreamModerationLog


@receiver(post_save, sender=StreamParticipant)
def handle_participant_activity(sender, instance, created, **kwargs):
    """Track participant joins and leaves."""
    stream = instance.stream
    if not hasattr(stream, "analytics"):
        return

    with transaction.atomic():
        analytics = stream.analytics
        current_viewers = StreamParticipant.objects.filter(
            stream=stream, left_at__isnull=True
        ).count()

        analytics.peak_concurrent_viewers = max(
            analytics.peak_concurrent_viewers, current_viewers
        )

        # Update watch time averages
        if instance.left_at and instance.joined_at:
            watch_time = instance.left_at - instance.joined_at
            instance.watch_time = watch_time

            all_participants = StreamParticipant.objects.filter(stream=stream)
            total_watch = sum(
                (p.watch_time.total_seconds() for p in all_participants if p.watch_time),
                0,
            )
            avg_seconds = total_watch / max(all_participants.count(), 1)
            analytics.average_watch_time = timezone.timedelta(seconds=avg_seconds)

        analytics.save(
            update_fields=[
                "peak_concurrent_viewers",
                "average_watch_time",
                "updated_at",
            ]
        )

    stream.update_viewer_count()

    if created and instance.role == StreamParticipant.ParticipantRole.MODERATOR:
        StreamModerationLog.objects.create(
            stream=stream,
            action="Moderator joined",
            performed_by=stream.streamer,
            target_user=instance.user,
            notes=f"{instance.user.email} joined as moderator",
        )


@receiver(post_delete, sender=StreamParticipant)
def handle_participant_delete(sender, instance, **kwargs):
    """Update analytics on participant removal."""
    stream = instance.stream
    if hasattr(stream, "analytics"):
        with transaction.atomic():
            current_viewers = StreamParticipant.objects.filter(
                stream=stream, left_at__isnull=True
            ).count()
            analytics = stream.analytics
            analytics.peak_concurrent_viewers = max(
                analytics.peak_concurrent_viewers, current_viewers
            )
            analytics.save(update_fields=["peak_concurrent_viewers", "updated_at"])
    stream.update_viewer_count()
