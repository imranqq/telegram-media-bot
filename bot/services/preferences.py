"""Пользовательские настройки (формат звука) в памяти процесса."""

from __future__ import annotations

from bot.services.formats import AUDIO_FORMATS


class Preferences:
    def __init__(self, default_audio_format: str = "mp3") -> None:
        self._default = default_audio_format if default_audio_format in AUDIO_FORMATS else "mp3"
        self._audio_formats: dict[int, str] = {}

    def audio_format(self, user_id: int) -> str:
        return self._audio_formats.get(user_id, self._default)

    def set_audio_format(self, user_id: int, value: str) -> None:
        if value in AUDIO_FORMATS:
            self._audio_formats[user_id] = value
