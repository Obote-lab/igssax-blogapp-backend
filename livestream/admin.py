from django.contrib import admin

from .models import (LiveStream, StreamAnalytics, StreamBan, StreamMessage,
                     StreamParticipant, StreamReaction)


@admin.register(LiveStream)
class LiveStreamAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "streamer",
        "status",
        "privacy",
        "viewer_count",
        "started_at",
    ]
    list_filter = ["status", "privacy", "category", "created_at"]
    search_fields = ["title", "streamer__email", "stream_key"]
    readonly_fields = ["stream_key", "created_at", "updated_at"]


@admin.register(StreamParticipant)
class StreamParticipantAdmin(admin.ModelAdmin):
    list_display = ["user", "stream", "role", "joined_at", "left_at"]
    list_filter = ["role", "joined_at"]
    search_fields = ["user__email", "stream__title"]


@admin.register(StreamMessage)
class StreamMessageAdmin(admin.ModelAdmin):
    list_display = ["user", "stream", "message_type", "is_moderated", "timestamp"]
    list_filter = ["message_type", "is_moderated", "timestamp"]
    search_fields = ["user__email", "stream__title", "content"]


@admin.register(StreamReaction)
class StreamReactionAdmin(admin.ModelAdmin):
    list_display = ["user", "stream", "reaction_type", "timestamp"]
    list_filter = ["reaction_type", "timestamp"]
    search_fields = ["user__email", "stream__title"]


@admin.register(StreamAnalytics)
class StreamAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        "stream",
        "total_messages",
        "total_reactions",
        "peak_concurrent_viewers",
    ]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(StreamBan)
class StreamBanAdmin(admin.ModelAdmin):
    list_display = ["user", "stream", "banned_by", "expires_at", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__email", "stream__title", "reason"]
