# reactions/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.contenttypes.models import ContentType
from posts.models import Post
from comments.models import Comment
from .models import Reaction
from .api.serializers import ReactionSerializer
from .utils.cache_utils import get_reaction_summary_cached


class ReactionConsumer(AsyncWebsocketConsumer):
    """
    Handles live reaction broadcasts per post.
    Integrates with Reaction model and cache.
    """

    async def connect(self):
        self.post_id = self.scope["url_route"]["kwargs"]["post_id"]
        self.room_group_name = f"reactions_{self.post_id}"

        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")
        user = self.scope["user"]

        if action == "toggle":
            await self.handle_toggle(user, data)

  
    # 🔁 Core Logic
    async def handle_toggle(self, user, data):
        reaction_type = data.get("reaction_type", "like")
        comment_id = data.get("comment")
        post_id = int(data.get("post", self.post_id))

        model_class = Comment if comment_id else Post
        obj_id = int(comment_id or post_id)

        ct = await database_sync_to_async(ContentType.objects.get_for_model)(model_class)
        existing = await database_sync_to_async(
            Reaction.objects.filter(user=user, content_type=ct, object_id=obj_id).first
        )()

        if existing:
            if existing.reaction_type == reaction_type:
                await database_sync_to_async(existing.delete)()
                await self.broadcast_summary(model_class, obj_id)
                await self.broadcast_event("removed", reaction_type, obj_id)
                return
            existing.reaction_type = reaction_type
            await database_sync_to_async(existing.save)()
            await self.broadcast_summary(model_class, obj_id)
            await self.broadcast_event("updated", reaction_type, obj_id)
            return

        # Create new reaction
        await database_sync_to_async(Reaction.objects.create)(
            user=user, reaction_type=reaction_type, content_type=ct, object_id=obj_id
        )
        await self.broadcast_summary(model_class, obj_id)
        await self.broadcast_event("created", reaction_type, obj_id)

  
    # 📡 Broadcast helpers
    async def broadcast_event(self, event_type, reaction_type, obj_id):
        """Notify all clients viewing this post/comment."""
        payload = {
            "type": "reaction_event",
            "event": event_type,
            "reaction_type": reaction_type,
            "object_id": obj_id,
        }
        await self.channel_layer.group_send(self.room_group_name, payload)

    async def reaction_event(self, event):
        await self.send(text_data=json.dumps(event))

    async def broadcast_summary(self, model_class, obj_id):
        """Send updated reaction summary to all clients."""
        summary = await database_sync_to_async(get_reaction_summary_cached)(
            model_class, obj_id
        )
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "reaction_summary",
                "object_id": obj_id,
                "summary": summary,
                "total": sum(summary.values()),
            },
        )

    async def reaction_summary(self, event):
        await self.send(text_data=json.dumps(event))
