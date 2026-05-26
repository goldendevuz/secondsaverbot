from app.utils.sanitizer import is_youtube, build_caption, sanitize_url


def test_is_youtube():
    assert is_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_youtube("https://youtu.be/dQw4w9WgXcQ") is True
    assert is_youtube("https://youtube.com/shorts/xyz") is True
    assert is_youtube("https://instagram.com/reel/xyz") is False
    assert is_youtube("https://tiktok.com/@xyz") is False


def test_sanitize_url():
    assert (
        sanitize_url("  https://youtube.com/watch?v=123  ")
        == "https://youtube.com/watch?v=123"
    )
    assert sanitize_url("youtube.com") == "https://youtube.com"


def test_build_caption():
    url = "https://youtube.com"
    caption = build_caption(url)
    assert url in caption
    assert "FastSaver Bot" in caption
