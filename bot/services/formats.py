"""Форматы yt-dlp: только звук, видео бот не отдаёт."""

from __future__ import annotations

AUDIO_FORMATS: tuple[str, ...] = ("mp3", "orig")
AUDIO_LABELS: dict[str, str] = {
    "mp3": "MP3 320 kbps",
    "orig": "Оригинал без перекодирования",
}
AUDIO_SHORT_LABELS: dict[str, str] = {
    "mp3": "MP3 320",
    "orig": "Оригинал",
}

MP3_BITRATE = "320"


def audio_format_selector() -> str:
    """Лучшая аудиодорожка источника."""
    return "bestaudio/best"


def audio_postprocessor(audio_format: str) -> dict[str, str]:
    """Постпроцессор аудио: перекодирование в MP3 320 или сохранение оригинального кодека."""
    if audio_format == "mp3":
        return {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": MP3_BITRATE,
        }
    return {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "best",
        "preferredquality": "0",
    }


def label_for_audio(audio_format: str) -> str:
    return AUDIO_LABELS.get(audio_format, AUDIO_LABELS["mp3"])
