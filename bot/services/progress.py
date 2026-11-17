"""Живой прогресс загрузки: собирает статистику и обновляет сообщение в Telegram."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from bot.utils.format import human_bytes, human_duration, human_speed, render_bar

log = logging.getLogger(__name__)

# Telegram не любит частые edit_message_text — держим интервал
EDIT_INTERVAL = 2.6

POSTPROCESSOR_LABELS: dict[str, str] = {
    "FFmpegExtractAudio": "конвертация звука",
    "FFmpegVideoConvertor": "перекодирование видео",
    "FFmpegVideoRemuxer": "упаковка в контейнер",
    "FFmpegMerger": "склейка видео и звука",
}


class JobProgress:
    """Состояние загрузки, обновляемое синхронно из потока yt-dlp."""

    def __init__(self) -> None:
        self._files: dict[str, dict[str, Any]] = {}
        self._phase: str = "download"
        # hooks yt-dlp приходят из рабочего потока, читаем из event loop
        self._lock = threading.Lock()

    def update_download(self, data: dict) -> None:
        key = str(data.get("filename") or data.get("info_dict", {}).get("id") or "unknown")
        status = data.get("status")
        with self._lock:
            entry = self._files.setdefault(
                key,
                {"total": 0, "downloaded": 0, "speed": None, "eta": None, "finished": False},
            )
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                if total:
                    entry["total"] = int(total)
                downloaded = data.get("downloaded_bytes") or 0
                if downloaded:
                    entry["downloaded"] = int(downloaded)
                entry["speed"] = data.get("speed")
                entry["eta"] = data.get("eta")
            elif status == "finished":
                entry["finished"] = True
                entry["downloaded"] = entry["total"] or entry["downloaded"]
                entry["speed"] = None
                entry["eta"] = None

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = phase

    @property
    def phase(self) -> str:
        with self._lock:
            return self._phase

    def has_files(self) -> bool:
        with self._lock:
            return bool(self._files)

    def snapshot(self) -> tuple[int, int, float | None, int | None]:
        """(скачано, всего, скорость, eta)"""
        with self._lock:
            files = list(self._files.values())
        total = sum(int(item.get("total") or 0) for item in files)
        downloaded = sum(int(item.get("downloaded") or 0) for item in files)
        speed = next(
            (float(item["speed"]) for item in reversed(files) if item.get("speed")),
            None,
        )
        eta = next(
            (int(item["eta"]) for item in reversed(files) if item.get("eta")),
            None,
        )
        return downloaded, total, speed, eta


class ProgressTracker:
    """Раз в пару секунд перерисовывает сообщение со статусом загрузки."""

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        header: str,
        interval: float = EDIT_INTERVAL,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._message_id = message_id
        self._header = header
        self._interval = interval
        self._state = JobProgress()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._last_text = ""

    # --- интеграция с yt-dlp (вызывается из рабочего потока) ---

    def hook(self, data: dict) -> None:
        self._state.update_download(data)

    def postprocessor_hook(self, data: dict) -> None:
        if data.get("status") == "started":
            name = str(data.get("postprocessor") or "")
            self._state.set_phase(POSTPROCESSOR_LABELS.get(name, "обработка"))

    # --- управление задачей ---

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="progress-loop")

    async def stop(self, final_text: str | None = None) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if final_text is not None:
            await self._safe_edit(final_text)

    async def _loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self._interval)
            text = self.render()
            if text:
                await self._safe_edit(text)

    # --- рендер ---

    def render(self) -> str | None:
        if not self._state.has_files():
            return None

        phase = self._state.phase
        if phase != "download":
            return "\n".join([f"<b>{self._header}</b>", "", f"⚙️ {phase.capitalize()}…"])

        downloaded, total, speed_bps, eta = self._state.snapshot()
        percent = (downloaded / total * 100) if total else 0.0
        parts = [human_bytes(downloaded), human_bytes(total)]
        speed = human_speed(speed_bps)
        if speed:
            parts.append(speed)
        if eta:
            parts.append(f"осталось {human_duration(eta)}")
        elif total and downloaded >= total:
            parts.append("сохранение")

        return "\n".join(
            [
                f"<b>{self._header}</b>",
                f"{render_bar(percent)} {percent:.0f}%",
                " · ".join(parts),
            ]
        )

    async def _safe_edit(self, text: str) -> None:
        if text == self._last_text:
            return
        try:
            await self._bot.edit_message_text(
                text=text,
                chat_id=self._chat_id,
                message_id=self._message_id,
            )
            self._last_text = text
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramBadRequest:
            # сообщение не изменилось или уже удалено — не критично
            pass
        except Exception:  # noqa: BLE001 - сеть может моргать, прогресс не должен падать
            log.debug("progress edit failed", exc_info=True)
