# Telegram Media Bot

Бот для скачивания музыки из **SoundCloud** и видео с **YouTube** по ссылке.

## Что умеет

| Источник | Что получите |
| --- | --- |
| SoundCloud трек | MP3 320 kbps **или** оригинальный файл без перекодирования |
| SoundCloud сет / альбом | все треки: ZIP-архивом, если влезает в лимит, иначе по одному |
| YouTube видео | MP4 (H.264 + AAC) до 1080p, со звуком в одной дорожке |

Дополнительно:

- живой прогресс-бар в сообщении: проценты, мегабайты, скорость, ETA;
- очередь загрузок: несколько задач одновременно, запросы одного пользователя выполняются последовательно;
- автоматический подбор качества под лимит файла — если 1080p не влезает, бот сам берёт 720p;
- кнопки «720p / 480p / 360p», если файл всё же оказался больше лимита;
- понятные тексты ошибок: приватное видео, возрастное ограничение, блокировка по региону, требование cookies;
- обложки треков подтягиваются и отправляются вместе с аудио.

## Быстрый старт (Windows)

### 1. ffmpeg

Без ffmpeg не будет ни склейки видео со звуком, ни MP3. Скачайте сборку с
[gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (`ffmpeg-release-essentials.zip`), распакуйте, например, в `C:\ffmpeg`,
и укажите в `.env`:

```env
FFMPEG_LOCATION=C:\ffmpeg\bin\ffmpeg.exe
```

Либо добавьте `C:\ffmpeg\bin` в `PATH` и оставьте переменную пустой.

### 2. Зависимости

```powershell
cd C:\Users\COMP_ING\projects\telegram-media-bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Настройки

```powershell
Copy-Item .env.example .env
```

Впишите в `.env` токен из [@BotFather](https://t.me/BotFather):

```env
BOT_TOKEN=123456789:AA...
DOWNLOAD_DIR=C:\Users\COMP_ING\media-bot-tmp
```

### 4. Запуск

```powershell
.\venv\Scripts\python.exe -m bot
```

В логе появится `Бот запущен · лимит файла 50 МБ`. Откройте бота в Telegram, отправьте ссылку.

Всё то же самое делает `run.bat` двойным кликом: создаёт `venv`, если его нет, проверяет
наличие пакетов (а не только папки) и доустанавливает их, при отсутствии `.env` копирует
шаблон и открывает его в блокноте.

> Локальный `venv` собран на Python 3.14, а в контейнере Render используется 3.11.
> Обе версии работают, но если появится странная ошибка зависимостей — пересоздайте
> окружение на 3.11–3.12, тест тогда будет ближе к проду.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `BOT_TOKEN` | — | Токен бота, обязателен |
| `TELEGRAM_API_BASE` | облачный API | Адрес Bot API; пусто = `https://api.telegram.org` |
| `MAX_UPLOAD_MB` | `50` | Лимит файла; `2000` для локального Bot API |
| `DOWNLOAD_DIR` | `/tmp/telegram_media_bot` | Временный каталог, чистится после отправки |
| `FFMPEG_LOCATION` | из `PATH` | Путь к `ffmpeg.exe` / `ffmpeg` |
| `COOKIES_FILE` | — | `cookies.txt` для YouTube |
| `MAX_CONCURRENT_DOWNLOADS` | `2` | Параллельных загрузок (на free-плане Render ставьте `1`) |
| `MAX_PLAYLIST_ITEMS` | `25` | Сколько треков брать из сета (на Render — `10`) |
| `MAX_VIDEO_DURATION_MIN` | `60` | Максимальная длительность видео в минутах |
| `JOB_TIMEOUT_MIN` | `30` | Предохранитель: через сколько минут задача прерывается |
| `DEFAULT_VIDEO_HEIGHT` | `1080` | Потолок качества видео |
| `DEFAULT_AUDIO_FORMAT` | `mp3` | `mp3` или `orig` |
| `YT_PLAYER_CLIENT` | по умолчанию yt-dlp | Например `android,web_safari`, если YouTube просит подтвердить «я не робот» |
| `PORT` | `8080` | Порт healthcheck |
| `LOG_LEVEL` | `INFO` | `DEBUG` для разбора проблем |

## Деплой на Render

Код уже в репозитории [imranqq/telegram-media-bot](https://github.com/imranqq/telegram-media-bot),
ветка `main`. Render собирает Docker-образ по `render.yaml`: там заданы план Free, регион Frankfurt,
healthcheck `/` и лимиты под 512 МБ RAM.

Создание сервиса (один раз):

1. Откройте <https://dashboard.render.com/blueprints> и нажмите **New Blueprint Instance**.
2. **Connect a repository** → `telegram-media-bot`. Если репозитория нет в списке, нажмите
   **Configure account** и дайте Render доступ к нему через GitHub App.
3. Branch — `main`, Blueprint Path — `render.yaml`.
4. Render покажет сервис `telegram-media-bot`: Docker, Free, Frankfurt. В поле `BOT_TOKEN`
   вставьте токен из @BotFather (`sync: false` означает, что значение спрашивают при создании).
5. **Apply**. Сборка занимает 5–8 минут: apt ставит ffmpeg, pip — зависимости.
6. В логах появится `Healthcheck слушает 0.0.0.0:8080/health` и `Run polling for bot @…`.
   Адрес сервиса — `https://<имя>-xxxx.onrender.com`, проверка — `/health`.

Если Blueprint не подхватился, сервис создаётся вручную: **New → Web Service**,
репозиторий `telegram-media-bot`, Runtime **Docker**, Dockerfile Path `Dockerfile`,
Plan **Free**, Region **Frankfurt**, Health Check Path `/`, переменная `BOT_TOKEN`.

Дальше каждый `git push` в `main` деплоится сам — в `render.yaml` стоит `autoDeploy: true`.

### Бот 24/7 на free-плане

Free-план усыпляет контейнер через 15 минут без HTTP-трафика, и бот перестаёт забирать
сообщения из Telegram. В репозитории лежит `.github/workflows/keepalive.yml`: он каждые
10 минут дёргает `/health` и держит сервис живым, без платного плана.

1. Скопируйте адрес сервиса.
2. GitHub → репозиторий → **Settings → Secrets and variables → Actions → Variables →
   New repository variable**. Имя `RENDER_URL`, значение — адрес без слэша на конце.
3. Проверка: **Actions → Keep-alive → Run workflow**.

То же самое из терминала:

```powershell
gh variable set RENDER_URL --body "https://<service>.onrender.com"
```

Первый запрос после долгого простоя всё равно ждёт ~50 секунд: это холодный старт контейнера.
Платный план ($7/мес) убирает сон полностью.

### Что важно помнить про Render

- **Диск эфемерный.** Файлы живут в `/tmp` и удаляются сразу после отправки, кэша между
  деплоями нет.
- **512 МБ RAM.** Поэтому качество видео в `render.yaml` снижено до 720p, одновременных
  загрузок — одна. На аудио с SoundCloud это не влияет.
- **Один экземпляр.** Бот работает через long polling: если запустить его одновременно локально
  и на Render, Telegram отдаст апдейты только одному, второй получит `409 Conflict`.

## Лимит 50 МБ и локальный Bot API

Облачной Bot API запрещено отдавать боту файлы больше 50 МБ — это ограничение Telegram,
а не бота. Варианты:

- **Бот сам понижает качество.** Уже реализовано: качество подбирается по оценке размера,
  а если файл всё же больше — приходит сообщение с кнопками «720p / 480p / 360p».
- **Свой Bot API server** (лимит 2000 МБ). Нужен VPS: соберите
  [telegram-bot-api](https://github.com/tdlib/telegram-bot-api), запустите и укажите

  ```env
  TELEGRAM_API_BASE=http://localhost:8081
  MAX_UPLOAD_MB=2000
  ```

  Так же поднимается `local`-режим для тестов без ограничений по размеру.

## YouTube просит cookies

Если в логах `Sign in to confirm you're not a bot` — YouTube не доверяет IP сервера.
Решение: экспортировать cookies из браузера расширением *Get cookies.txt LOCALLY*, положить
файл рядом с проектом и указать:

```env
COOKIES_FILE=C:\Users\COMP_ING\projects\telegram-media-bot\cookies.txt
```

На Render файл нужно передать как Secret File (**Environment → Secret Files**), путь будет
`/etc/secrets/cookies.txt`. Cookies живут несколько недель, потом процедуру надо повторить.

## Архитектура

```
telegram-media-bot/
├── bot/
│   ├── __main__.py          # python -m bot
│   ├── main.py              # сборка приложения, polling, логирование
│   ├── config.py            # Settings из переменных окружения
│   ├── middlewares.py       # внедрение сервисов в хендлеры
│   ├── web.py               # /health для Render
│   ├── handlers/
│   │   ├── commands.py      # /start, /help, /format
│   │   └── media.py         # ссылка → job → отправка, кнопки формата и качества
│   ├── keyboards/
│   │   └── inline.py        # выбор формата звука, понижение качества
│   ├── services/
│   │   ├── downloader.py    # yt-dlp: анализ, выбор качества, загрузка
│   │   ├── formats.py       # селекторы форматов yt-dlp
│   │   ├── progress.py      # прогресс-бар и троттлинг edit_message_text
│   │   ├── queue.py         # семафор + блокировка на пользователя
│   │   ├── sender.py        # send_audio / send_video / ZIP
│   │   ├── preferences.py   # формат звука пользователя
│   │   └── pending.py       # токены для повторной загрузки в другом качестве
│   └── utils/
│       ├── links.py         # разбор ссылок YouTube / SoundCloud
│       ├── format.py        # размеры, скорости, прогресс-бар
│       ├── text.py          # тексты и перевод ошибок
│       └── telegram.py      # безопасные edit/delete сообщений
├── Dockerfile
├── render.yaml
└── requirements.txt
```

Поток обработки одной ссылки:

```
сообщение → links.parse_link → downloader.run
   → probe (метаданные) → выбор качества под лимит
   → yt-dlp download (progress_hooks → ProgressTracker)
   → sender.deliver (audio / video / zip)
   → удаление временных файлов
```

## Обновление yt-dlp

YouTube меняет защиту чаще, чем выходят релизы бота. Если перестало качаться —
обновите зависимость:

```powershell
.\venv\Scripts\python.exe -m pip install -U yt-dlp
```

На Render: **Manual Deploy → Clear build cache & deploy**.

## Частые проблемы

| Симптом | Причина и лечение |
| --- | --- |
| `ffmpeg not found` | Не установлен ffmpeg или не задан `FFMPEG_LOCATION` |
| `Sign in to confirm you're not a bot` | Нужен `COOKIES_FILE` |
| `Файл весит X, а лимит 50 МБ` | Так работает Bot API: выберите качество ниже или поднимите локальный сервер |
| Бот молчит после деплоя | Free-план Render усыпил сервис — пингуйте `/health` |
| `ModuleNotFoundError: aiogram` при запуске `run.bat` | Старая версия скрипта проверяла папку `venv`, а не пакеты. Актуальный `run.bat` проверяет импорты — запустите его снова |
| `Не задан BOT_TOKEN` | Нет `.env` или переменная не передана в Render |
| Скачалось 0 файлов | Ссылка приватная/удалённая, проверьте `LOG_LEVEL=DEBUG` |

## Дисклеймер

Бот скачивает контент по публичным ссылкам. Соблюдайте условия использования SoundCloud и
YouTube и авторские права: используйте для личного прослушивания, а не для перепубликации.
