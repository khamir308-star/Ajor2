# آجُرپاره — مستندات بهینه‌سازی و فیچرها

> آخرین بروزرسانی: ۱۴۰۵/۰۵/۱۳ (August 2026)

## 📊 خلاصه وضعیت

| آیتم | مقدار |
|------|-------|
| فایل‌های پایتون | ۸ فایل (bot.py + 7 سرویس) |
| فایل‌های Mini App | ۱۰ فایل (HTML/CSS/JS) |
| تست‌ها | ۵۶ پاس ✅ |
| لینت | ruff F,E9,B تمیز ✅ |
| فیچرها | ۳۰+ فیچر فعال |
| بازی‌ها | ۱۰+ بازی (Mini App + ربات) |

---

## 🔧 بهینه‌سازی‌های اعمال‌شده

### فاز ۱: فیکس باگ‌ها (Memory Leak)
- **نشت حافظه `group_message_times`**: پاک‌سازی خودکار هر ۱۵ دقیقه در `perform_self_heal()`
- **نشت حافظه `ai_request_locks`**: حذف لاک‌های آزاد اضافی

### فاز ۲: بهینه‌سازی عملکرد
- **ایندکس دیتابیس**: اضافه شدن `group_settings_col` index
- **سشن HTTP مشترک**: قبلاً موجود — یک `aiohttp.ClientSession` برای کل عمر برنامه
- **کش خبر و مناسبت**: TTL 5 دقیقه (خبر) و ۶ ساعت (مناسبت)
- **Rate Limiting**: Flood control 0.8 ثانیه‌ای

### فاز ۳: امنیت
- **بدون `eval()`/`exec()`**: ماشین‌حساب با AST امن
- **بدون `bare except`**: تمام خطاها مشخص هستند
- **HMAC تأیید Mini App**: `verify_telegram_init_data()` با `hmac.compare_digest`
- **CSP headers**: Content-Security-Policy فعال
- **SSRF protection**: `resolve_public_host()` با بررسی IP خصوصی

### فاز ۴: توسعه فیچرها

#### بازی‌های جدید
| بازی | فایل | وضعیت |
|------|------|-------|
| 🧱 آجرچین | `ajorchin.js` + `ajorchin.css` | ✅ LIVE |
| 🐍 مار غذایی | `snake.js` + `snake.css` | ✅ LIVE |
| ⚔️ دوئل ۱v۱ | API `/api/duel` | ✅ LIVE |
| 🎡 گردونه VIP | ارتقا WHEEL_TABLE | ✅ LIVE |
| 📅 چالش روزانه | API `/api/challenges` | ✅ LIVE |

#### مرکز دانلود
- **۱۰۰+ سایت پشتیبانی‌شده**: شبکه‌های اجتماعی، موسیقی، تصویر، فایل، آموزشی، ایرانی
- **Fallback هوشمند**: اگه yt-dlp نتونست، aiohttp امتحان می‌کنه
- **تشخیص خودکار**: لینک مستقیم فایل → حالت direct
- **User-Agent Chrome**: جلوگیری از بلاک شدن
- **Geo bypass**: فعال (کشور US)

#### بازی حکم
- **گرافیک واقعی کارت**: گوشه‌ها، خال، چهره (شاه/بی‌بی/آس)
- **پخش کارت ۵-۴-۴**: طبق قانون واقعی
- **شروع دست اول با حاکم**: فیکس شد

---

## 🧪 تست‌ها

| تست | توضیح |
|-----|-------|
| `test_miniapp_has_matching_pages` | صفحات Mini App با منوها مطابقت داره |
| `test_ajorchin_game_reward` | جایزه آجرچین درست محاسبه می‌شه |
| `test_snake_game_reward` | جایزه مار غذایی درست محاسبه می‌شه |
| `test_duel_room_creation` | اتاق دوئل ساخته می‌شه |
| `test_wheel_table_has_vip_items` | گردونه آیتم‌های VIP داره |
| + ۵۱ تست دیگه | عملکرد کلی ربات |

---

## 📦 وابستگی‌ها

| پکیج | نسخه | وضعیت |
|------|------|-------|
| aiogram | 3.30.0 | ✅ آپدیت |
| aiohttp | 3.14.3 | ✅ آپدیت |
| motor | 3.7.1 | ✅ آپدیت |
| yt-dlp | 2026.7.4 | ✅ آپدیت |
| Pillow | 12.3.0 | ✅ آپدیت |
| qrcode | 8.2 | ✅ آپدیت |

---

## 🔐 متغیرهای محیطی (Railway Variables)

| متغیر | توضیح |
|-------|-------|
| BOT_TOKEN | توکن ربات تلگرام |
| MONGO_URI | URI اتصال MongoDB |
| ADMIN_IDS | آیدی ادمین‌ها |
| ELEVENLABS_API_KEY | کلید ElevenLabs TTS |
| AUDD_API_KEY | کلید تشخیص آهنگ |
| OPENWEATHER_API_KEY | کلید آب‌وهوا |
| UPSTASH_REDIS_REST_URL | URL Redis |
| TELEGRAM_API_ID | API ID تلگرام |
| LOCAL_BOT_API | سرور لوکال Bot API |
| MAX_MEDIA_BYTES_MB | سقف حجم فایل (1950) |

---

## 🚀 گردش کار دیپلوی

1. کد تغییر می‌کنه
2. تست: `.venv/bin/python -m pytest tests/ -q`
3. لینت: `.venv/bin/ruff check . --select F,E9,B`
4. کامیت + پوش گیتهاب
5. دیپلوی Railway: `railway up`
6. health چک: `curl /health`
7. لاگ چک: `railway logs`
8. پاک‌سازی فایل‌های auth
