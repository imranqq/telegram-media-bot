"""Конфигурация бота из переменных окружения."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_UPLOAD_MB = 50
CLOUD_API_BASE = "https://api.telegram.org"
WEBHOOK_PATH = "/webhook"


def _get(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _int(name: str, default: int) -> int:
    raw = _get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _path(name: str) -> Path | None:
    raw = _get(name)
    return Path(raw).expanduser() if raw else None


def _webhook_secret(token: str) -> str:
    """Стабильный секрет для заголовка X-Telegram-Bot-Api-Secret-Token.

    Telegram присылает его с каждым апдейтом, бот сверяет — так на /webhook не может
    постучаться кто угодно. Из токена, чтобы не заводить ещё одну переменную.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def load_dotenv_file() -> None:
    """Подхватываем .env при локальном запуске. На Render переменные приходят из окружения."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # библиотека опциональна
        return
    load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    """Все настройки приложения в одном неизменяемом объекте."""

    bot_token: str
    api_base: str
    max_upload_bytes: int
    download_dir: Path
    ffmpeg_location: str | None
    cookies_file: Path | None
    max_concurrent_downloads: int
    max_playlist_items: int
    max_video_duration: int
    job_timeout: int
    default_audio_format: str
    default_video_height: int
    yt_player_client: str | None
    port: int
    log_level: str
    webhook_base: str | None
    webhook_secret: str

    @property
    def uses_local_api(self) -> bool:
        return self.api_base.rstrip("/") != CLOUD_API_BASE

    @property
    def uses_webhook(self) -> bool:
        return bool(self.webhook_base)

    @property
    def webhook_url(self) -> str | None:
        return f"{self.webhook_base}{WEBHOOK_PATH}" if self.webhook_base else None

    @property
    def max_upload_mb(self) -> int:
        return self.max_upload_bytes // (1024 * 1024)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv_file()
        token = _get("BOT_TOKEN")
        if not token:
            raise RuntimeError(
                "Не задан BOT_TOKEN. Скопируйте .env.example в .env и вставьте токен из @BotFather."
            )

        audio_format = (_get("DEFAULT_AUDIO_FORMAT") or "mp3").lower()
        if audio_format not in {"mp3", "orig"}:
            audio_format = "mp3"

        return cls(
            bot_token=token,
            api_base=(_get("TELEGRAM_API_BASE") or CLOUD_API_BASE).rstrip("/"),
            max_upload_bytes=max(1, _int("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)) * 1024 * 1024,
            download_dir=_path("DOWNLOAD_DIR") or Path("/tmp/telegram_media_bot"),
            ffmpeg_location=_get("FFMPEG_LOCATION"),
            cookies_file=_path("COOKIES_FILE"),
            max_concurrent_downloads=max(1, _int("MAX_CONCURRENT_DOWNLOADS", 2)),
            max_playlist_items=max(1, _int("MAX_PLAYLIST_ITEMS", 25)),
            max_video_duration=max(60, _int("MAX_VIDEO_DURATION_MIN", 60) * 60),
            job_timeout=max(120, _int("JOB_TIMEOUT_MIN", 30) * 60),
            default_audio_format=audio_format,
            default_video_height=max(144, _int("DEFAULT_VIDEO_HEIGHT", 1080)),
            yt_player_client=_get("YT_PLAYER_CLIENT"),
            port=_int("PORT", 8080),
            log_level=(_get("LOG_LEVEL") or "INFO").upper(),
            # Render сам подставляет RENDER_EXTERNAL_URL — webhook включается без настройки
            webhook_base=(_get("WEBHOOK_URL") or _get("RENDER_EXTERNAL_URL") or "").rstrip("/")
            or None,
            webhook_secret=_webhook_secret(token),
        )
