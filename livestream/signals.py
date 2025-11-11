# from django.db import transaction
# from django.db.models.signals import post_delete, post_save
# from django.dispatch import receiver
# from django.utils import timezone

# from .models import (LiveStream, StreamAnalytics, StreamMessage,
#                      StreamModerationLog, StreamParticipant, StreamReaction)

# # Import with error handling for the service
# try:
#     from .services import StreamNotificationService

#     notification_service = StreamNotificationService()
# except ImportError:
#     notification_service = None
#     print("StreamNotificationService not available")


# @receiver(post_save, sender=LiveStream)
# def handle_livestream_changes(sender, instance, created, **kwargs):
#     """Handle all LiveStream post-save events"""
#     if created:
#         # Create analytics record for new stream
#         StreamAnalytics.objects.create(stream=instance)
#     else:
#         # Handle status changes for existing streams
#         handle_stream_status_change(instance)

#         # Update analytics when viewer count changes
#         if hasattr(instance, "analytics"):
#             instance.analytics.update_realtime_metrics()


# def handle_stream_status_change(stream):
#     """Handle stream status changes with notification"""
#     if not notification_service:
#         return

#     try:
#         if stream.status == LiveStream.StreamStatus.LIVE:
#             notification_service.notify_stream_started(stream)

#             # Create moderation log entry
#             StreamModerationLog.objects.create(
#                 stream=stream,
#                 action="Stream started",
#                 performed_by=stream.streamer,
#                 notes=f"Stream '{stream.title}' went live",
#             )

#         elif stream.status == LiveStream.StreamStatus.ENDED:
#             notification_service.notify_stream_ended(stream)

#             # Create moderation log entry
#             StreamModerationLog.objects.create(
#                 stream=stream,
#                 action="Stream ended",
#                 performed_by=stream.streamer,
#                 notes=f"Stream '{stream.title}' ended after {stream.duration}",
#             )

#     except Exception as e:
#         # Log the error but don't crash the application
#         print(f"Notification service error: {e}")


# @receiver(post_save, sender=StreamMessage)
# def handle_new_message(sender, instance, created, **kwargs):
#     """Handle new stream messages"""
#     if created and hasattr(instance.stream, "analytics"):
#         # Use atomic transaction for safety
#         with transaction.atomic():
#             analytics = instance.stream.analytics
#             analytics.total_messages = StreamMessage.objects.filter(
#                 stream=instance.stream
#             ).count()
#             analytics.save(update_fields=["total_messages", "updated_at"])

#         # Auto-flag messages with certain keywords
#         auto_flag_keywords = ["spam", "http://", "https://", "buy now", "click here"]
#         message_lower = instance.content.lower()

#         if any(keyword in message_lower for keyword in auto_flag_keywords):
#             instance.is_flagged = True
#             instance.flag_count += 1
#             instance.save()

#             # Log the auto-flagging
#             StreamModerationLog.objects.create(
#                 stream=instance.stream,
#                 action="Message auto-flagged",
#                 performed_by=None,  # System action
#                 target_user=instance.user,
#                 notes=f"Auto-flagged for containing suspicious keywords",
#             )


# @receiver(post_save, sender=StreamReaction)
# def handle_new_reaction(sender, instance, created, **kwargs):
#     """Handle new stream reactions"""
#     if created and hasattr(instance.stream, "analytics"):
#         # Batch update for better performance
#         with transaction.atomic():
#             analytics = instance.stream.analytics
#             analytics.total_reactions = StreamReaction.objects.filter(
#                 stream=instance.stream
#             ).count()
#             analytics.save(update_fields=["total_reactions", "updated_at"])


# @receiver(post_delete, sender=StreamMessage)
# def handle_deleted_message(sender, instance, **kwargs):
#     """Update analytics when a message is deleted"""
#     if hasattr(instance.stream, "analytics"):
#         with transaction.atomic():
#             analytics = instance.stream.analytics
#             analytics.total_messages = StreamMessage.objects.filter(
#                 stream=instance.stream
#             ).count()
#             analytics.save(update_fields=["total_messages", "updated_at"])


# @receiver(post_delete, sender=StreamReaction)
# def handle_deleted_reaction(sender, instance, **kwargs):
#     """Update analytics when a reaction is deleted"""
#     if hasattr(instance.stream, "analytics"):
#         with transaction.atomic():
#             analytics = instance.stream.analytics
#             analytics.total_reactions = StreamReaction.objects.filter(
#                 stream=instance.stream
#             ).count()
#             analytics.save(update_fields=["total_reactions", "updated_at"])


# @receiver(post_save, sender=StreamMessage)
# def handle_flagged_messages(sender, instance, **kwargs):
#     """Handle message flagging and auto-moderation"""
#     if instance.is_flagged and instance.flag_count >= 3:
#         # Auto-moderate messages with 3+ flags
#         instance.is_moderated = True
#         instance.save()

#         StreamModerationLog.objects.create(
#             stream=instance.stream,
#             action="Message auto-moderated",
#             performed_by=None,  # System action
#             target_user=instance.user,
#             notes=f"Message auto-moderated after {instance.flag_count} flags",
#         )


# @receiver(post_save, sender=StreamParticipant)
# def handle_participant_activity(sender, instance, created, **kwargs):
#     """Update stream analytics when participants join/leave"""
#     stream = instance.stream

#     if hasattr(stream, "analytics"):
#         with transaction.atomic():
#             analytics = stream.analytics

#             # Update peak concurrent viewers
#             current_viewers = StreamParticipant.objects.filter(
#                 stream=stream, left_at__isnull=True
#             ).count()

#             analytics.peak_concurrent_viewers = max(
#                 analytics.peak_concurrent_viewers, current_viewers
#             )

#             # Update average watch time when participant leaves
#             if instance.left_at and instance.joined_at:
#                 # Calculate this participant's watch time
#                 watch_time = instance.left_at - instance.joined_at
#                 instance.watch_time = watch_time

#                 # Update average watch time for all participants
#                 active_participants = StreamParticipant.objects.filter(stream=stream)
#                 if active_participants.exists():
#                     total_watch_time = sum(
#                         (
#                             p.watch_time.total_seconds()
#                             for p in active_participants
#                             if p.watch_time
#                         ),
#                         0,
#                     )
#                     avg_seconds = total_watch_time / active_participants.count()
#                     analytics.average_watch_time = timezone.timedelta(
#                         seconds=avg_seconds
#                     )

#             analytics.save(
#                 update_fields=[
#                     "peak_concurrent_viewers",
#                     "average_watch_time",
#                     "updated_at",
#                 ]
#             )

#     # Update the stream's viewer count
#     stream.update_viewer_count()

#     # Create moderation log for moderator assignments
#     if instance.role == StreamParticipant.ParticipantRole.MODERATOR:
#         StreamModerationLog.objects.create(
#             stream=stream,
#             action="Moderator assigned",
#             performed_by=stream.streamer,
#             target_user=instance.user,
#             notes=f"User {instance.user.email} assigned as moderator",
#         )


# @receiver(post_save, sender=StreamParticipant)
# def handle_participant_join(sender, instance, created, **kwargs):
#     """Handle when a participant joins a stream"""
#     if created and instance.left_at is None:
#         # Participant just joined
#         stream = instance.stream

#         # Increment total views for the stream
#         stream.total_views += 1
#         stream.save(update_fields=["total_views", "updated_at"])

#         # Send join notification (if implemented)
#         if notification_service:
#             try:
#                 # You could add a notification method for joins
#                 pass
#             except Exception as e:
#                 print(f"Join notification error: {e}")


# @receiver(post_save, sender=StreamParticipant)
# def handle_participant_leave(sender, instance, **kwargs):
#     """Handle when a participant leaves a stream"""
#     if instance.left_at is not None:
#         stream = instance.stream

#         # Create moderation log for important departures
#         if instance.role in [
#             StreamParticipant.ParticipantRole.MODERATOR,
#             StreamParticipant.ParticipantRole.GUEST,
#         ]:
#             StreamModerationLog.objects.create(
#                 stream=stream,
#                 action=f"{instance.get_role_display()} left stream",
#                 performed_by=instance.user,
#                 target_user=instance.user,
#                 notes=f"Watch time: {instance.watch_time}",
#             )


# @receiver(post_delete, sender=StreamParticipant)
# def handle_participant_delete(sender, instance, **kwargs):
#     """Handle when a participant record is deleted"""
#     stream = instance.stream

#     # Update stream viewer count
#     if hasattr(stream, "analytics"):
#         with transaction.atomic():
#             current_viewers = StreamParticipant.objects.filter(
#                 stream=stream, left_at__isnull=True
#             ).count()

#             analytics = stream.analytics
#             analytics.peak_concurrent_viewers = max(
#                 analytics.peak_concurrent_viewers, current_viewers
#             )
#             analytics.save(update_fields=["peak_concurrent_viewers", "updated_at"])

#     stream.update_viewer_count()
