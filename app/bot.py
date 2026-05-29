import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

from app.config import get_settings
from app.logging_routes import logs_handler
from app.redis.client import RedisManager
from app.services.download import DownloadService
from app.logging_setup import setup_logging
from app.middlewares import (
    LoggingMiddleware,
    RateLimitMiddleware,
    ErrorHandlingMiddleware,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)
setup_logging()

async def health_api_handler(request):
    """
    HTTP route handler checking Redis health.
    """
    redis_manager: RedisManager = request.app["redis_manager"]
    redis_status = (
        "connected" if await redis_manager.is_healthy() else "disconnected"
    )

    return web.json_response(
        {"status": "ok", "redis": redis_status, "bot": "alive"}
    )


async def start_health_server(redis_manager: RedisManager):
    """
    Runs the HTTP server for platform/container health checks.
    """
    app = web.Application()
    app["redis_manager"] = redis_manager
    app.router.add_get("/health", health_api_handler)
    app.router.add_get("/logs", logs_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=2026)
    await site.start()
    logger.info("🩺 Health API server listening on http://0.0.0.0:2026/health")

    try:
        # Keep running
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await runner.cleanup()


async def main():
    logger.info("🚀 Starting FastSaver Production Bot...")

    settings = get_settings()

    # 1. Initialize Redis Connection Manager
    redis_manager = RedisManager(url=settings.REDIS_URL)
    redis_client = redis_manager.connect()

    # 2. Initialize SOLID Business Services
    download_service = DownloadService(
        api_url=settings.API_URL, api_key=settings.API_KEY
    )

    # 3. Create Bot and Dispatcher Core Instantiations
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    dp = Dispatcher()
    dp.include_router(main_router)

    # Register Middlewares on Dispatcher Observers
    for observer in [dp.message, dp.business_message]:
        observer.outer_middleware(ErrorHandlingMiddleware())
        observer.outer_middleware(LoggingMiddleware())
        observer.outer_middleware(RateLimitMiddleware(redis_client=redis_client))

    # 4. Spin up concurrent health check API and bot polling tasks
    health_task = asyncio.create_task(start_health_server(redis_manager))
    polling_task = asyncio.create_task(
        dp.start_polling(
            bot,
            redis_manager=redis_manager,
            download_service=download_service,
        )
    )

    try:
        await asyncio.gather(health_task, polling_task)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("🛑 Graceful shutdown initiated...")

        # Cancel tasks
        polling_task.cancel()
        health_task.cancel()

        # Gracefully release resources
        await download_service.close()
        await bot.session.close()
        await redis_manager.disconnect()

        logger.info("✅ Shutdown complete. Resources released.")


if __name__ == "__main__":
    asyncio.run(main())
