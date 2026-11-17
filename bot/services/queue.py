"""Очередь загрузок: ограничивает параллелизм и сериализует запросы одного пользователя."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class DownloadQueue:
    def __init__(self, workers: int) -> None:
        self._workers = max(1, workers)
        self._semaphore = asyncio.Semaphore(self._workers)
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._active = 0
        self._waiting = 0

    @property
    def workers(self) -> int:
        return self._workers

    def is_busy(self) -> bool:
        return self._active >= self._workers or self._waiting > 0

    def load_text(self) -> str:
        text = f"{self._active} из {self._workers} в работе"
        if self._waiting:
            text += f", в очереди {self._waiting}"
        return text

    @asynccontextmanager
    async def acquire(self, user_id: int) -> AsyncIterator[None]:
        lock = self._user_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            self._waiting += 1
            try:
                await self._semaphore.acquire()
            finally:
                self._waiting -= 1
            self._active += 1
            try:
                yield
            finally:
                self._active -= 1
                self._semaphore.release()

        # Чистим карту блокировок, чтобы она не росла бесконечно
        if len(self._user_locks) > 500 and not lock.locked():
            self._user_locks.pop(user_id, None)
