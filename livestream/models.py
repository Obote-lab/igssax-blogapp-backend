import hashlib
import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from .models import StreamMessage, StreamParticipant, StreamReaction


User = settings.AUTH_USER_MODEL


class LiveStream(models.Model):
    class StreamStatus(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        LIVE = "live", _("Live")
        ENDED = "ended", _("Ended")
        CANCELLED = "cancelled", _("Cancelled")

    class PrivacyLevel(models.TextChoices):
        PUBLIC = "public", _("Public")
        FRIENDS = "friends", _("Friends Only")
        PRIVATE = "private", _("Private")

    # Core stream info
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    streamer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="live_streams"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    messages: models.Manager["StreamMessage"]
    reactions: models.Manager["StreamReaction"]
    participants: models.Manager["StreamParticipant"]

    # Stream configuration
    privacy = models.CharField(
        max_length=20, choices=PrivacyLevel.choices, default=PrivacyLevel.PUBLIC
    )
    status = models.CharField(
        max_length=20, choices=StreamStatus.choices, default=StreamStatus.SCHEDULED
    )

    # Stream keys and URLs
    stream_key = models.CharField(max_length=100, unique=True, editable=False)
    rtmp_url = models.CharField(max_length=500, blank=True)
    playback_url = models.CharField(max_length=500, blank=True)
    thumbnail = models.ImageField(upload_to="stream_thumbnails/", null=True, blank=True)
    is_featured = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=10, default="en")
    age_restriction = models.BooleanField(default=False)

    # Stream metrics
    viewer_count = models.PositiveIntegerField(default=0)
    peak_viewers = models.PositiveIntegerField(default=0)
    total_views = models.PositiveIntegerField(default=0)
    duration = models.DurationField(null=True, blank=True)

    # Timestamps
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["streamer", "status"]),
            models.Index(fields=["status", "privacy"]),
            models.Index(fields=["stream_key"]),
            models.Index(fields=["category"]),
            models.Index(fields=["is_featured", "status"]),
            models.Index(fields=["created_at", "status"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.streamer.email}"

    def is_live(self):
        return self.status == self.StreamStatus.LIVE

    def can_view(self, user):
        if self.privacy == self.PrivacyLevel.PUBLIC:
            return True
        elif self.privacy == self.PrivacyLevel.FRIENDS:
            return self.streamer.is_friend(user)
            # return other_user in self.get_friends()

        elif self.privacy == self.PrivacyLevel.PRIVATE:
            return user == self.streamer
        return False

    def start_stream(self):
        """Start the stream"""
        if self.status != self.StreamStatus.LIVE:
            self.status = self.StreamStatus.LIVE
            self.started_at = timezone.now()
            self.save()

    def end_stream(self):
        """End the stream"""
        if self.status == self.StreamStatus.LIVE:
            self.status = self.StreamStatus.ENDED
            self.ended_at = timezone.now()
            if self.started_at:
                self.duration = self.ended_at - self.started_at
            self.save()

    def update_viewer_count(self):
        """Update viewer count based on active participants"""
        active_count = self.participants.filter(left_at__isnull=True).count()
        self.viewer_count = active_count
        if active_count > self.peak_viewers:
            self.peak_viewers = active_count
        self.save()

    def add_moderator(self, user):
        """Add a moderator to the stream"""
        participant, created = self.participants.get_or_create(
            user=user, defaults={"role": StreamParticipant.ParticipantRole.MODERATOR}
        )
        if not created:
            participant.role = StreamParticipant.ParticipantRole.MODERATOR
            participant.save()
        return participant

    def generate_stream_key(self):
        """More secure stream key generation"""
        import secrets

        return secrets.token_urlsafe(32)

    def save(self, *args, **kwargs):
        if not self.stream_key:
            self.stream_key = self.generate_stream_key()

        # Auto-generate RTMP URL if not provided
        if not self.rtmp_url and self.stream_key:
            self.rtmp_url = f"rtmp://your-server.com/live/{self.stream_key}"

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("livestream:stream-detail", kwargs={"pk": self.id})

    @property
    def is_scheduled(self):
        return self.status == self.StreamStatus.SCHEDULED and self.scheduled_for

    @classmethod
    def get_live_streams(cls):
        """Get all currently live streams"""
        return cls.objects.filter(status=cls.StreamStatus.LIVE)

    @classmethod
    def get_featured_streams(cls):
        """Get featured live streams"""
        return cls.get_live_streams().filter(is_featured=True)


class StreamRecording(models.Model):
    stream = models.OneToOneField(
        LiveStream, on_delete=models.CASCADE, related_name="recording"
    )
    video_file = models.FileField(upload_to="stream_recordings/")
    duration = models.DurationField()
    file_size = models.PositiveBigIntegerField()  # in bytes
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recording for {self.stream.title}"


class StreamParticipant(models.Model):
    class ParticipantRole(models.TextChoices):
        VIEWER = "viewer", _("Viewer")
        GUEST = "guest", _("Guest")
        MODERATOR = "moderator", _("Moderator")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream = models.ForeignKey(
        LiveStream, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="stream_participations"
    )
    role = models.CharField(
        max_length=20, choices=ParticipantRole.choices, default=ParticipantRole.VIEWER
    )

    # Connection info
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)

    # Viewer stats
    watch_time = models.DurationField(default=timezone.timedelta(0))

    class Meta:
        unique_together = ["stream", "user"]
        indexes = [
            models.Index(fields=["stream", "user"]),
            models.Index(fields=["user", "joined_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} in {self.stream.title}"


class StreamMessage(models.Model):
    class MessageType(models.TextChoices):
        CHAT = "chat", _("Chat Message")
        DONATION = "donation", _("Donation")
        SUPER_CHAT = "super_chat", _("Super Chat")
        SYSTEM = "system", _("System Message")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream = models.ForeignKey(
        LiveStream, on_delete=models.CASCADE, related_name="messages"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="stream_messages"
    )

    # Message content
    message_type = models.CharField(
        max_length=20, choices=MessageType.choices, default=MessageType.CHAT
    )
    content = models.TextField()
    # Add these fields to StreamMessage
    is_flagged = models.BooleanField(default=False)
    flag_count = models.PositiveIntegerField(default=0)

    # For donations/super chats
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")

    # Moderation
    is_moderated = models.BooleanField(default=False)
    moderated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_messages",
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["stream", "timestamp"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.user.email}: {self.content[:50]}"

    def flag_message(self, user=None):
        """Flag a message for moderation"""
        self.is_flagged = True
        self.flag_count += 1
        self.save()

        # Create moderation log entry
        if user:
            StreamModerationLog.objects.create(
                stream=self.stream,
                action=f"Message flagged by {user.email}",
                performed_by=user,
                target_user=self.user,
                notes=f"Flag count: {self.flag_count}",
            )


class StreamReaction(models.Model):
    REACTION_TYPES = [
        ("like", "👍 Like"),
        ("love", "❤️ Love"),
        ("laugh", "😂 Laugh"),
        ("wow", "😮 Wow"),
        ("sad", "😢 Sad"),
        ("angry", "😠 Angry"),
        ("fire", "🔥 Fire"),
        ("heart", "💖 Heart"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream = models.ForeignKey(
        LiveStream, on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="stream_reactions"
    )
    reaction_type = models.CharField(
        max_length=20, choices=REACTION_TYPES, default="like"
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["stream", "user", "reaction_type"]
        indexes = [
            models.Index(fields=["stream", "reaction_type"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.user.email} reacted {self.reaction_type} to {self.stream.title}"


class StreamAnalytics(models.Model):
    stream = models.OneToOneField(
        LiveStream, on_delete=models.CASCADE, related_name="analytics"
    )

    # Engagement metrics
    total_messages = models.PositiveIntegerField(default=0)
    total_reactions = models.PositiveIntegerField(default=0)
    average_watch_time = models.DurationField(default=timezone.timedelta(0))
    peak_concurrent_viewers = models.PositiveIntegerField(default=0)

    # Technical metrics
    average_bitrate = models.FloatField(default=0)
    buffering_ratio = models.FloatField(default=0)
    error_rate = models.FloatField(default=0)

    # Financial metrics (if monetized)
    total_donations = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_super_chats = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analytics for {self.stream.title}"

    def update_metrics(self):
        self.total_messages = self.stream.messages.count()
        self.total_reactions = self.stream.reactions.count()
        participants = self.stream.participants.all()
        if participants.exists():
            total_watch_time = sum(
                (p.watch_time for p in participants), timezone.timedelta()
            )
            self.average_watch_time = total_watch_time / participants.count()
        self.save()

    def update_realtime_metrics(self):
        """Update real-time metrics without full recalculation"""
        self.total_messages = self.stream.messages.count()
        self.total_reactions = self.stream.reactions.count()
        self.peak_concurrent_viewers = max(
            self.peak_concurrent_viewers, self.stream.viewer_count
        )
        self.save(
            update_fields=[
                "total_messages",
                "total_reactions",
                "peak_concurrent_viewers",
                "updated_at",
            ]
        )


class StreamBan(models.Model):
    stream = models.ForeignKey(
        LiveStream, on_delete=models.CASCADE, related_name="bans"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stream_bans")
    banned_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="given_stream_bans"
    )
    reason = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["stream", "user"]
        indexes = [
            models.Index(fields=["stream", "user"]),
        ]

    def __str__(self):
        return f"{self.user.email} banned from {self.stream.title}"

    def is_active(self):
        if self.expires_at:
            return timezone.now() < self.expires_at
        return True


class StreamModerationLog(models.Model):
    stream = models.ForeignKey(
        LiveStream, on_delete=models.CASCADE, related_name="moderation_logs"
    )
    action = models.CharField(max_length=100)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="moderation_targets"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.action} by {self.performed_by} on {self.target_user}"
