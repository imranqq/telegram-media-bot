"""Обёртка над yt-dlp: анализ ссылки, выбор качества и загрузка файлов."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpError

from bot.config import Settings
from bot.services.formats import (
    MAX_VIDEO_HEIGHT,
    VIDEO_LADDER,
    audio_format_selector,
    audio_postprocessor,
    video_format_selector,
)
from bot.utils.links import Platform

log = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".opus",
    ".ogg",
    ".flac",
    ".wav",
    ".mp4",
    ".webm",
    ".mkv",
    ".mov",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".webp", ".png"}
MAX_THUMBNAIL_BYTES = 190_000

MODE_AUDIO = "audio"
MODE_VIDEO = "video"

# Если каталог плейлиста не влезает в лимит целиком — шлём треки по одному
SAFE_PLAYLIST_VIDEO_HEIGHT = 720


class MediaDownloadError(Exception):
    """Ошибка, текст которой можно показать пользователю."""


class OversizeError(MediaDownloadError):
    """Файл больше лимита Telegram."""

    def __init__(self, size: int, limit: int, height: int | None = None) -> None:
        super().__init__(f"файл {size} байт больше лимита {limit} байт")
        self.size = size
        self.limit = limit
        self.height = height


@dataclass(slots=True)
class DownloadRequest:
    url: str
    platform: Platform
    mode: str = MODE_VIDEO
    audio_format: str = "mp3"
    max_height: int | None = None

    @property
    def is_audio(self) -> bool:
        return self.mode == MODE_AUDIO


@dataclass(slots=True)
class MediaItem:
    path: Path
    title: str
    kind: str
    size: int
    duration: int | None = None
    performer: str | None = None
    thumbnail: Path | None = None
    width: int | None = None
    height: int | None = None

    @property
    def extension(self) -> str:
        return self.path.suffix.lower().lstrip(".")


@dataclass(slots=True)
class DownloadResult:
    items: list[MediaItem]
    workdir: Path
    title: str
    notice: str | None = None
    height: int | None = None

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


class MediaDownloader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------ probe

    async def probe(self, url: str, *, flat: bool = True) -> dict[str, Any]:
        return await asyncio.to_thread(self._probe_sync, url, flat)

    def _probe_sync(self, url: str, flat: bool) -> dict[str, Any]:
        opts = self._base_opts()
        opts["skip_download"] = True
        if flat:
            opts["extract_flat"] = "in_playlist"
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except YtDlpError as exc:
            raise MediaDownloadError(str(exc)) from exc
        if not isinstance(info, dict):
            raise MediaDownloadError("Не удалось прочитать информацию по ссылке")
        return info

    # -------------------------------------------------------------------- run

    async def run(
        self,
        request: DownloadRequest,
        tracker: Any | None = None,
    ) -> DownloadResult:
        self._settings.download_dir.mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(prefix="job_", dir=self._settings.download_dir))
        try:
            info = await self.probe(request.url, flat=True)
            if info.get("_type") != "playlist" and not info.get("formats"):
                # flat-режим не отдал форматы — нужен полный анализ для оценки размера
                info = await self.probe(request.url, flat=False)

            is_playlist = info.get("_type") == "playlist"
            entries = info.get("entries") or []
            if is_playlist and not entries:
                raise MediaDownloadError("Плейлист пуст или скрыт автором")

            notice: str | None = None
            if is_playlist and len(entries) > self._settings.max_playlist_items:
                notice = (
                    f"В коллекции {len(entries)} треков, качаю первые "
                    f"{self._settings.max_playlist_items}."
                )

            if is_playlist:
                height = None
                if not request.is_audio:
                    height = request.max_height or SAFE_PLAYLIST_VIDEO_HEIGHT
            else:
                if request.mode == MODE_VIDEO:
                    self._check_duration(info, request)
                height = self._select_height(info, request)

            items = await asyncio.to_thread(
                self._download_sync, request, workdir, is_playlist, height, tracker
            )
            if not items:
                raise MediaDownloadError("Файлы не получены: ссылка недоступна или удалена")

            if not is_playlist and items[0].size > self._settings.max_upload_bytes:
                raise OversizeError(items[0].size, self._settings.max_upload_bytes, height)

            return DownloadResult(
                items=items,
                workdir=workdir,
                title=info.get("title") or "download",
                notice=notice,
                height=height,
            )
        except BaseException:
            shutil.rmtree(workdir, ignore_errors=True)
            raise

    # --------------------------------------------------------------- quality

    def _check_duration(self, info: dict[str, Any], request: DownloadRequest) -> None:
        if request.mode != MODE_VIDEO:
            return
        duration = info.get("duration") or 0
        if duration and duration > self._settings.max_video_duration:
            limit_min = self._settings.max_video_duration // 60
            raise MediaDownloadError(
                f"Видео длится {int(duration) // 60} мин, лимит бота — {limit_min} мин."
            )

    def _select_height(self, info: dict[str, Any], request: DownloadRequest) -> int | None:
        if request.mode != MODE_VIDEO:
            return None
        if request.max_height:
            return min(request.max_height, MAX_VIDEO_HEIGHT)

        budget = int(self._settings.max_upload_bytes * 0.92)
        formats = info.get("formats") or []
        for height in VIDEO_LADDER:
            size = self._estimate_size(formats, height)
            if size is not None and size <= budget:
                return height
        return VIDEO_LADDER[-1]

    @staticmethod
    def _estimate_size(formats: list[dict[str, Any]], height: int) -> int | None:
        videos = [
            fmt
            for fmt in formats
            if (fmt.get("vcodec") or "none") != "none"
            and (fmt.get("height") or 0)
            and fmt["height"] <= height
        ]
        if not videos:
            return None
        audios = [
            fmt
            for fmt in formats
            if (fmt.get("acodec") or "none") != "none"
            and (fmt.get("vcodec") or "none") == "none"
        ]
        video = max(videos, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
        video_size = video.get("filesize") or video.get("filesize_approx")
        if not video_size:
            return None
        audio_size = 0
        if audios:
            audio = max(audios, key=lambda f: (f.get("abr") or f.get("tbr") or 0))
            audio_size = audio.get("filesize") or audio.get("filesize_approx") or 0
        return int(video_size + audio_size)

    # -------------------------------------------------------------- download

    def _base_opts(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 5,
            "noplaylist": False,
            "consoletitle": False,
        }
        cookies = self._settings.cookies_file
        if cookies and cookies.exists():
            opts["cookiefile"] = str(cookies)
        if self._settings.ffmpeg_location:
            opts["ffmpeg_location"] = self._settings.ffmpeg_location
        client = self._settings.yt_player_client
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": client.split(",")}}
        return opts

    def _download_opts(
        self,
        request: DownloadRequest,
        workdir: Path,
        is_playlist: bool,
        height: int | None,
    ) -> dict[str, Any]:
        opts = self._base_opts()
        template = (
            "%(playlist_index)02d - %(title).100B [%(id)s].%(ext)s"
            if is_playlist
            else "%(title).120B [%(id)s].%(ext)s"
        )
        opts.update(
            {
                "paths": {"home": str(workdir)},
                "outtmpl": {"default": template},
                "noplaylist": not is_playlist,
                "ignoreerrors": "only_download",
                "concurrent_fragment_downloads": 4,
                "writethumbnail": True,
                "trim_file_name": 120,
                "overwrites": True,
                "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg"}],
            }
        )
        if is_playlist:
            opts["playlistend"] = self._settings.max_playlist_items

        if request.is_audio:
            opts["format"] = audio_format_selector()
            opts["postprocessors"].insert(0, audio_postprocessor(request.audio_format))
        else:
            opts["format"] = video_format_selector(height or MAX_VIDEO_HEIGHT)
            opts["merge_output_format"] = "mp4"
        return opts

    def _download_sync(
        self,
        request: DownloadRequest,
        workdir: Path,
        is_playlist: bool,
        height: int | None,
        tracker: Any | None = None,
    ) -> list[MediaItem]:
        opts = self._download_opts(request, workdir, is_playlist, height)
        if tracker is not None:
            opts["progress_hooks"] = [tracker.hook]
            opts["postprocessor_hooks"] = [tracker.postprocessor_hook]

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
        except YtDlpError as exc:
            raise MediaDownloadError(str(exc)) from exc

        entries = (info or {}).get("entries") if (info or {}).get("_type") == "playlist" else [info]
        items: list[MediaItem] = []
        used: set[Path] = set()
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            path = self._resolve_path(entry, workdir, used)
            if path is None:
                log.warning("Не найден файл для %s", entry.get("title"))
                continue
            used.add(path)
            items.append(self._build_item(path, entry, request, workdir))
        return items

    # ------------------------------------------------------------ file lookup

    def _resolve_path(
        self,
        entry: dict[str, Any],
        workdir: Path,
        used: set[Path],
    ) -> Path | None:
        for download in entry.get("requested_downloads") or ():
            if not isinstance(download, dict):
                continue
            for key in ("filepath", "_filename"):
                candidate = self._existing(download.get(key), used)
                if candidate:
                    return candidate

        for key in ("filepath", "_filename"):
            candidate = self._existing(entry.get(key), used)
            if candidate:
                return candidate

        video_id = entry.get("id")
        if video_id:
            for path in workdir.iterdir():
                if path in used or path.suffix.lower() not in MEDIA_EXTENSIONS:
                    continue
                if f"[{video_id}]" in path.name:
                    return path
        return None

    @staticmethod
    def _existing(raw: str | None, used: set[Path]) -> Path | None:
        if not raw:
            return None
        candidate = Path(raw)
        if candidate in used or not candidate.is_file():
            return None
        if candidate.suffix.lower() not in MEDIA_EXTENSIONS:
            return None
        return candidate

    def _build_item(
        self,
        path: Path,
        entry: dict[str, Any],
        request: DownloadRequest,
        workdir: Path,
    ) -> MediaItem:
        duration = entry.get("duration")
        return MediaItem(
            path=path,
            title=(entry.get("title") or path.stem)[:180],
            kind=MODE_AUDIO if request.is_audio else MODE_VIDEO,
            size=path.stat().st_size,
            duration=int(duration) if duration else None,
            performer=self._performer(entry),
            thumbnail=self._find_thumbnail(workdir, path, entry.get("id")),
            width=entry.get("width"),
            height=entry.get("height"),
        )

    @staticmethod
    def _performer(entry: dict[str, Any]) -> str | None:
        for key in ("artist", "creator", "uploader", "channel"):
            value = entry.get(key)
            if value:
                return str(value)[:120]
        return None

    @staticmethod
    def _find_thumbnail(workdir: Path, media_path: Path, video_id: str | None) -> Path | None:
        prefix = media_path.stem[:40]
        candidates = [
            path
            for path in workdir.iterdir()
            if path.suffix.lower() in IMAGE_EXTENSIONS
            and (path.stem.startswith(prefix) or (video_id and f"[{video_id}]" in path.name))
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda p: p.stat().st_size)
        if best.suffix.lower() not in {".jpg", ".jpeg"}:
            return None
        if best.stat().st_size > MAX_THUMBNAIL_BYTES:
            return None
        return best
