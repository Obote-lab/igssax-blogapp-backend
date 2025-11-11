from rest_framework import serializers

from users.api.serializers import UserSerializer

from ..models import (LiveStream, StreamAnalytics, StreamBan, StreamMessage,
                      StreamParticipant, StreamReaction, StreamRecording)


class LiveStreamSerializer(serializers.ModelSerializer):
    streamer_info = UserSerializer(source="streamer", read_only=True)
    is_live = serializers.SerializerMethodField()
    can_view = serializers.SerializerMethodField()
    current_viewers = serializers.SerializerMethodField()

    class Meta:
        model = LiveStream
        fields = [
            "id",
            "streamer",
            "streamer_info",
            "title",
            "description",
            "category",
            "privacy",
            "status",
            "stream_key",
            "rtmp_url",
            "playback_url",
            "thumbnail",
            "viewer_count",
            "peak_viewers",
            "total_views",
            "duration",
            "current_viewers",
            "scheduled_for",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
            "is_live",
            "can_view",
        ]
        read_only_fields = [
            "id",
            "streamer",
            "stream_key",
            "viewer_count",
            "peak_viewers",
            "total_views",
            "duration",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
            "is_live",
            "can_view",
            "current_viewers",
        ]

    def get_is_live(self, obj):
        return obj.is_live()

    def get_can_view(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.can_view(request.user)
        return obj.privacy == LiveStream.PrivacyLevel.PUBLIC

    def get_current_viewers(self, obj):
        # Real-time active participants count
        return obj.participants.filter(left_at__isnull=True).count()


class LiveStreamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiveStream
        fields = [
            "title",
            "description",
            "category",
            "privacy",
            "scheduled_for",
            "thumbnail",
        ]

    def validate_scheduled_for(self, value):
        """Validate that scheduled time is in the future"""
        from django.utils import timezone

        if value and value < timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future.")
        return value


class LiveStreamUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating live streams (streamer only)"""

    class Meta:
        model = LiveStream
        fields = ["title", "description", "category", "privacy", "thumbnail"]

    def update(self, instance, validated_data):
        # Only allow updates if stream is not live
        if instance.is_live():
            raise serializers.ValidationError("Cannot update stream while it's live.")
        return super().update(instance, validated_data)


class StreamParticipantSerializer(serializers.ModelSerializer):
    user_info = UserSerializer(source="user", read_only=True)
    is_online = serializers.SerializerMethodField()

    class Meta:
        model = StreamParticipant
        fields = [
            "id",
            "stream",
            "user",
            "user_info",
            "role",
            "joined_at",
            "left_at",
            "last_activity",
            "watch_time",
            "is_online",
        ]
        read_only_fields = [
            "id",
            "stream",
            "user",
            "joined_at",
            "left_at",
            "last_activity",
            "watch_time",
            "is_online",
        ]

    def get_is_online(self, obj):
        """Check if participant is currently online (in last 2 minutes)"""
        from datetime import timedelta

        from django.utils import timezone

        if obj.left_at is not None:
            return False
        return obj.last_activity > timezone.now() - timedelta(minutes=2)


class StreamMessageSerializer(serializers.ModelSerializer):
    user_info = UserSerializer(source="user", read_only=True)
    can_moderate = serializers.SerializerMethodField()

    class Meta:
        model = StreamMessage
        fields = [
            "id",
            "stream",
            "user",
            "user_info",
            "message_type",
            "content",
            "amount",
            "currency",
            "is_moderated",
            "is_flagged",
            "flag_count",
            "moderated_by",
            "timestamp",
            "can_moderate",
        ]
        read_only_fields = [
            "id",
            "stream",
            "user",
            "timestamp",
            "is_flagged",
            "flag_count",
            "moderated_by",
            "can_moderate",
        ]

    def get_can_moderate(self, obj):
        """Check if current user can moderate this message"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        # Streamer can always moderate
        if obj.stream.streamer == request.user:
            return True

        # Check if user is a moderator
        return obj.stream.participants.filter(
            user=request.user,
            role=StreamParticipant.ParticipantRole.MODERATOR,
            left_at__isnull=True,
        ).exists()

    def validate_content(self, value):
        """Validate message content"""
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Message content cannot be empty.")
        if len(value) > 1000:
            raise serializers.ValidationError(
                "Message is too long (max 1000 characters)."
            )
        return value

    def validate(self, data):
        """Additional validation for donation/super chat messages"""
        message_type = data.get("message_type")
        amount = data.get("amount")

        if message_type in [
            StreamMessage.MessageType.DONATION,
            StreamMessage.MessageType.SUPER_CHAT,
        ]:
            if not amount or amount <= 0:
                raise serializers.ValidationError(
                    {
                        "amount": "Amount is required for donation and super chat messages."
                    }
                )

        return data


class StreamReactionSerializer(serializers.ModelSerializer):
    user_info = UserSerializer(source="user", read_only=True)
    emoji = serializers.SerializerMethodField()

    class Meta:
        model = StreamReaction
        fields = [
            "id",
            "stream",
            "user",
            "user_info",
            "reaction_type",
            "emoji",
            "timestamp",
        ]
        read_only_fields = ["id", "stream", "user", "timestamp", "emoji"]

    def get_emoji(self, obj):
        """Get the emoji representation of the reaction"""
        emoji_map = {
            "like": "👍",
            "love": "❤️",
            "laugh": "😂",
            "wow": "😮",
            "sad": "😢",
            "angry": "😠",
            "fire": "🔥",
            "heart": "💖",
        }
        return emoji_map.get(obj.reaction_type, "👍")

    def validate_reaction_type(self, value):
        """Validate reaction type"""
        valid_types = [choice[0] for choice in StreamReaction.REACTION_TYPES]
        if value not in valid_types:
            raise serializers.ValidationError(
                f"Invalid reaction type. Must be one of: {', '.join(valid_types)}"
            )
        return value


class StreamAnalyticsSerializer(serializers.ModelSerializer):
    stream_title = serializers.CharField(source="stream.title", read_only=True)
    engagement_rate = serializers.SerializerMethodField()

    class Meta:
        model = StreamAnalytics
        fields = [
            "id",
            "stream",
            "stream_title",
            "total_messages",
            "total_reactions",
            "average_watch_time",
            "peak_concurrent_viewers",
            "average_bitrate",
            "buffering_ratio",
            "error_rate",
            "total_donations",
            "total_super_chats",
            "engagement_rate",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "stream",
            "created_at",
            "updated_at",
            "engagement_rate",
        ]

    def get_engagement_rate(self, obj):
        """Calculate engagement rate as percentage"""
        if obj.peak_concurrent_viewers > 0:
            total_engagement = obj.total_messages + obj.total_reactions
            return round((total_engagement / obj.peak_concurrent_viewers) * 100, 2)
        return 0


class StreamBanSerializer(serializers.ModelSerializer):
    user_info = UserSerializer(source="user", read_only=True)
    banned_by_info = UserSerializer(source="banned_by", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    stream_title = serializers.CharField(source="stream.title", read_only=True)

    class Meta:
        model = StreamBan
        fields = [
            "id",
            "stream",
            "stream_title",
            "user",
            "user_info",
            "banned_by",
            "banned_by_info",
            "reason",
            "expires_at",
            "created_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "stream",
            "banned_by",
            "created_at",
            "is_active",
            "stream_title",
        ]

    def validate_expires_at(self, value):
        """Validate that expiry date is in the future"""
        from django.utils import timezone

        if value and value < timezone.now():
            raise serializers.ValidationError("Expiry date must be in the future.")
        return value

    def validate(self, data):
        """Additional validation for bans"""
        stream = data.get("stream")
        user = data.get("user")

        if stream and user:
            # Can't ban the streamer
            if stream.streamer == user:
                raise serializers.ValidationError(
                    {"user": "Cannot ban the streamer from their own stream."}
                )

            # Check if user is already banned
            existing_ban = StreamBan.objects.filter(
                stream=stream, user=user, expires_at__gt=timezone.now()
            ).exists()

            if existing_ban:
                raise serializers.ValidationError(
                    {"user": "This user is already banned from the stream."}
                )

        return data


# Additional serializers for specialized use cases
class StreamStatsSerializer(serializers.Serializer):
    """Serializer for stream statistics"""

    total_streams = serializers.IntegerField()
    total_live_streams = serializers.IntegerField()
    total_viewers = serializers.IntegerField()
    average_viewers_per_stream = serializers.FloatField()
    popular_categories = serializers.DictField()


class LiveStreamDetailSerializer(LiveStreamSerializer):
    """Extended serializer for detailed stream view"""

    streamer_full_profile = serializers.SerializerMethodField()
    is_following_streamer = serializers.SerializerMethodField()
    chat_messages_count = serializers.SerializerMethodField()

    class Meta(LiveStreamSerializer.Meta):
        fields = LiveStreamSerializer.Meta.fields + [
            "streamer_full_profile",
            "is_following_streamer",
            "chat_messages_count",
            "tags",
        ]

    def get_streamer_full_profile(self, obj):
        from users.api.serializers import UserProfileSerializer

        return UserProfileSerializer(obj.streamer.profile, context=self.context).data

    def get_is_following_streamer(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return request.user.following.filter(id=obj.streamer.id).exists()
        return False

    def get_chat_messages_count(self, obj):
        return obj.messages.count()


class StreamRecordingSerializer(serializers.ModelSerializer):
    stream_title = serializers.CharField(source="stream.title", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = StreamRecording
        fields = [
            "id",
            "stream",
            "stream_title",
            "video_file",
            "duration",
            "file_size",
            "download_url",
            "created_at",
        ]
        read_only_fields = ["id", "stream", "created_at"]

    def get_download_url(self, obj):
        request = self.context.get("request")
        if request and obj.video_file:
            return request.build_absolute_uri(obj.video_file.url)
        return None
