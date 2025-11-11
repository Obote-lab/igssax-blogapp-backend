# messaging/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import DirectMessage

User = get_user_model()


class DMConsumer(AsyncWebsocketConsumer):
    """Advanced WebSocket consumer for 1-to-1 direct messaging."""

    async def connect(self):
        self.other_user_id = self.scope["url_route"]["kwargs"].get("other_user_id")
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        try:
            other_id = int(self.other_user_id)
        except Exception:
            await self.close()
            return

        # deterministic room name
        low, high = (min(self.user.id, other_id), max(self.user.id, other_id))
        self.room_group_name = f"dm_{low}_{high}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Notify others that user joined
        await self.channel_layer.group_send(self.room_group_name, {
            "type": "user_status",
            "event": "joined",
            "username": self.user.email,
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await self.channel_layer.group_send(self.room_group_name, {
            "type": "user_status",
            "event": "left",
            "username": self.user.email,
        })

    async def receive(self, text_data):
        data = json.loads(text_data)
        event_type = data.get("type")

        if event_type == "typing":
            await self.channel_layer.group_send(self.room_group_name, {
                "type": "typing_event",
                "username": self.user.email,
            })
            return

        if event_type == "read":
            message_id = data.get("message_id")
            if message_id:
                await self.mark_read(message_id)
            return

        if event_type == "message":
            content = data.get("content", "")
            in_reply_to = data.get("in_reply_to")
            await self.create_and_broadcast_message(content, in_reply_to)
            return

    async def typing_event(self, event):
        await self.send_json({"type": "typing", "username": event["username"]})

    async def user_status(self, event):
        await self.send_json({"type": "status", "event": event["event"], "username": event["username"]})

    async def chat_message(self, event):
        await self.send_json({"type": "message", "message": event["message"]})

    async def read_event(self, event):
        await self.send_json({"type": "read", "message_id": event["message_id"], "username": event["username"]})

    @database_sync_to_async
    def create_and_broadcast_message(self, content, in_reply_to_id=None):
        parts = self.room_group_name.split("_")
        low = int(parts[1])
        high = int(parts[2])
        recipient_id = high if self.user.id == low else low

        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            return

        in_reply_to = DirectMessage.objects.filter(id=in_reply_to_id).first()
        dm = DirectMessage.objects.create(
            sender=self.user,
            recipient=recipient,
            content=content,
            in_reply_to=in_reply_to,
            delivered=True,
        )

        payload = {
            "id": dm.id,
            "sender": {"id": self.user.id, "email": self.user.email},
            "recipient": {"id": recipient.id, "email": recipient.email},
            "content": dm.content,
            "created_at": dm.created_at.isoformat(),
            "delivered": dm.delivered,
            "read": dm.read,
        }

        # Broadcast to group
        from asgiref.sync import async_to_sync
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {"type": "chat_message", "message": payload},
        )

    @database_sync_to_async
    def mark_read(self, message_id):
        dm = DirectMessage.objects.filter(id=message_id).first()
        if not dm or dm.recipient_id != self.user.id:
            return
        if not dm.read:
            dm.read = True
            dm.save(update_fields=["read"])

        from asgiref.sync import async_to_sync
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {"type": "read_event", "message_id": dm.id, "username": self.user.email},
        )
