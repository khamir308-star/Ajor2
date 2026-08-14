# Stage 1: باینری سرور لوکال Bot API (TDLight — سازگار با Alpine/musl)
FROM tdlight/tdlightbotapi:10.2 AS botapi

# Stage 2: محیط اجرای ربات — Debian slim (build سریع و مطمئن روی Render)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# باینری TDLight (musl) فقط با Alpine کار می‌کند؛ روی Debian از طریق استاتیک‌های گلایبک در دسترس نیست.
# در این تصویر سرور لوکال ۲ گیگابایتی فعلاً غیرفعال است (LOCAL_BOT_API=false)؛
# سقف آپلود ۵۰MB است و بعداً با تصویر Alpine قابل ارتقا است.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py prompt_catalog.py greeting_catalog.py iranian_music_catalog.py ai_service.py media_service.py instagram_comment_service.py music_service.py hokm_engine.py tools_service.py calendar_service.py prayer_service.py googlec331ce8b78c548bd.html start.sh ./
COPY webapp ./webapp

EXPOSE 8080

CMD ["sh", "start.sh"]
