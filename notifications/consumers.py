import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Handles real-time notifications for authenticated users.
    Uses `user_<id>` group for delivery.
    """

    async def connect(self):
        user = self.scope["user"]
        if user.is_anonymous or not user.is_active:
            await self.close()
            return

        self.user = user
        self.group_name = f"user_{user.id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send(
            json.dumps({"type": "connection_established", "message": "Connected."})
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Handle WebSocket events (e.g., mark as read).
        """
        data = json.loads(text_data)
        action = data.get("action")

        if action == "ping":
            await self.send(json.dumps({"type": "pong"}))

        elif action == "mark_read":
            notif_id = data.get("notification_id")
            if notif_id:
                await self.mark_as_read(notif_id)

    @database_sync_to_async
    def mark_as_read(self, notif_id):
        from .models import Notification

        Notification.objects.filter(id=notif_id, recipient=self.user).update(
            is_read=True
        )

    async def send_notification(self, event):
        await self.send(
            json.dumps({"type": "notification", "content": event["content"]})
        )
