"""Роутеры бота."""

from aiogram import Dispatcher

from bot.handlers import commands, media

__all__ = ["commands", "media", "setup_routers"]


def setup_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(commands.router)
    dispatcher.include_router(media.router)
