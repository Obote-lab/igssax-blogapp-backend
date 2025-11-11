import asyncio
import json

import redis
from channels.layers import get_channel_layer


# This task runs in the background, subscribing to Redis channels
async def redis_event_listener():
    channel_layer = get_channel_layer()
    redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    pubsub = redis_client.pubsub()
    pubsub.subscribe("global_stream_updates")  # listen to all stream updates

    print("🔌 Redis listener started for global_stream_updates")

    # Infinite loop: listen and forward messages
    for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                stream_id = data.get("stream_id")
                if not stream_id:
                    continue

                # Broadcast to stream WebSocket group
                await channel_layer.group_send(
                    f"stream_{stream_id}",
                    {
                        "type": "redis_message",
                        "data": data,
                    },
                )
            except Exception as e:
                print(f"Error processing Redis message: {e}")
