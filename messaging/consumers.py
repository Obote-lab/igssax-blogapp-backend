# messaging/consumers.py
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from .models import DirectMessage

User = get_user_model()


class DMConsumer(AsyncWebsocketConsumer):
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

        low, high = min(self.user.id, other_id), max(self.user.id, other_id)
        self.room_group_name = f"dm_{low}_{high}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_status",
                "event": "joined",
                "username": self.user.get_username(),
            },
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_status",
                "event": "left",
                "username": self.user.get_username(),
            },
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        event_type = data.get("type")

        if event_type == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_event",
                    "username": self.user.get_username(),
                },
            )
            return

        if event_type == "read":
            message_id = data.get("message_id")
            if message_id:
                await self.mark_read(message_id)
            return

        if event_type == "message":
            await self.create_and_broadcast_message(
                data.get("content", ""),
                data.get("in_reply_to"),
            )

    async def typing_event(self, event):
        await self.send_json({"type": "typing", "username": event["username"]})

    async def user_status(self, event):
        await self.send_json(
            {"type": "status", "event": event["event"], "username": event["username"]}
        )

    async def chat_message(self, event):
        await self.send_json({"type": "message", "message": event["message"]})

    async def read_event(self, event):
        await self.send_json(
            {
                "type": "read",
                "message_id": event["message_id"],
                "username": event["username"],
            }
        )

    async def create_and_broadcast_message(self, content, in_reply_to_id=None):
        dm, payload = await self._create_dm(content, in_reply_to_id)
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "chat_message", "message": payload},
        )

    @database_sync_to_async
    def _create_dm(self, content, in_reply_to_id):
        low, high = map(int, self.room_group_name.split("_")[1:])
        recipient_id = high if self.user.id == low else low

        recipient = User.objects.get(id=recipient_id)
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
            "sender": {"id": self.user.id, "username": self.user.get_username()},
            "recipient": {"id": recipient.id, "username": recipient.get_username()},
            "content": dm.content,
            "created_at": dm.created_at.isoformat(),
            "delivered": dm.delivered,
            "read": dm.read,
        }

        return dm, payload

    async def mark_read(self, message_id):
        updated = await self._mark_read_db(message_id)
        if updated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "read_event",
                    "message_id": message_id,
                    "username": self.user.get_username(),
                },
            )

    @database_sync_to_async
    def _mark_read_db(self, message_id):
        dm = DirectMessage.objects.filter(
            id=message_id,
            recipient=self.user,
            read=False,
        ).first()
        if not dm:
            return False
        dm.read = True
        dm.save(update_fields=["read"])
        return True
