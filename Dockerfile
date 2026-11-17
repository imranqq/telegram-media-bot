FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DOWNLOAD_DIR=/tmp/downloads \
    PORT=8080

# ffmpeg нужен для склейки видео+аудио и конвертации в MP3
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /tmp/downloads \
    && chown -R app:app /app /tmp/downloads

USER app

EXPOSE 8080

CMD ["python", "-m", "bot"]
