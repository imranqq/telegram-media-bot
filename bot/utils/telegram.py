"""Безопасные операции с сообщениями: ошибки Telegram не должны ломать сценарий."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions, Message

log = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(text=text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass
    except Exception:  # noqa: BLE001
        log.debug("edit failed", exc_info=True)


async def safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception:  # noqa: BLE001
        log.debug("delete failed", exc_info=True)
