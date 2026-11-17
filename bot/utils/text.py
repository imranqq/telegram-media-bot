"""Тексты сообщений и перевод ошибок yt-dlp на человеческий язык."""

from __future__ import annotations

import html

ERROR_HINTS: tuple[tuple[str, str], ...] = (
    (
        "sign in to confirm you're not a bot",
        "YouTube требует подтверждения, что запрос не от бота.\n"
        "Нужно добавить cookies.txt (инструкция в README, переменная COOKIES_FILE).",
    ),
    (
        "confirm your age",
        "Видео с возрастным ограничением: без cookies.txt его не скачать.",
    ),
    (
        "private video",
        "Это приватное видео, доступ есть только по приглашению автора.",
    ),
    (
        "members-only",
        "Видео доступно только участникам канала.",
    ),
    (
        "this video is unavailable",
        "Видео недоступно: удалено или скрыто автором.",
    ),
    (
        "video unavailable",
        "Видео недоступно: удалено, скрыто или заблокировано в регионе сервера.",
    ),
    (
        "not available in your country",
        "Видео заблокировано в регионе, где работает сервер.",
    ),
    (
        "unsupported url",
        "Ссылка не поддерживается. Нужна ссылка на трек SoundCloud или видео YouTube.",
    ),
    (
        "requested format is not available",
        "У этого видео нет подходящего формата — попробуйте другое качество.",
    ),
    (
        "http error 403",
        "Источник отклонил запрос (403). Обычно помогает обновление yt-dlp или свежие cookies.",
    ),
    (
        "http error 429",
        "Источник ограничил частоту запросов. Подождите пару минут.",
    ),
    (
        "ffmpeg",
        "Ошибка ffmpeg. Проверьте, что ffmpeg установлен и доступен (переменная FFMPEG_LOCATION).",
    ),
    (
        "unable to download webpage",
        "Не удалось открыть страницу. Проверьте ссылку или повторите позже.",
    ),
)


def humanize_error(exc: Exception) -> str:
    raw = str(exc).strip()
    lowered = raw.lower()
    for needle, hint in ERROR_HINTS:
        if needle in lowered:
            return hint
    snippet = html.escape(raw)[:280]
    if not snippet:
        return "Не удалось скачать файл. Попробуйте другую ссылку."
    return f"Не удалось скачать.\n<code>{snippet}</code>"


def escape(value: str) -> str:
    return html.escape(value, quote=False)
