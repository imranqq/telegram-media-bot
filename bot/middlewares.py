"""Внедрение сервисов в хендлеры."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ServicesMiddleware(BaseMiddleware):
    """Кладёт зависимости в data — хендлеры получают их как обычные аргументы."""

    def __init__(self, **services: Any) -> None:
        self._services = services

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data.update(self._services)
        return await handler(event, data)
