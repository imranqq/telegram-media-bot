"""Форматы yt-dlp: селекторы качества и подписи."""

from __future__ import annotations

# Доступные разрешения для видео (по убыванию)
VIDEO_LADDER: tuple[int, ...] = (1080, 720, 480, 360)
MAX_VIDEO_HEIGHT = VIDEO_LADDER[0]

# Аудио-форматы для SoundCloud
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


def video_format_selector(height: int) -> str:
    """Селектор лучшего видео не выше height с приоритетом H.264 + AAC в MP4."""
    return (
        f"bestvideo[height<={height}][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}]/best"
    )


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


def label_for_video(height: int | None) -> str:
    if not height:
        return "лучшее качество"
    return f"до {height}p"
