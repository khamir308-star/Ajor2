#!/bin/sh
set -e

# اگر api_id و api_hash تنظیم شده باشد، سرور لوکال Bot API را بالا می‌آوریم.
# این سرور محدودیت فایل را از ۵۰MB به ۲۰۰۰MB (۲ گیگابایت) افزایش می‌دهد.
if [ -n "$TELEGRAM_API_ID" ] && [ -n "$TELEGRAM_API_HASH" ]; then
  echo "Starting local Telegram Bot API server on 127.0.0.1:8081..."
  mkdir -p /tmp/tgapi /tmp/tgapi-tmp
  /usr/local/bin/telegram-bot-api --local \
    --api-id="$TELEGRAM_API_ID" \
    --api-hash="$TELEGRAM_API_HASH" \
    --dir=/tmp/tgapi \
    --temp-dir=/tmp/tgapi-tmp \
    --http-port=8081 \
    --log=/tmp/tgapi.log &
  # صبر می‌کنیم تا پورت 8081 بالا بیاید (حداکثر ۳۰ ثانیه)
  i=0
  until python -c "import socket; s=socket.create_connection(('127.0.0.1',8081),2); s.close()" >/dev/null 2>&1 || [ "$i" -ge 30 ]; do
    sleep 1
    i=$((i+1))
  done
  echo "Local Bot API ready after ${i}s"
fi

exec python -u bot.py
