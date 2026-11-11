import asyncio
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import yt_dlp
from aiogram import types, exceptions
import aiohttp

from enums import ProgressState

VIDEOS_DIR = Path("videos")
VIDEOS_DIR.mkdir(exist_ok=True)

COOKIES_FILE = Path("/app/cookies.txt")


def get_video_metadata(filepath: str | Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams", "v:0",
        "-show_entries",
        "format=duration:stream=width,height,duration:stream_tags=rotate:stream_side_data=rotation",
        "-of",
        "json",
        str(filepath),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            duration = 0
            if "format" in data and "duration" in data["format"]:
                try:
                    duration = int(float(data["format"]["duration"]))
                except (ValueError, TypeError):
                    pass

            width, height = 0, 0
            for stream in data.get("streams", []):
                if stream.get("width") and stream.get("height"):
                    width = int(stream["width"])
                    height = int(stream["height"])
                    
                    rotation = 0
                    if "tags" in stream and "rotate" in stream["tags"]:
                        rotation = int(float(stream["tags"]["rotate"]))
                    elif "side_data_list" in stream:
                        for sd in stream["side_data_list"]:
                            if "rotation" in sd:
                                rotation = int(float(sd["rotation"]))
                    if abs(rotation) == 90 or abs(rotation) == 270:
                        width, height = height, width
                        
                    if not duration and stream.get("duration"):
                        try:
                            duration = int(float(stream["duration"]))
                        except (ValueError, TypeError):
                            pass
                    break

            return {"duration": duration, "width": width, "height": height}
    except Exception as e:
        print(f"Error extracting metadata with ffprobe for {filepath}: {e}")

    return {"duration": 0, "width": 0, "height": 0}


def format_bytes(value: int | float | None) -> str:
    if value is None:
        return "N/A"

    value = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{value:.1f} TB"


def format_time(seconds: int | None) -> str:
    if seconds is None:
        return "N/A"

    minutes, seconds = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02}:{seconds:02}"

    return f"{minutes:02}:{seconds:02}"


def get_percentage(data: dict) -> float:
    downloaded = data.get("downloaded_bytes", 0)
    total = data.get("total_bytes") or data.get("total_bytes_estimate")

    return downloaded / total * 100 if total else 0


def format_message(
    state: ProgressState,
    progress: float = 0,
) -> str:
    steps = [
        ProgressState.PREPARING,
        ProgressState.VIDEO_DOWNLOADING,
        ProgressState.AUDIO_DOWNLOADING,
        ProgressState.FINALIZING,
    ]

    lines = []

    for step in steps:
        if steps.index(step) < steps.index(state):
            lines.append(f"✅ {step.value}")
        elif step == state:
            if step in (
                ProgressState.VIDEO_DOWNLOADING,
                ProgressState.AUDIO_DOWNLOADING,
            ):
                lines.append(f"🔄 {step.value} ({progress:.1f}%)")
            else:
                lines.append(f"🔄 {step.value}")
        else:
            lines.append(f"⏳ {step.value}")

    return "\n".join(lines)


async def download_tiktok_video(msg: types.Message, url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://www.tikwm.com/api/?url={url}",
            headers={"User-Agent": "Mozilla/5.0"},
        ) as resp:
            data = await resp.json()

    if data.get("code") != 0 or "data" not in data:
        raise Exception("Failed to fetch TikTok data")

    video_url = data["data"]["play"]
    duration = int(data["data"].get("duration", 0))

    try:
        await msg.edit_text(format_message(ProgressState.FINALIZING))
    except exceptions.TelegramBadRequest:
        pass

    return {
        "filename": video_url,
        "width": 0,
        "height": 0,
        "duration": duration,
        "thumbnail": None
    }


async def download_video(msg: types.Message, url: str, quality: str = '720', clip: tuple[int, int] | None = None):
    if "tiktok.com" in url.lower():
        return await download_tiktok_video(msg, url)

    loop = asyncio.get_running_loop()
    last_update = [0.0]
    progress = [0.0]
    current_state = [ProgressState.VIDEO_DOWNLOADING]

    async def update_progress() -> None:
        await msg.edit_text(
            format_message(
                current_state[0],
                progress[0],
            )
        )

    def progress_hook(data):
        if data["status"] != "downloading":
            return

        info = data.get("info_dict", {})

        if info.get("vcodec") == "none":
            current_state[0] = ProgressState.AUDIO_DOWNLOADING
        else:
            current_state[0] = ProgressState.VIDEO_DOWNLOADING

        progress[0] = get_percentage(data)

        now = loop.time()
        if now - last_update[0] < 1:
            return

        last_update[0] = now

        asyncio.run_coroutine_threadsafe(
            update_progress(),
            loop,
        )

    def download():
        import tempfile

        video_id = str(uuid.uuid4())

        is_instagram = "instagram.com" in url.lower()
        if is_instagram:
            proxy_url = None
        else:
            proxy_url = os.getenv("PROXY_URL") or os.getenv("WARP_PROXY", "socks5://warp:9091")

        # Format selector for any target height (144/360/720/1080/...): merges video+audio
        h = int(quality) if str(quality).isdigit() else 720
        format_selector = (
            f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={h}]+bestaudio/"
            f"best[height<={h}][ext=mp4]/"
            f"best[height<={h}]/"
            "18/best"
        )

        options = {
            "format": format_selector,
            "merge_output_format": "mp4",
            "outtmpl": str(VIDEOS_DIR / f"{video_id}.%(ext)s"),
            "noplaylist": True,
            "proxy": proxy_url,
            "js_runtimes": {"quickjs": {"path": "/usr/bin/qjs"}} if shutil.which("qjs") else {},
            "concurrent_fragment_downloads": 16,
            "http_chunk_size": 10 * 1024 * 1024,
            "buffersize": 16 * 1024 * 1024,
            "writethumbnail": True,
            "progress_hooks": [progress_hook],
            "postprocessors": [],
        }

        if clip:
            from yt_dlp.utils import download_range_func
            options["download_ranges"] = download_range_func(None, [clip])
            options["force_keyframes_at_cuts"] = True

        # Copy cookies to a writable temp file if valid Netscape format
        tmp_cookies = None
        if not is_instagram and COOKIES_FILE.exists() and COOKIES_FILE.is_file() and COOKIES_FILE.stat().st_size > 10:
            cookie_text = COOKIES_FILE.read_text(encoding="utf-8").strip()
            if "# Netscape" in cookie_text or "\t" in cookie_text:
                tmp_cookies = tempfile.NamedTemporaryFile(
                    suffix=".txt", delete=False, mode="w", encoding="utf-8"
                )
                tmp_cookies.write(cookie_text + "\n")
                tmp_cookies.flush()
                tmp_cookies.close()
                options["cookiefile"] = tmp_cookies.name

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)

                # Find final file in case postprocessor changed extension to .mp4
                file_path = Path(downloaded_file)
                if not file_path.exists():
                    mp4_candidate = file_path.with_suffix(".mp4")
                    if mp4_candidate.exists():
                        file_path = mp4_candidate

                meta = get_video_metadata(file_path)

                width = meta["width"] or info.get("width", 0)
                height = meta["height"] or info.get("height", 0)
                raw_dur = info.get("duration")
                yt_duration = int(float(raw_dur)) if raw_dur is not None else 0
                duration = meta["duration"] or yt_duration

                thumb_path = None
                # Check if yt-dlp downloaded thumbnail
                for ext in [".jpg", ".webp", ".png", ".jpeg"]:
                    tp = file_path.with_suffix(ext)
                    if tp.exists() and tp.stat().st_size > 0:
                        thumb_path = tp
                        break

                # Ensure thumbnail is jpg and max 320px for Telegram
                if thumb_path and thumb_path.exists():
                    jpg_path = file_path.with_suffix(".thumb.jpg")
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(thumb_path),
                        "-vf", "scale='if(gt(iw,ih),320,-1)':'if(gt(iw,ih),-1,320)'",
                        "-q:v", "2", str(jpg_path)
                    ], capture_output=True)
                    if jpg_path.exists() and jpg_path.stat().st_size > 0:
                        if thumb_path != jpg_path:
                            thumb_path.unlink(missing_ok=True)
                        thumb_path = jpg_path
                    else:
                        thumb_path = None

                # If no thumbnail yet, generate directly from video file via ffmpeg (<0.1s)
                if not thumb_path or not thumb_path.exists():
                    gen_thumb = file_path.with_suffix(".thumb.jpg")
                    seek_time = "00:00:01.000" if duration > 2 else "00:00:00.000"
                    try:
                        subprocess.run([
                            "ffmpeg", "-y", "-ss", seek_time, "-i", str(file_path),
                            "-vframes", "1",
                            "-vf", "scale='if(gt(iw,ih),320,-1)':'if(gt(iw,ih),-1,320)'",
                            "-q:v", "2", str(gen_thumb)
                        ], capture_output=True, timeout=3)
                        if gen_thumb.exists() and gen_thumb.stat().st_size > 0:
                            thumb_path = gen_thumb
                    except Exception:
                        pass

                return {
                    "filename": str(file_path),
                    "width": width,
                    "height": height,
                    "duration": duration,
                    "thumbnail": str(thumb_path) if (thumb_path and thumb_path.exists()) else None,
                    "format_id": info.get("format_id"),
                    "filesize": file_path.stat().st_size if file_path.exists() else info.get("filesize"),
                    "vcodec": info.get("vcodec"),
                    "acodec": info.get("acodec"),
                    "ext": file_path.suffix.lstrip(".") or info.get("ext", "mp4"),
                }
        finally:
            if tmp_cookies:
                Path(tmp_cookies.name).unlink(missing_ok=True)

    info = await loop.run_in_executor(None, download)

    await msg.edit_text(format_message(ProgressState.FINALIZING))

    return {
        "filename": info["filename"],
        "width": info["width"],
        "height": info["height"],
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail"),
        "format_id": info.get("format_id"),
        "filesize": info.get("filesize"),
        "vcodec": info.get("vcodec"),
        "acodec": info.get("acodec"),
        "ext": info.get("ext", "mp4"),
    }


async def download_audio(msg: types.Message, url: str):
    loop = asyncio.get_running_loop()
    last_update = [0.0]
    progress = [0.0]

    async def update_progress() -> None:
        await msg.edit_text(format_message(ProgressState.AUDIO_DOWNLOADING, progress[0]))

    def progress_hook(data):
        if data["status"] != "downloading":
            return
        progress[0] = get_percentage(data)
        now = loop.time()
        if now - last_update[0] < 1:
            return
        last_update[0] = now
        asyncio.run_coroutine_threadsafe(update_progress(), loop)

    def download():
        import tempfile
        audio_id = str(uuid.uuid4())
        is_instagram = "instagram.com" in url.lower()
        proxy_url = None if is_instagram else (os.getenv("PROXY_URL") or os.getenv("WARP_PROXY", "socks5://warp:9091"))

        # Best pristine audio stream (m4a/aac or mp3) without quality loss
        options = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(VIDEOS_DIR / f"{audio_id}.%(ext)s"),
            "noplaylist": True,
            "proxy": proxy_url,
            "js_runtimes": {"quickjs": {"path": "/usr/bin/qjs"}} if shutil.which("qjs") else {},
            "concurrent_fragment_downloads": 16,
            "http_chunk_size": 10 * 1024 * 1024,
            "buffersize": 16 * 1024 * 1024,
            "writethumbnail": True,
            "progress_hooks": [progress_hook],
            "postprocessors": [],
        }

        tmp_cookies = None
        if not is_instagram and COOKIES_FILE.exists() and COOKIES_FILE.is_file() and COOKIES_FILE.stat().st_size > 10:
            cookie_text = COOKIES_FILE.read_text(encoding="utf-8").strip()
            if "# Netscape" in cookie_text or "\t" in cookie_text:
                tmp_cookies = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
                tmp_cookies.write(cookie_text + "\n")
                tmp_cookies.flush()
                tmp_cookies.close()
                options["cookiefile"] = tmp_cookies.name

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                file_path = Path(downloaded_file)

                # Thumbnail for audio cover
                thumb_path = None
                for ext in [".jpg", ".webp", ".png", ".jpeg"]:
                    tp = file_path.with_suffix(ext)
                    if tp.exists() and tp.stat().st_size > 0:
                        thumb_path = tp
                        break

                # Ensure thumbnail is jpg and max 320px for Telegram
                if thumb_path and thumb_path.exists():
                    jpg_path = file_path.with_suffix(".thumb.jpg")
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(thumb_path),
                        "-vf", "scale='if(gt(iw,ih),320,-1)':'if(gt(iw,ih),-1,320)'",
                        "-q:v", "2", str(jpg_path)
                    ], capture_output=True)
                    if jpg_path.exists() and jpg_path.stat().st_size > 0:
                        if thumb_path != jpg_path:
                            thumb_path.unlink(missing_ok=True)
                        thumb_path = jpg_path
                    else:
                        thumb_path = None

                return {
                    "filename": str(file_path),
                    "duration": int(float(info.get("duration", 0) or 0)),
                    "title": info.get("title") or "Audio",
                    "performer": info.get("uploader") or info.get("channel") or info.get("artist") or "Second Saver",
                    "thumbnail": str(thumb_path) if (thumb_path and thumb_path.exists()) else None,
                    "filesize": file_path.stat().st_size if file_path.exists() else info.get("filesize"),
                    "format_id": info.get("format_id"),
                    "ext": file_path.suffix.lstrip(".") or "m4a",
                }
        finally:
            if tmp_cookies:
                Path(tmp_cookies.name).unlink(missing_ok=True)

    info = await loop.run_in_executor(None, download)
    await msg.edit_text(format_message(ProgressState.FINALIZING))
    return info


def extract_youtube_id(url: str) -> str | None:
    import re
    m = re.search(
        r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|embed/|live/|shorts/))([A-Za-z0-9_-]{11})",
        url,
    )
    return m.group(1) if m else None


async def fetch_youtube_info(url: str) -> dict:
    """Title, channel, duration and per-resolution size estimates, without downloading."""
    import tempfile
    loop = asyncio.get_running_loop()

    def run():
        opts = {
            "proxy": os.getenv("PROXY_URL") or os.getenv("WARP_PROXY", "socks5://warp:9091"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"quickjs": {"path": "/usr/bin/qjs"}} if shutil.which("qjs") else {},
        }
        tmp = None
        if COOKIES_FILE.exists() and COOKIES_FILE.is_file() and COOKIES_FILE.stat().st_size > 10:
            text = COOKIES_FILE.read_text(encoding="utf-8").strip()
            if "# Netscape" in text or "\t" in text:
                tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
                tmp.write(text + "\n")
                tmp.close()
                opts["cookiefile"] = tmp.name
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        finally:
            if tmp:
                Path(tmp.name).unlink(missing_ok=True)

        fmts = info.get("formats") or []
        size_of = lambda f: f.get("filesize") or f.get("filesize_approx") or 0
        best_audio = max(
            (size_of(f) for f in fmts if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")),
            default=0,
        )
        ladder = [144, 240, 360, 480, 720, 1080, 1440, 2160]
        sizes: dict[int, int] = {}
        for f in fmts:
            h = f.get("height")
            if not h or f.get("vcodec") in (None, "none"):
                continue
            size = size_of(f)
            if not size:
                continue
            if f.get("acodec") in (None, "none"):
                size += best_audio
            std = min((x for x in ladder if x >= h - 10), default=h)
            sizes[std] = max(sizes.get(std, 0), size)

        return {
            "id": info.get("id"),
            "title": info.get("title") or "Video",
            "channel": info.get("channel") or info.get("uploader") or "",
            "channel_url": info.get("channel_url") or info.get("uploader_url"),
            "duration": int(info.get("duration") or 0),
            "views": info.get("view_count"),
            "thumbnail": info.get("thumbnail"),
            "sizes": dict(sorted(sizes.items())),
            "audio_size": best_audio,
        }

    return await loop.run_in_executor(None, run)
