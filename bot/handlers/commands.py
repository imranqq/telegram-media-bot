"""Команды /start, /help, /format."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot.config import Settings
from bot.keyboards.inline import format_keyboard
from bot.services.formats import AUDIO_LABELS
from bot.services.preferences import Preferences
from bot.utils.telegram import NO_PREVIEW

router = Router(name="commands")

START_TEXT = (
    "<b>Скачиваю музыку и видео по ссылке</b>\n\n"
    "SoundCloud — трек или целый сет\n"
    "YouTube — видео в MP4, до 1080p\n\n"
    "Пришлите ссылку одним сообщением. Формат звука выбирается кнопкой ниже."
)


def build_help(settings: Settings) -> str:
    lines = [
        "<b>Как пользоваться</b>",
        "1. Скопируйте ссылку на трек, видео или плейлист.",
        "2. Отправьте её боту.",
        "3. Дождитесь файла — прогресс виден в сообщении.",
        "",
        "<b>Команды</b>",
        "/format mp3 — перекодировать звук в MP3 320 kbps",
        "/format orig — отдать исходный файл без перекодирования",
        "/help — эта справка",
        "",
        "<b>Ограничения</b>",
        f"Размер файла: {settings.max_upload_mb} МБ",
        f"Плейлист: до {settings.max_playlist_items} треков",
        f"Длительность видео: до {settings.max_video_duration // 60} мин",
        f"Одновременных загрузок: {settings.max_concurrent_downloads}",
    ]
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, prefs: Preferences) -> None:
    await message.answer(
        START_TEXT,
        reply_markup=format_keyboard(prefs.audio_format(message.from_user.id)),
        link_preview_options=NO_PREVIEW,
    )


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    await message.answer(build_help(settings), link_preview_options=NO_PREVIEW)


@router.message(Command("format"))
async def cmd_format(
    message: Message,
    command: CommandObject,
    prefs: Preferences,
) -> None:
    user_id = message.from_user.id
    argument = (command.args or "").strip().lower()

    if argument not in AUDIO_LABELS:
        current = prefs.audio_format(user_id)
        await message.answer(
            f"Формат звука: <b>{AUDIO_LABELS[current]}</b>\n\n"
            "/format mp3 — MP3 320 kbps\n"
            "/format orig — оригинальный файл",
            reply_markup=format_keyboard(current),
            link_preview_options=NO_PREVIEW,
        )
        return

    prefs.set_audio_format(user_id, argument)
    await message.answer(
        f"Готово. SoundCloud будет приходить как <b>{AUDIO_LABELS[argument]}</b>.",
        reply_markup=format_keyboard(argument),
        link_preview_options=NO_PREVIEW,
    )
