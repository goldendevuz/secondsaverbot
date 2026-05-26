from app.config import Settings


def test_settings_fields():
    """Test that Settings can be constructed with explicit values."""
    s = Settings(
        BOT_TOKEN="fake_token",
        REDIS_URL="redis://fake_host:6379/0",
        API_URL="https://fake-api.com",
        API_KEY="fake_key",
    )
    assert s.BOT_TOKEN == "fake_token"
    assert s.REDIS_URL == "redis://fake_host:6379/0"
    assert s.API_URL == "https://fake-api.com"
    assert s.API_KEY == "fake_key"


def test_settings_default_redis_url():
    """Test that REDIS_URL has a sensible default when not provided."""
    s = Settings(
        BOT_TOKEN="tok",
        API_URL="https://api.example.com",
        API_KEY="key",
    )
    # default_factory uses decouple which may read .env,
    # but explicit construction should work
    assert isinstance(s.REDIS_URL, str)
