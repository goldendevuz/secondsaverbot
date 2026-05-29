import pathlib
from aiohttp import web

# Determine the path to the bot.log file located at the project root.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG_FILE_PATH = PROJECT_ROOT / "bot.log"

async def logs_handler(request: web.Request) -> web.Response:
    """Serve the bot.log file as plain text.

    Returns the full content of the log file. If the file does not exist,
    a 404 response is returned.
    """
    if not LOG_FILE_PATH.is_file():
        return web.Response(status=404, text="Log file not found.")
    try:
        # Reading the file synchronously is acceptable for small log sizes.
        content = LOG_FILE_PATH.read_text(encoding="utf-8")
    except Exception as e:
        return web.Response(status=500, text=f"Error reading log file: {e}")
    return web.Response(text=content, content_type="text/plain")
