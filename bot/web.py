"""HTTP-сервер для Render: healthcheck и приём апдейтов Telegram по webhook.

Webhook нужен именно из-за free-плана: контейнер засыпает без входящего трафика,
а сообщение в Telegram — это и есть входящий запрос. Render поднимает сервис, и
апдейт доезжает, вместо того чтобы висеть в очереди у Telegram.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiohttp import web

log = logging.getLogger(__name__)

HEALTH_PAYLOAD = {"status": "ok", "service": "telegram-media-bot"}
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


async def _health(_: web.Request) -> web.Response:
    return web.json_response(HEALTH_PAYLOAD)


def _webhook_handler(bot: Bot, dispatcher: Dispatcher, secret: str | None):
    async def handler(request: web.Request) -> web.Response:
        if secret and request.headers.get(SECRET_HEADER) != secret:
            return web.Response(status=403)
        try:
            payload = await request.json()
        except ValueError:
            return web.Response(status=400)

        update = Update.model_validate(payload, context={"bot": bot})
        # Отвечаем Telegram сразу, обработку уводим в фон: загрузка файла идёт минутами,
        # а webhook обязан отвечать быстро, иначе Telegram пришлёт апдейт повторно.
        asyncio.create_task(dispatcher.feed_webhook_update(bot, update))
        return web.Response()

    return handler


def build_app(
    *,
    bot: Bot | None = None,
    dispatcher: Dispatcher | None = None,
    webhook_path: str = "/webhook",
    secret: str | None = None,
) -> web.Application:
    """Собирает приложение: healthcheck всегда, webhook — если переданы bot и dispatcher."""
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    if bot is not None and dispatcher is not None:
        app.router.add_post(webhook_path, _webhook_handler(bot, dispatcher, secret))
    return app


async def start_web_server(
    port: int,
    *,
    bot: Bot | None = None,
    dispatcher: Dispatcher | None = None,
    webhook_path: str = "/webhook",
    secret: str | None = None,
) -> web.AppRunner:
    """Поднимает HTTP-сервер. С bot и dispatcher дополнительно включает webhook."""
    app = build_app(bot=bot, dispatcher=dispatcher, webhook_path=webhook_path, secret=secret)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info(
        "HTTP слушает 0.0.0.0:%s · health%s",
        port,
        " · webhook" if bot is not None else "",
    )
    return runner
