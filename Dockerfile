# Stage 1: باینری سرور لوکال Bot API (TDLight — سازگار با Alpine/musl)
FROM tdlight/tdlightbotapi:10.2 AS botapi

# Stage 2: محیط اجرای ربات (Alpine) + libssl1.1 از Alpine 3.16 (مورد نیاز باینری Bot API)
FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ffmpeg برای فشرده‌سازی ویدئو؛ openssl/libstdc++ برای باینری Bot API؛
# build-base/python3-dev برای پکیج‌هایی که ویل musllinux ندارند (مثل pymongo).
# باینری TDLight با OpenSSL 3 سازگار نیست؛ libssl.so.1.1 و libcrypto.so.1.1
# از پکیج‌های Alpine 3.16 (آخرین نسخه‌ی OpenSSL 1.1) به‌صورت دستی استخراج می‌شوند.
RUN apk add --no-cache ca-certificates ffmpeg openssl libstdc++ build-base python3-dev wget curl \
    && wget -q https://dl-cdn.alpinelinux.org/alpine/v3.16/main/x86_64/libcrypto1.1-1.1.1w-r1.apk \
    && wget -q https://dl-cdn.alpinelinux.org/alpine/v3.16/main/x86_64/libssl1.1-1.1.1w-r1.apk \
    && mkdir -p /tmp/ossl11 \
    && tar -xzf libcrypto1.1-1.1.1w-r1.apk -C /tmp/ossl11 \
    && tar -xzf libssl1.1-1.1.1w-r1.apk -C /tmp/ossl11 \
    && cp /tmp/ossl11/lib/libcrypto.so.1.1 /usr/lib/ \
    && cp /tmp/ossl11/lib/libssl.so.1.1 /usr/lib/ \
    && rm -rf /tmp/ossl11 libcrypto1.1-1.1.1w-r1.apk libssl1.1-1.1.1w-r1.apk \
    && update-ca-certificates

COPY --from=botapi /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py prompt_catalog.py greeting_catalog.py iranian_music_catalog.py ai_service.py media_service.py instagram_comment_service.py music_service.py hokm_engine.py tools_service.py calendar_service.py prayer_service.py googlec331ce8b78c548bd.html start.sh ./
COPY webapp ./webapp

EXPOSE 8080

CMD ["sh", "start.sh"]
