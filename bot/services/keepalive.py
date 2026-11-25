"""Самопинг: не даёт free-плану Render усыпить контейнер.

Render останавливает free-инстанс, если 15 минут не было входящих HTTP-запросов.
Опрос Telegram (или webhook в простое) входящим трафиком не считается, поэтому бот
периодически дёргает собственный /health через публичный адрес. Запрос идёт наружу
и возвращается через прокси Render, то есть для платформы это обычный входящий трафик.

Работает только когда известен публичный адрес (в облаке — RENDER_EXTERNAL_URL).
Локально и при KEEPALIVE_MIN=0 не запускается.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

PING_TIMEOUT = aiohttp.ClientTimeout(total=90)


class SelfPinger:
    """Раз в interval секунд дёргает {base_url}/health, чтобы сервис не засыпал."""

    def __init__(self, base_url: str, interval: int = 600) -> None:
        self._url = f"{base_url.rstrip('/')}/health"
        self._interval = max(60, interval)

    @property
    def url(self) -> str:
        return self._url

    async def run(self) -> None:
        log.info("Самопинг каждые %s с → %s", self._interval, self._url)
        # Даём приложению подняться, прежде чем стучаться в собственный health
        await asyncio.sleep(min(60, self._interval))
        async with aiohttp.ClientSession(timeout=PING_TIMEOUT) as session:
            while True:
                try:
                    async with session.get(self._url) as response:
                        if response.status != 200:
                            log.warning("Самопинг: HTTP %s", response.status)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - сеть может моргать
                    log.debug("Самопинг не удался: %s", exc)
                await asyncio.sleep(self._interval)
