import logging
from redis.asyncio import Redis, ConnectionError

logger = logging.getLogger(__name__)


class RedisManager:
    """
    Manager for the async Redis client, handling connection lifecycle and health checks.
    """

    def __init__(self, url: str):
        self.url = url
        self.client: Redis | None = None

    def connect(self) -> Redis:
        if self.client is None:
            logger.info("🔌 Connecting to Redis...")
            self.client = Redis.from_url(self.url, decode_responses=True)
        return self.client

    async def disconnect(self):
        if self.client:
            logger.info("🛑 Disconnecting from Redis...")
            await self.client.aclose()
            self.client = None

    async def is_healthy(self) -> bool:
        if self.client is None:
            return False
        try:
            await self.client.ping()
            return True
        except ConnectionError as e:
            logger.error(f"Redis connection health check failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            return False
