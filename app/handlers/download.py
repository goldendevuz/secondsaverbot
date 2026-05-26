import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from app.enums import Links
from app.services.download import DownloadService

router = Router()
logger = logging.getLogger(__name__)

FRAMES = [
    "⏳ Yuklanmoqda...",
    "⏳ Yuklanmoqda ▰▱▱▱",
    "⏳ Yuklanmoqda ▰▰▱▱",
    "⏳ Yuklanmoqda ▰▰▰▱",
    "⏳ Yuklanmoqda ▰▰▰▰",
]


async def loading_loop(
    bot: Bot, chat_id: int, message_id: int, stop: asyncio.Event
):
    i = 0
    while not stop.is_set():
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=FRAMES[i % len(FRAMES)],
            )
        except Exception:
            pass
        i += 1
        await asyncio.sleep(0.5)


async def process_download(
    message: Message, bot: Bot, download_service: DownloadService
):
    chat_id = message.chat.id
    text = (message.text or "").strip()

    msg = await bot.send_message(chat_id=chat_id, text="⏳ Boshlanmoqda...")
    stop = asyncio.Event()
    loader = asyncio.create_task(
        loading_loop(bot, chat_id, msg.message_id, stop)
    )

    try:
        # Delegate business logic to the service
        data = await download_service.fetch_download_data(text)

        stop.set()
        await loader

        if not data or data.get("error"):
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg.message_id,
                text="❌ Video topilmadi",
            )
            return

        video_url = data.get("video_url")
        if not video_url:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg.message_id,
                text="❌ URL yo‘q",
            )
            return

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text="📥 Yuklab olinmoqda...",
        )

        # Delegate local download, file sending, and cleanup to service
        await download_service.send_video_safely(
            bot=bot,
            chat_id=chat_id,
            video_url=video_url,
            caption=data.get("caption") or "📥 Tayyor",
            business_connection_id=message.business_connection_id,
        )

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text="🎉 Tayyor!",
        )

    except Exception as e:
        stop.set()
        await loader
        logger.error(
            "Error processing download in handler: %s", e, exc_info=True
        )
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text="💥 Xatolik yuz berdi",
        )


@router.message(F.text.startswith(tuple(Links.STANDART.value)))
async def download_private(
    message: Message, bot: Bot, download_service: DownloadService
):
    await process_download(message, bot, download_service)


@router.business_message(F.text.startswith(tuple(Links.STANDART.value)))
async def download_business(
    message: Message, bot: Bot, download_service: DownloadService
):
    await process_download(message, bot, download_service)
