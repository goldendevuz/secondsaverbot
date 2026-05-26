from aiohttp import web

async def health(request):
    return web.json_response({
        "status": "ok"
    })

def create_health_app():
    app = web.Application()
    app.router.add_get("/health", health)
    return app
