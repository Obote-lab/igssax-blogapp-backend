import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Handles real-time notifications for authenticated users.
    Uses `user_<id>` group for delivery.
    """

    async def connect(self):
        user = self.scope["user"]
        if user.is_anonymous:
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
        Notification.objects.filter(id=notif_id, recipient=self.user).update(is_read=True)

    async def send_notification(self, event):
        await self.send(json.dumps({"type": "notification", "content": event["content"]}))



















# import json

# from channels.generic.websocket import AsyncWebsocketConsumer


# class NotificationConsumer(AsyncWebsocketConsumer):
#     """
#     Handles real-time delivery of user notifications over WebSocket.
#     Each user connects to a group named `user_<user_id>`.
#     """

#     async def connect(self):
#         # Extract the user_id from the URL
#         self.user_id = self.scope["url_route"]["kwargs"]["user_id"]
#         self.group_name = f"user_{self.user_id}"

#         # Add this connection to the user's group
#         await self.channel_layer.group_add(self.group_name, self.channel_name)

#         await self.accept()

#         # Optionally confirm connection
#         await self.send(
#             json.dumps(
#                 {
#                     "type": "connection_established",
#                     "message": f"Connected to notifications for user {self.user_id}",
#                 }
#             )
#         )

#     async def disconnect(self, close_code):
#         # Remove connection from group on disconnect
#         await self.channel_layer.group_discard(self.group_name, self.channel_name)

#     async def receive(self, text_data):
#         """
#         Handle incoming messages from frontend WebSocket.
#         Usually, clients don't send data here, but you can
#         extend this for read receipts or other actions.
#         """
#         data = json.loads(text_data)
#         action = data.get("action")

#         if action == "ping":
#             await self.send(json.dumps({"type": "pong"}))

#     async def send_notification(self, event):
#         """
#         Called by create_notification() through group_send().
#         """
#         await self.send(
#             json.dumps(
#                 {
#                     "type": "notification",
#                     "content": event["content"],
#                 }
#             )
#         )
