@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist venv (
    echo [1/3] Создаю виртуальное окружение...
    python -m venv venv || goto :error
)

rem Папка venv ничего не гарантирует: проверяю, что пакеты реально установлены
venv\Scripts\python.exe -c "import aiogram, yt_dlp, aiohttp, dotenv" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Устанавливаю зависимости...
    venv\Scripts\python.exe -m pip install --upgrade pip -q || goto :error
    venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
) else (
    echo [2/3] Зависимости уже установлены.
)

if not exist .env (
    echo [3/3] Нет файла .env — копирую шаблон.
    copy /y .env.example .env >nul
    echo.
    echo Вставьте токен из @BotFather в строку BOT_TOKEN= и сохраните файл.
    notepad .env
    pause
    goto :eof
)

echo Запускаю бота. Остановка — Ctrl+C.
venv\Scripts\python.exe -m bot
goto :eof

:error
echo.
echo Не удалось подготовить окружение. Проверьте, что Python установлен и добавлен в PATH.
pause
