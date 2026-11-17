"""Основной сценарий: ссылка → загрузка → отправка файла."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.keyboards.inline import format_keyboard, oversize_keyboard
from bot.services.downloader import (
    MODE_AUDIO,
    MODE_VIDEO,
    DownloadRequest,
    DownloadResult,
    MediaDownloadError,
    MediaDownloader,
    OversizeError,
)
from bot.services.formats import MAX_VIDEO_HEIGHT, label_for_audio
from bot.services.pending import PendingStore
from bot.services.preferences import Preferences
from bot.services.progress import ProgressTracker
from bot.services.queue import DownloadQueue
from bot.services.sender import deliver
from bot.utils.format import human_bytes
from bot.utils.links import Platform, parse_link
from bot.utils.telegram import NO_PREVIEW, safe_delete, safe_edit
from bot.utils.text import humanize_error

log = logging.getLogger(__name__)

router = Router(name="media")

NO_LINK_TEXT = (
    "Ссылку не нашёл.\n\n"
    "Подойдёт:\n"
    "• soundcloud.com/…  — трек или сет\n"
    "• youtube.com/watch?v=…  или youtu.be/…\n\n"
    "Формат звука можно переключить кнопкой ниже."
)


def build_header(request: DownloadRequest) -> str:
    if request.is_audio:
        return f"🎧 SoundCloud · {label_for_audio(request.audio_format)}"
    quality = f"до {request.max_height}p" if request.max_height else "лучшее в пределах лимита"
    return f"🎬 YouTube · {quality}"


def request_from_link(url: str, platform: Platform, prefs: Preferences, user_id: int) -> DownloadRequest:
    is_audio = platform is Platform.SOUNDCLOUD
    return DownloadRequest(
        url=url,
        platform=platform,
        mode=MODE_AUDIO if is_audio else MODE_VIDEO,
        audio_format=prefs.audio_format(user_id),
    )


# --------------------------------------------------------------------- handlers


@router.message(F.text & ~F.text.startswith("/"))
async def on_link(
    message: Message,
    bot: Bot,
    settings: Settings,
    downloader: MediaDownloader,
    queue: DownloadQueue,
    prefs: Preferences,
    pending: PendingStore,
) -> None:
    if message.from_user is None:
        return
    link = parse_link(message.text or "")
    if link is None:
        await message.answer(
            NO_LINK_TEXT,
            reply_markup=format_keyboard(prefs.audio_format(message.from_user.id)),
            link_preview_options=NO_PREVIEW,
        )
        return

    request = request_from_link(link.url, link.platform, prefs, message.from_user.id)
    status = await message.answer(f"{build_header(request)}\n\nГотовлю загрузку…")
    await run_job(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        request=request,
        status=status,
        settings=settings,
        downloader=downloader,
        queue=queue,
        pending=pending,
    )


@router.callback_query(F.data.startswith("fmt:"))
async def on_format_changed(callback: CallbackQuery, prefs: Preferences) -> None:
    value = (callback.data or "").split(":", 1)[1]
    if value not in {"mp3", "orig"}:
        await callback.answer("Неизвестный формат", show_alert=True)
        return
    prefs.set_audio_format(callback.from_user.id, value)
    await callback.answer(f"Формат: {label_for_audio(value)}")
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=format_keyboard(value))
        except Exception:  # noqa: BLE001
            log.debug("markup edit failed", exc_info=True)


@router.callback_query(F.data.startswith("retry:"))
async def on_quality_retry(
    callback: CallbackQuery,
    bot: Bot,
    settings: Settings,
    downloader: MediaDownloader,
    queue: DownloadQueue,
    pending: PendingStore,
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or callback.message is None:
        await callback.answer("Кнопка устарела", show_alert=True)
        return
    _, token, raw_height = parts
    if not raw_height.isdigit():
        await callback.answer("Кнопка устарела", show_alert=True)
        return

    job = pending.pop(token)
    if job is None or job.user_id != callback.from_user.id:
        await callback.answer("Задача устарела, пришлите ссылку заново", show_alert=True)
        return

    await callback.answer()
    request = replace(job.request, max_height=min(int(raw_height), MAX_VIDEO_HEIGHT))
    status = await callback.message.answer(f"{build_header(request)}\n\nГотовлю загрузку…")
    await run_job(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        request=request,
        status=status,
        settings=settings,
        downloader=downloader,
        queue=queue,
        pending=pending,
    )


# ------------------------------------------------------------------ job runner


async def run_job(
    *,
    bot: Bot,
    chat_id: int,
    user_id: int,
    request: DownloadRequest,
    status: Message,
    settings: Settings,
    downloader: MediaDownloader,
    queue: DownloadQueue,
    pending: PendingStore,
) -> None:
    header = build_header(request)
    tracker = ProgressTracker(bot, chat_id, status.message_id, header)
    result: DownloadResult | None = None
    waiter: asyncio.Task[None] | None = None
    started = time.monotonic()

    try:
        if queue.is_busy():
            await safe_edit(status, f"{header}\n\nОчередь · {queue.load_text()}")
            log.info("queued user=%s url=%s load=%s", user_id, request.url, queue.load_text())
            waiter = asyncio.create_task(
                _queue_ticker(status, header, queue, started), name="queue-ticker"
            )

        async with queue.acquire(user_id):
            if waiter is not None:
                waiter.cancel()
                waiter = None
            tracker.start()
            log.info("job start user=%s url=%s mode=%s", user_id, request.url, request.mode)
            result = await asyncio.wait_for(
                downloader.run(request, tracker), timeout=settings.job_timeout
            )
            log.info(
                "job done user=%s url=%s items=%s in %.0f с",
                user_id,
                request.url,
                len(result.items),
                time.monotonic() - started,
            )

        await tracker.stop()
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
        await deliver(bot, chat_id, result.items, settings=settings, archive_name=result.title)
        await safe_delete(status)
        if result.notice:
            await bot.send_message(chat_id, result.notice)

    except OversizeError as exc:
        await tracker.stop()
        token = pending.put(user_id, request)
        text = (
            f"{header}\n\n"
            f"Файл весит {human_bytes(exc.size)}, а лимит Telegram — "
            f"{human_bytes(exc.limit)}.\n"
        )
        if request.is_audio:
            text += "Попробуйте другой формат звука."
            keyboard = None
        else:
            text += "Выберите качество ниже — перекачаю только нужное."
            keyboard = oversize_keyboard(token, exc.height or request.max_height)
        await safe_edit(status, text, keyboard)

    except asyncio.TimeoutError:
        await tracker.stop()
        limit_min = settings.job_timeout // 60
        log.warning("job timeout user=%s url=%s", user_id, request.url)
        await safe_edit(
            status,
            f"{header}\n\nЗадача идёт дольше {limit_min} мин, останавливаю.\n"
            "Для большого сета возьмите ссылку на отдельный трек или повторите позже.",
        )

    except MediaDownloadError as exc:
        await tracker.stop()
        await safe_edit(status, f"{header}\n\n{humanize_error(exc)}")

    except Exception:  # noqa: BLE001 - последний рубеж, бот не должен падать
        await tracker.stop()
        log.exception("Не удалось обработать %s", request.url)
        await safe_edit(
            status,
            f"{header}\n\nВнутренняя ошибка. Пришлите ссылку ещё раз или попробуйте позже.",
        )

    finally:
        if waiter is not None:
            waiter.cancel()
        await tracker.stop()
        if result is not None:
            result.cleanup()


async def _queue_ticker(
    status: Message,
    header: str,
    queue: DownloadQueue,
    started: float,
) -> None:
    """Пока задача ждёт слот, сообщение обновляется — иначе выглядит как зависание."""
    while True:
        await asyncio.sleep(5)
        elapsed = int(time.monotonic() - started)
        await safe_edit(
            status,
            f"{header}\n\nОчередь · {queue.load_text()} · ждём {elapsed} с",
        )
