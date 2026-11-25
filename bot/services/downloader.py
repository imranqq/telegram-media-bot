"""Обёртка над yt-dlp: анализ ссылки и загрузка аудио.

Поддерживаются SoundCloud (трек или сет), YouTube (звук из видео) и Spotify
(метаданные трека подставляются в поиск по YouTube, потому что сам Spotify
не отдаёт аудиофайлы).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpError

from bot.config import Settings
from bot.services import spotify
from bot.services.formats import audio_format_selector, audio_postprocessor
from bot.utils.links import Platform

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".opus",
    ".ogg",
    ".flac",
    ".wav",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".webp", ".png"}
MAX_THUMBNAIL_BYTES = 190_000
MEDIA_LIMIT_HINT = "Пришлите трек покороче или переключите формат звука на «Оригинал»."


class MediaDownloadError(Exception):
    """Ошибка, текст которой можно показать пользователю."""


class OversizeError(MediaDownloadError):
    """Файл больше лимита Telegram."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"файл {size} байт больше лимита {limit} байт")
        self.size = size
        self.limit = limit


@dataclass(slots=True)
class DownloadRequest:
    url: str
    platform: Platform
    audio_format: str = "mp3"
    spotify_id: str | None = None


@dataclass(slots=True)
class MediaItem:
    path: Path
    title: str
    size: int
    duration: int | None = None
    performer: str | None = None
    thumbnail: Path | None = None

    @property
    def extension(self) -> str:
        return self.path.suffix.lower().lstrip(".")


@dataclass(slots=True)
class DownloadResult:
    items: list[MediaItem]
    workdir: Path
    title: str
    notice: str | None = None

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
            async with aiohttp.ClientSession() as session:
                target, meta = await self._resolve_target(session, request)

                info = await self.probe(target, flat=True)
                if info.get("_type") != "playlist" and not info.get("formats"):
                    # flat-режим не отдал форматы — нужен полный анализ
                    info = await self.probe(target, flat=False)

                is_playlist = info.get("_type") == "playlist"
                entries = info.get("entries") or []
                if is_playlist and not entries:
                    raise MediaDownloadError("Плейлист пуст или скрыт автором")
                if not is_playlist:
                    self._check_duration(info)

                notice: str | None = None
                take = min(len(entries), self._settings.max_playlist_items) if is_playlist else 1
                if is_playlist:
                    log.info(
                        "playlist %s: %s элементов, берём %s", request.url, len(entries), take
                    )
                    if tracker is not None and hasattr(tracker, "set_playlist_total"):
                        tracker.set_playlist_total(take)
                    if len(entries) > self._settings.max_playlist_items:
                        notice = (
                            f"В коллекции {len(entries)} треков, качаю первые "
                            f"{self._settings.max_playlist_items}."
                        )

                # Поиск yt-dlp отдаёт результат как одноэлементный плейлист, поэтому
                # noplaylist для Spotify трогать нельзя, но нумерация треков не нужна
                playlist_download = is_playlist or request.platform is Platform.SPOTIFY
                items = await asyncio.to_thread(
                    self._download_sync,
                    request,
                    workdir,
                    is_playlist,
                    playlist_download,
                    target,
                    tracker,
                )
                if not items:
                    raise MediaDownloadError("Файлы не получены: ссылка недоступна или удалена")

                if meta is not None:
                    await self._apply_spotify_meta(session, items[0], meta, workdir)

                if len(items) == 1 and items[0].size > self._settings.max_upload_bytes:
                    raise OversizeError(items[0].size, self._settings.max_upload_bytes)

                title = meta.title if meta is not None else (info.get("title") or "download")
                return DownloadResult(
                    items=items,
                    workdir=workdir,
                    title=title,
                    notice=notice,
                )
        except BaseException:
            shutil.rmtree(workdir, ignore_errors=True)
            raise

    # ------------------------------------------------------------ spotify glue

    async def _resolve_target(
        self,
        session: aiohttp.ClientSession,
        request: DownloadRequest,
    ) -> tuple[str, spotify.TrackMeta | None]:
        """Возвращает то, что реально пойдёт в yt-dlp, и метаданные Spotify, если они есть."""
        if request.platform is not Platform.SPOTIFY:
            return request.url, None

        if not request.spotify_id:
            raise MediaDownloadError(
                "Поддерживаются только ссылки на отдельный трек Spotify. "
                "Альбомы и плейлисты пока не разворачиваю."
            )

        try:
            meta = await spotify.resolve(
                session, track_url=request.url, track_id=request.spotify_id
            )
        except spotify.SpotifyError as exc:
            raise MediaDownloadError(str(exc)) from exc

        query = f"ytsearch1:{meta.search_query}"
        log.info("spotify %s → «%s»", request.spotify_id, meta.search_query)
        return query, meta

    async def _apply_spotify_meta(
        self,
        session: aiohttp.ClientSession,
        item: MediaItem,
        meta: spotify.TrackMeta,
        workdir: Path,
    ) -> None:
        item.title = meta.title
        item.performer = meta.artist
        if meta.duration:
            # Длительность из Spotify точнее, чем из найденного видео
            item.duration = meta.duration
        cover = await spotify.download_cover(session, meta.thumbnail_url, workdir)
        if cover is not None:
            item.thumbnail = cover

    # --------------------------------------------------------------- quality

    def _check_duration(self, info: dict[str, Any]) -> None:
        duration = info.get("duration") or 0
        if duration and duration > self._settings.max_audio_duration:
            limit_min = self._settings.max_audio_duration // 60
            raise MediaDownloadError(
                f"Трек длится {int(duration) // 60} мин, лимит бота — {limit_min} мин."
            )

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
        playlist_download: bool,
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
                "noplaylist": not playlist_download,
                "ignoreerrors": "only_download",
                "concurrent_fragment_downloads": 4,
                "writethumbnail": True,
                "trim_file_name": 120,
                "overwrites": True,
                "format": audio_format_selector(),
                "postprocessors": [
                    audio_postprocessor(request.audio_format),
                    {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
                ],
            }
        )
        if is_playlist:
            opts["playlistend"] = self._settings.max_playlist_items
        return opts

    def _download_sync(
        self,
        request: DownloadRequest,
        workdir: Path,
        is_playlist: bool,
        playlist_download: bool,
        target: str,
        tracker: Any | None = None,
    ) -> list[MediaItem]:
        opts = self._download_opts(request, workdir, is_playlist, playlist_download)
        if tracker is not None:
            opts["progress_hooks"] = [tracker.hook]
            opts["postprocessor_hooks"] = [tracker.postprocessor_hook]

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=True)
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
            items.append(self._build_item(path, entry, workdir))
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
                if path in used or path.suffix.lower() not in AUDIO_EXTENSIONS:
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
        if candidate.suffix.lower() not in AUDIO_EXTENSIONS:
            return None
        return candidate

    def _build_item(
        self,
        path: Path,
        entry: dict[str, Any],
        workdir: Path,
    ) -> MediaItem:
        duration = entry.get("duration")
        return MediaItem(
            path=path,
            title=(entry.get("title") or path.stem)[:180],
            size=path.stat().st_size,
            duration=int(duration) if duration else None,
            performer=self._performer(entry),
            thumbnail=self._find_thumbnail(workdir, path, entry.get("id")),
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
