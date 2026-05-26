from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from app.redis.client import RedisManager

router = Router()


@router.message(Command("health"))
async def health_handler(message: Message, redis_manager: RedisManager):
    redis_status = (
        "connected" if await redis_manager.is_healthy() else "disconnected"
    )

    text = (
        "🩺 <b>FastSaver Health Status</b>\n\n"
        f"• status: ok\n"
        f"• redis: {redis_status}\n"
        f"• bot: alive"
    )
    await message.answer(text)
