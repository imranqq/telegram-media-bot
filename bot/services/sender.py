"""Отправка скачанных файлов в Telegram."""

from __future__ import annotations

import asyncio
import logging
import zipfile
from pathlib import Path
from typing import Sequence

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

from bot.config import Settings
from bot.services.downloader import MODE_AUDIO, MediaDownloadError, MediaItem, OversizeError
from bot.utils.format import human_bytes, pluralize_tracks

log = logging.getLogger(__name__)

FORBIDDEN_CHARS = set('<>:"/\\|?*\n\r\t')
THUMBNAIL_LIMIT = 190_000


def safe_filename(name: str, fallback: str = "download") -> str:
    cleaned = "".join("_" if char in FORBIDDEN_CHARS else char for char in name)
    cleaned = cleaned.strip().strip(".")
    return (cleaned or fallback)[:80]


async def deliver(
    bot: Bot,
    chat_id: int,
    items: Sequence[MediaItem],
    *,
    settings: Settings,
    archive_name: str | None = None,
) -> None:
    """Одиночный файл — как медиа, коллекция — архивом, если влезает в лимит."""
    if not items:
        raise MediaDownloadError("Нечего отправлять")

    if len(items) == 1:
        await _send_single(bot, chat_id, items[0], settings)
        return

    total = sum(item.size for item in items)
    if total <= settings.max_upload_bytes:
        archive = await asyncio.to_thread(_build_archive, items, safe_filename(archive_name or "collection"))
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
        try:
            await bot.send_document(
                chat_id,
                FSInputFile(archive, filename=archive.name),
                caption=f"{pluralize_tracks(len(items))} · {human_bytes(total)}",
            )
        except TelegramBadRequest as exc:
            raise MediaDownloadError(_delivery_error(exc)) from exc
        return

    # Не влезает в лимит одним архивом — отправляем по одному
    await bot.send_message(
        chat_id,
        f"{pluralize_tracks(len(items))} · {human_bytes(total)} — архив больше лимита "
        f"{human_bytes(settings.max_upload_bytes)}, отправляю по одному.",
    )
    for item in items:
        await _send_single(bot, chat_id, item, settings)
        await asyncio.sleep(0.4)


async def _send_single(bot: Bot, chat_id: int, item: MediaItem, settings: Settings) -> None:
    if item.size > settings.max_upload_bytes:
        raise OversizeError(item.size, settings.max_upload_bytes, item.height)

    document = FSInputFile(item.path, filename=_display_filename(item))
    thumbnail = FSInputFile(item.thumbnail) if item.thumbnail else None

    try:
        if item.kind == MODE_AUDIO:
            await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VOICE)
            await bot.send_audio(
                chat_id,
                document,
                title=item.title[:64],
                performer=(item.performer or "")[:64] or None,
                duration=item.duration,
                thumbnail=thumbnail,
            )
        else:
            await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
            await bot.send_video(
                chat_id,
                document,
                duration=item.duration,
                width=item.width,
                height=item.height,
                supports_streaming=True,
                thumbnail=thumbnail,
            )
    except TelegramBadRequest as exc:
        raise MediaDownloadError(_delivery_error(exc)) from exc


def _display_filename(item: MediaItem) -> str:
    return safe_filename(f"{item.title}.{item.extension}", fallback=f"file.{item.extension}")


def _delivery_error(exc: TelegramBadRequest) -> str:
    text = str(exc).lower()
    if "too big" in text or "file is too large" in text:
        return "Telegram отказал: файл больше лимита. Выберите качество ниже."
    if "wrong file identifier" in text:
        return "Telegram не принял файл, попробуйте ссылку снова."
    return f"Telegram вернул ошибку: {exc}"


def _build_archive(items: Sequence[MediaItem], base_name: str) -> Path:
    """ZIP без сжатия: mp3/mp4 всё равно не сжимаются, зато быстро."""
    archive = items[0].path.parent / f"{base_name}.zip"
    used: set[str] = set()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        for index, item in enumerate(items, start=1):
            name = _display_filename(item)
            if name in used:
                name = f"{index:02d} - {name}"
            used.add(name)
            bundle.write(item.path, arcname=name)
    return archive
