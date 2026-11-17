"""Утилиты форматирования: размеры, скорость, длительность, прогресс-бар."""

from __future__ import annotations

BAR_FULL = "█"
BAR_EMPTY = "░"

SIZE_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")


def human_bytes(value: float | int | None) -> str:
    """12345678 -> '11.8 МБ'."""
    if not value or value < 0:
        return "0 Б"
    number = float(value)
    for unit in SIZE_UNITS:
        if number < 1024 or unit == SIZE_UNITS[-1]:
            if unit == "Б":
                return f"{int(number)} {unit}"
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} ГБ"


def human_speed(bytes_per_second: float | None) -> str | None:
    """Скорость загрузки в читаемом виде."""
    if not bytes_per_second or bytes_per_second <= 0:
        return None
    return f"{human_bytes(bytes_per_second)}/с"


def human_duration(seconds: float | int | None) -> str:
    """3725 -> '1:02:05', 95 -> '01:35'."""
    if not seconds or seconds < 0:
        return "—"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def render_bar(percent: float, width: int = 14) -> str:
    """Текстовый прогресс-бар: ███████░░░░░░░"""
    clamped = max(0.0, min(100.0, percent))
    filled = int(round(clamped / 100 * width))
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def pluralize_tracks(count: int) -> str:
    """1 трек, 2 трека, 5 треков."""
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} трек"
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return f"{count} трека"
    return f"{count} треков"
