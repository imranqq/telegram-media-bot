"""Метаданные трека Spotify без официального API и ключей.

Основной источник — embed-страница трека: в её `__NEXT_DATA__` лежит название,
исполнители и длительность. oEmbed даёт обложку, которой в embed нет.

Сам Spotify аудиофайлы не отдаёт (DRM), поэтому название и исполнитель нужны
только для поиска этого трека на YouTube.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

OEMBED_ENDPOINT = "https://open.spotify.com/oembed"
EMBED_PAGE = "https://open.spotify.com/embed/track/{track_id}"
TIMEOUT = aiohttp.ClientTimeout(total=20)
COVER_LIMIT = 190_000
COVER_NAME = "spotify_cover.jpg"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
NOISE = re.compile(r"\s*[|\-–]\s*(song and lyrics by .*|Spotify)\s*$", re.I)


class SpotifyError(Exception):
    """Не удалось разобрать трек Spotify."""


@dataclass(slots=True)
class TrackMeta:
    title: str
    artist: str | None = None
    thumbnail_url: str | None = None
    duration: int | None = None

    @property
    def search_query(self) -> str:
        """Запрос для поиска на YouTube: «Artist - Title», иначе просто название."""
        return f"{self.artist} - {self.title}" if self.artist else self.title


async def resolve(session: aiohttp.ClientSession, *, track_url: str, track_id: str) -> TrackMeta:
    """Собирает название, исполнителя, длительность и обложку по ссылке на трек."""
    title, artist, duration = await _embed_meta(session, track_id)
    oembed_title, thumbnail = await _oembed(session, track_url)

    title = _clean(title) or _clean(oembed_title) or track_id
    if not title:
        raise SpotifyError("Не удалось прочитать название трека Spotify")
    return TrackMeta(
        title=title,
        artist=_clean(artist),
        thumbnail_url=thumbnail,
        duration=duration,
    )


async def download_cover(
    session: aiohttp.ClientSession,
    url: str | None,
    workdir: Path,
) -> Path | None:
    """Скачивает обложку, чтобы приложить её к аудио в Telegram."""
    if not url:
        return None
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as response:
            if response.status != 200:
                return None
            payload = await response.read()
    except Exception as exc:  # noqa: BLE001 - обложка не критична
        log.debug("Spotify cover failed: %s", exc)
        return None

    if not payload or len(payload) > COVER_LIMIT:
        return None
    path = workdir / COVER_NAME
    path.write_bytes(payload)
    return path


async def _embed_meta(
    session: aiohttp.ClientSession,
    track_id: str,
) -> tuple[str | None, str | None, int | None]:
    """Название, исполнители и длительность из __NEXT_DATA__ embed-страницы."""
    try:
        async with session.get(
            EMBED_PAGE.format(track_id=track_id),
            headers=HEADERS,
            timeout=TIMEOUT,
        ) as response:
            if response.status != 200:
                log.debug("Spotify embed HTTP %s", response.status)
                return None, None, None
            page = await response.text()
    except Exception as exc:  # noqa: BLE001
        log.debug("Spotify embed failed: %s", exc)
        return None, None, None

    script = NEXT_DATA.search(page)
    if not script:
        log.debug("Spotify embed без __NEXT_DATA__")
        return None, None, None

    try:
        payload = json.loads(script.group(1))
    except ValueError:
        log.debug("Spotify embed: битый JSON")
        return None, None, None

    entity = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("state", {})
        .get("data", {})
        .get("entity", {})
    )
    if not isinstance(entity, dict):
        return None, None, None

    artists = [
        str(item.get("name"))
        for item in entity.get("artists") or []
        if isinstance(item, dict) and item.get("name")
    ]
    duration_ms = entity.get("duration")
    duration = int(duration_ms) // 1000 if isinstance(duration_ms, (int, float)) else None

    return (
        entity.get("name") or entity.get("title"),
        ", ".join(artists) or None,
        duration or None,
    )


async def _oembed(session: aiohttp.ClientSession, url: str) -> tuple[str | None, str | None]:
    try:
        async with session.get(
            OEMBED_ENDPOINT,
            params={"url": url},
            headers=HEADERS,
            timeout=TIMEOUT,
        ) as response:
            if response.status != 200:
                log.debug("Spotify oEmbed HTTP %s", response.status)
                return None, None
            data = await response.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        log.debug("Spotify oEmbed failed: %s", exc)
        return None, None
    return data.get("title"), data.get("thumbnail_url")


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value).strip()
    text = NOISE.sub("", text).strip()
    return text or None
