from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from cache import get_cached_media, cache_media, get_cached_video, cache_video
import logging
import os
import shutil
from pathlib import Path

from aiogram import F, Router, exceptions, types
from aiogram.filters import Command, CommandStart
from dotenv import load_dotenv

from enums import Links, ProgressState, VideoStatusMessages
from utils import (VIDEOS_DIR, download_video, download_audio, format_bytes, format_message,
                   format_time, extract_youtube_id, fetch_youtube_info)

router = Router()
load_dotenv()

# Local Bot API supports up to 2000 MB (2 GB)
MAX_TELEGRAM_SIZE = 2000 * 1024 * 1024
FILES_URL = os.getenv("FILES_URL")


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _size(n: int) -> str:
    return format_bytes(n).replace(".0 ", " ")


def build_youtube_card(info: dict, vid: str):
    """Info card: title, channel, duration, real size per quality + action buttons."""
    lines = [f"🎬 <b>{_esc(info['title'])}</b>"]
    meta = []
    if info.get("channel"):
        meta.append(f"👤 {_esc(info['channel'])}")
    if info.get("duration"):
        meta.append(f"⏱ {format_time(info['duration'])}")
    if info.get("views"):
        meta.append("👁 " + f"{info['views']:,}".replace(",", " "))
    if meta:
        lines.append(" · ".join(meta))
    lines.append("")

    sizes = info["sizes"]
    for height, size in sizes.items():
        lines.append(f"▫️ <code>{height}p</code> — {_size(size)}")
    if info.get("audio_size"):
        lines.append(f"▫️ <code>MP3</code> — {_size(info['audio_size'])}")
    lines.append("")
    lines.append("👇 <b>Sifatni tanlang</b>")

    icons = {144: "🪶", 240: "🪶", 360: "⚡", 480: "📱", 720: "🔥", 1080: "💎", 1440: "👑", 2160: "👑"}
    heights = list(sizes) or [360, 720]
    kb = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(
            text=f"{icons.get(h, '🎞')} {h}p · {_size(sizes[h])}" if h in sizes else f"{icons.get(h, '🎞')} {h}p",
            callback_data=f"dl:{h}:{vid}",
        )
        for h in heights
    ]
    for i in range(0, len(buttons), 2):
        kb.row(*buttons[i:i + 2])
    kb.row(
        InlineKeyboardButton(text="🎧 MP3", callback_data=f"dl:audio:{vid}"),
        InlineKeyboardButton(text="🖼 Muqova", callback_data=f"dl:cover:{vid}"),
    )
    if info.get("channel_url"):
        kb.row(InlineKeyboardButton(text="📺 Kanalga o'tish", url=info["channel_url"]))
    return "\n".join(lines), kb.as_markup()


@router.message(F.text.startswith(tuple(Links.STANDART.value)))
async def handle_standart_download(message: types.Message):
    url = message.text.strip()
    if not url:
        return

    await message.react([types.reaction_type_emoji.ReactionTypeEmoji(emoji="👀")])

    # 1. Check Redis cache for instant 0.5s response (if already fetched before)
    cached = await get_cached_media(url)
    if cached and cached.get("file_id"):
        caption = VideoStatusMessages.Caption.value.format(url=url)
        await message.answer_video(
            video=cached["file_id"],
            caption=caption,
            width=cached.get("width", 0),
            height=cached.get("height", 0),
            duration=cached.get("duration", 0),
        )
        await message.delete()
        return

    # YouTube video: rich info card with real sizes per quality
    is_yt = any(domain in url.lower() for domain in ["youtube.com", "youtu.be"])
    vid = extract_youtube_id(url) if is_yt else None
    if vid and "/shorts/" not in url.lower():
        wait = await message.answer("🔎 Video ma'lumotlari olinmoqda...")
        try:
            info = await fetch_youtube_info(url)
        except Exception as e:
            logging.exception(f"Info fetch failed: {e}")
            await wait.delete()
            await message.reply(VideoStatusMessages.VideoError.value)
            return
        await wait.delete()
        text, markup = build_youtube_card(info, vid)
        try:
            if info.get("thumbnail"):
                await message.answer_photo(info["thumbnail"], caption=text, reply_markup=markup)
            else:
                await message.answer(text, reply_markup=markup)
        except exceptions.TelegramBadRequest:
            await message.answer(text, reply_markup=markup)
        return

    # For Shorts, Reels, TikTok - direct instant download
    msg = await message.answer(format_message(ProgressState.PREPARING))
    try:
        info = await download_video(msg, url, quality="720")
        filename = info["filename"]
        duration = info.get("duration", 0)

        thumb_input = None
        if info.get("thumbnail") and os.path.exists(info["thumbnail"]):
            thumb_input = types.FSInputFile(info["thumbnail"])

        video_input = types.FSInputFile(filename, chunk_size=4 * 1024 * 1024)

        sent_msg = await message.answer_video(
            video=video_input,
            caption=(VideoStatusMessages.Caption.value.format(url=url)),
            width=info.get("width", 0),
            height=info.get("height", 0),
            duration=duration,
            thumbnail=thumb_input
        )

        if sent_msg and sent_msg.video:
            await cache_media(
                key=url,
                file_id=sent_msg.video.file_id,
                media_type="video",
                width=info.get("width", 0),
                height=info.get("height", 0),
                duration=duration,
                format_id=info.get("format_id"),
                resolution=f"{info.get('width', 0)}x{info.get('height', 0)}",
                filesize=info.get("filesize"),
                vcodec=info.get("vcodec"),
                acodec=info.get("acodec"),
                ext=info.get("ext", "mp4")
            )

        if info.get("thumbnail") and os.path.exists(info["thumbnail"]):
            try:
                os.remove(info["thumbnail"])
            except:
                pass

        # Telegram's file_id never expires, so the local copy is disposable once sent.
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass
    except Exception as e:
        logging.exception(f"Direct download failed: {e}")
        try:
            await msg.delete()
        except:
            pass
        await message.reply(VideoStatusMessages.VideoError.value)
    else:
        await msg.delete()
        await message.delete()


@router.callback_query(F.data.startswith("dl:"))
async def handle_quality_choice(callback: types.CallbackQuery):
    _, choice, vid = callback.data.split(":", 2)
    url = f"https://www.youtube.com/watch?v={vid}"
    message = callback.message
    await callback.answer()

    if choice == "cover":
        try:
            await callback.bot.send_photo(
                chat_id=message.chat.id,
                photo=f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
                caption=VideoStatusMessages.Caption.value.format(url=url),
            )
        except exceptions.TelegramBadRequest:
            await callback.bot.send_photo(
                chat_id=message.chat.id,
                photo=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                caption=VideoStatusMessages.Caption.value.format(url=url),
            )
        return

    # Progress goes into a separate message so the card stays usable for other qualities
    msg = await message.answer(format_message(ProgressState.PREPARING))

    cache_key = f"{url}#{choice}"

    try:
        # Check cache
        cached = await get_cached_media(cache_key)
        if cached and cached.get("file_id"):
            caption = VideoStatusMessages.Caption.value.format(url=url)
            if cached.get("media_type") == "audio":
                await callback.bot.send_audio(
                    chat_id=callback.from_user.id,
                    audio=cached["file_id"],
                    caption=caption,
                    title=cached.get("title"),
                    performer=cached.get("performer"),
                    duration=cached.get("duration", 0),
                )
            else:
                await callback.bot.send_video(
                    chat_id=callback.from_user.id,
                    video=cached["file_id"],
                    caption=caption,
                    width=cached.get("width", 0),
                    height=cached.get("height", 0),
                    duration=cached.get("duration", 0),
                )
            await msg.delete()
            return

        # Audio choice
        if choice == "audio":
            info = await download_audio(msg, url)
            filename = info["filename"]
            duration = info.get("duration", 0)

            thumb_input = None
            if info.get("thumbnail") and os.path.exists(info["thumbnail"]):
                thumb_input = types.FSInputFile(info["thumbnail"])

            audio_input = types.FSInputFile(filename, chunk_size=4 * 1024 * 1024)

            sent_msg = await callback.bot.send_audio(
                chat_id=callback.from_user.id,
                audio=audio_input,
                caption=(VideoStatusMessages.Caption.value.format(url=url)),
                duration=duration,
                title=info.get("title"),
                performer=info.get("performer"),
                thumbnail=thumb_input
            )

            if sent_msg and sent_msg.audio:
                await cache_media(
                    key=cache_key,
                    file_id=sent_msg.audio.file_id,
                    media_type="audio",
                    duration=duration,
                    title=info.get("title"),
                    performer=info.get("performer"),
                    format_id=info.get("format_id"),
                    filesize=info.get("filesize"),
                    ext=info.get("ext", "m4a")
                )

            if info.get("thumbnail") and os.path.exists(info["thumbnail"]):
                try:
                    os.remove(info["thumbnail"])
                except:
                    pass

            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except:
                    pass
        else:
            # Video choice (360p or 720p)
            info = await download_video(msg, url, quality=choice)
            filename = info["filename"]
            duration = info.get("duration", 0)

            thumb_input = None
            if info.get("thumbnail") and os.path.exists(info["thumbnail"]):
                thumb_input = types.FSInputFile(info["thumbnail"])

            video_input = types.FSInputFile(filename, chunk_size=4 * 1024 * 1024)

            sent_msg = await callback.bot.send_video(
                chat_id=callback.from_user.id,
                video=video_input,
                caption=(VideoStatusMessages.Caption.value.format(url=url)),
                width=info.get("width", 0),
                height=info.get("height", 0),
                duration=duration,
                thumbnail=thumb_input
            )

            if sent_msg and sent_msg.video:
                await cache_media(
                    key=cache_key,
                    file_id=sent_msg.video.file_id,
                    media_type="video",
                    width=info.get("width", 0),
                    height=info.get("height", 0),
                    duration=duration,
                    format_id=info.get("format_id"),
                    resolution=f"{info.get('width', 0)}x{info.get('height', 0)}",
                    filesize=info.get("filesize"),
                    vcodec=info.get("vcodec"),
                    acodec=info.get("acodec"),
                    ext=info.get("ext", "mp4")
                )

            if info.get("thumbnail") and os.path.exists(info["thumbnail"]):
                try:
                    os.remove(info["thumbnail"])
                except:
                    pass

            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except:
                    pass

    except Exception as e:
        logging.exception(f"Download choice failed: {e}")
        try:
            await msg.delete()
        except:
            pass
        await message.reply(VideoStatusMessages.VideoError.value)
    else:
        await msg.delete()


@router.message(Command("stats"))
async def stats(message: types.Message):
    if message.from_user.id != int(os.getenv("ADMIN_ID", 0)):
        return

    counts = {}
    total_size = 0
    total_files = 0

    for file in VIDEOS_DIR.rglob("*"):
        if file.is_file():
            total_files += 1
            total_size += file.stat().st_size
            counts[file.suffix or "[none]"] = counts.get(file.suffix or "[none]", 0) + 1

    disk = shutil.disk_usage("/")
    text = [
        "<b>Videolar:</b>",
        f"Fayllar: {total_files}",
        f"Hajm: {format_bytes(total_size)}",
        "",
        "<b>Formatlar:</b>",
    ]

    for ext, count in sorted(counts.items()):
        text.append(f"{ext}: {count}")

    text += [
        "",
        "<b>Xotira:</b>",
        f"Ishlatilgan: {format_bytes(disk.used)} / {format_bytes(disk.total)}",
        f"Bo'sh: {format_bytes(disk.free)}",
    ]
    await message.answer("\n".join(text))


@router.message(Command("clean"))
async def clean(message: types.Message):
    if message.from_user.id != int(os.getenv("ADMIN_ID", 0)):
        return

    deleted = 0
    for file in filter(Path.is_file, VIDEOS_DIR.rglob("*")):
        file.unlink()
        deleted += 1

    await message.answer(f"{deleted} ta fayl o'chirildi.")


@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        f"Assalomu alaykum, @{message.from_user.username or message.from_user.first_name}!\n\n"
        "Yuklab olmoqchi bo'lgan video havolasini yuboring (YouTube, TikTok, Instagram, Twitter, Facebook).\n\n"
        "⚡ Tezkor va qulay yuklab olish xizmati!",
    )