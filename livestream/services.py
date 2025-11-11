import json
import logging
import redis
from django.conf import settings
from django.utils import timezone
from .models import LiveStream
from livestream.utils.redis_client import get_redis_client



logger = logging.getLogger(__name__)


class StreamNotificationService:
    def __init__(self):
        self.redis_client = get_redis_client(0)
        try:
            self.redis_client = redis.Redis(
                host=getattr(settings, "REDIS_HOST", "localhost"),
                port=getattr(settings, "REDIS_PORT", 6379),
                db=getattr(settings, "REDIS_DB", 0),
                decode_responses=True,  # Automatically decode responses to strings
            )
            # Test connection
            self.redis_client.ping()
        except redis.ConnectionError as e:
            logger.warning(
                f"Redis connection failed: {e}. Notifications will not work."
            )
            self.redis_client = None

    def notify_stream_started(self, stream):
        """Notify followers when a stream starts"""
        if not self.redis_client:
            return

        try:
            notification_data = {
                "type": "stream_started",
                "stream_id": str(stream.id),
                "streamer_id": str(stream.streamer.id),
                "streamer_name": stream.streamer.username()
                or stream.streamer.email,
                "title": stream.title,
                "thumbnail": stream.thumbnail.url if stream.thumbnail else None,
                "started_at": (
                    stream.started_at.isoformat() if stream.started_at else None
                ),
                "category": stream.category,
                "viewer_count": stream.viewer_count,
            }

            # Publish to multiple channels for different use cases
            channels = [
                f"user_{stream.streamer.id}_followers",  # Followers notifications
                "global_stream_updates",  # Global stream updates
                f"stream_{stream.id}",  # Stream-specific updates
            ]

            for channel in channels:
                self.redis_client.publish(channel, json.dumps(notification_data))

            logger.info(f"Stream started notification sent for stream {stream.id}")

        except Exception as e:
            logger.error(f"Failed to send stream started notification: {e}")

    def notify_stream_ended(self, stream):
        """Notify viewers when a stream ends"""
        if not self.redis_client:
            return

        try:
            notification_data = {
                "type": "stream_ended",
                "stream_id": str(stream.id),
                "streamer_id": str(stream.streamer.id),
                "streamer_name": stream.streamer.get_full_name()
                or stream.streamer.email,
                "title": stream.title,
                "ended_at": stream.ended_at.isoformat() if stream.ended_at else None,
                "duration": str(stream.duration) if stream.duration else None,
                "peak_viewers": stream.peak_viewers,
                "total_views": stream.total_views,
            }

            channels = [
                f"stream_{stream.id}",
                "global_stream_updates",
                f"user_{stream.streamer.id}_followers",
            ]

            for channel in channels:
                self.redis_client.publish(channel, json.dumps(notification_data))

            logger.info(f"Stream ended notification sent for stream {stream.id}")

        except Exception as e:
            logger.error(f"Failed to send stream ended notification: {e}")

    def notify_new_message(self, message):
        """Notify about new chat messages"""
        if not self.redis_client:
            return

        try:
            notification_data = {
                "type": "new_message",
                "message_id": str(message.id),
                "stream_id": str(message.stream.id),
                "user_id": str(message.user.id),
                "user_name": message.user.get_full_name() or message.user.email,
                "content": message.content,
                "message_type": message.message_type,
                "timestamp": message.timestamp.isoformat(),
            }

            self.redis_client.publish(
                f"stream_{message.stream.id}_chat", json.dumps(notification_data)
            )

        except Exception as e:
            logger.error(f"Failed to send message notification: {e}")

    def get_live_streams_count(self):
        """Get count of currently live streams"""
        return LiveStream.objects.filter(status=LiveStream.StreamStatus.LIVE).count()

    def get_trending_streams(self, limit=10):
        """Get trending live streams based on viewer count"""
        return LiveStream.objects.filter(status=LiveStream.StreamStatus.LIVE).order_by(
            "-viewer_count"
        )[:limit]

    def get_redis_stats(self):
        """Get Redis connection statistics"""
        if not self.redis_client:
            return {"error": "Redis not connected"}

        try:
            return {
                "connected_clients": self.redis_client.info("clients")[
                    "connected_clients"
                ],
                "used_memory": self.redis_client.info("memory")["used_memory_human"],
                "connected": True,
            }
        except Exception as e:
            return {"error": str(e), "connected": False}


class StreamHealthService:
    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=getattr(settings, "REDIS_HOST", "localhost"),
                port=getattr(settings, "REDIS_PORT", 6379),
                db=getattr(settings, "REDIS_DB", 0),
                decode_responses=True,
            )
            self.redis_client.ping()
        except redis.ConnectionError as e:
            logger.warning(
                f"Redis connection failed: {e}. Health monitoring will not work."
            )
            self.redis_client = None

    def update_stream_health(self, stream_id, health_data):
        """Update stream health metrics"""
        if not self.redis_client:
            return

        try:
            key = f"stream_health_{stream_id}"
            health_data["last_updated"] = timezone.now().isoformat()
            health_data["stream_id"] = str(stream_id)

            self.redis_client.setex(
                key, 60, json.dumps(health_data)
            )  # Expire in 60 seconds

            # Also store in a sorted set for health monitoring
            health_score = self._calculate_health_score(health_data)
            self.redis_client.zadd(
                "stream_health_scores", {str(stream_id): health_score}
            )

        except Exception as e:
            logger.error(f"Failed to update stream health: {e}")

    def _calculate_health_score(self, health_data):
        """Calculate a health score from 0-100 based on stream metrics"""
        score = 100

        # Deduct points for high error rates
        error_rate = health_data.get("error_rate", 0)
        if error_rate > 0.1:  # 10% error rate
            score -= 30
        elif error_rate > 0.05:  # 5% error rate
            score -= 15

        # Deduct points for high buffering
        buffering_ratio = health_data.get("buffering_ratio", 0)
        if buffering_ratio > 0.1:  # 10% buffering
            score -= 20
        elif buffering_ratio > 0.05:  # 5% buffering
            score -= 10

        # Deduct points for low bitrate
        bitrate = health_data.get("average_bitrate", 0)
        if bitrate < 500:  # Very low bitrate
            score -= 20
        elif bitrate < 1000:  # Low bitrate
            score -= 10

        return max(0, score)

    def get_stream_health(self, stream_id):
        """Get stream health metrics"""
        if not self.redis_client:
            return None

        try:
            key = f"stream_health_{stream_id}"
            data = self.redis_client.get(key)
            if data:
                health_data = json.loads(data)
                health_data["health_score"] = (
                    self.redis_client.zscore("stream_health_scores", str(stream_id))
                    or 0
                )
                return health_data
            return None
        except Exception as e:
            logger.error(f"Failed to get stream health: {e}")
            return None

    def get_unhealthy_streams(self, threshold=70):
        """Get streams with health score below threshold"""
        if not self.redis_client:
            return []

        try:
            unhealthy = self.redis_client.zrangebyscore(
                "stream_health_scores", 0, threshold
            )
            return [stream_id for stream_id in unhealthy]
        except Exception as e:
            logger.error(f"Failed to get unhealthy streams: {e}")
            return []

    def check_inactive_streams(self):
        """Check for streams that might have crashed"""
        if not self.redis_client:
            return

        inactive_threshold = timezone.now() - timezone.timedelta(minutes=5)

        inactive_streams = LiveStream.objects.filter(
            status=LiveStream.StreamStatus.LIVE, updated_at__lt=inactive_threshold
        )

        for stream in inactive_streams:
            logger.warning(
                f"Auto-ending inactive stream: {stream.title} (ID: {stream.id})"
            )

            # Auto-end streams that haven't been updated in 5 minutes
            stream.status = LiveStream.StreamStatus.ENDED
            stream.ended_at = timezone.now()
            if stream.started_at:
                stream.duration = stream.ended_at - stream.started_at
            stream.save()

    def cleanup_old_health_data(self):
        """Clean up old health data from Redis"""
        if not self.redis_client:
            return

        try:
            # Remove health data older than 1 hour
            old_streams = self.redis_client.keys("stream_health_*")
            for key in old_streams:
                # Check if the stream is still active
                stream_id = key.replace("stream_health_", "")
                if not LiveStream.objects.filter(
                    id=stream_id, status=LiveStream.StreamStatus.LIVE
                ).exists():
                    self.redis_client.delete(key)

        except Exception as e:
            logger.error(f"Failed to cleanup old health data: {e}")


# services.py - Add rate limiting


class RateLimitService:
    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=getattr(settings, "REDIS_HOST", "localhost"),
                port=getattr(settings, "REDIS_PORT", 6379),
                db=getattr(settings, "REDIS_DB", 1),  # Different DB for rate limiting
                decode_responses=True,
            )
        except redis.ConnectionError:
            self.redis_client = None

    def check_rate_limit(self, key, limit, window):
        """Check if rate limit is exceeded"""
        if not self.redis_client:
            return True

        try:
            current = self.redis_client.get(key)
            if current and int(current) >= limit:
                return False

            pipeline = self.redis_client.pipeline()
            pipeline.incr(key, 1)
            pipeline.expire(key, window)
            pipeline.execute()
            return True
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return True

    def get_remaining_requests(self, key, limit):
        """Get remaining requests"""
        if not self.redis_client:
            return limit

        try:
            current = self.redis_client.get(key)
            return max(0, limit - (int(current) if current else 0))
        except Exception as e:
            logger.error(f"Failed to get remaining requests: {e}")
            return limit



