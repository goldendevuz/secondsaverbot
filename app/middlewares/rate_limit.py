import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """
    Middleware for Redis-backed rate limiting per user and action.
    """

    def __init__(self, redis_client: Redis, limit: int = 5, period: int = 10):
        self.redis = redis_client
        self.limit = limit
        self.period = period
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        # Detect action based on command or regular text (e.g. video links)
        action = "message"
        if event.text:
            if event.text.startswith("/"):
                action = event.text.split()[0].replace("/", "")
            else:
                action = "download"

        key = f"rate:{user_id}:{action}"

        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.period)

            if count > self.limit:
                logger.warning(
                    "Rate limit exceeded: user_id=%s, action=%s, count=%s",
                    user_id,
                    action,
                    count,
                )
                if count == self.limit + 1:
                    await event.answer(
                        "⚠️ Tezlik cheklovi: Iltimos, biroz kutib harakat qiling (10 soniyada ko‘pi bilan 5 ta so‘rov)."
                    )
                return  # Block request propagation

        except Exception as e:
            # Fail-safe: log Redis errors but let bot continue functioning
            logger.error("Rate limit check failed due to Redis error: %s", e)
            return await handler(event, data)

        return await handler(event, data)
