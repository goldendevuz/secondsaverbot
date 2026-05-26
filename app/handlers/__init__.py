from aiogram import Router
from .start import router as start_router
from .health import router as health_router
from .download import router as download_router

# Combine routers
main_router = Router()
main_router.include_router(start_router)
main_router.include_router(health_router)
main_router.include_router(download_router)

__all__ = ["main_router"]
