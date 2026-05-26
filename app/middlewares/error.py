import logging
import traceback
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
    """
    Middleware to catch exceptions globally, log traceback internally,
    and respond to the user with a generic safe error message to prevent crashes.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            # Log full traceback internally
            logger.error(
                "CRITICAL ERROR ENCOUNTERED: %s\n%s",
                e,
                traceback.format_exc(),
            )

            # Inform user with a safe message
            try:
                safe_msg = "💥 Kechirasiz, xatolik yuz berdi. Iltimos, birozdan so‘ng qayta urunib ko‘ring."
                if isinstance(event, Message):
                    await event.answer(safe_msg)
                elif hasattr(event, "message") and event.message:
                    await event.message.answer(safe_msg)
            except Exception as send_err:
                logger.error("Could not send error message to user: %s", send_err)

            # Absorb error, returning None so bot does not crash
            return None
