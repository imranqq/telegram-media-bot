"""Инлайн-клавиатуры: выбор формата звука и понижение качества."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.formats import AUDIO_LABELS, AUDIO_SHORT_LABELS, VIDEO_LADDER


def format_keyboard(current: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("• " if value == current else "") + AUDIO_SHORT_LABELS[value],
                callback_data=f"fmt:{value}",
            )
        ]
        for value in AUDIO_LABELS
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def oversize_keyboard(token: str, failed_height: int | None) -> InlineKeyboardMarkup:
    """Предлагаем разрешения ниже того, что не влезло в лимит."""
    candidates = [
        height
        for height in VIDEO_LADDER
        if failed_height is None or height < failed_height
    ]
    if not candidates:
        return InlineKeyboardMarkup(inline_keyboard=[])
    buttons = [
        InlineKeyboardButton(text=f"{height}p", callback_data=f"retry:{token}:{height}")
        for height in candidates
    ]
    rows = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(inline_keyboard=rows)
