"""HTTP-healthcheck для Render: сервис должен отвечать 200, иначе контейнер перезапустят."""

from __future__ import annotations

import logging

from aiohttp import web

log = logging.getLogger(__name__)


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "telegram-media-bot"})


async def start_health_server(port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("Healthcheck слушает 0.0.0.0:%s/health", port)
    return runner
