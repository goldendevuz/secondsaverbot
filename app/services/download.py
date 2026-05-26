import os
import tempfile
import asyncio
import logging
import httpx
from aiogram import Bot
from aiogram.types import FSInputFile
from app.utils.sanitizer import is_youtube, build_caption, sanitize_url

logger = logging.getLogger(__name__)


class DownloadService:
    """
    SOLID-compliant business service for fetching video metadata, downloading files locally,
    sending them over Telegram, and safely cleaning up disk space.
    """

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=httpx.Timeout(
                connect=10.0, read=60.0, write=10.0, pool=10.0
            ),
            limits=httpx.Limits(
                max_connections=50, max_keepalive_connections=20
            ),
        )

    async def close(self):
        """
        Gracefully close the underlying HTTP client session.
        """
        await self.client.aclose()

    async def fetch_youtube(self, url: str, retries: int = 2) -> dict:
        for attempt in range(retries):
            try:
                response = await self.client.post(
                    "/youtube/download",
                    headers={
                        "X-Api-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json={"url": url, "format": "1080p"},
                )

                if response.status_code == 429:
                    await asyncio.sleep(2 + attempt)
                    continue

                if response.status_code >= 500:
                    await asyncio.sleep(1 + attempt)
                    continue

                if response.status_code != 200:
                    return {"error": "YouTube API xatolik"}

                data = response.json()
                if not isinstance(data, dict) or not data.get("ok"):
                    return {"error": "YouTube video topilmadi"}

                download_url = data.get("download_url")
                if not download_url:
                    return {"error": "YouTube yuklab olish havolasi yo‘q"}

                return {
                    "video_url": download_url,
                    "caption": build_caption(url),
                }

            except httpx.TimeoutException:
                await asyncio.sleep(1.5 + attempt)
            except Exception as e:
                logger.error(
                    "Error fetching YouTube link on attempt %s: %s", attempt, e
                )
                await asyncio.sleep(1)

        return {"error": "YouTube yuklab bo‘lmadi"}

    async def fetch_generic(self, url: str, retries: int = 3) -> dict:
        for attempt in range(retries):
            try:
                response = await self.client.get(
                    "/fetch",
                    params={"url": url},
                    headers={"X-Api-Key": self.api_key},
                )

                if response.status_code == 429:
                    await asyncio.sleep(2 + attempt)
                    continue

                if response.status_code >= 500:
                    await asyncio.sleep(1 + attempt)
                    continue

                if response.status_code != 200:
                    return {"error": "API error"}

                data = response.json()
                if not isinstance(data, dict) or not data.get("ok"):
                    return {"error": "Video topilmadi"}

                download_url = data.get("download_url")
                if not download_url:
                    return {"error": "Download URL yo‘q"}

                return {
                    "video_url": download_url,
                    "caption": build_caption(url),
                }

            except httpx.TimeoutException:
                await asyncio.sleep(1.5 + attempt)
            except Exception as e:
                logger.error(
                    "Error fetching generic link on attempt %s: %s", attempt, e
                )
                await asyncio.sleep(1)

        return {"error": "Yuklab bo‘lmadi"}

    async def fetch_download_data(self, url: str) -> dict:
        sanitized = sanitize_url(url)
        try:
            if is_youtube(sanitized):
                return await self.fetch_youtube(sanitized)
            return await self.fetch_generic(sanitized)
        except Exception as e:
            logger.error(
                "Failed to fetch download metadata for %s: %s",
                url,
                e,
                exc_info=True,
            )
            return {"error": str(e)}

    async def download_file(self, url: str) -> str:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_path = temp_file.name

        async with self.client.stream("GET", url) as response:
            response.raise_for_status()
            with open(temp_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

        return temp_path

    async def send_video_safely(
        self,
        bot: Bot,
        chat_id: int,
        video_url: str,
        caption: str,
        business_connection_id: str | None = None,
    ):
        """
        Downloads a video to a local temp file, uploads it to Telegram as a native streamable
        video or a document fallback, and guarantees that disk storage is cleaned up.
        """
        logger.info("📥 Downloading and streaming video to Telegram: %s", video_url)
        file_path = None
        try:
            file_path = await self.download_file(video_url)
            video = FSInputFile(file_path)

            if business_connection_id:
                await bot.send_video(
                    chat_id=chat_id,
                    video=video,
                    caption=caption,
                    supports_streaming=True,
                    business_connection_id=business_connection_id,
                )
            else:
                await bot.send_video(
                    chat_id=chat_id,
                    video=video,
                    caption=caption,
                    supports_streaming=True,
                )
        except Exception as e:
            logger.warning(
                "send_video failed: %s. Attempting document fallback.", e
            )
            try:
                if not file_path or not os.path.exists(file_path):
                    file_path = await self.download_file(video_url)

                doc = FSInputFile(file_path)
                fallback_caption = "📥 Video (document sifatida)"

                if business_connection_id:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=doc,
                        caption=fallback_caption,
                        business_connection_id=business_connection_id,
                    )
                else:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=doc,
                        caption=fallback_caption,
                    )
            except Exception as e2:
                logger.error("Fallback send_document failed: %s", e2)
                raise e2
        finally:
            # Guarantee file cleanup in finally block
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info("🗑️ Successfully deleted temp file %s", file_path)
                except Exception as clean_err:
                    logger.error(
                        "Failed to delete temp file %s: %s",
                        file_path,
                        clean_err,
                    )
