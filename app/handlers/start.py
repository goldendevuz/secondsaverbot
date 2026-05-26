from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command

router = Router()


async def send_message_safe(bot: Bot, message: Message, text: str):
    """
    Private + Business safe message sender.
    """
    if message.business_connection_id:
        await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            business_connection_id=message.business_connection_id,
        )
    else:
        await message.answer(text)


@router.message(Command("start"))
async def start_handler(message: Message, bot: Bot):
    user = message.from_user
    is_premium = getattr(user, "is_premium", False)

    if is_premium:
        text = "🚀 Bot ishlamoqda 🚀\n\n✨ Siz Telegram Premium foydalanuvchisiz"
    else:
        text = "🚀 Bot ishlamoqda 🚀\n\n💡 Siz oddiy foydalanuvchisiz"

    await send_message_safe(bot, message, text)


@router.business_message(Command("start"))
async def business_start_handler(message: Message, bot: Bot):
    user = message.from_user
    is_premium = getattr(user, "is_premium", False)

    if is_premium:
        text = "🚀 Bot ishlamoqda 🚀\n\n✨ Siz Telegram Premium foydalanuvchisiz"
    else:
        text = "🚀 Bot ishlamoqda 🚀\n\n💡 Siz oddiy foydalanuvchisiz"

    await send_message_safe(bot, message, text)
