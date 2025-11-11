import asyncio
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (LiveStream, StreamBan, StreamMessage, StreamParticipant,
                     StreamReaction)

User = get_user_model()


class LiveStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.stream_id = self.scope["url_route"]["kwargs"]["stream_id"]
        self.stream_group_name = f"stream_{self.stream_id}"
        self.user = self.scope["user"]

        # Check if user can access the stream
        if await self.can_access_stream():
            # Join stream group
            await self.channel_layer.group_add(
                self.stream_group_name, self.channel_name
            )
            await self.accept()

            # Add user as participant
            await self.add_participant()

            # Send current viewer count
            await self.send_viewer_count()

            # Send welcome message
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "system_message",
                        "message": f"Connected to stream {self.stream_id}",
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )
        else:
            await self.close()

    async def disconnect(self, close_code):
        # Remove from stream group
        await self.channel_layer.group_discard(
            self.stream_group_name, self.channel_name
        )

        # Remove user as participant
        await self.remove_participant()

        # Update viewer count
        await self.send_viewer_count()

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get("type")

        if message_type == "chat_message":
            await self.handle_chat_message(data)
        elif message_type == "reaction":
            await self.handle_reaction(data)
        elif message_type == "stream_control":
            await self.handle_stream_control(data)
        elif message_type == "viewer_heartbeat":
            await self.handle_heartbeat()

    async def handle_chat_message(self, data):
        """Handle chat messages from viewers"""
        content = data.get("content", "").strip()

        if not content:
            return

        # Check if user is banned
        if await self.is_user_banned():
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": "You are banned from this stream"}
                )
            )
            return

        # Save message to database
        message = await self.save_chat_message(content)

        # Broadcast message to stream group
        await self.channel_layer.group_send(
            self.stream_group_name,
            {
                "type": "chat_message",
                "message_id": str(message.id),
                "user_id": str(self.user.id),
                "username": self.user.username() or self.user.email,
                "content": content,
                "timestamp": message.timestamp.isoformat(),
                "avatar": await self.get_user_avatar(),
            },
        )

    async def handle_reaction(self, data):
        """Handle reactions from viewers"""
        reaction_type = data.get("reaction_type", "like")

        # Save reaction to database
        reaction = await self.save_reaction(reaction_type)

        # Broadcast reaction to stream group
        await self.channel_layer.group_send(
            self.stream_group_name,
            {
                "type": "reaction",
                "reaction_type": reaction_type,
                "user_id": str(self.user.id),
                "username": self.user.username() or self.user.email,
                "timestamp": reaction.timestamp.isoformat(),
            },
        )

    async def handle_stream_control(self, data):
        """Handle stream control commands (streamer only)"""
        action = data.get("action")

        # Check if user is the streamer
        if not await self.is_streamer():
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Only the streamer can control the stream",
                    }
                )
            )
            return

        if action == "start_stream":
            await self.start_stream()
        elif action == "end_stream":
            await self.end_stream()
        elif action == "update_title":
            await self.update_stream_title(data.get("title"))

    async def handle_heartbeat(self):
        """Handle viewer heartbeat to track active viewers"""
        await self.update_participant_activity()

    # Message type handlers
    async def chat_message(self, event):
        """Send chat message to WebSocket"""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat_message",
                    "message_id": event["message_id"],
                    "user_id": event["user_id"],
                    "username": event["username"],
                    "content": event["content"],
                    "timestamp": event["timestamp"],
                    "avatar": event["avatar"],
                }
            )
        )

    async def reaction(self, event):
        """Send reaction to WebSocket"""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "reaction",
                    "reaction_type": event["reaction_type"],
                    "user_id": event["user_id"],
                    "username": event["username"],
                    "timestamp": event["timestamp"],
                }
            )
        )

    async def viewer_count_update(self, event):
        """Send viewer count update to WebSocket"""
        await self.send(
            text_data=json.dumps(
                {"type": "viewer_count_update", "viewer_count": event["viewer_count"]}
            )
        )

    async def stream_status_update(self, event):
        """Send stream status update to WebSocket"""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "stream_status_update",
                    "status": event["status"],
                    "message": event.get("message", ""),
                }
            )
        )

    # Database operations
    @database_sync_to_async
    def can_access_stream(self):
        """Check if user can access the stream"""
        try:
            stream = LiveStream.objects.get(id=self.stream_id)
            return stream.can_view(self.user)
        except LiveStream.DoesNotExist:
            return False

    @database_sync_to_async
    def is_streamer(self):
        """Check if user is the streamer"""
        try:
            stream = LiveStream.objects.get(id=self.stream_id)
            return stream.streamer == self.user
        except LiveStream.DoesNotExist:
            return False

    @database_sync_to_async
    def is_user_banned(self):
        """Check if user is banned from the stream"""
        return StreamBan.objects.filter(
            stream_id=self.stream_id, user=self.user, expires_at__gt=timezone.now()
        ).exists()

    @database_sync_to_async
    def add_participant(self):
        """Add user as stream participant"""
        stream = LiveStream.objects.get(id=self.stream_id)
        participant, created = StreamParticipant.objects.get_or_create(
            stream=stream, user=self.user, defaults={"joined_at": timezone.now()}
        )

        if not created and participant.left_at:
            participant.left_at = None
            participant.save()

        return participant

    @database_sync_to_async
    def remove_participant(self):
        """Remove user as stream participant"""
        try:
            participant = StreamParticipant.objects.get(
                stream_id=self.stream_id, user=self.user, left_at__isnull=True
            )
            participant.left_at = timezone.now()

            # Calculate watch time
            if participant.joined_at:
                participant.watch_time = timezone.now() - participant.joined_at

            participant.save()
            return True
        except StreamParticipant.DoesNotExist:
            return False

    @database_sync_to_async
    def update_participant_activity(self):
        """Update participant's last activity"""
        try:
            participant = StreamParticipant.objects.get(
                stream_id=self.stream_id, user=self.user, left_at__isnull=True
            )
            participant.last_activity = timezone.now()
            participant.save()
            return True
        except StreamParticipant.DoesNotExist:
            return False

    @database_sync_to_async
    def save_chat_message(self, content):
        """Save chat message to database"""
        stream = LiveStream.objects.get(id=self.stream_id)
        message = StreamMessage.objects.create(
            stream=stream, user=self.user, content=content
        )
        return message

    @database_sync_to_async
    def save_reaction(self, reaction_type):
        """Save reaction to database"""
        stream = LiveStream.objects.get(id=self.stream_id)
        reaction, created = StreamReaction.objects.get_or_create(
            stream=stream, user=self.user, reaction_type=reaction_type
        )
        return reaction

    @database_sync_to_async
    def get_user_avatar(self):
        """Get user's avatar URL"""
        if hasattr(self.user, "profile") and self.user.profile.avatar:
            return self.user.profile.avatar.url
        return None

    @database_sync_to_async
    def send_viewer_count(self):
        """Calculate and broadcast viewer count"""
        stream = LiveStream.objects.get(id=self.stream_id)
        viewer_count = StreamParticipant.objects.filter(
            stream=stream, left_at__isnull=True
        ).count()

        stream.viewer_count = viewer_count
        stream.peak_viewers = max(stream.peak_viewers, viewer_count)
        stream.save()

        return viewer_count

    @database_sync_to_async
    def start_stream(self):
        """Start the stream"""
        stream = LiveStream.objects.get(id=self.stream_id)
        stream.status = LiveStream.StreamStatus.LIVE
        stream.started_at = timezone.now()
        stream.save()
        return stream

    @database_sync_to_async
    def end_stream(self):
        """End the stream"""
        stream = LiveStream.objects.get(id=self.stream_id)
        stream.status = LiveStream.StreamStatus.ENDED
        stream.ended_at = timezone.now()

        if stream.started_at:
            stream.duration = stream.ended_at - stream.started_at

        stream.save()
        return stream

    @database_sync_to_async
    def update_stream_title(self, title):
        """Update stream title"""
        if title:
            stream = LiveStream.objects.get(id=self.stream_id)
            stream.title = title
            stream.save()
            return stream
        return None

    async def redis_message(self, event):
        """Handle forwarded Redis events"""
        data = event["data"]
        await self.send(text_data=json.dumps(data))
