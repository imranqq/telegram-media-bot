"""Короткие токены для повторного запуска задачи с другим качеством."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from bot.services.downloader import DownloadRequest

TTL_SECONDS = 60 * 60


class PendingStore:
    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl = ttl
        self._jobs: dict[str, "PendingJob"] = {}

    def put(self, user_id: int, request: DownloadRequest) -> str:
        self._prune()
        token = secrets.token_hex(6)
        self._jobs[token] = PendingJob(user_id=user_id, request=request, created_at=time.time())
        return token

    def pop(self, token: str) -> "PendingJob | None":
        self._prune()
        return self._jobs.pop(token, None)

    def _prune(self) -> None:
        if len(self._jobs) < 200:
            return
        deadline = time.time() - self._ttl
        for token in [key for key, job in self._jobs.items() if job.created_at < deadline]:
            self._jobs.pop(token, None)


@dataclass(slots=True)
class PendingJob:
    user_id: int
    request: DownloadRequest
    created_at: float
