# 🧱 آجُرپاره — خلاصهٔ وضعیت برای جلسهٔ بعد (Handoff)

> این سند برای ادامهٔ کار در یک چت/جلسهٔ جدید نوشته شده. کافی است همین متن را در چت جدید بچسبانید.

## وضعیت فعلی (آخرین بهروزرسانی: ۱۴۰۵/۰۵/۱۲)
- ربات **LIVE** روی Railway: `ajor2-production.up.railway.app` — حالت **Polling + سرور لوکال Bot API** (سقف آپلود/دانلود ~۱.۹۵ گیگابایت با api_id واقعی `26781648` — فقط در Railway Variables، نه در سورس/گیت).
- آخرین کامیت پوششده: `89ecbfd` (فروشگاه ستارهای مینیاپ) — شاخهٔ `main` ریپوی `gorgalikhanzebel-alt/Ajor2`.
- ۵۱ تست پاس (`tests/test_core.py`) + lint تمیز (ruff F,E9,B).
- مسیر پروژه: `/home/user/ajor2-upgraded` — فایلهای اصلی: `bot.py`، `media_service.py`، `music_service.py`، `prayer_service.py`، `tools_service.py`، `calendar_service.py`، `hokm_engine.py` + `webapp/` (مینیاپ).

## کلیدها (فقط در Railway Variables — هرگز در سورس/گیت)
- `BOT_TOKEN`، `ADMIN_IDS=466050034`، `CHANNEL_ID=-1001277492702`، `CHANNEL_LINK=https://t.me/Ajor_pareh`
- `ELEVENLABS_API_KEY`، `AUDD_API_KEY`، `OPENWEATHER_API_KEY`
- `UPSTASH_REDIS_REST_URL=https://guided-barnacle-177047.upstash.io` + توکن (دیتابیس **دائمی** با اکانت خود کاربر — قبلی موقت بود و منقضی شده)
- مدلهای AI: `GEMINI_MODEL`، `GROQ_MODEL`، `AI_MODEL` و… (زنجیره: Gemini → Groq → Cerebras → OpenRouter)
- `TELEGRAM_API_ID=26781648`، `TELEGRAM_API_HASH=…`، `LOCAL_BOT_API=true`، `USE_WEBHOOK=false`، `MAX_MEDIA_BYTES_MB=1950`

## فیچرهای اخیراً اضافهشده
1. **سقف ۲ گیگابایت** — سرور لوکال TDLight؛ فیکس build: استخراج دستی `libssl.so.1.1`/`libcrypto.so.1.1` از Alpine 3.16 (apk add مستقیم خراب بود)؛ healthcheck با بالا آمدن وبسرور قبل از دیتابیس حل شد.
2. **ستاره (Stars)** — طبق مستند رسمی تلگرام **نیازی به فعالسازی BotFather ندارد** (فقط کالای فیزیکی نیاز به provider دارد)؛ نرخ **خودکار** = ۲ سنت رسمی × دلار لحظهای (الان ~۲٬۴۰۰ تومان/ستاره)؛ پنل: پنل مدیریت ← «💰 مالی و اقتصاد» ← «💰 تنظیمات اقتصاد» ← «⭐ تنظیمات پرداخت ستاره».
3. **فروشگاه مینیاپ با ستاره** — صفحهٔ `shop` در مینیاپ (تنظیمات ← فروشگاه سرویسها)؛ API ها: `GET /api/shop/services` و `POST /api/shop/stars-invoice` → `WebApp.openInvoice`؛ هندلر `successful_payment` موجود، سرویس را تحویل میدهد.
4. **اذان روزانه کانال** — هر روز ۵:۳۰ صبح تهران (ورکر `daily_prayer_worker`)؛ شهر قابل تنظیم (دکمهٔ «🏙 تغییر شهر اذان»)؛ فعالسازی: پنل ← «📢 محتوا و انتشار» ← «🕌 پست اذان روزانه در کانال».
5. **اذانگوی شخصی** — `/praysub` یا دکمهٔ «🕌 اذانگوی شخصی» در منوی اطلاعات؛ در هر ۵ وقت نماز به مشترکین پیام میدهد (ورکر `prayer_azan_worker`، دکمهٔ لغو `azan_off`).
6. **گزارش مالی هفتگی کانال** — هر جمعه ۲۱:۰۰ (ورکر `weekly_finance_worker`) + دکمهٔ ارسال دستی؛ شامل فروش/کیف پول/سکه/امتیاز/کاربران + تفکیک روش پرداخت؛ فعالسازی: پنل ← «💰 مالی و اقتصاد».
7. **طلای ۱۸ عیار در پست خودکار نرخ ارز** — `gold_price_toman()` در `tools_service.py` (api.gold-api.com + دلار).
8. **رفع باگ ناوبری پنل ادمین** — دکمههای ستاره/فال/نرخ ارز قبلاً در منوی مخفی `admin_menu()` بودند؛ حالا از منوهای reply قابل دسترسیاند.
9. **Redis دائمی** — با اکانت خود کاربر ساخته شد و جایگزین دیتابیس موقت شد.

## شناسههای Railway/GitHub/OAuth (برای جلسهٔ بعد)
- Project ID: `5014302f-f477-49a9-a667-7af8bd8abdf7` — Environment ID: `d230ec0c-f957-47a7-a04d-6936690d97d9` — Service ID: `7c56cf25-84e2-42a6-9b54-05953aa0cbf0` (نام: Ajor2)
- دیپلوی: `npx --yes @railway/cli up --detach --json --yes --project … --environment … --service … --message "..."`
- GitHub OAuth device flow: client_id `178c6fc778ccc68e1d6a`، scope `repo read:org`، activation `https://github.com/login/device` → توکن در `.balance_auth_gh_token`
- Railway OAuth device flow: client_id `rlwy_oaci_onEklvmksh1hRUiCo7E2zX12`، scope `openid email profile offline_access workspace:admin project:admin ssh_keys`؛ device endpoint `https://backboard.railway.com/oauth/device/auth`؛ activation `https://railway.com/activate`؛ UA کجای `Railway CLI/5.30.1`؛ config در `~/.railway/config.json`
- توکنها/کوکیها معمولاً بین جلسات پاک میشوند → قبل از هر push: `git remote remove origin; git remote add origin https://github.com/gorgalikhanzebel-alt/Ajor2.git` + ست کردن `user.name`/`user.email`؛ push با `GIT_ASKPASS` (اسکریپت خواندن `.balance_auth_gh_token`)

## نکات فنی مهم
- `.venv` بین جلسات پاک میشود → هر بار: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt ruff pytest pytest-asyncio`
- Railway گاهی deploy را FAILED میزند با لاگ سالم → یک بار دیگر deploy کن (معمولاً بار دوم موفق میشود)
- چک بعد از هر deploy: health (`https://ajor2-production.up.railway.app/health` باید mode=polling بدهد) + لاگها (`railway logs`) + پاکسازی فایلهای auth موقت
- `railway ssh -p … -e … -s … "command"` برای اجرای دستور داخل کانتینر (کلید `~/.ssh/id_ed25519` ثبتشده به نام `ajor2-deploy`؛ در صورت «bad permissions» → `chmod 600`)
- تستهای مینیاپ: صفحات داخلی `hokm/calendar/boardgames/music/shop` در `parser.pages` تست میشوند
- API گرفتن: my.telegram.org سشن را به IP میبندد؛ راهحل قبلی: Cloudflare WARP از طریق wireproxy (SOCKS5) — اگر دوباره نیاز شد، همان روش را تکرار کن

## نکتههای جلسهٔ آخر (۱۴۰۵/۰۵/۱۲)
- یک **توکن API ریلیوی** به نام `ajor2-new-chat` ساخته شده و به کاربر داده شده (برای استفاده در چت جدید با `RAILWAY_API_TOKEN`). اگر گم شد: `apiTokenCreate` در GraphQL با workspaceId `666481cd-9f06-4cc2-9fb8-b469df2bb0a1`، یا از داشبورد Railway (Account → Tokens) بساز؛ باطلکردن هم با `apiTokenDelete`.
- پوشهای گیتهاب یک deploy خودکار FAILED روی Railway میسازند (اتصال GitHub ریپو خراب است — «repository not found»)؛ بیخطر است و سرویس روی آخرین deploy دستی (`railway up`) میماند. برای دیپلوی همیشه از `railway up` استفاده کن.
- کاربر میخواست بحث را به چت جدید منتقل کند؛ این فایل همان خلاصهٔ انتقال است.

## بهروزرسانی ۱۴۰۵/۰۵/۱۲ (آخرین فیچر)
- **انیمیشن پیشرفت دانلود URL + پاکسازی خودکار ۳۰ ثانیهای** (کامیت `bc12cf4`):
  - در `media_service.py`: `download_direct_file` پارامتر `progress_callback(percent, received, total)` گرفت.
  - در `bot.py`: `media_progress_bar()` (نوار `▓░` + درصد)، `auto_delete_media_messages()` و فلوی پیشرفت در `process_media_job` برای mode=direct.
  - برای کاربران عادی: پیام «⏳ در حال دریافت فایل…» با نوار زنده از ۰٪ تا ۱۰۰٪ + هشدار «فایل و پیامها بعد از ۳۰ ثانیه پاک میشن؛ به Saved Messages فوروارد کن» + پاکسازی خودکار پیام پیشرفت/فایلها/پیام تأیید بعد از ۳۰ ثانیه.
  - **ادمینها (ADMIN_IDS) مستثنیاند**: نه نوار، نه هشدار، نه پاکسازی — فایلها ماندگار میمانند (برای جلوگیری از حذف فایلهای حساس).
  - تست زنده داخل کانتینر انجام شد (job با فایل ۲MB از speed.cloudflare.com کامل شد و فایل به ادمین رسید). تست واحد `test_media_progress_bar` اضافه شد (۵۲ تست پاس).
- ریپوی گیتهاب در وضعیت عجیبی است: یک چت دیگر آن را force-push کرده که فقط فایلهای اصلی (bot.py, Dockerfile, railway.toml, requirements.txt, docs) را دارد و `webapp/` و فایلهای سرویس (media_service.py, music_service.py, prayer_service.py, tools_service.py, calendar_service.py, hokm_engine.py, start.sh) در آن نیستند. **کد کامل و دیپلویشده همیشه در `/home/user/ajor2-upgraded` است** — اگر خواستیم ریپو را کامل کنیم باید کل درخت لوکال را push کنیم.
