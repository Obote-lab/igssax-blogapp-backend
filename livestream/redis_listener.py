import asyncio
import json

import redis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


async def redis_event_listener():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_redis_listener)


def _blocking_redis_listener():
    channel_layer = get_channel_layer()
    redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

    pubsub = redis_client.pubsub()
    pubsub.subscribe("global_stream_updates")

    for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            stream_id = data.get("stream_id")
            if not stream_id:
                continue

            async_to_sync(channel_layer.group_send)(
                f"stream_{stream_id}",
                {"type": "redis_message", "data": data},
            )
