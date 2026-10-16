import json

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from posts.querysets import visible_posts_for_user

from .api.serializers import CommentSerializer, ConversationMessageSerializer
from .models import Comment, Conversation, ConversationMessage

User = get_user_model()
from posts.models import Post


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.room_group_name = f"conversation_{self.conversation_id}"
        user = self.scope["user"]

        if not user.is_authenticated:
            await self.close()
            return

        # Join the group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Notify group of user joining
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_status",
                "event": "joined",
                "username": user.username,
            },
        )

    async def disconnect(self, close_code):
        user = self.scope["user"]
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        # Notify group user left
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_status",
                "event": "left",
                "username": user.username,
            },
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        event_type = data.get("type")
        user = self.scope["user"]

        if event_type == "typing":
            await self.handle_typing(user)
        elif event_type == "read":
            await self.handle_read(user, data)
        elif event_type == "message":
            await self.handle_message(user, data)

    # Typing Indicator
    async def handle_typing(self, user):
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "typing_event", "username": user.username},
        )

    async def typing_event(self, event):
        await self.send(
            text_data=json.dumps({"type": "typing", "username": event["username"]})
        )

    # New Message (Sent + Delivered)
    async def handle_message(self, user, data):
        message_text = data.get("message")

        conversation = await sync_to_async(Conversation.objects.get)(
            id=self.conversation_id
        )

        if not await sync_to_async(
            conversation.participants.filter(id=user.id).exists
        )():
            await self.send_json({"error": "Not a participant"})
            return

        # Create message (Sent)
        message = await sync_to_async(ConversationMessage.objects.create)(
            conversation=conversation, sender=user, content=message_text
        )

        # Mark delivered to all current participants except sender
        participants = await sync_to_async(list)(
            conversation.participants.exclude(id=user.id)
        )
        for p in participants:
            await sync_to_async(message.delivered_to.add)(p)

        serialized = ConversationMessageSerializer(message)
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "chat_message", "message": serialized.data},
        )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "data": event["message"],
                }
            )
        )

    # 🟢 Read Receipt (Mark as Read)
    async def handle_read(self, user, data):
        message_id = data.get("message_id")

        message = await sync_to_async(ConversationMessage.objects.get)(id=message_id)
        await sync_to_async(message.read_by.add)(user)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "read_receipt_event",
                "message_id": message_id,
                "username": user.username,
            },
        )

    async def read_receipt_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "read_receipt",
                    "message_id": event["message_id"],
                    "username": event["username"],
                }
            )
        )

    # User Status Events
    async def user_status(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "status",
                    "event": event["event"],
                    "username": event["username"],
                }
            )
        )


class CommentConsumer(AsyncWebsocketConsumer):
    """Handles live comments and replies per post."""

    async def connect(self):
        self.post_id = self.scope["url_route"]["kwargs"]["post_id"]
        self.room_group_name = f"comments_{self.post_id}"

        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "status_event",
                "event": "joined",
                "username": user.username,
            },
        )

    async def disconnect(self, close_code):
        user = self.scope["user"]
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "status_event",
                "event": "left",
                "username": user.username,
            },
        )

    # RECEIVE EVENTS
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")
        user = self.scope["user"]

        if action == "new_comment":
            await self.handle_new_comment(user, data)
        elif action == "new_reply":
            await self.handle_new_reply(user, data)
        elif action == "typing":
            await self.handle_typing(user)

    # COMMENT HANDLERS
    async def handle_new_comment(self, user, data):
        content = data.get("content")
        if not content:
            return

        comment = await self.save_comment(user, content, parent_id=None)
        serialized = await self.serialize_comment(comment)

        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "broadcast_comment", "comment": serialized},
        )

    async def handle_new_reply(self, user, data):
        parent_id = data.get("parent_id")
        content = data.get("content")
        if not parent_id or not content:
            return

        comment = await self.save_comment(user, content, parent_id)
        serialized = await self.serialize_comment(comment)

        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "broadcast_reply", "comment": serialized},
        )

    async def handle_typing(self, user):
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "typing_event", "username": user.username},
        )

    # SEND EVENTS
    async def broadcast_comment(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "new_comment",
                    "comment": event["comment"],
                }
            )
        )

    async def broadcast_reply(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "new_reply",
                    "comment": event["comment"],
                }
            )
        )

    async def typing_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "typing",
                    "username": event["username"],
                }
            )
        )

    async def status_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "status",
                    "event": event["event"],
                    "username": event["username"],
                }
            )
        )

    # DB HELPERS
    @database_sync_to_async
    def save_comment(self, user, content, parent_id):
        post = (
            Post.objects.filter(id=self.post_id)
            .filter(visible_posts_for_user(user))
            .first()
        )

        if not post:
            raise PermissionError("Cannot comment on this post")

        parent = (
            Comment.objects.filter(id=parent_id, post=post).first()
            if parent_id
            else None
        )

        return Comment.objects.create(
            author=user,
            post=post,
            content=content,
            parent=parent,
        )

    @database_sync_to_async
    def serialize_comment(self, comment):
        return CommentSerializer(comment).data
