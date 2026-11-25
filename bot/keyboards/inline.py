"""Инлайн-клавиатура выбора формата звука."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.formats import AUDIO_LABELS, AUDIO_SHORT_LABELS


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
