from rest_framework import serializers

from ..models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)
    sender_avatar = serializers.ImageField(
        source="sender.profile.avatar", read_only=True
    )
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "message",
            "sender",
            "sender_name",
            "sender_avatar",
            "is_read",
            "content_type",
            "object_id",
            "time_ago",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_time_ago(self, obj):
        from django.utils.timesince import timesince

        return timesince(obj.created_at) + " ago"


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            # Email preferences
            "email_friend_requests",
            "email_friend_acceptances",
            "email_post_likes",
            "email_post_comments",
            "email_comment_replies",
            "email_mentions",
            "email_messages",
            "email_system",
            # Push preferences
            "push_friend_requests",
            "push_friend_acceptances",
            "push_post_likes",
            "push_post_comments",
            "push_comment_replies",
            "push_mentions",
            "push_messages",
            "push_system",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class NotificationCountSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()
    total_count = serializers.IntegerField()
