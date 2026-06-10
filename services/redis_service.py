import os
import json
import time
import logging
import redis
import redis.exceptions
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class RedisService:
    """Pub/sub subscriber for ai-worker events. Yields parsed event dicts from the configured channel."""

    def __init__(self):
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.channel = os.getenv('REDIS_CHANNEL', 'ai-worker:events')
        self._client = None
        self._pubsub = None

    def _connect(self):
        # socket_timeout=None keeps the listen() call blocking indefinitely
        # so read timeouts don't look like connection errors
        self._client = redis.from_url(self.redis_url, decode_responses=True, socket_timeout=None)
        self._client.ping()
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        self._pubsub.subscribe(self.channel)
        logger.info(f"Subscribed to Redis channel: {self.channel}")

    def listen(self):
        """Yield parsed event dicts. Blocks until a message arrives. Reconnects on error."""
        while True:
            try:
                if self._pubsub is None:
                    self._connect()
                for raw in self._pubsub.listen():
                    if raw and raw.get('type') == 'message':
                        try:
                            yield json.loads(raw['data'])
                        except (json.JSONDecodeError, KeyError):
                            logger.warning(f"Received non-JSON Redis message: {raw.get('data')}")
            except redis.exceptions.TimeoutError:
                pass  # socket read timed out with no message — not a real error, keep listening
            except Exception as e:
                logger.error(f"Redis connection error: {e}. Reconnecting in 5s...")
                self._reset()
                time.sleep(5)

    def _reset(self):
        try:
            if self._pubsub:
                self._pubsub.close()
        except Exception:
            pass
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        self._pubsub = None
        self._client = None

    def close(self):
        self._reset()
