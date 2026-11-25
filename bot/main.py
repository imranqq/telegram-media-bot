"""Сборка и запуск приложения."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from logging.config import dictConfig
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from bot.config import WEBHOOK_PATH, Settings
from bot.handlers import setup_routers
from bot.middlewares import ServicesMiddleware
from bot.services.downloader import MediaDownloader
from bot.services.keepalive import SelfPinger
from bot.services.preferences import Preferences
from bot.services.queue import DownloadQueue
from bot.web import start_web_server

log = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                    "datefmt": "%H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "aiogram.event": {"level": "WARNING"},
                "yt_dlp": {"level": "WARNING"},
                "aiohttp.access": {"level": "WARNING"},
            },
        }
    )


def check_ffmpeg(settings: Settings) -> None:
    """ffmpeg нужен для MP3 и склейки видео — предупреждаем сразу, а не при первой загрузке."""
    if settings.ffmpeg_location:
        if not Path(settings.ffmpeg_location).exists():
            log.warning("FFMPEG_LOCATION=%s не найден по этому пути", settings.ffmpeg_location)
        return
    if shutil.which("ffmpeg") is None:
        log.warning("ffmpeg не найден в PATH: MP3 и склейка видео работать не будут")


def cleanup_download_dir(settings: Settings) -> None:
    """Убираем недокачанные каталоги от прошлых запусков."""
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    for path in settings.download_dir.glob("job_*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


async def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    cleanup_download_dir(settings)
    check_ffmpeg(settings)

    session = (
        AiohttpSession(api=TelegramAPIServer.from_base(settings.api_base))
        if settings.uses_local_api
        else None
    )
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    downloader = MediaDownloader(settings)
    dispatcher = Dispatcher()
    middleware = ServicesMiddleware(
        settings=settings,
        downloader=downloader,
        queue=DownloadQueue(settings.max_concurrent_downloads),
        prefs=Preferences(settings.default_audio_format),
    )
    dispatcher.message.middleware(middleware)
    dispatcher.callback_query.middleware(middleware)
    setup_routers(dispatcher)

    runner = None
    pinger_task: asyncio.Task[None] | None = None

    log.info(
        "Бот запущен · лимит файла %s МБ · ffmpeg %s · API %s",
        settings.max_upload_mb,
        settings.ffmpeg_location or "из PATH",
        "локальный" if settings.uses_local_api else "облачный",
    )

    # Самопинг имеет смысл только с публичным адресом: локально сервис не засыпает
    if settings.uses_webhook and settings.keepalive_interval > 0:
        pinger = SelfPinger(settings.webhook_base or "", settings.keepalive_interval)
        pinger_task = asyncio.create_task(pinger.run(), name="self-ping")

    try:
        if settings.uses_webhook:
            # Сначала сервер, потом set_webhook: к моменту первого апдейта URL уже живой
            runner = await start_web_server(
                settings.port,
                bot=bot,
                dispatcher=dispatcher,
                webhook_path=WEBHOOK_PATH,
                secret=settings.webhook_secret,
            )
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
                allowed_updates=dispatcher.resolve_used_update_types(),
                # false: апдейты, пришедшие пока контейнер спал, доедут после пробуждения
                drop_pending_updates=False,
            )
            log.info("Режим webhook · %s", settings.webhook_url)
            await asyncio.Event().wait()
        else:
            runner = await start_web_server(settings.port)
            webhook = await bot.get_webhook_info()
            if webhook.url:
                log.warning(
                    "У бота уже стоит webhook (%s): локальный polling будет конфликтовать с ним",
                    webhook.url,
                )
            log.info("Режим long polling")
            await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        if pinger_task is not None:
            pinger_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pinger_task
        if runner is not None:
            await runner.cleanup()
        await bot.session.close()
        log.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
