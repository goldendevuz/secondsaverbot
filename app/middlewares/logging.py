import time
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware for logging structured telemetry of incoming updates and their processing.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        event_type = type(event).__name__
        action = event_type

        # Extract user ID if present
        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id
        elif (
            hasattr(event, "message")
            and event.message
            and event.message.from_user
        ):
            user_id = event.message.from_user.id

        # Extract text or callback data for action naming
        if hasattr(event, "text") and event.text:
            action = f"{event_type}:{event.text[:30]}"
        elif hasattr(event, "data") and event.data:
            action = f"{event_type}:{event.data[:30]}"

        handler_name = "unknown"
        if "handler" in data:
            handler_name = data["handler"].callback.__name__

        start_time = time.perf_counter()
        error = None
        try:
            return await handler(event, data)
        except Exception as e:
            error = type(e).__name__
            raise e
        finally:
            latency = time.perf_counter() - start_time
            logger.info(
                "TELEMETRY | user_id: %s | handler: %s | action: %s | latency: %.4fs | error: %s",
                user_id,
                handler_name,
                action,
                latency,
                error or "None",
            )
