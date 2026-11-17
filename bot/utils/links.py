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
    "soundcloud.app.goog.gl",
    "soundcloud.app.goo.gl",
}


class Platform(str, Enum):
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"


@dataclass(frozen=True, slots=True)
class MediaLink:
    url: str
    platform: Platform
    likely_playlist: bool


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
    raw = extract_url(text)
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

    return None
