# livestream/utils/redis_client.py
import redis
from django.conf import settings

def get_redis_client(db=0):
    return redis.Redis(
        host=getattr(settings, "REDIS_HOST", "localhost"),
        port=getattr(settings, "REDIS_PORT", 6379),
        db=db,
        decode_responses=True,
    )
