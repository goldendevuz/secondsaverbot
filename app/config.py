from functools import lru_cache
from pydantic import BaseModel, Field
from decouple import config


class Settings(BaseModel):
    BOT_TOKEN: str = Field(default_factory=lambda: config("BOT_TOKEN"))
    REDIS_URL: str = Field(
        default_factory=lambda: config("REDIS_URL", default="redis://redis:6379/0")
    )
    API_URL: str = Field(default_factory=lambda: config("API_URL"))
    API_KEY: str = Field(default_factory=lambda: config("API_KEY"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Lazy singleton: Settings are only instantiated on first call.
    This avoids crashes at import time when env vars are missing (e.g. in tests).
    """
    return Settings()
