# Telegram Media Bot

Бот присылает музыку по ссылке: **SoundCloud**, **YouTube** (только звук) и **Spotify**
(трек находится на YouTube по названию и исполнителю). Видео бот не отдаёт.

## Что умеет

| Источник | Что получите |
| --- | --- |
| SoundCloud трек | MP3 320 kbps **или** оригинальный файл без перекодирования |
| SoundCloud сет / альбом | все треки: ZIP-архивом, если влезает в лимит, иначе по одному |
| YouTube видео | аудиодорожка, MP3 320 kbps или оригинальный кодек |
| Spotify трек | MP3: бот берёт название и исполнителя и находит трек на YouTube |

Дополнительно:

- живой прогресс-бар в сообщении: проценты, мегабайты, скорость, ETA, номер трека в сете;
- очередь загрузок: несколько задач одновременно, запросы одного пользователя выполняются последовательно;
- обложки треков подтягиваются и отправляются вместе с аудио (для Spotify — обложка из Spotify);
- понятные тексты ошибок: приватное видео, возрастное ограничение, требование cookies.

### Про Spotify

Spotify не отдаёт аудиофайлы — звук защищён DRM. Поэтому ссылка `open.spotify.com/track/…`
разбирается на название и исполнителя (через oEmbed и метатеги страницы, без API-ключей),
а сам файл скачивается с YouTube. Качество и точность совпадения — ютубовские: если на YouTube
нет этого трека или матчинг промахнулся, бот пришлёт то, что нашлось. Альбомы и плейлисты
пока не разворачиваются, поддерживаются только отдельные треки.

## Быстрый старт (Windows)

### 1. ffmpeg

Без ffmpeg бот не сможет перекодировать звук в MP3. Скачайте сборку с
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
| `MAX_AUDIO_DURATION_MIN` | `60` | Максимальная длительность трека в минутах |
| `JOB_TIMEOUT_MIN` | `30` | Предохранитель: через сколько минут задача прерывается |
| `DEFAULT_AUDIO_FORMAT` | `mp3` | `mp3` или `orig` |
| `YT_PLAYER_CLIENT` | по умолчанию yt-dlp | Например `android,web_safari`, если YouTube просит подтвердить «я не робот» |
| `WEBHOOK_URL` | `RENDER_EXTERNAL_URL` | База для webhook; пусто = long polling (локально) |
| `KEEPALIVE_MIN` | `10` | Самопинг `/health` в минутах, чтобы Render не усыплял сервис; `0` — выключить |
| `PORT` | `8080` | Порт healthcheck и webhook |
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

### Free-план и «спящий» сервис

Free-план останавливает контейнер после 15 минут без **входящего** HTTP-трафика. Опрос Telegram
(polling) идёт наружу и сном не считается, поэтому на голом polling бот замолкает навсегда,
пока его не разбудят.

Что сделано в боте:

- **webhook вместо polling в облаке.** Render сам подставляет `RENDER_EXTERNAL_URL`, бот видит его
  и вызывает `setWebhook` на `/webhook`. Каждое сообщение — это входящий запрос: Render поднимает
  контейнер, и апдейт доезжает. Ответ придёт с задержкой холодного старта (~40 с), но не потеряется.
- **`drop_pending_updates=False`** — сообщения, отправленные во время сна, не выбрасываются.
- **Секрет в заголовке** `X-Telegram-Bot-Api-Secret-Token` (sha256 от токена): посторонний
  на `/webhook` не постучится, получит `403`.
- **самопинг** (`bot/services/keepalive.py`): проснувшись, бот раз в `KEEPALIVE_MIN` (по умолчанию
  10) минут запрашивает собственный `/health` через публичный адрес. Запрос проходит через прокси
  Render и для платформы считается входящим трафиком, поэтому сервис больше не засыпает.
- **`.github/workflows/keepalive.yml`** пингует `/health` снаружи. Оговорка: GitHub сильно
  задерживает `schedule` — по факту запуски шли раз в 8–10 часов, так что это лишь страховка
  на случай, если контейнер всё-таки остановят.

Порядок работы получается такой: контейнер поднимается на деплое, самопинг держит его живым,
а если Render всё же остановит инстанс — первое сообщение в Telegram разбудит его через webhook.
Единственное, что не решается кодом, — гарантия «никогда ни секунды сна»: это платный план
Render ($7/мес) либо внешний пинг из UptimeRobot/cron-job.org каждые 5 минут.

Помните про лимит free-плана: постоянно бодрствующий инстанс съедает ~730 из 750 часов в месяц,
так что держать так можно только один сервис.

### Что важно помнить про Render

- **Диск эфемерный.** Файлы живут в `/tmp` и удаляются сразу после отправки, кэша между
  деплоями нет.
- **512 МБ RAM и 0.1 CPU.** Поэтому в `render.yaml` одновременных загрузок — одна, а из сета
  берётся 10 треков: перекодирование в MP3 упирается в процессор, а не в сеть.
- **Один экземпляр.** В облаке бот работает через webhook, локально — через long polling.
  Это разные способы получения апдейтов, поэтому одновременно держать оба нельзя: локальный
  запуск увидит установленный webhook, напишет предупреждение в лог, а Telegram начнёт
  отдавать сообщения только облаку.

## Лимит 50 МБ и локальный Bot API

Облачной Bot API запрещено отдавать боту файлы больше 50 МБ — это ограничение Telegram,
а не бота. Варианты:

- **Бот подсказывает формат.** Если MP3 320 не влезает, приходит сообщение с предложением
  переключиться на «Оригинал»: файл без перекодирования бывает заметно меньше.
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
│   ├── main.py              # сборка приложения: webhook в облаке, polling локально
│   ├── config.py            # Settings из переменных окружения
│   ├── middlewares.py       # внедрение сервисов в хендлеры
│   ├── web.py               # /health и приём апдейтов по webhook
│   ├── handlers/
│   │   ├── commands.py      # /start, /help, /format
│   │   └── media.py         # ссылка → job → отправка аудио
│   ├── keyboards/
│   │   └── inline.py        # выбор формата звука
│   ├── services/
│   │   ├── downloader.py    # yt-dlp: анализ ссылки и загрузка аудио
│   │   ├── spotify.py       # метаданные трека Spotify без API-ключей
│   │   ├── formats.py       # селекторы аудиоформатов yt-dlp
│   │   ├── progress.py      # прогресс-бар и троттлинг edit_message_text
│   │   ├── queue.py         # семафор + блокировка на пользователя
│   │   ├── sender.py        # send_audio и ZIP для сетов
│   │   ├── keepalive.py     # самопинг, чтобы Render не усыплял сервис
│   │   └── preferences.py   # формат звука пользователя
│   └── utils/
│       ├── links.py         # разбор ссылок YouTube / SoundCloud / Spotify
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
   → Spotify? spotify.resolve → ytsearch1:"Artist - Title"
   → probe (метаданные, для сета — список треков)
   → yt-dlp download + FFmpegExtractAudio (progress_hooks → ProgressTracker)
   → sender.deliver (audio / zip для сета)
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
| `Файл весит X, а лимит 50 МБ` | Так работает Bot API: переключите формат на «Оригинал» или поднимите локальный Bot API |
| Spotify прислал не тот трек | Бот ищет на YouTube по названию и исполнителю. Пришлите ссылку SoundCloud/YouTube или уточните название |
| Бот молчит после деплоя | Free-план Render усыпил сервис — пингуйте `/health` |
| `ModuleNotFoundError: aiogram` при запуске `run.bat` | Старая версия скрипта проверяла папку `venv`, а не пакеты. Актуальный `run.bat` проверяет импорты — запустите его снова |
| `Не задан BOT_TOKEN` | Нет `.env` или переменная не передана в Render |
| Скачалось 0 файлов | Ссылка приватная/удалённая, проверьте `LOG_LEVEL=DEBUG` |

## Дисклеймер

Бот скачивает контент по публичным ссылкам. Соблюдайте условия использования SoundCloud,
YouTube и Spotify и авторские права: используйте для личного прослушивания, а не для
перепубликации. Spotify не отдаёт аудиофайлы — бот берёт только метаданные трека и ищет
его на YouTube.
