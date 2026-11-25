"""Разбор ссылок: определяем платформу и тип контента."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING_JUNK = ".,;:!?)]}>»\"'"

YOUTUBE_HOSTS = {
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "music.youtube.com",
}
SOUNDCLOUD_HOSTS = {
    "soundcloud.com",
    "on.soundcloud.com",
    "soundcloud.app.goo.gl",
}
SPOTIFY_HOSTS = {
    "open.spotify.com",
    "play.spotify.com",
}

SPOTIFY_TRACK_PATH = re.compile(r"/(?:intl-[a-z-]+/)?track/([A-Za-z0-9]+)")
SPOTIFY_URI = re.compile(r"spotify:track:([A-Za-z0-9]+)")


class Platform(str, Enum):
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"
    SPOTIFY = "spotify"


@dataclass(frozen=True, slots=True)
class MediaLink:
    url: str
    platform: Platform
    likely_playlist: bool
    spotify_id: str | None = None


def _normalize_host(host: str) -> str:
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    return host


def _matches(host: str, known: set[str]) -> bool:
    return any(host == item or host.endswith("." + item) for item in known)


def extract_url(text: str) -> str | None:
    """Достаёт первую ссылку из сообщения и срезает хвостовую пунктуацию."""
    match = URL_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(TRAILING_JUNK)


def parse_link(text: str) -> MediaLink | None:
    """Возвращает описание ссылки или None, если ссылка не поддерживается."""
    raw_text = text or ""

    # Spotify можно прислать и внутренним URI: spotify:track:ID
    uri = SPOTIFY_URI.search(raw_text)
    if uri:
        track_id = uri.group(1)
        return MediaLink(
            url=f"https://open.spotify.com/track/{track_id}",
            platform=Platform.SPOTIFY,
            likely_playlist=False,
            spotify_id=track_id,
        )

    raw = extract_url(raw_text)
    if not raw:
        return None

    parsed = urlparse(raw)
    host = _normalize_host(parsed.netloc or "")
    if not host:
        return None

    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()

    if _matches(host, YOUTUBE_HOSTS):
        is_playlist = "list=" in query or path.startswith("/playlist")
        return MediaLink(url=raw, platform=Platform.YOUTUBE, likely_playlist=is_playlist)

    if _matches(host, SOUNDCLOUD_HOSTS):
        is_playlist = "/sets/" in path or "/albums/" in path
        return MediaLink(url=raw, platform=Platform.SOUNDCLOUD, likely_playlist=is_playlist)

    if _matches(host, SPOTIFY_HOSTS):
        track = SPOTIFY_TRACK_PATH.search(parsed.path or "")
        track_id = track.group(1) if track else None
        return MediaLink(
            url=raw,
            platform=Platform.SPOTIFY,
            likely_playlist=track_id is None,
            spotify_id=track_id,
        )

    return None
