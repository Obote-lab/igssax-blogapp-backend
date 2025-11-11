# livestream/signals/livestream_signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.utils import timezone

from ..models import LiveStream, StreamAnalytics, StreamModerationLog

# Optional: notification service (fail gracefully)
try:
    from ..services import StreamNotificationService
    notification_service = StreamNotificationService()
except ImportError:
    notification_service = None
    print("[Signal] StreamNotificationService not available")


@receiver(post_save, sender=LiveStream)
def handle_livestream_creation(sender, instance, created, **kwargs):
    """Handle LiveStream creation or update events."""
    if created:
        # Create analytics record for new stream
        StreamAnalytics.objects.create(stream=instance)
    else:
        # Handle status changes for existing streams
        handle_stream_status_change(instance)

        # Update analytics if metrics have changed
        if hasattr(instance, "analytics"):
            instance.analytics.update_realtime_metrics()


def handle_stream_status_change(stream):
    """Handle stream status transitions."""
    if not notification_service:
        return

    try:
        if stream.status == LiveStream.StreamStatus.LIVE:
            notification_service.notify_stream_started(stream)

            StreamModerationLog.objects.create(
                stream=stream,
                action="Stream started",
                performed_by=stream.streamer,
                notes=f"Stream '{stream.title}' went live",
            )

        elif stream.status == LiveStream.StreamStatus.ENDED:
            notification_service.notify_stream_ended(stream)

            StreamModerationLog.objects.create(
                stream=stream,
                action="Stream ended",
                performed_by=stream.streamer,
                notes=f"Stream '{stream.title}' ended at {timezone.now()}",
            )
    except Exception as e:
        print(f"[Signal Error] Notification service error: {e}")
