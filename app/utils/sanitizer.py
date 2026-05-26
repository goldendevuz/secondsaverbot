import re


def is_youtube(url: str) -> bool:
    """
    Pure function to determine if a URL is a YouTube link.
    """
    return bool(re.search(r"(youtube\.com|youtu\.be)", url))


def build_caption(url: str) -> str:
    """
    Pure function to construct the standard video caption with HTML links.
    """
    return f"<b><i><a href='https://t.me/free_yt_dl_bot'>via</a> | <a href='{url}'>link</a></i></b>"


def sanitize_url(url: str) -> str:
    """
    Pure function to sanitize user input URLs.
    Strips trailing spaces and ensures the protocol is specified.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url
