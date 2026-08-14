import asyncio
import os
import ast
import base64
import operator
import logging
import math
import random
import shutil
import uuid
import csv
import hashlib
import hmac
import html
from difflib import SequenceMatcher
import io
import json
import re
import time
import tempfile
import zipfile
from collections import deque
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from defusedxml import ElementTree

import aiohttp
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    WebAppInfo,
    MenuButtonWebApp,
    BufferedInputFile,
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
    InputSticker,
)
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from aiogram.utils.text_decorations import add_surrogates, remove_surrogates, html_decoration
from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from PIL import Image, ImageOps
import qrcode
from aiohttp import web

from ai_service import AIConfig, AIService, AIResult, AIImageResult
from hokm_engine import HokmGame
from prayer_service import (
    format_prayer_text,
    hafez_fal,
    prayer_times,
)
from calendar_service import (
    JALALI_MONTHS,
    month_grid as cal_month_grid,
    month_occasions as cal_month_occasions,
    today_info as cal_today_info,
    today_jalali as cal_today_jalali,
)
from tools_service import (
    book_search,
    country_info,
    crypto_price,
    exchange_rate,
    gold_price_toman,
    opentdb_quiz,
    pwned_password_count,
    weather,
    wiki_summary,
    world_time,
)
from music_service import (
    QUALITY_PRESETS,
    audius_host,
    download_audius_track,
    download_preview,
    download_youtube_audio_cobalt,
    download_youtube_video_cobalt,
    recognize_audio,
    search_songs,
    search_iranian_songs,
    trending_iranian_songs,
    trending_songs,
)
from media_service import (
    MAX_MEDIA_BYTES,
    media_size_label,
    SUPPORTED_SOCIAL_DOMAINS,
    MediaServiceError,
    DownloadedMedia,
    download_audio_track,
    download_direct_file,
    download_social_media,
    fetch_instagram_metadata,
    inspect_link,
    normalized_host,
    normalize_youtube_url,
    validate_public_url,
)
from instagram_comment_service import (
    InstagramCommentError,
    extract_instagram_comment,
    is_instagram_comment_url,
)
from prompt_catalog import EXTENDED_PROMPTS, EXTENDED_PROMPT_COUNT
from greeting_catalog import MIDNIGHT_DEFAULT_SENTENCES, MORNING_DEFAULT_SENTENCES

# yt-dlp در media_service و instagram_comment_service برای محتوای عمومی استفاده می‌شود.

# ======== لاگ ========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("bot")

# ======== تنظیمات محیطی (از تب Variables توی Railway خونده می‌شود) ========
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def parse_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID", "466050034")
    ids: set[int] = set()
    for value in raw.split(","):
        try:
            ids.add(int(value.strip()))
        except ValueError:
            log.warning("ADMIN_IDS contains an invalid value: %s", value)
    return ids


ADMIN_IDS = parse_admin_ids()
ADMIN_ID = next(iter(ADMIN_IDS), 466050034)  # سازگاری با بخش‌های قدیمی
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001277492702"))
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/Ajor_pareh")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "Ajorparehbot").lstrip("@")
FORCE_JOIN_DEFAULT = env_bool("FORCE_JOIN", True)

# Railway همان دامنه سرویس ربات را برای Mini App هم استفاده می‌کند.
_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
_default_mini_app_url = (
    f"https://{_public_domain}/app/"
    if _public_domain
    else "https://ajor2-production.up.railway.app/app/"
)
MINI_APP_URL = os.getenv("MINI_APP_URL", _default_mini_app_url).strip()
APP_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = APP_DIR / "webapp"
LANDING_FILE = WEBAPP_DIR / "landing.html"
GOOGLE_VERIFICATION_FILENAME = "googlec331ce8b78c548bd.html"
GOOGLE_VERIFICATION_FILE = APP_DIR / GOOGLE_VERIFICATION_FILENAME

# اگر Railway دامنه عمومی بدهد، ربات خودکار در حالت webhook بالا می‌آید.
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/")
if not WEBHOOK_BASE_URL and _public_domain:
    WEBHOOK_BASE_URL = f"https://{_public_domain}"
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram/webhook")
if not WEBHOOK_PATH.startswith("/"):
    WEBHOOK_PATH = "/" + WEBHOOK_PATH
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
# ===== تبدیل متن به صدا (ElevenLabs) =====
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
TTS_VOICES = {
    "bella": {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella (مونث)", "emoji": "👩"},
    "adam": {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (مذکر)", "emoji": "👨"},
}
TTS_MODEL = "eleven_flash_v2_5"
TTS_DAILY_CHAR_LIMIT = int(os.getenv("TTS_DAILY_CHAR_LIMIT", "500"))
if TOKEN and not WEBHOOK_SECRET:
    WEBHOOK_SECRET = hashlib.sha256(TOKEN.encode()).hexdigest()[:48]
USE_WEBHOOK = env_bool("USE_WEBHOOK", bool(WEBHOOK_BASE_URL)) and bool(WEBHOOK_BASE_URL)
# حالت سرور لوکال Bot API: با نصب telegram-bot-api روی همان سرویس، سقف فایل تا ۲ گیگابایت می‌شود.
# در این حالت ربات با long polling از طریق http://127.0.0.1:8081 کار می‌کند.
LOCAL_BOT_API = env_bool("LOCAL_BOT_API", False)
BOT_API_BASE_URL = os.getenv("BOT_API_BASE_URL", "http://127.0.0.1:8081").strip().rstrip("/")
if LOCAL_BOT_API:
    USE_WEBHOOK = False

if not TOKEN or not MONGO_URI:
    log.error("❌ متغیرهای BOT_TOKEN و MONGO_URI را در Variables پروژه Railway تنظیم کنید.")
    raise SystemExit(1)
if not ADMIN_IDS:
    log.error("❌ حداقل یک ADMIN_ID یا ADMIN_IDS معتبر تنظیم کنید.")
    raise SystemExit(1)
if not MINI_APP_URL.startswith("https://"):
    log.error("❌ MINI_APP_URL باید با https:// شروع شود.")
    raise SystemExit(1)

# ======== دیتابیس (Async - Motor) ========
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_col = db["users"]
files_col = db["files"]
groups_col = db["groups"]
activities_col = db["activities"]
configs_col = db["configs"]  # پروکسی‌ها و کانفیگ‌های V2Ray/NPV
withdrawals_col = db["withdrawals"]
tickets_col = db["support_tickets"]
broadcasts_col = db["broadcasts"]
settings_col = db["settings"]
required_channels_col = db["required_channels"]
profiles_col = db["miniapp_profiles"]
scheduled_posts_col = db["scheduled_posts"]
scheduled_greetings_col = db["scheduled_greetings"]
scheduled_message_history_col = db["scheduled_message_history"]
public_music_playlist_col = db["public_music_playlist"]
managed_chats_col = db["managed_chats"]
group_settings_col = db["group_settings"]
warnings_col = db["group_warnings"]
channel_posts_col = db["channel_posts"]
channel_reaction_events_col = db["channel_reaction_events"]
wallet_transactions_col = db["wallet_transactions"]
miniapp_rewards_col = db["miniapp_rewards"]
admins_col = db["admin_roles"]
admin_audit_col = db["admin_audit"]
referral_events_col = db["referral_events"]
promo_codes_col = db["promo_codes"]
promo_redemptions_col = db["promo_redemptions"]
missions_col = db["missions"]
mission_claims_col = db["mission_claims"]
content_templates_col = db["content_templates"]
health_events_col = db["health_events"]
coin_transactions_col = db["coin_transactions"]
score_events_col = db["score_events"]
shop_purchases_col = db["shop_purchases"]
raffles_col = db["raffles"]
raffle_entries_col = db["raffle_entries"]
predictions_col = db["trend_predictions"]
prediction_bets_col = db["prediction_bets"]
sponsor_rewards_col = db["sponsor_rewards"]
wheel_spins_col = db["wheel_spins"]
service_orders_col = db["service_orders"]
user_services_col = db["user_services"]
ai_usage_col = db["ai_daily_usage"]
ai_provider_metrics_col = db["ai_provider_metrics"]
reminders_col = db["user_reminders"]
reviews_col = db["user_reviews"]
media_jobs_col = db["media_jobs"]

ai_service = AIService(AIConfig.from_env(), ai_usage_col, ai_provider_metrics_col, users_col)

if LOCAL_BOT_API:
    # درخواست‌ها به سرور لوکال Bot API می‌روند (همان فرمت /bot<token>/... و /file/bot<token>/...)
    bot = Bot(token=TOKEN, session=AiohttpSession(api=TelegramAPIServer.from_base(BOT_API_BASE_URL)))
else:
    bot = Bot(token=TOKEN)
dp = Dispatcher()
BOT_STARTED_AT = time.monotonic()
runtime_settings = {
    "maintenance": False,
    "force_join": FORCE_JOIN_DEFAULT,
    "scheduler_paused": False,
    "repost_cta": "📣 اخبار و ترندهای روز را از @Ajor_pareh دنبال کنید.",
    "daily_fal_enabled": False,
    "daily_fal_channel_enabled": False,
    "daily_fal_channel_id": None,
    "daily_fal_channel_title": "",
    "daily_fal_channel_type": "",
    "daily_fal_channel_username": "",
    "daily_fal_channel_link": "",
    "greeting_target_enabled": False,
    "greeting_target_id": None,
    "greeting_target_title": "",
    "greeting_target_type": "",
    "greeting_target_username": "",
    "greeting_target_link": "",
    "midnight_greeting_enabled": False,
    "morning_greeting_enabled": False,
    "daily_music_enabled": False,
    "daily_music_target_enabled": False,
    "daily_music_target_id": None,
    "daily_music_target_title": "",
    "daily_music_target_type": "",
    "daily_music_target_username": "",
    "daily_music_target_link": "",
    "daily_music_time": "12:00",
}


def load_daily_fal_runtime(saved: dict) -> None:
    """تنظیمات فال صبحگاهی و مقصد کانال را از MongoDB به حافظه می‌آورد."""
    runtime_settings["daily_fal_enabled"] = bool(saved.get("daily_fal_enabled", False))
    runtime_settings["daily_fal_channel_enabled"] = bool(saved.get("daily_fal_channel_enabled", False))
    runtime_settings["daily_fal_channel_id"] = saved.get("daily_fal_channel_id")
    runtime_settings["daily_fal_channel_title"] = str(saved.get("daily_fal_channel_title") or "")[:100]
    runtime_settings["daily_fal_channel_type"] = str(saved.get("daily_fal_channel_type") or "")[:20]
    runtime_settings["daily_fal_channel_username"] = str(saved.get("daily_fal_channel_username") or "")[:40]
    runtime_settings["daily_fal_channel_link"] = str(saved.get("daily_fal_channel_link") or "")[:200]
    if not runtime_settings["daily_fal_channel_id"]:
        runtime_settings["daily_fal_channel_enabled"] = False


def load_greeting_runtime(saved: dict) -> None:
    """تنظیمات مقصد و وضعیت دو زمان‌بندی جمله‌ها را از MongoDB می‌خواند."""
    runtime_settings["greeting_target_enabled"] = bool(saved.get("greeting_target_enabled", False))
    runtime_settings["greeting_target_id"] = saved.get("greeting_target_id")
    runtime_settings["greeting_target_title"] = str(saved.get("greeting_target_title") or "")[:100]
    runtime_settings["greeting_target_type"] = str(saved.get("greeting_target_type") or "")[:20]
    runtime_settings["greeting_target_username"] = str(saved.get("greeting_target_username") or "")[:40]
    runtime_settings["greeting_target_link"] = str(saved.get("greeting_target_link") or "")[:200]
    runtime_settings["midnight_greeting_enabled"] = bool(saved.get("midnight_greeting_enabled", False))
    runtime_settings["morning_greeting_enabled"] = bool(saved.get("morning_greeting_enabled", False))
    if not runtime_settings["greeting_target_id"]:
        runtime_settings["greeting_target_enabled"] = False


def load_daily_music_runtime(saved: dict) -> None:
    runtime_settings["daily_music_enabled"] = bool(saved.get("daily_music_enabled", False))
    runtime_settings["daily_music_target_enabled"] = bool(saved.get("daily_music_target_enabled", False))
    runtime_settings["daily_music_target_id"] = saved.get("daily_music_target_id")
    runtime_settings["daily_music_target_title"] = str(saved.get("daily_music_target_title") or "")[:100]
    runtime_settings["daily_music_target_type"] = str(saved.get("daily_music_target_type") or "")[:20]
    runtime_settings["daily_music_target_username"] = str(saved.get("daily_music_target_username") or "")[:40]
    runtime_settings["daily_music_target_link"] = str(saved.get("daily_music_target_link") or "")[:200]
    value = str(saved.get("daily_music_time") or "12:00")
    runtime_settings["daily_music_time"] = value if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) else "12:00"
    if not runtime_settings["daily_music_target_id"]:
        runtime_settings["daily_music_target_enabled"] = False


SERVICE_CATALOG = {
    "v2ray": {"title": "V2Ray اختصاصی", "app": "V2rayNG / V2Box", "emoji": "⚡"},
    "npv": {"title": "NPV اختصاصی", "app": "NapsternetV", "emoji": "🌀"},
}
SERVICE_PLANS = {
    1: {"title": "یک‌ماهه", "price": 60_000},
    3: {"title": "سه‌ماهه", "price": 150_000},
    6: {"title": "شش‌ماهه", "price": 280_000},
    12: {"title": "یک‌ساله", "price": 500_000},
}
service_shop_settings = {
    "card_number": os.getenv("SERVICE_PAYMENT_CARD", "").strip(),
    "card_holder": os.getenv("SERVICE_PAYMENT_HOLDER", "").strip(),
    "payment_note": "بعد از کارت‌به‌کارت، تصویر رسید را همین‌جا ارسال کن.",
    "offer_active": False,
    "offer_percent": 0,
    "offer_title": "",
    "offer_expires_at": None,
}

economy_settings = {
    "referral_points": 100,
    "point_toman_rate": 100,
    "min_convert_points": 1000,
    "min_withdraw_toman": 100000,
    "daily_withdraw_limit": 5000000,
    "large_withdraw_threshold": 1000000,
    "usdt_toman_rate": int(os.getenv("USDT_TOMAN_RATE", "0")),
    "usdt_network": "TRC20",
    "daily_coin_cap": 500,
    "daily_emission_target": 50000,
    "min_reward_multiplier": 0.35,
    "paid_spin_cost": 50,
    "sponsor_join_coins": 20,
    "referrer_coins": 100,
    "referred_coins": 25,
    "referral_ai_text_bonus": int(os.getenv("AI_REFERRAL_TEXT_BONUS", "1")),
    "referral_ai_bonus_cap": int(os.getenv("AI_REFERRAL_TEXT_BONUS_CAP", "10")),
    "stars_rate_toman": int(os.getenv("STARS_RATE_TOMAN", "10000")),
    "stars_enabled": True,
    "stars_auto_rate": True,  # نرخ ستاره به‌صورت خودکار از قیمت رسمی تلگرام (۲ سنت) × دلار لحظه‌ای
}

# قیمت رسمی هر ستاره تلگرام به دلار (Telegram Stars یک ارز رسمی است؛ ۱ ستاره ≈ ۲ سنت)
STAR_USD_PRICE = float(os.getenv("STAR_USD_PRICE", "0.02"))


async def stars_toman_rate_auto() -> int:
    """نرخ هر ستاره به تومان بر اساس قیمت رسمی تلگرام و نرخ لحظه‌ای دلار (مانند تتر)."""
    try:
        res = await exchange_rate("usd", "irr")
        rial = float(res.get("rate") or 0)
        if rial > 0:
            toman = int(round(rial / 10 * STAR_USD_PRICE / 100) * 100)
            if toman >= 100:
                return toman
    except Exception:
        pass
    return max(100, int(economy_settings.get("stars_rate_toman", 10000) or 10000))


async def stars_toman_rate() -> int:
    """نرخ مؤثر هر ستاره به تومان: خودکار (قیمت رسمی) یا دستی."""
    if economy_settings.get("stars_auto_rate", True):
        return await stars_toman_rate_auto()
    return max(100, int(economy_settings.get("stars_rate_toman", 10000) or 10000))
ROLE_PERMISSIONS = {
    "owner": {"*"},
    "content": {"content", "templates", "broadcast", "schedule", "configs"},
    "support": {"support", "users.view"},
    "finance": {"finance", "users.view"},
    "moderator": {"moderation", "users.view"},
    "analyst": {"stats", "users.view", "backup"},
}
SHOP_CATALOG = {
    "badge_neon": {"title": "مدال نئون", "price": 180, "emoji": "💜", "kind": "badge"},
    "badge_meme": {"title": "مدال پادشاه میم", "price": 350, "emoji": "😂", "kind": "badge"},
    "premium_games_7d": {"title": "بازی‌های ویژه ۷ روزه", "price": 500, "emoji": "🎮", "kind": "entitlement", "days": 7},
    "group_pro_30d": {"title": "ابزار Pro گروه ۳۰ روزه", "price": 1200, "emoji": "🛡", "kind": "entitlement", "days": 30},
}
BUILTIN_MISSIONS = [
    {"slug": "invite_one_friend", "title": "یکی از دوستات رو بیار", "description": "یک دوست واقعی با لینک دعوتت وارد ربات بشه و مراحل عضویت رو کامل کنه.", "type": "referrals", "target": 1, "points": 120, "coins": 10},
    {"slug": "react_last_five", "title": "روی ۵ پست آخر واکنش بزن", "description": "روی پنج پست تازه کانال رسمی @Ajor_pareh ری‌اکشن بزن.", "type": "reactions", "target": 5, "points": 100, "coins": 15},
    {"slug": "leave_one_review", "title": "نظرت رو درباره ربات بگو", "description": "از پشتیبانی ← نظرات کاربران، یک نظر ثبت کن.", "type": "reviews", "target": 1, "points": 80, "coins": 5},
    {"slug": "play_three_games", "title": "سه بازی انجام بده", "description": "هر سه بازی یا چالش ثبت‌شده در ربات و Mini App قبول است.", "type": "games", "target": 3, "points": 60, "coins": 5},
    {"slug": "use_ai_twice", "title": "دو بار از هوش مصنوعی استفاده کن", "description": "چت، ترجمه، خلاصه، تصویر یا ابزارهای AI رو امتحان کن.", "type": "ai_requests", "target": 2, "points": 50, "coins": 5},
    {"slug": "transcribe_voice", "title": "یک ویس رو به متن تبدیل کن", "description": "از گزینه ویس به متن در بخش هوش مصنوعی استفاده کن.", "type": "voice_transcriptions", "target": 1, "points": 50, "coins": 5},
    {"slug": "three_day_streak", "title": "استریک سه‌روزه بساز", "description": "سه روز پیاپی جایزه روزانه یا فعالیت ثبت‌شده داشته باش.", "type": "streak", "target": 3, "points": 100, "coins": 10},
]

MISSION_FIELD_MAP = {
    "referrals": "referral_count",
    "games": "games_played",
    "streak": "streak",
    "points": "xp",
    "reactions": "channel_reaction_count",
    "reviews": "reviews_submitted_count",
    "ai_requests": "ai_requests_count",
    "voice_transcriptions": "voice_transcriptions_count",
}


async def ensure_builtin_missions() -> None:
    now = datetime.now(timezone.utc)
    for mission in BUILTIN_MISSIONS:
        await missions_col.update_one(
            {"slug": mission["slug"]},
            {"$setOnInsert": {
                **mission,
                "active": True,
                "builtin": True,
                "created_by": "system",
                "created_at": now,
            }},
            upsert=True,
        )


WHEEL_TABLE = [
    {"coins": 0, "weight": 300, "label": "پوچ 😅"},
    {"coins": 5, "weight": 200, "label": "۵ سکه"},
    {"coins": 10, "weight": 150, "label": "۱۰ سکه"},
    {"coins": 20, "weight": 100, "label": "۲۰ سکه"},
    {"coins": 50, "weight": 60, "label": "۵۰ سکه"},
    {"coins": 100, "weight": 30, "label": "۱۰۰ سکه"},
    {"coins": 250, "weight": 12, "label": "۲۵۰ سکه"},
    {"coins": 500, "weight": 4, "label": "🪙 جک‌پات ۵۰۰"},
    {"coins": 100, "weight": 8, "xp": 50, "label": "⭐ ۵۰ XP + ۱۰۰ سکه"},
    {"coins": 0, "weight": 3, "ai_quota": 2, "label": "🤖 ۲ سهمیه AI"},
    {"coins": 200, "weight": 2, "badge": "wheel_king", "label": "👑 بج VIP گردونه"},
]
delegated_admins_cache: dict[int, set[str]] = {}
required_channels_cache: list[dict] = []
engagement_gate_cache: dict = {
    "enabled": False,
    "version": None,
    "url": None,
    "instruction": "۱۰ پست آخر کانال را ببین و روی یکی از آن‌ها واکنش بزن.",
    "wait_seconds": 15,
}

# یک سشن HTTP مشترک برای کل عمر برنامه (به‌جای ساخت سشن جدید در هر درخواست)
http_session: aiohttp.ClientSession | None = None
maintenance_notification_lock = asyncio.Lock()

DEFAULT_CAPTION = "📌 عضویت در کانال ما: @Ajor_pareh"

# ======== لیست‌ها ========
FUNNY_FALLBACKS = [
    "این یکی رو دقیق نگرفتم 😅 یه کم واضح‌تر بگو تا پایه‌ات باشم.",
    "منظورت رو کامل نفهمیدم؛ ولی می‌تونیم بازی کنیم، جوک بخونیم یا با هم گپ بزنیم 😎",
    "یه جور دیگه بگو رفیق؛ مغز دیجیتالم هنوز داره لود می‌شه! 🤖",
    "حرفتو گرفتم... تقریباً! یکم بیشتر توضیح بده تا جواب درست‌وحسابی بدم 👀",
    "اگه دنبال سرگرمی هستی «منو» رو بفرست؛ کلی بازی و چیز خفن دارم ⚡",
    "این پیام مرموز بود! 🕵️ یکم سرنخ بیشتر بده.",
]

JOKES = [
    "وزنه‌برداره پشت کامیونش نوشته بود: یا علی مدد، تو هم کلاچ بگیر کمک کن! 😂",
    "رفتیم رستوران، گارسون گفت میل دارید؟ گفتم پ نه پ، اومدیم صندلی‌ها رو تست کنیم! 😂",
    "به بابام گفتم برام آیفون می‌خری؟ گفت آره، قفل فرمون هم براش می‌خرم دزد نبره! 😂",
    "گوشیم گفت حافظه‌ام پره؛ گفتم مال منم پره، ولی کسی منو آپدیت نمی‌کنه! 😅",
    "به اینترنت گفتم چرا کندی؟ گفت من کند نیستم، تو زیادی عجله داری! 🐢",
    "برنامه‌نویس رفت خرید؛ گفت یه نون بده، اگه تخم‌مرغ داشتی ۶ تا بده... با ۶ تا نون برگشت! 🤓",
    "زنگ زدم پشتیبانی گفتم اینترنت ندارم؛ گفت مودم رو خاموش روشن کن. گفتم خودمو چی؟ 😂",
    "گربه‌م روی کیبورد راه رفت؛ الان مدیر پروژه‌ست و کدم از قبل بهتر کار می‌کنه! 🐈",
    "گفتم از شنبه ورزش می‌کنم؛ شنبه گفت منو قاطی برنامه‌هات نکن! 🏃",
    "رفتم رژیم بگیرم، یخچال گفت: این رابطه رو این‌طوری تموم نکن! 🍕",
    "ساعتم زنگ زد که بیدار شم؛ خاموشش کردم تا خودش یکم استراحت کنه! ⏰",
    "دوستم گفت مثبت فکر کن؛ قبض برق رو دیدم، مثبتش خیلی زیاد بود! ⚡",
    "معلم گفت چرا مشقت رو ننوشتی؟ گفتم خواستم در مصرف جوهر صرفه‌جویی کنم! ✍️",
    "رفتم بانک گفتم موجودی می‌خوام؛ گفت توی حسابت یا توی زندگیت؟ گفتم بی‌خیال! 😭",
    "گوشی افتاد توی آب؛ سریع گذاشتمش روی حالت پرواز که غرق نشه! ✈️",
    "به دوستم گفتم چرا انقدر آنلاینی؟ گفت دارم از اینترنت مراقبت می‌کنم قطع نشه! 🌐",
    "دکتر گفت استرس نداشته باش؛ گفتم باشه، استرسم رو می‌دم شما نگه دار! 😄",
    "مامانم گفت اتاقت رو مرتب کن؛ چراغ رو خاموش کردم، دیگه هیچی معلوم نبود! 😎",
    "رفتم باشگاه ثبت‌نام کردم؛ همین ثبت‌نام انقدر خسته‌ام کرد که برگشتم خونه! 💪",
    "به لپ‌تاپم گفتم خسته نباشی؛ هنگ کرد... ظاهراً احساساتی شد! 💻",
    "دوستم گفت حافظه‌ات ضعیفه؛ گفتم از کی؟ گفت چی از کی؟ گفتم چی؟ 🤔",
    "به تقویم گفتم چرا انقدر روزات شلوغه؟ گفت همه قراراشونو با من می‌ذارن! 📅",
    "رفتم عینک‌فروشی گفتم آینده‌ام رو تار می‌بینم؛ گفت اینجا عینک داریم، معجزه نه! 👓",
    "آلارم گوشی تنها کسیه که هر روز با اعتمادبه‌نفس منو صدا می‌زنه و جواب رد می‌شنوه! 😂",
]

QUOTES = [
    "فرداهای روشن، سهم کسانی است که امروز برای رویاهایشان می‌جنگند. ✨",
    "موفقیت یک‌شبه نیست؛ نتیجه قدم‌های کوچکی است که هر روز برمی‌داری. 💪",
    "بزرگ‌ترین ریسک زندگی، ریسک نکردن است. مسیرت را خودت بساز! 🚀",
    "هرگز اجازه نده ترس‌هایت جای رویاهایت را بگیرند. 🌅",
    "بهترین زمان برای شروع، بعد از «دیروز» همین الان است. 🌱",
    "قرار نیست همیشه انگیزه داشته باشی؛ گاهی فقط باید ادامه بدهی. 🔥",
    "سرعت مهم نیست؛ مهم این است که متوقف نشوی. 🛤",
    "تو از روزهای سخت قبلی عبور کردی؛ از این یکی هم عبور می‌کنی. 🧡",
    "مقایسه‌ات را با دیروزِ خودت انجام بده، نه امروز دیگران. 🎯",
    "یک تصمیم کوچک امروز می‌تواند مسیر یک سال آینده را عوض کند. ⚡",
    "شجاعت یعنی با وجود ترس، یک قدم جلو بروی. 🦁",
    "استراحت‌کردن عقب‌نشینی نیست؛ بخشی از ادامه‌دادن است. 🌿",
    "گاهی بسته‌شدن یک در، راه دیدن پنجره‌ای تازه است. 🪟",
    "روی چیزی که کنترل می‌کنی تمرکز کن: تلاش، انتخاب و نگرشت. 🧠",
    "هیچ مهارتی از روز اول حرفه‌ای نبوده؛ به خودت فرصت بده. 🛠",
    "روزهای معمولی‌اند که نتیجه‌های فوق‌العاده را می‌سازند. ☀️",
    "اگر مسیر سخت شده، شاید دقیقاً داری رشد می‌کنی. 🏔",
    "نسخه بهتر تو با یک حرکت بزرگ ساخته نمی‌شود؛ با تکرار قدم‌های کوچک ساخته می‌شود. 📈",
    "خودت را برای پیشرفت‌های آرام هم تشویق کن؛ آن‌ها واقعی‌اند. 👏",
    "امروز لازم نیست کامل باشی؛ کافی است حاضر باشی و تلاش کنی. 💫",
]

QUIZ_QUESTIONS = [
    ("کدام حیوان سه قلب دارد؟", ["دلفین", "اختاپوس", "پنگوئن", "کوسه"], 1, "اختاپوس سه قلب دارد! 🐙"),
    ("اولین هشتگ در کدام پلتفرم معروف شد؟", ["تلگرام", "اینستاگرام", "توییتر/X", "یوتیوب"], 2, "هشتگ در توییتر معروف شد. #️⃣"),
    ("کدام ایموجی در سال ۲۰۱۵ واژه سال آکسفورد شد؟", ["😂", "❤️", "🔥", "🤔"], 0, "ایموجی اشک شوق 😂 انتخاب شد."),
    ("سرعت نور تقریباً چند کیلومتر بر ثانیه است؟", ["۳۰ هزار", "۳۰۰ هزار", "۳ میلیون", "۳ هزار"], 1, "حدود ۳۰۰ هزار کیلومتر بر ثانیه! ⚡"),
    ("کدام مورد یک زبان برنامه‌نویسی نیست؟", ["Python", "Telegram", "Go", "Rust"], 1, "تلگرام پلتفرم پیام‌رسان است."),
]

# بانک کوییز فوری؛ سؤال‌ها محلی‌اند تا به چند سؤال محدود و تکراری وابسته نباشیم.
QUIZ_QUESTIONS.extend([
    ("بزرگ‌ترین اقیانوس جهان کدام است؟", ["اطلس", "آرام", "هند", "منجمد شمالی"], 1, "اقیانوس آرام بزرگ‌ترین اقیانوس جهان است."),
    ("سیارهٔ سرخ کدام است؟", ["زهره", "مریخ", "مشتری", "عطارد"], 1, "مریخ به‌دلیل رنگ سطحش سیارهٔ سرخ نامیده می‌شود."),
    ("فرمول شیمیایی آب چیست؟", ["CO2", "O2", "H2O", "NaCl"], 2, "آب از دو هیدروژن و یک اکسیژن ساخته شده است."),
    ("بزرگ‌ترین سیارهٔ منظومهٔ شمسی کدام است؟", ["زمین", "زحل", "مشتری", "نپتون"], 2, "مشتری بزرگ‌ترین سیارهٔ منظومهٔ شمسی است."),
    ("پایتخت ژاپن کدام است؟", ["کیوتو", "توکیو", "سئول", "پکن"], 1, "پایتخت ژاپن توکیو است."),
    ("کدام حیوان سریع‌ترین جانور خشکی است؟", ["شیر", "یوزپلنگ", "اسب", "گرگ"], 1, "یوزپلنگ سریع‌ترین جانور خشکی است."),
    ("شاهنامه اثر کدام شاعر است؟", ["حافظ", "فردوسی", "سعدی", "مولوی"], 1, "شاهنامهٔ فردوسی یکی از بزرگ‌ترین آثار حماسی جهان است."),
    ("نوروز آغاز کدام فصل است؟", ["تابستان", "پاییز", "بهار", "زمستان"], 2, "نوروز با آغاز بهار و سال نو ایرانی همراه است."),
    ("نماد شیمیایی طلا چیست؟", ["Ag", "Fe", "Au", "Cu"], 2, "نماد شیمیایی طلا Au است."),
    ("نیروی لازم برای حرکت جسم با چه واحدی سنجیده می‌شود؟", ["وات", "نیوتن", "ژول", "پاسکال"], 1, "واحد نیرو نیوتن است."),
    ("قلب انسان معمولاً چند حفره دارد؟", ["دو", "سه", "چهار", "پنج"], 2, "قلب انسان چهار حفره دارد."),
    ("واحد پول ژاپن چیست؟", ["وون", "یوان", "ین", "روپیه"], 2, "واحد پول ژاپن ین است."),
    ("اولین انسانی که روی ماه قدم گذاشت چه کسی بود؟", ["یوری گاگارین", "نیل آرمسترانگ", "باز آلدرین", "ایلان ماسک"], 1, "نیل آرمسترانگ در مأموریت آپولو ۱۱ روی ماه قدم گذاشت."),
    ("حاصل ۲ به توان ۳ چند است؟", ["۶", "۸", "۹", "۱۲"], 1, "۲×۲×۲ برابر با ۸ است."),
    ("کدام کشور به شکل چکمه شناخته می‌شود؟", ["اسپانیا", "ایتالیا", "یونان", "پرتغال"], 1, "شکل جغرافیایی ایتالیا شبیه چکمه است."),
    ("زبان رسمی برزیل چیست؟", ["اسپانیایی", "پرتغالی", "انگلیسی", "فرانسوی"], 1, "زبان رسمی برزیل پرتغالی است."),
    ("کدام گاز برای تنفس انسان ضروری است؟", ["هلیوم", "اکسیژن", "نیتروژن خالص", "هیدروژن"], 1, "اکسیژن برای تنفس سلولی ضروری است."),
    ("کدام فلز در دمای اتاق مایع است؟", ["آهن", "مس", "جیوه", "آلومینیوم"], 2, "جیوه در دمای اتاق مایع است."),
    ("کدام اندام وظیفهٔ اصلی پمپاژ خون را دارد؟", ["ریه", "کبد", "قلب", "کلیه"], 2, "قلب خون را در بدن پمپاژ می‌کند."),
    ("کدام عدد اول است؟", ["۹", "۱۵", "۱۷", "۲۱"], 2, "۱۷ فقط بر ۱ و خودش بخش‌پذیر است."),
    ("کدام قاره بزرگ‌ترین جمعیت را دارد؟", ["اروپا", "آسیا", "آفریقا", "آمریکای جنوبی"], 1, "آسیا پرجمعیت‌ترین قارهٔ جهان است."),
    ("کدام ساز معمولاً شش سیم دارد؟", ["فلوت", "گیتار", "ویولن", "پیانو"], 1, "گیتار معمولاً شش سیم دارد."),
    ("کدام دانشمند نظریهٔ نسبیت را مطرح کرد؟", ["نیوتن", "اینشتین", "داروین", "ادیسون"], 1, "نظریهٔ نسبیت با نام آلبرت اینشتین گره خورده است."),
    ("کدام ماده در مداد معمولی وجود دارد؟", ["گرافیت", "الماس", "آهن", "شیشه"], 0, "مغز مداد از گرافیت ساخته می‌شود."),
    ("پایتخت ایران کدام شهر است؟", ["تبریز", "تهران", "اصفهان", "شیراز"], 1, "تهران پایتخت ایران است."),
    ("کدام اثر متعلق به سعدی است؟", ["گلستان", "شاهنامه", "مثنوی", "منطق‌الطیر"], 0, "گلستان از آثار مشهور سعدی است."),
    ("کدام رود از شهر لندن می‌گذرد؟", ["سن", "تایمز", "دانوب", "راین"], 1, "رود تایمز از لندن عبور می‌کند."),
    ("کدام جانور پستاندار است؟", ["کوسه", "دلفین", "اختاپوس", "مار"], 1, "دلفین پستاندار است، نه ماهی."),
    ("کدام رنگ از ترکیب آبی و زرد به‌وجود می‌آید؟", ["سبز", "بنفش", "نارنجی", "صورتی"], 0, "ترکیب آبی و زرد سبز می‌شود."),
    ("کدام سیاره به حلقه‌هایش مشهور است؟", ["مریخ", "زحل", "زمین", "عطارد"], 1, "زحل حلقه‌های بسیار شناخته‌شده‌ای دارد."),
    ("کدام ویتامین بیشتر با نور خورشید مرتبط است؟", ["A", "B12", "C", "D"], 3, "بدن با کمک نور خورشید ویتامین D تولید می‌کند."),
    ("کدام کشور اهرام جیزه را دارد؟", ["مصر", "هند", "مکزیک", "پرو"], 0, "اهرام معروف جیزه در مصر قرار دارند."),
    ("کدام پرنده نمی‌تواند پرواز کند؟", ["عقاب", "پنگوئن", "پرستو", "شاهین"], 1, "پنگوئن پرنده‌ای شناگر و بدون توان پرواز است."),
    ("کدام ابزار برای اندازه‌گیری دماست؟", ["فشارسنج", "دماسنج", "قطب‌نما", "ترازو"], 1, "دماسنج دما را اندازه‌گیری می‌کند."),
    ("کدام بخش گیاه آب را از خاک جذب می‌کند؟", ["گل", "برگ", "ریشه", "میوه"], 2, "ریشه آب و مواد معدنی را جذب می‌کند."),
    ("کدام ورزش با راکت و توپ پردار انجام می‌شود؟", ["تنیس", "بدمینتون", "هندبال", "والیبال"], 1, "توپ پردار بدمینتون شاتل‌کاک نام دارد."),
    ("کدام ماده برای ساخت شیشه اصلی‌تر است؟", ["شن سیلیسی", "چوب", "پنبه", "نمک"], 0, "شیشه عمدتاً از سیلیس موجود در شن ساخته می‌شود."),
    ("کدام اقیانوس میان آفریقا و استرالیا قرار دارد؟", ["اطلس", "هند", "آرام", "منجمد جنوبی"], 1, "اقیانوس هند میان آفریقا، آسیا و استرالیا قرار دارد."),
    ("کدام شهر به نصف‌جهان مشهور است؟", ["اصفهان", "رشت", "کرمان", "اهواز"], 0, "اصفهان به‌خاطر موقعیت تاریخی‌اش نصف جهان نامیده شده است."),
    ("کدام حیوان به کشتی صحرا معروف است؟", ["اسب", "شتر", "فیل", "گوزن"], 1, "شتر با زندگی در بیابان سازگار است."),
    ("کدام عنصر برای زنگ‌زدگی آهن لازم است؟", ["اکسیژن و رطوبت", "هلیوم", "طلا", "نیتروژن خالص"], 0, "اکسیژن و آب به زنگ‌زدگی آهن کمک می‌کنند."),
    ("کدام قمر متعلق به زمین است؟", ["تیتان", "ماه", "اروپا", "فوبوس"], 1, "ماه قمر طبیعی زمین است."),
    ("کدام کشور به سرزمین آفتاب تابان معروف است؟", ["ژاپن", "کانادا", "مصر", "نروژ"], 0, "ژاپن سرزمین آفتاب تابان نامیده می‌شود."),
    ("کدام بخش بدن اکسیژن را به خون منتقل می‌کند؟", ["ریه‌ها", "معده", "پوست", "استخوان"], 0, "ریه‌ها تبادل اکسیژن و دی‌اکسیدکربن را انجام می‌دهند."),
    ("کدام عدد حاصل ۹×۹ است؟", ["۷۲", "۸۱", "۹۹", "۱۰۸"], 1, "۹ ضربدر ۹ برابر با ۸۱ است."),
    ("کدام شاعر اثر مثنوی معنوی را سروده است؟", ["مولوی", "فردوسی", "خیام", "نظامی"], 0, "مثنوی معنوی اثر مولاناست."),
    ("کدام حیوان بزرگ‌ترین پستاندار جهان است؟", ["فیل", "نهنگ آبی", "زرافه", "کرگدن"], 1, "نهنگ آبی بزرگ‌ترین پستاندار شناخته‌شده است."),
    ("کدام کشور شهر باستانی پترا را دارد؟", ["اردن", "چین", "ایتالیا", "برزیل"], 0, "پترا در اردن قرار دارد."),
    ("کدام حس با گوش ارتباط دارد؟", ["بینایی", "شنوایی", "چشایی", "لامسه"], 1, "گوش اندام شنوایی و تعادل است."),
    ("کدام مورد منبع انرژی تجدیدپذیر است؟", ["زغال‌سنگ", "نفت", "باد", "گاز طبیعی"], 2, "انرژی باد تجدیدپذیر است."),
    ("کدام شهر به شهر عشق و ادبیات فارسی مشهور است؟", ["شیراز", "قم", "بندرعباس", "زاهدان"], 0, "شیراز با حافظ و سعدی پیوند عمیقی دارد."),
])

MOOD_RESULTS = [

    "امروز انرژی‌ات روی حالت «میمِ ترکوننده» است 😂🔥",
    "امروز مغزت سریع‌تر از اینترنت همسایه کار می‌کنه ⚡🧠",
    "مود امروزت: آروم ولی آماده‌ی یک حرکت عجیب 😎",
    "امروز شانس خنده‌ات ۹۹٪ و شانس جدی‌بودنت ۱٪ است 🤡",
    "مود امروزت: قهرمان مخفی جدول رکوردها 🏆",
]

WEIRD_FACTS = [
    "🐙 اختاپوس سه قلب دارد و خونش به‌خاطر مس، آبی‌رنگ است.",
    "🍌 از نظر گیاه‌شناسی موز یک نوع توت است، اما توت‌فرنگی توت واقعی نیست!",
    "🦈 کوسه‌ها قبل از به‌وجودآمدن درختان روی زمین زندگی می‌کردند.",
    "🧠 خود بافت مغز گیرنده درد ندارد؛ برای همین بعضی جراحی‌های مغز با بیمار بیدار انجام می‌شود.",
    "🦦 سمورهای دریایی موقع خواب دست هم را می‌گیرند تا از هم دور نشوند.",
    "🍯 عسل در ظرف بسته و شرایط مناسب می‌تواند هزاران سال سالم بماند.",
    "🗼 برج ایفل در تابستان به‌خاطر انبساط فلز چند سانتی‌متر بلندتر می‌شود.",
    "🐦 کلاغ‌ها می‌توانند چهره انسان‌ها را سال‌ها به خاطر بسپارند.",
    "🌩 دمای مسیر صاعقه می‌تواند چند برابر سطح خورشید باشد.",
    "🧊 مدفوع وامبت‌ها مکعبی‌شکل است تا از روی سطوح نغلتد!",
    "🐬 دلفین‌ها برای هم اسم مخصوص دارند و با سوت یکدیگر را صدا می‌زنند.",
    "🌊 بیشتر اکسیژن زمین را جانداران ریز اقیانوسی تولید می‌کنند، نه فقط درختان.",
    "👃 انسان می‌تواند هزاران میلیارد ترکیب بویایی متفاوت را تشخیص دهد.",
    "🐘 فیل‌ها نمی‌توانند بپرند، اما شناگران بسیار خوبی هستند.",
    "🪐 یک روز در سیاره زهره از یک سال آن طولانی‌تر است.",
]

FUN_RIDDLES = [
    ("آن چیست که هرچه بیشتر از آن برداری، بزرگ‌تر می‌شود؟", "چاله"),
    ("چه چیزی مال توست ولی دیگران بیشتر از خودت از آن استفاده می‌کنند؟", "اسمت"),
    ("کدام ماه ۲۸ روز دارد؟", "همه ماه‌ها"),
    ("چه چیزی بالا می‌رود ولی پایین نمی‌آید؟", "سن"),
    ("بدون دهان حرف می‌زند و بدون گوش می‌شنود؛ چیست؟", "پژواک یا اکو"),
    ("چه چیزی کلید دارد ولی قفل باز نمی‌کند؟", "پیانو یا کیبورد"),
    ("همیشه جلوی توست ولی دیده نمی‌شود؛ چیست؟", "آینده"),
    ("هرچه خشک‌تر شود، بیشتر خیس می‌کند؛ چیست؟", "حوله"),
    ("چه چیزی پر از سوراخ است ولی آب را نگه می‌دارد؟", "اسفنج"),
    ("پا دارد اما راه نمی‌رود؛ چیست؟", "میز یا صندلی"),
    ("وقتی جوان است بلند و وقتی پیر می‌شود کوتاه است؛ چیست؟", "شمع"),
    ("می‌شکند بدون اینکه لمسش کنی؛ چیست؟", "قول"),
]

WOULD_YOU_RATHER = [
    ("یک هفته بدون اینترنت", "یک ماه بدون فست‌فود"),
    ("ذهن دوستت را بخوانی", "آینده را ده دقیقه ببینی"),
    ("همیشه ۱۰ دقیقه دیر برسی", "همیشه ۲۰ دقیقه زود برسی"),
    ("فقط با ایموجی حرف بزنی", "فقط با ویس جواب بدهی"),
    ("قدرت نامرئی‌شدن", "قدرت پرواز"),
    ("هر روز شنبه باشد", "هیچ‌وقت تعطیلات نباشد"),
    ("گوشی با باتری بی‌نهایت", "اینترنت با سرعت بی‌نهایت"),
    ("در گذشته زندگی کنی", "در آینده زندگی کنی"),
    ("همیشه حقیقت را بگویی", "هیچ‌وقت نتوانی سؤال بپرسی"),
    ("یک ربات آشپز داشته باشی", "یک ربات انجام تکالیف"),
]

QUICK_FUN_CHALLENGES = [
    "در ۳۰ ثانیه پنج چیز بنفش اطرافت پیدا کن! 💜",
    "اسم سه شهر رو بدون استفاده از حرف «ا» بگو! 🧠",
    "یک جمله معمولی رو مثل گوینده تریلر فیلم اکشن بخون! 🎬",
    "تا ۳۰ ثانیه بدون خندیدن به آخرین استیکری که گرفتی نگاه کن 😐",
    "به یک دوست فقط با سه ایموجی بگو امروز چه حالی داری 🎭",
    "اسم خودت رو با دست مخالف روی کاغذ بنویس ✍️",
    "سه بار سریع بگو «لایو وایرال واقعی»! ⚡",
    "بدون استفاده از حرف «م» یک تعریف از دوستت بنویس 🤝",
    "در ۳۰ ثانیه ده بار بشین و بلند شو؛ نتیجه رو گزارش کن 💪",
    "اولین آهنگی که یادت اومد رو فقط با ایموجی توصیف کن 🎵",
    "از آخرین عکس گالریت یک عنوان فیلم بساز 📸",
    "یک میم یک‌خطی درباره اینترنت کند بنویس 😂",
]

TEXT_MEMES = [
    "POV: فقط اومدی ساعت رو ببینی، ۴۵ دقیقه بعد هنوز تو تلگرامی 😂",
    "من: امشب زود می‌خوابم\nهمچنین من ساعت ۳: معنی خواب در زندگی چیست؟ 🤡",
    "اینترنت وقتی کار مهم داری: 🐢\nاینترنت وقتی باید بخوابی: 🚀",
    "مامان: مهمونا دارن میان، اتاقت رو جمع کن\nمن: کدوم اتاق؟ این یک اثر هنری مفهومی است 🎨",
    "برنامه‌نویس: فقط یک باگ کوچیکه\nسه ساعت بعد: کل اینترنت مقصره 💻🔥",
    "وقتی می‌گی فقط یک قسمت سریال و خورشید طلوع می‌کنه 🌅🍿",
    "من قبل از قهوه: فایل پیدا نشد\nمن بعد از قهوه: سیستم‌عامل ارتقا یافت ☕⚡",
    "گوشی روی ۱٪ باتری، ولی اعتمادبه‌نفس من برای دیدن یک ویدئوی دیگه: ۱۰۰٪ 🔋",
    "وقتی جواب درست رو بعد از تحویل امتحان یادت میاد: 🧠💡 دیر رسیدی!",
    "جلسه‌ای که می‌تونست یک پیام دوخطی باشه: 👥🕒😐",
]

FUN_FORTUNES = [
    "امروز یک پیام غیرمنتظره مودت رو بهتر می‌کنه 📩✨",
    "شانس امروزت روی حالت «یه امتحان دیگه بکن» تنظیم شده 🎯",
    "یک ایده کوچیک امروز می‌تونه شروع یک کار باحال باشه 💡",
    "امروز احتمال پیدا کردن پول تو جیب لباس قدیمی بالاست؛ تضمینی نیست ولی بگرد 😄",
    "کائنات می‌گه قبل از تصمیم مهم یک لیوان آب بخور 💧",
    "امروز یک نفر از انرژی مثبتت شارژ می‌شه؛ خسیس نباش 😎",
    "فال دیجیتال: باتری رو شارژ کن، ماجرا نزدیکه 🔋",
    "امروز بهترین زمان برای فرستادن اون پیامی‌ـه که هی عقب می‌ندازی 🚀",
]

# خبرها فقط از RSS عمومی منابع خوانده می‌شوند و با نام منبع نمایش داده می‌شوند.
NEWS_FEEDS = [
    ("https://news.google.com/rss/search?q=%D8%AA%DA%A9%D9%86%D9%88%D9%84%D9%88%DA%98%DB%8C&hl=fa&gl=IR&ceid=IR:fa", "Google News فارسی", "tech", "💻"),
    ("https://www.shahrsakhtafzar.com/fa/?format=feed&type=rss", "شهر سخت‌افزار", "tech", "🖥"),
    ("https://news.google.com/rss/search?q=%D8%A7%DB%8C%D8%B1%D8%A7%D9%86&hl=fa&gl=IR&ceid=IR:fa", "Google News فارسی", "iran", "🇮🇷"),
    ("https://feeds.bbci.co.uk/persian/rss.xml", "BBC فارسی", "world", "🌍"),
    ("https://parsi.euronews.com/rss?level=theme&name=news", "یورونیوز فارسی", "world", "🗞"),
]
NEWS_CACHE_TTL = 5 * 60
news_cache: dict = {"expires_at": 0.0, "items": [], "updated_at": None}
news_cache_lock = asyncio.Lock()

# تقویم مناسبت‌ها در API سرور نگهداری می‌شود تا Mini App بدون انتشار مجدد
# فایل‌های فرانت‌اند، هر روز اطلاعات تازه را دریافت کند.
CURATED_WORLD_DAYS: dict[str, list[str]] = {
    "1-1": ["روز جهانی صلح", "آغاز سال نو میلادی"],
    "1-4": ["روز جهانی خط بریل"],
    "1-24": ["روز جهانی آموزش"],
    "1-28": ["روز جهانی حفاظت از داده‌ها"],
    "2-4": ["روز جهانی مبارزه با سرطان"],
    "2-11": ["روز جهانی زنان و دختران در علم"],
    "2-13": ["روز جهانی رادیو"],
    "2-14": ["روز ولنتاین"],
    "2-20": ["روز جهانی عدالت اجتماعی"],
    "2-21": ["روز جهانی زبان مادری"],
    "3-3": ["روز جهانی حیات وحش"],
    "3-8": ["روز جهانی زنان"],
    "3-14": ["روز جهانی عدد پی"],
    "3-17": ["روز جهانی بوسیدن"],
    "3-20": ["روز جهانی شادی"],
    "3-21": ["روز جهانی شعر", "روز جهانی جنگل‌ها"],
    "3-22": ["روز جهانی آب"],
    "3-27": ["روز جهانی تئاتر"],
    "4-1": ["روز جهانی شوخی و خنده"],
    "4-2": ["روز جهانی آگاهی از اوتیسم"],
    "4-7": ["روز جهانی سلامت"],
    "4-12": ["روز جهانی سفر فضایی انسان"],
    "4-15": ["روز جهانی هنر"],
    "4-22": ["روز جهانی زمین"],
    "4-23": ["روز جهانی کتاب"],
    "4-30": ["روز جهانی جاز"],
    "5-1": ["روز جهانی کارگر"],
    "5-3": ["روز جهانی آزادی مطبوعات"],
    "5-4": ["روز جهانی جنگ ستارگان"],
    "5-15": ["روز جهانی خانواده"],
    "5-17": ["روز جهانی ارتباطات و جامعه اطلاعاتی"],
    "5-20": ["روز جهانی زنبور"],
    "5-21": ["روز جهانی تنوع فرهنگی"],
    "5-31": ["روز جهانی بدون دخانیات"],
    "6-1": ["روز جهانی والدین"],
    "6-3": ["روز جهانی دوچرخه"],
    "6-5": ["روز جهانی محیط زیست"],
    "6-8": ["روز جهانی اقیانوس‌ها"],
    "6-20": ["روز جهانی پناهندگان"],
    "6-21": ["روز جهانی موسیقی", "روز جهانی یوگا"],
    "6-22": ["روز جهانی بغل کردن"],
    "6-30": ["روز جهانی شبکه‌های اجتماعی"],
    "7-6": ["روز جهانی بوسه"],
    "7-11": ["روز جهانی جمعیت"],
    "7-15": ["روز جهانی مهارت‌های جوانان"],
    "7-17": ["روز جهانی ایموجی"],
    "7-20": ["روز جهانی شطرنج"],
    "7-28": ["روز جهانی حفاظت از طبیعت"],
    "7-29": ["روز جهانی باران", "روز جهانی ببر"],
    "7-30": ["روز جهانی دوستی"],
    "8-8": ["روز جهانی گربه"],
    "8-9": ["روز جهانی مردمان بومی"],
    "8-12": ["روز جهانی جوانان"],
    "8-19": ["روز جهانی عکاسی", "روز جهانی انسان‌دوستی"],
    "9-5": ["روز جهانی خیریه"],
    "9-8": ["روز جهانی سوادآموزی"],
    "9-15": ["روز جهانی دموکراسی"],
    "9-21": ["روز جهانی صلح"],
    "9-27": ["روز جهانی گردشگری"],
    "9-30": ["روز جهانی پادکست"],
    "10-1": ["روز جهانی قهوه", "روز جهانی سالمندان"],
    "10-4": ["روز جهانی حیوانات"],
    "10-5": ["روز جهانی معلم"],
    "10-10": ["روز جهانی سلامت روان"],
    "10-16": ["روز جهانی غذا"],
    "10-31": ["هالووین"],
    "11-10": ["روز جهانی علم در خدمت صلح"],
    "11-13": ["روز جهانی مهربانی"],
    "11-19": ["روز جهانی مردان"],
    "11-20": ["روز جهانی کودکان"],
    "11-21": ["روز جهانی تلویزیون"],
    "12-1": ["روز جهانی ایدز"],
    "12-3": ["روز جهانی افراد دارای معلولیت"],
    "12-5": ["روز جهانی داوطلب"],
    "12-10": ["روز جهانی حقوق بشر"],
    "12-18": ["روز جهانی زبان عربی"],
    "12-20": ["روز جهانی همبستگی انسانی"],
}
ONLINE_OCCASION_TRANSLATIONS = {
    "Rain Day": "روز جهانی باران",
    "International Tiger Day": "روز جهانی ببر",
    "World Emoji Day": "روز جهانی ایموجی",
    "International Day of Friendship": "روز جهانی دوستی",
    "World Nature Conservation Day": "روز جهانی حفاظت از طبیعت",
    "World Photography Day": "روز جهانی عکاسی",
    "World Kindness Day": "روز جهانی مهربانی",
    "World Mental Health Day": "روز جهانی سلامت روان",
    "World Animal Day": "روز جهانی حیوانات",
    "International Coffee Day": "روز جهانی قهوه",
    "World Tourism Day": "روز جهانی گردشگری",
    "International Day of Peace": "روز جهانی صلح",
    "World Population Day": "روز جهانی جمعیت",
    "World Environment Day": "روز جهانی محیط زیست",
    "World Oceans Day": "روز جهانی اقیانوس‌ها",
    "World Book Day": "روز جهانی کتاب",
    "World Health Day": "روز جهانی سلامت",
    "International Women's Day": "روز جهانی زنان",
    "World Radio Day": "روز جهانی رادیو",
    "International Mother Language Day": "روز جهانی زبان مادری",
    "International Left-Handers Day": "روز جهانی چپ‌دستان",
    "International Youth Day": "روز جهانی جوانان",
    "World Humanitarian Day": "روز جهانی بشردوستی",
    "International Literacy Day": "روز جهانی سوادآموزی",
    "World Suicide Prevention Day": "روز جهانی پیشگیری از خودکشی",
    "International Day of Democracy": "روز جهانی دموکراسی",
    "World Cleanup Day": "روز جهانی پاکسازی زمین",
    "International Day of Charity": "روز جهانی خیریه",
    "World Water Day": "روز جهانی آب",
    "World Autism Awareness Day": "روز جهانی آگاهی از اوتیسم",
    "World Teachers' Day": "روز جهانی معلم",
    "World Post Day": "روز جهانی پست",
    "World Food Day": "روز جهانی غذا",
    "World Savings Day": "روز جهانی پس‌انداز",
    "World Science Day": "روز جهانی علم",
    "World Television Day": "روز جهانی تلویزیون",
    "World Children's Day": "روز جهانی کودک",
    "World AIDS Day": "روز جهانی ایدز",
    "International Day of Persons with Disabilities": "روز جهانی معلولان",
    "World Soil Day": "روز جهانی خاک",
    "World Human Rights Day": "روز جهانی حقوق بشر",
    "International Mountain Day": "روز جهانی کوهستان",
    "International Migrants Day": "روز جهانی مهاجران",
    "World Cancer Day": "روز جهانی سرطان",
    "World Wetlands Day": "روز جهانی تالاب‌ها",
    "World Wildlife Day": "روز جهانی حیات وحش",
    "World Backup Day": "روز جهانی پشتیبان‌گیری",
    "International Men's Day": "روز جهانی مردان",
    "International Men’s Day": "روز جهانی مردان",
    "World Men's Day": "روز جهانی مردان",
    "World Men’s Day": "روز جهانی مردان",
    "International Day of Men": "روز جهانی مردان",
    "World Day of Men": "روز جهانی مردان",
    "World Consumer Rights Day": "روز جهانی حقوق مصرف‌کننده",
    "World Sleep Day": "روز جهانی خواب",
    "World Poetry Day": "روز جهانی شعر",
    "World Theatre Day": "روز جهانی تئاتر",
    "World Press Freedom Day": "روز جهانی آزادی مطبوعات",
    "International Day of Happiness": "روز جهانی شادی",
}
OCCASION_CACHE_TTL = 6 * 60 * 60
occasion_cache: dict = {"key": None, "expires_at": 0.0, "online": []}
occasion_cache_lock = asyncio.Lock()

WEB_JOKES = JOKES + [
    "گوشیم گفت فضای ذخیره‌سازی کمه؛ چندتا عکس از غذام پاک کردم، الان خودش گرسنه‌ش شده! 😂",
    "به اینترنت گفتم چرا کندی؟ گفت من کند نیستم، تو زیادی عجله داری! 🐢",
    "برنامه‌نویس رفت خرید، گفت یه نون بده؛ اگه تخم‌مرغ داشتی ۶ تا بده... با ۶ تا نون برگشت! 🤓",
    "زنگ زدم پشتیبانی گفتم اینترنت ندارم؛ گفت مودم رو خاموش روشن کن. گفتم خودمو چی؟ 😅",
    "گربه‌م روی کیبورد راه رفت؛ الان مدیر پروژه‌ست و کدم از قبل بهتر کار می‌کنه! 🐈",
    "گفتم از شنبه ورزش می‌کنم؛ شنبه گفت منو قاطی برنامه‌هات نکن! 🏃",
]

# ======== مکالمه محاوره‌ای فارسی ========
MOOD_RESPONSES = {
    "good": [
        "خداروشکر که خوبی! همین انرژی خوب رو نگه دار 💖",
        "چه عالی! خوشحال شدم شنیدم حالت خوبه 😄",
        "دمت گرم، پس امروز باید یه رکورد خفن هم بزنی! 🔥",
        "عالیه رفیق! امیدوارم روزت از اینم بهتر بشه ✨",
        "این خبر خوب حال منم خوب کرد! 😎",
    ],
    "bad": [
        "ای بابا... متأسفم که حالت خوب نیست 😔 اگر دوست داری حرف بزن، من گوش می‌دم.",
        "سخت می‌گذره، ولی لازم نیست تنهایی تحملش کنی. یکم نفس بکش و به خودت فرصت بده 💛",
        "خسته نباشی رفیق؛ گاهی یک استراحت کوتاه واقعاً لازمه 🌿",
        "امیدوارم زودتر سبک‌تر بشی. می‌خوای یک جوک بگم یا باهم بازی کنیم؟ 🌈",
        "من اینجام؛ حتی اگه فقط بخوای چند دقیقه حواست پرت بشه 🤍",
    ],
}

BOT_MOOD_RESPONSES = [
    "سلام رفیق! من خوبم و پرانرژی‌ام؛ تو چطوری؟ 😊⚡",
    "عالی‌ام، مخصوصاً حالا که اومدی! خودت چه خبر؟ 😄🔥",
    "رو فرم و آنلاینم! بگو امروز قراره چی رو بترکونیم؟ 🚀",
    "من توپم رفیق؛ تو فقط بگو چه برنامه‌ای داریم! 😎",
    "همیشه آماده‌ی گپ و بازی‌ام! حال تو چطوره قهرمان؟ ❤️‍🔥",
]

# این نگاشت با الهام از الگوهای رایج زبان محاوره‌ای فارسی و منابع باز
# مانند ParsMap و GPTInformal-Persian، شکل‌های روزمره را یکدست می‌کند.
COLLOQUIAL_ALIASES = {
    "نیسم": "نیستم", "هسم": "هستم", "میخام": "میخوام", "میخاد": "میخواد",
    "میخوایم": "میخوایم", "نمخام": "نمیخوام", "نمیشه": "نمی شه", "میشه": "می شه",
    "چجوری": "چطور", "چطوری": "چطور", "چیکار": "چه کار", "چیکارا": "چه کارها",
    "واسه": "برای", "برا": "برای", "رو": "را", "توو": "تو", "اینقد": "اینقدر",
    "اونقد": "اونقدر", "یه": "یک", "یخورده": "یکم", "یکم": "کمی",
    "آخه": "آخر", "اره": "آره", "آری": "آره", "نخیر": "نه", "اوکیه": "اوکی",
    "مرسیی": "مرسی", "سلاممم": "سلام", "خوبیی": "خوبی", "باحاله": "باحال",
    "خستم": "خسته ام", "گرسنمه": "گرسنه ام", "خوابم میاد": "خواب آلودم",
    "دلم گرفته": "ناراحتم", "اعصابم خورده": "کلافه ام", "حوصلم": "حوصله ام",
    "نمیدونم": "نمی دونم", "میدونی": "می دونی", "میگم": "می گم",
}

CHAT_INTENTS = [
    ({"فدات", "فداتشم", "فدات شوم", "فدات شم", "قربونت", "قربونت برم", "دورت بگردم"}, [
        "قربون مرامت، فدای تو رفیق! ❤️",
        "اختیار داری، خودت عزیزی! 🫶",
        "الهی من فدای این همه محبتت بشم 😄",
        "مرسی که انقدر باحالی؛ دمت گرم! 🌹",
    ]),
    ({"عشقی", "عشق منی", "عشقمی", "قلبمی", "دوستت دارم", "لاو یو", "عاشقتم"}, [
        "خودت عشقی رفیق! ❤️‍🔥",
        "این انرژی قشنگت به کل ربات رسید! 🫶",
        "دوست داشتنت برگشت خورد سمت خودت؛ دو برابر! 💜",
        "قلب منم با این پیامت نئونی شد! 💖",
    ]),
    ({"دمت گرم", "مرسی", "ممنون", "متشکرم", "سپاس", "تشکر", "لطف کردی"}, [
        "خواهش می‌کنم رفیق، روی من حساب کن! 🤝",
        "قابلی نداشت؛ هر وقت خواستی من هستم ❤️",
        "دمت گرم که گفتی! خوشحالم به کارت اومد 😄",
        "مخلصیم! حالا بریم سراغ یه چیز خفن‌تر؟ ⚡",
    ]),
    ({"چاکرم", "نوکرم", "مخلصم", "مخلص", "ارادت", "قربانت"}, [
        "چاکریم رفیقِ با مرام! 🙌",
        "مخلص خودت، چه خبر ازت؟ 😎",
        "ارادت دوطرفه‌ست رفیق! 🤝",
        "نوکر مرامت! بگو چه کمکی ازم برمیاد؟ ❤️",
    ]),
    ({"باحالی", "خفنی", "عالی هستی", "کارت درسته", "دمت گرم ربات", "تو خوبی"}, [
        "از خودت یاد گرفتم رفیق! 😎🔥",
        "خفن واقعی خودتی که اینجایی! ⚡",
        "این تعریف رفت مستقیم توی حافظه قلبم! 💜",
        "مرسی! قول می‌دم خفن‌تر هم بشم 🚀",
    ]),
    ({"خخ", "هههه", "هاها", "ترکیدم", "مردم از خنده", "خیلی خنده دار بود"}, [
        "خنده‌ات مستدام! 😂",
        "صبر کن هنوز جوکای سنگین‌ترم مونده! 🤣",
        "ماموریت خندوندن با موفقیت انجام شد ✅😂",
        "پس گرفت! یکی دیگه بگم؟ 😄",
    ]),
    ({"حوصلم سر رفته", "حوصله ندارم", "بیکارم", "چی کار کنم", "سرگرمم کن"}, [
        "وقتشه بزن در رو یا کوئیز فوری رو امتحان کنی! «منو» رو بفرست 🎮",
        "بیا یه جوک بگم یا بریم سراغ جرأت یا حقیقت؟ 😏",
        "حوصله‌سربری ممنوع! Mini App پر از بازی و چالشه ⚡",
        "یه پیشنهاد: اول جایزه روزانه‌ات رو بگیر، بعد رکورد بازی بزن! 🏆",
    ]),
    ({"ببخشید", "شرمنده", "معذرت", "ببخش", "سوری"}, [
        "قابلی نداشت رفیق، همه‌چی اوکیه 🤍",
        "بی‌خیال، اصلاً چیزی نشده! 😄",
        "بخشیده شدی؛ جریمه‌ات فقط یه لبخنده 😁",
    ]),
    ({"خداحافظ", "فعلا", "بای", "شب خوش", "میبینمت", "بعدا میام"}, [
        "فعلاً رفیق! زود برگرد که کلی بازی داریم 👋",
        "خداحافظ، مراقب خودت باش! 💜",
        "بای بای! درِ ربات همیشه به روت بازه 😄",
    ]),
    ({"کی هستی", "اسمت چیه", "تو چی هستی", "خودتو معرفی کن"}, [
        "من Ajorpareh‌ام؛ رفیق دیجیتالیِ بازی، خبر، جوک و حال خوب! 👾⚡",
        "یه سوپرربات شیطون و باحال که برای سرگرمی و کمک اینجاست 😎",
    ]),
    ({"چه کارایی بلدی", "چیکار میکنی", "چه امکاناتی داری", "راهنما", "کمک"}, [
        "بازی، Mini App، خبر روز، جوک، کوئیز، کپشن‌سازی، دانلود و کلی چیز دیگه! «منو» رو بفرست 🚀",
        "کافیه «منو» رو بفرستی تا کل قابلیت‌هام رو ببینی؛ انتخاب با توئه 😄",
    ]),
    ({"باشه", "اوکی", "حله", "چشم", "قبوله", "آره"}, [
        "حله رفیق! ✅",
        "بزن بریم! 😎",
        "اوکیه، من پایه‌ام ⚡",
    ]),
    ({"نه", "نخیر", "بیخیال", "ولش کن"}, [
        "باشه رفیق، هر جور راحتی 😊",
        "اوکی، می‌ریم سراغ گزینه بعدی! 👌",
        "بی‌خیالش شدیم؛ بگو چی دوست داری؟",
    ]),
    ({"چه خبر", "چه میکنی", "اوضاع چطوره"}, [
        "سلامتی! اینجا خبر، بازی و انرژی خوب همیشه هست؛ تو چه خبر؟ 😄",
        "همه‌چی رو به راهه؛ منتظرم تو یه مأموریت خفن بدی! ⚡",
    ]),
    ({"سلام", "درود", "سلام علیکم", "های", "hello", "صبح بخیر", "عصر بخیر", "شب بخیر"}, [
        "سلام رفیق! خوش اومدی 👋 حالت چطوره؟",
        "درود به روی ماهت! چه خبر؟ 😄",
        "سلام سلام! آماده‌ای امروز یه کار خفن کنیم؟ ⚡",
        "خوش اومدی رفیق! بازی، جوک یا گپ؟ انتخاب با تو 😎",
    ]),
]

EXTENDED_CHAT_INTENTS = [
    ({"کجایی", "هستی", "آنلاینی", "بیداری", "هنوز هستی"}, [
        "همین‌جام رفیق، آنلاین و فول‌انرژی! بگو چه خبره؟ ⚡",
        "آره که هستم! من که خواب ندارم، پایه‌ام 😄",
        "حواسم کامل به توئه؛ بگو ببینم چی شده 👀",
    ]),
    ({"گرسنمه", "گرسنه ام", "چی بخورم", "غذا چی", "ناهار چی", "شام چی"}, [
        "اگه سریع می‌خوای: املت یا ساندویچ خونگی؛ اگه حال داری پاستا رو بترکون! 🍳🍝",
        "اول ببین یخچال چی می‌گه 😄 موادت رو بگو تا یه پیشنهاد خفن بچینم.",
        "من رأی می‌دم به چیزی که هم خوشمزه باشه هم بعدش پشیمونت نکنه! چی دم دستته؟ 🍕",
    ]),
    ({"خوابم میاد", "خواب آلودم", "برم بخوابم", "نمی تونم بخوابم", "بی خوابم"}, [
        "اگه چشمت سنگینه، گوشی رو بذار کنار و یه خواب حسابی برو؛ فردا انرژی‌ات دوبرابر می‌شه 😴✨",
        "برای خواب: نور کم، گوشی دور، چند نفس آروم. مغزت رو از حالت اسکرول بیار بیرون 🌙",
        "اگه فردا کار داری، بزن به دل خواب قهرمان! ربات فردا هم همین‌جاست 😄",
    ]),
    ({"سر کارم", "دارم کار می کنم", "درس دارم", "امتحان دارم", "باید درس بخونم", "تمرکز ندارم"}, [
        "بزن بریم: فقط ۲۵ دقیقه تمرکز، بعد ۵ دقیقه استراحت. شروع کوچیک، نتیجه خفن! ⏱️🔥",
        "کار رو به یه قدم خیلی کوچیک تبدیل کن و همونو همین الان بزن؛ حرکت که کنی موتور روشن می‌شه 🚀",
        "گوشی رو ده دقیقه سایلنت کن، سخت‌ترین بخش رو اول بزن؛ تو از پسش برمیای 💪",
    ]),
    ({"استرس دارم", "نگرانم", "دلشوره دارم", "می ترسم", "اضطراب دارم"}, [
        "یک نفس عمیق رفیق؛ چهار ثانیه دم، چهار ثانیه مکث، شش ثانیه بازدم. الان فقط قدم بعدی مهمه 🤍",
        "نگرانی‌ات قابل فهمه. بیا موضوع رو تیکه‌تیکه کنیم تا از یه هیولای بزرگ بشه چند کار کوچیک 💛",
        "تنها نیستی رفیق. اگه دوست داری بگو دقیقاً کدوم بخشش بیشتر فشارت می‌ده.",
    ]),
    ({"تنها شدم", "تنهایی", "کسی نیست", "دلم گرفته", "حالم گرفته"}, [
        "من اینجام رفیق 🤍 حرف بزن؛ لازم نیست همه‌چی رو مرتب و قشنگ تعریف کنی.",
        "دلت هرچی می‌خواد بگه، من قضاوت نمی‌کنم. از کجاش شروع کنیم؟ 🌿",
        "یه بغل دیجیتالی محکم برای تو 🫂 بیا چند دقیقه باهم گپ بزنیم.",
    ]),
    ({"نظرت چیه", "تو چی فکر می کنی", "به نظرت", "پیشنهادت چیه"}, [
        "پایه‌ام نظر بدم! فقط موضوع یا گزینه‌هات رو کامل بگو تا دقیق بریم سر اصل مطلب 😎",
        "بذار منطقی و رفیقانه نگاهش کنیم؛ جزئیاتش رو بگو 👀",
        "من می‌گم مزایا و ایرادهاش رو کنار هم بچینیم، بعد تصمیم رو بترکونیم! ⚡",
    ]),
    ({"جدی", "واقعا", "راست میگی", "شوخی میکنی", "باورم نمیشه"}, [
        "جدیِ جدی! 😄 ولی اگه موضوع اطلاعاتیه، بذار دقیق چکش کنیم.",
        "آره رفیق! خودمم جای تو بودم یه ابرو می‌انداختم بالا 😂",
        "حق داری شک کنی؛ بگو کدوم بخش رو روشن‌تر توضیح بدم 👌",
    ]),
    ({"آفرین", "باریکلا", "ایول", "حرف نداری", "دمت جیز"}, [
        "ایول به خودت که این‌همه انرژی می‌دی! 🔥🙌",
        "دمت گرم قهرمان! حالا بریم مرحله بعد رو هم بترکونیم 🚀",
        "قربون مرامت! این تعریف رفت توی بخش افتخارات 😄🏆",
    ]),
    ({"نمیدونم", "نمی دونم", "گیج شدم", "دو دلم", "تصمیم ندارم"}, [
        "اشکال نداره؛ گزینه‌هات رو بگو، باهم سبک‌سنگینشون می‌کنیم تا واضح بشه ⚖️✨",
        "وقتی گیجی، تصمیم رو کوچیک کن: الان فقط قدم بعدی چیه؟ من کنارت می‌چینمش 😎",
        "عجله نکن رفیق. دو تا انتخاب اصلیت رو بگو تا بریم سراغ مزایا و دردسرهاشون.",
    ]),
    ({"خسته نباشی", "دستت درد نکنه", "زحمت کشیدی"}, [
        "سلامت باشی رفیق! انرژی تو خستگی نمی‌ذاره بمونه 😄⚡",
        "قربونت، انجام وظیفه بود! حالا بگو بعدی چیه 🚀",
    ]),
    ({"امروز چطور بود", "روزت چطور بود", "امروز چه کردی"}, [
        "روز من با پیام تو روشن شد رفیق! 😄 روز خودت چطور گذشت؟",
        "پر از کد و بازی و انرژی بود؛ حالا نوبت قصه توئه، امروز چه خبر بود؟ ⚡",
    ]),
]


def normalize_chat_text(text: str) -> str:
    text = text.lower().translate(str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه"}))
    text = text.replace("\u200c", " ")
    text = re.sub(r"[ًٌٍَُِّْـ]", "", text)
    text = re.sub(r"[^\w\s\u0600-\u06ff😂🤣❤️❤]", " ", text)
    text = re.sub(r"(.)\1{3,}", r"\1\1", text)
    compact = re.sub(r"\s+", " ", text).strip()
    normalized = f" {compact} "
    for informal, standard in sorted(COLLOQUIAL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(f" {informal} ", f" {standard} ")
    return re.sub(r"\s+", " ", normalized).strip()


def detect_mood(text: str) -> str | None:
    normalized = normalize_chat_text(text)
    bad_phrases = ["خوب نیستم", "خوب نیسم", "حالم بده", "حالم خوب نیست", "ناراحتم", "خسته ام", "داغونم", "غمگینم", "دلگیرم", "کلافه ام"]
    if any(phrase in normalized for phrase in bad_phrases):
        return "bad"
    good_phrases = ["خوبم", "عالی ام", "خوشحالم", "سرحالم", "رو فرم", "بد نیستم", "خوب هستم"]
    if any(phrase in normalized for phrase in good_phrases):
        return "good"
    return None


def get_chat_response(text: str) -> str | None:
    normalized = normalize_chat_text(text)
    words = set(normalized.split())
    for patterns, responses in [*CHAT_INTENTS, *EXTENDED_CHAT_INTENTS]:
        matched = any(
            pattern in words if " " not in pattern and len(pattern) <= 3 else pattern in normalized
            for pattern in patterns
        )
        if matched:
            return random.choice(responses)
    return None


def detect_profanity(text: str) -> set[str]:
    normalized = normalize_chat_text(text).replace("‌", " ")
    words = set(normalized.split())
    joined = normalized.replace(" ", "")
    matches = {term for term in PROFANITY_WORDS if (term in words or (" " in term and term in normalized))}
    # برای شکل‌های جداشده/سانسورشده فقط ناسزاهای شدید و کم‌ابهام را بررسی می‌کنیم.
    for term in SEVERE_PROFANITY:
        if len(joined) <= 80 and term.replace(" ", "") in joined:
            matches.add(term)
    return matches


TRUTH_QUESTIONS = [
    # عمومی
    "آخرین باری که الکی گفتی «الان میام» کی بود؟ 😏",
    "خجالت‌آورترین آهنگی که یواشکی دوست داری چیه؟ 🎵",
    "اگه یک روز نامرئی بشی، اولین کاری که می‌کنی چیه؟ 👻",
    "آخرین چیزی که توی گوگل سرچ کردی چی بود؟ 🔍",
    "کدوم عادتت رو دوست داری هیچ‌کس نفهمه؟ 🙈",
    "اگه مجبور باشی یک اپ رو برای همیشه پاک کنی، کدومه؟ 📱",
    "بدترین سوتی‌ای که جلوی جمع دادی چی بوده؟ 😅",
    "بین دوستات کی بیشتر از همه میم می‌فرسته؟ 😂",
    "اگه همین الان یک آرزو برآورده بشه، چی می‌خوای؟ ✨",
    "تا حالا پیام کسی رو دیدی و عمداً جواب ندادی؟ چرا؟ 👀",
    "عجیب‌ترین غذایی که دوست داری چیه؟ 🍕",
    "اگه زندگیت فیلم بود، اسمش چی می‌شد؟ 🎬",
    "بزرگ‌ترین ترس خنده‌دارت چیه؟ 😬",
    "کدوم شخصیت کارتونی بیشتر شبیه توئه؟ 🧸",
    "آخرین بار سر چی از ته دل خندیدی؟ 🤣",
    "آخرین پیامی که تایپ کردی و بعد پاکش کردی چی بود؟ ⌨️",
    "اگه یک هفته فقط یک خوراکی می‌تونستی بخوری، چی می‌خوردی؟ 🍜",
    "کدوم کارت رو همه فکر می‌کنن بلدی ولی واقعاً بلد نیستی؟ 🎭",
    "آخرین بار کی اشک ریختی و دلیلش چی بود؟ 🥺",
    "اگه توی یک گروه موسیقی بودی، چه ساز یا نقشی داشتی؟ 🎸",
    "کدوم استایل/مدلی رو هیچ‌وقت جرات نمی‌کنی بپوشی؟ 👗",
    "بدترین تاریخی که تا حالا رفتی چطور بود؟ (اگه بوده) 💔",
    "اگه بتونی یک خاطره رو از ذهنت پاک کنی، کدومه؟ 🧹",
    "تا حالا برای یک چیزی توی صف موندی و آخرش پشیمون شدی؟ 🕐",
    "کدوم جمله از حرفای بزرگ‌ترها همیشه توی ذهنت می‌مونه؟ 🗣",
    "اگه یک شب با یک شخصیت تاریخی شام می‌خوردی، کی رو انتخاب می‌کردی؟ 🏛",
    "آخرین باری که از خجالت سرخ شدی کی بود؟ 🔴",
    "اگه فقط یک اپلیکیشن روی گوشیت می‌موند، کدومو نگه می‌داشتی؟ 📲",
    "چیزی که الان توی کوله/کیفت هست و نباید اونجا باشه چیه؟ 🎒",
    "اگه یک روز با کفش‌های جاوا می‌رفتی بیرون، کجا می‌رفتی؟ 👟",
    "تا حالا به کسی که دوستش داری اعتراف کردی؟ نتیجه چی شد؟ 💘",
    "کدوم سریال/انیمه رو بیشتر از ۳ بار دیدی؟ 🍿",
    "اگر یک سوپرپاور داشتی که فقط ۲۴ ساعت بود، چی انتخاب می‌کردی؟ ⚡",
    "بدترین خریدی که کردی و بعدش پشیمون شدی چی بود؟ 🛍",
    "اگه ربات بودی، اولین دستوری که می‌گفتی چی بود؟ 🤖",
]

DARE_CHALLENGES = [
    "تا ۵ دقیقه فقط با ایموجی جواب بده! 😎",
    "یک ویس ۵ ثانیه‌ای با صدای گوینده اخبار ضبط کن! 🎙",
    "به آخرین نفری که چت کردی یک میم بفرست 😂",
    "اسم خودت رو با دست مخالف بنویس و عکسش رو بفرست ✍️",
    "۳۰ ثانیه بدون خندیدن به صفحه نگاه کن 😐",
    "یک جمله معمولی رو طوری بگو انگار تریلر فیلم اکشنه 🎬",
    "سه بار سریع بگو «لایو وایرالِ واقعی»! ⚡",
    "تا یک دقیقه عکس پروفایلت رو با یک ایموجی توصیف کن 👾",
    "یک تعریف واقعی و باحال از یکی از دوستات بکن 💜",
    "۱۰ حرکت ورزشی انجام بده و فقط نتیجه رو گزارش کن 💪",
    "اسم سه خوراکی رو در کمتر از ۵ ثانیه برعکس بگو! 🍔",
    "یک استیکر تصادفی برای نفر پنجم لیست چتت بفرست 🎲",
    "بدون استفاده از حرف «ا» یک جمله بنویس 🧠",
    "صدای یک حیوان رو تقلید کن؛ بقیه باید حدس بزنن 🐸",
    "یک دقیقه گوشی رو کنار بذار و بعد با «انجام شد» برگرد 🌿",
    "به مدت ۲ دقیقه فقط با لهجه شیرازی حرف بزن 🍊",
    "یک سلفی با حالتی که داری الان بفرست (بدون فیلتر!) 🤳",
    "سه تا چیزی که توی جیبت/کیفت هست رو اسم ببر 🎒",
    "حالا یک رپ ۱۰ ثانیه‌ای درباره خودت بداهه بگو 🎤",
    "تا ۳ پیام بعدی، اول همه رو با «قربونت» شروع کن 😂",
    "با حالت چهره‌ات یک احساس رو نشون بده؛ بقیه حدس بزنن 🎭",
    "یک ویس با صدای یک کارتون (مثلاً باب‌اسفنجی) بفرست 🧽",
    "پست آخر اینستاگرام/تلگرام خودت رو برای گروه بفرست 📤",
    "یک چیز که تا حالا به هیچ‌کس نگفتی رو بگو (در حد معقول) 🤫",
    "تا آخر بازی، هر جوابی می‌دی آخرش «والا» بگو 🐪",
    "چشمانت رو ببند و یک شکل بکش؛ عکسش رو بفرست 🎨",
    "۱۰ ثانیه با صدای یک پیرمرد/پیرزن حرف بزن 👵",
    "به نفر بعدی یک تعارف واقعی بکن (بدون خنده) 😊",
    "یک آهنگ رو با کلمات خودت برای بقیه توصیف کن 🎵",
    "تا ۵ دقیقه، به هر سؤالی فقط با «بله» یا «نه» جواب بده ✅❌",
    "حدس بزن چند نفر الان پیامت رو باز کردن؛ نزدیک‌ترین برنده 🎯",
    "یک جمله با کلمات: پیتزا، موشک، کتاب بساز 🚀🍕📚",
    "مثل یک ربات با صدای خشک و بی‌احساس صحبت کن 🤖",
    "با چشم بسته یک عدد ۱ تا ۱۰۰ بگو؛ بعدش یه حقیقت اضافه بگو 🎲",
]

COUPLE_TRUTH = [
    "اولین باری که دلت خواست منو ببینی کی بود؟ 🥰",
    "کدوم عادت من اول از همه توجت رو جلب کرد؟ 👀",
    "اگه یک روز کامل فقط ما دوتا باشیم، چیکار می‌کنیم؟ 🌙",
    "کدوم جای دنیا رو دوس داری با هم بریم؟ ✈️",
    "بهترین پیامی که تا حالا برات فرستادم چی بوده؟ 💌",
    "کدوم کار من ناخودآگاه حالِ خوب بهت میده؟ 😊",
    "اگه من یک ابرقهرمان بودم، اسمم چی بود؟ 🦸‍♀️",
    "اولین چیزی که از من توی ذهنت مونده چیه؟ 💭",
    "چه غذایی رو دوست داری اولین بار برات درست کنم؟ 🍳",
    "با کدوم آهنگ ما رو یادت میاد؟ 🎶",
    "اگه قرار بود یک سریال رو با هم ببینیم، چی می‌گفتی؟ 📺",
    "کدوم کارای من رو دوست داری بیشتر انجام بدم؟ 💫",
    "آخرین باری که دلت برام تنگ شد کی بود؟ 🥺",
    "اگه یک روز بتونی توی ذهن منو بخونی، چی رو می‌خوای بدونی؟ 🧠",
    "چه چیزی توی رابطه‌مون برات مهم‌تر از همه‌ست؟ 💎",
    "کدوم جای شهرمون رو دوست داری قدم بزنیم؟ 🌆",
    "بهترین تعریفی که می‌تونی از من بکنی چیه؟ 🌟",
    "اگه قرار بود یک اسم رمز عاشقانه داشته باشیم، چی بود؟ 🤫",
    "کدوم خاطره باهم هنوز لبخند به لبت میاره؟ 😁",
    "دوست داری پنج سال بعد کجا باشیم؟ 🔮",
    "کدوم قول می‌خوای همیشه بهم بدی؟ 🤝",
    "اگه یک شعر کوتاه درباره ما بگی چی می‌گی؟ 📝",
    "کدوم لحظه با من بیشتر از همه بهت آرامش داده؟ 🕊",
    "اگه من سه تا هدیه بخوام، دوست داری چی باشه؟ 🎁",
    "بهترین چیز درباره ما که هیچ‌کس دیگه نداره چیه؟ 👑",
]

COUPLE_DARE = [
    "یک ویس بفرست که توش بهم بگی «دلم برات تنگ شده» 🎙",
    "با یک جمله عاشقانه که هیچ‌وقت نگفتی، منو غافلگیر کن 💘",
    "یک عکس از چیزی که الان بهم فکر می‌کنه بفرست 🖼",
    "یک آهنگ عاشقانه رو برای من «دس‌کریپشن» کن 🎵",
    "همین الان یک پیام صوتی با آهنگِ «دوستت دارم» بفرست 🎶",
    "سه تا صفتی که دوست داری درباره‌ت بگم رو بگو 😌",
    "یک «کارت پستال متنی» از جایی که دوست داری بریم بنویس ✉️",
    "یک اسم بامزه برای ما دوتا بساز و همیشه صدایم کن 😄",
    "به مدت ۳ پیام، بهم با «عزیز دلم» جواب بده 💞",
    "یک خواسته‌ای که تا حالا نگفتی رو همین الان بگو 🫣",
    "یک بازی «این یا اون» با ۳ تا سؤال عاشقانه با من بکن 🎮",
    "بهترین خاطره‌مون رو توی یک جمله خلاصه کن 🥹",
    "یک ایموجی بفرست که الان حالت رو نشون بده و توضیح بده 🌈",
    "قول بده امروز یک کار کوچیک برای خودت انجام بدی 💆",
    "یک لطیفه بامزه تعریف کن و خودت اول بخند 😂",
    "بگو دوست داری تولدمون رو چطور جشن بگیریم 🎂",
    "یک سلفی با لبخندِ واقعی (نه ژست) بفرست 😊",
    "به مدت یک دقیقه فقط با کلمه‌های قشنگ صحبت کن ✨",
    "یک داستان کوتاه از «اولین دیدارمون» تعریف کن 📖",
    "بگو کدوم ترند رو دوست داری با هم انجام بدیم؟ 🔥",
]

PROFANITY_WORDS = {
    "کیر", "کیرم", "کیری", "کص", "کسکش", "کصکش", "کصخل", "کسخل", "سیکتیر",
    "کصشعر", "کسشر", "جنده", "مادرجنده", "حرومزاده", "حرامزاده", "کونی", "کونکش",
    "لاشی", "گوه", "گوهخور", "بی ناموس", "بیناموس", "دیوث", "قرمساق", "پفیوز",
    "عوضی", "آشغال", "احمق", "نفهم", "بیشعور", "بی شعور",
}
SEVERE_PROFANITY = {"کیر", "کص", "کسکش", "کصکش", "سیکتیر", "کصشعر", "کسشر", "مادرجنده", "کونی", "کونکش", "دیوث", "قرمساق"}

CAPTION_TEMPLATES = [
    "{topic}؛ همون لحظه‌ای که می‌فهمی قراره داستان تازه‌ای شروع بشه ✨\n\n#حال_خوب #Ajorpareh #وایرال",
    "قانون امروز: کمتر فکر کن، بیشتر زندگی کن؛ مخصوصاً وقتی پای {topic} وسطه 😎🔥\n\n#انرژی_مثبت #ترند #Ajorpareh",
    "بعضی لحظه‌ها کپشن نمی‌خوان... ولی {topic} فرق داره! 👀⚡\n\n#میم #وایرال #تلگرام",
    "POV: وقتی {topic} دقیقاً همون چیزی می‌شه که منتظرش بودی 😂\n\n#پست_جدید #خنده #Ajorpareh",
    "این پست رو برای کسی بفرست که با دیدن {topic} یادش می‌افتی 💜\n\n#رفیق #حال_خوب #وایرال",
]

DEMO_REVIEWS = [
    {"name": "سارا", "rating": 5, "text": "چالش‌هاش خیلی خفنه، مخصوصاً بازی حافظه!", "demo": True},
    {"name": "امیرعلی", "rating": 5, "text": "هوش مصنوعیش سریع جواب می‌ده و منوی ربات خیلی کامل شده.", "demo": True},
    {"name": "نگار", "rating": 5, "text": "طراحی نئونی Mini App واقعاً حس یه اپ حرفه‌ای می‌ده.", "demo": True},
    {"name": "آرین", "rating": 4, "text": "گردونه و جدول رتبه‌بندی باعث شد هر روز سر بزنم.", "demo": True},
    {"name": "مهسا", "rating": 5, "text": "تبدیل ویس به متن برای من خیلی کاربردیه.", "demo": True},
    {"name": "محمد", "rating": 5, "text": "از اینکه چند مدل AI پشت سر هم داره خیلی خوشم اومد.", "demo": True},
    {"name": "یاسمن", "rating": 4, "text": "خبر، بازی و هوش مصنوعی همه توی یک جاست؛ عالیه.", "demo": True},
    {"name": "پارسا", "rating": 5, "text": "چالش تایپ معکوس واقعاً اعتیادآوره!", "demo": True},
    {"name": "رها", "rating": 5, "text": "یادآورها دقیق و ساده‌ان و از داخل تلگرام پیام میاد.", "demo": True},
    {"name": "علی", "rating": 4, "text": "سرعت ربات خوبه و ابزارهای گروه هم خیلی به درد می‌خوره.", "demo": True},
    {"name": "آوا", "rating": 5, "text": "قسمت ساخت تصویر باحال‌ترین بخش Mini App بود.", "demo": True},
    {"name": "سام", "rating": 5, "text": "بازی بزن‌دررو و رقابت هفتگی رو خیلی دوست داشتم.", "demo": True},
    {"name": "حدیث", "rating": 4, "text": "رابط فارسی و ساده‌اش باعث می‌شه راحت همه‌چیز رو پیدا کنم.", "demo": True},
    {"name": "کیان", "rating": 5, "text": "کپشن‌ساز و برنامه‌نویسی AI واقعاً کاربردی‌اند.", "demo": True},
    {"name": "مریم", "rating": 5, "text": "چالش نخندیدن رو با دوستام انجام دادیم، خیلی بامزه بود.", "demo": True},
    {"name": "دانیال", "rating": 4, "text": "اینکه امتیاز و سکه واقعاً ثبت می‌شن حس خوبی می‌ده.", "demo": True},
    {"name": "الناز", "rating": 5, "text": "پروفایل و مدال‌ها خیلی قشنگ طراحی شدن.", "demo": True},
    {"name": "رضا", "rating": 5, "text": "پشتیبانی و گزارش مشکل مستقیم داخل Mini App عالیه.", "demo": True},
    {"name": "هلیا", "rating": 4, "text": "خبرهای کوتاه و جوک‌دونی ترکیب جالبی شده.", "demo": True},
    {"name": "بردیا", "rating": 5, "text": "هم برای سرگرمی خوبه هم ابزارهای روزمره داره.", "demo": True},
]

EMOJI_API_GUIDE = (
    "🧩 <b>راهنمای شکلک‌های سفارشی تلگرام برای برنامه‌نویسان</b>\n\n"
    "اگه برنامه‌نویس هستی و می‌خوای شکلک‌های سفارشی (Custom Emoji) رو در ربات یا نرم‌افزارت مدیریت کنی، "
    "تلگرام این APIها رو ارائه می‌ده:\n\n"
    "• <code>messages.getCustomEmojiDocuments</code>\n"
    "  دریافت اطلاعات و فایل شکلک‌های سفارشی.\n\n"
    "• <code>messages.searchCustomEmoji</code>\n"
    "  جستجوی شکلک‌های سفارشی در تلگرام.\n\n"
    "• <code>messageEntityCustomEmoji</code>\n"
    "  ارسال پیام حاوی شکلک‌های سفارشی (با شناسهٔ شکلک).\n\n"
    "💡 <b>کاربرد کدنویسی در عمل:</b> با این APIها می‌تونی رباتی بسازی که مثلاً بر اساس توضیحات کاربر، "
    "با هوش مصنوعی شکلک تولید کنه. همچنین برای ارسال شکلک در دکمه‌های ربات، باید از کدهای یونیکد "
    "یا خود شکلک به‌صورت مستقیم در کد استفاده کنی.\n\n"
    "📌 برای شروع، اپلیکیشن خودت رو در <code>my.telegram.org</code> بساز و از مستندات رسمی Bot API استفاده کن."
)


# ======== سشن‌ها ======
_user_cache: dict[int, tuple[float, dict]] = {}  # {user_id: (timestamp, doc)} — کش ۶۰ ثانیه‌ای
_USER_CACHE_TTL = 60.0

# مجموعه برچسب‌های دکمه‌های ReplyKeyboard — پیام کاربر بعد از پردازش پاک می‌شه
REPLY_BUTTON_LABELS: set[str] = {
    # منوی اصلی
    "🎮 بازی‌ها", "🎁 جوایز و کیف پول", "📰 اخبار و ترندها", "🧰 ابزارهای ربات",
    "📱 QR ساز", "🎨 گیف و استیکرساز", "🤖 هوش مصنوعی", "🛍 سرویس اختصاصی",
    "💬 پشتیبانی", "⚙️ پنل مدیریت",
    # منوی بازی‌ها
    "🏃 بزن در رو", "🧠 کوئیز فوری", "🎲 تاس", "🎯 دارت",
    "🪨 سنگ‌کاغذ‌قیچی", "🪙 شیر یا خط", "🔢 حدس عدد", "🎭 جرأت یا حقیقت",
    "🧠 جورچین حافظه", "🃏 بیست و یک", "🏠 منوی اصلی",
    # بازی‌ها
    "🪨 سنگ", "📄 کاغذ", "✂️ قیچی", "🪙 شیر", "🪙 خط",
    "💬 حقیقت", "🔥 جرأت", "❤️ کاپلی", "🎲 شانسی",
    "↩️ بازی‌ها",
    # جوایز
    "🔥 جایزه روزانه", "💳 کیف پول", "🎁 دعوت دوستان", "🎟 کد هدیه",
    "🎯 مأموریت‌های جایزه", "🏆 رتبه‌بندی",
    # خبر و سرگرمی
    "📰 اخبار زنده", "😂 جوک تازه", "🧠 دانستنی عجیب", "🧩 معمای فوری",
    "🎭 این یا اون", "⚡ چالش ۳۰ ثانیه", "🤡 میم متنی", "🔮 فال فان امروز",
    "✨ جمله انگیزشی", "🔥 داغ‌های کانال", "📣 کانال Ajorpareh",
    "🇮🇷 اخبار ایران", "🌍 اخبار جهان", "💻 اخبار تکنولوژی", "🔄 تازه‌ترین خبرها",
    # ابزارها
    "🌐 پروکسی", "🔐 کانفیگ", "⏰ یادآور هوشمند", "➕ یادآور جدید", "🕛 00:00", "🌅 صبح بخیر",
    "📋 یادآورهای من", "🧠 پرامپت‌ها", "✨ کپشن‌ساز", "🧮 ماشین‌حساب", "🎭 حال‌سنج",
    "🎬 دانلود یوتیوب", "🧩 API شکلک سفارشی", "🤖 راهنمای برنامه‌نویسان",
    "↩️ ابزارهای ربات", "↩️ پشتیبانی",
    # دانلود
    "📸 دانلود اینستاگرام", "🖼 پروفایل اینستاگرام", "🎵 دانلود تیک‌تاک", "▶️ دانلود یوتیوب",
    "🌐 دانلود سایر شبکه‌ها", "🔗 آپلود فایل از URL", "🛡 بررسی امنیت لینک",
    "💬 کپی متن کامنت اینستاگرام", "🎵 موسیقی", "📋 دانلودهای اخیر", "📊 سهمیه دانلود", "ℹ️ راهنمای دانلود",
    "↩️ مرکز دانلود و آپلود",
    # موسیقی
    "🔎 جستجوی آهنگ", "🔥 آهنگ‌های ترند", "🇮🇷 ترند ایرانی", "🎚 ریمیکس ایرانی",
    "📅 موزیک امروز", "📚 پلی‌لیست ایرانی", "📤 آپلود گروهی موسیقی", "🎤 تشخیص آهنگ با تکه صدا",
    "📖 راهنمای موسیقی",
    # سرویس
    "🚀 خرید سرویس جدید", "♻️ تمدید سرویس", "📱 سرویس‌های من",
    "💰 اعتبار من", "🎁 تخفیف و آفر ویژه", "🏆 کاربران برتر",
    "👥 معرفی به دوستان", "💡 آموزش استفاده", "👨‍💻 تماس با پشتیبانی",
    "📊 وضعیت سفارش",
    # پشتیبانی
    "✍️ ارسال پیام پشتیبانی", "💬 نظرات کاربران", "👀 دیدن نظرات",
    "✍️ نوشتن نظر", "❓ راهنمای ربات", "🔄 بروزرسانی و رفع مشکل", "👤 پروفایل من",
    # پنل مدیریت
    "📊 آمار و گزارش", "📡 رصد فعالیت‌ها", "🔥 کاربران فعال",
    "📡 رصد زنده فعالیت‌ها", "🕵️ فعالیت یک کاربر", "📊 آمار رسانه",
    "🧹 پاکسازی صف رسانه", "📈 آمار هوش مصنوعی",
    "👥 کاربران و تیکت‌ها", "👥 مدیریت کاربران", "🎫 تیکت‌های پشتیبانی",
    "💰 افزایش موجودی کاربر", "🔎 جستجوی کاربر", "📥 خروجی CSV",
    "📢 محتوا و انتشار", "💰 مالی و اقتصاد", "🌐 کانفیگ و فایل‌ها",
    "🛡 گروه و کانال", "🎯 کمپین و جوایز", "👮 مدیران و امنیت",
    "🩺 سلامت و پشتیبان",
    "⚡ انتشار فوری", "♻️ بازنشر گروهی", "⏰ پست زمان‌دار",
    "✍️ متن دعوت بازنشر", "📢 پیام همگانی", "📝 قالب‌های محتوا",
    "💸 برداشت‌های در انتظار", "💰 تنظیمات اقتصاد", "🛒 فروش و سفارش سرویس",
    "📊 گزارش مالی و ضدتقلب", "🌐 مدیریت پروکسی و کانفیگ",
    "📁 مدیریت فایل‌ها", "📤 گروه فایل جدید", "✅ انتشار گروه فایل",
    "🛡 گروه‌ها و کانال‌ها", "📣 کانال‌های عضویت اجباری",
    "🎟 کدهای جایزه", "🎯 مأموریت‌ها", "🎡 قرعه‌کشی‌ها",
    "📈 پیش‌بینی ترند", "👮 نقش مدیران", "📜 گزارش فعالیت مدیران",
    "🩺 سلامت ربات", "🤖 وضعیت هوش مصنوعی", "💾 دریافت پشتیبان",
    "🟢/🔴 حالت تعمیرات", "✅/☑️ عضویت اجباری",
    "🍷 فال روزانه صبحگاهی", "📈 پست خودکار نرخ ارز",
    "🕌 پست اذان روزانه در کانال", "📊 آمار مالی هفتگی در کانال",
    "📤 ارسال گزارش مالی به کانال", "🔄 خودترمیم و بروزرسانی",
    # ساخت استیکر و گیف
    "🪄 ساخت استیکر", "🎞 ساخت گیف", "📦 پک استیکرهای من",
    "ℹ️ راهنمای گیف و استیکر",
    # یادآور
    "⏰ یادآور من",
}
guess_games: dict[int, dict] = {}
hit_run_sessions: dict[int, dict] = {}
memory_games: dict[str, dict] = {}
twenty_one_games: dict[str, dict] = {}
calculator_sessions: dict[int, str] = {}
broadcast_sessions: set[int] = set()
awaiting_prayer_city: set[int] = set()
broadcast_targets: dict[int, str] = {}
withdrawal_sessions: set[int] = set()
receipt_sessions: set[tuple[int, int]] = set()  # سازگاری با درخواست‌های قدیمی
config_upload_sessions: dict[int, str] = {}  # {admin_id: "proxy" | "v2ray" | "npv"}
support_sessions: set[int] = set()
review_sessions: set[int] = set()
caption_sessions: set[int] = set()
admin_search_sessions: set[int] = set()
channel_add_sessions: set[int] = set()
engagement_post_sessions: set[int] = set()
economy_setting_sessions: dict[int, str] = {}
repost_cta_sessions: set[int] = set()
admin_role_sessions: dict[int, str] = {}
promo_create_sessions: set[int] = set()
promo_sticker_sessions: dict[int, dict] = {}
gift_redeem_sessions: set[int] = set()
mission_create_sessions: set[int] = set()
raffle_create_sessions: set[int] = set()
prediction_create_sessions: set[int] = set()
template_create_sessions: set[int] = set()
qr_sessions: set[int] = set()
daily_fal_channel_sessions: set[int] = set()
greeting_target_sessions: set[int] = set()
# {admin_id: {"kind": "midnight" | "morning", "count": int}}
greeting_add_sessions: dict[int, dict[str, object]] = {}
greeting_edit_sessions: dict[int, tuple[str, str]] = {}
sticker_sessions: set[int] = set()
gif_sessions: set[int] = set()
video_round_sessions: set[int] = set()  # تبدیل ویدئو به ویدئو مسیج دایره‌ای
media_request_sessions: dict[int, str] = {}
instagram_comment_sessions: set[int] = set()
prompt_image_sessions: dict[int, str] = {}
music_search_sessions: set[int] = set()
music_recognize_sessions: set[int] = set()
music_daily_target_sessions: set[int] = set()
music_daily_time_sessions: set[int] = set()
music_playlist_upload_sessions: dict[int, int] = {}
music_search_cache: dict[int, list[dict]] = {}
quick_quiz_recent: dict[int, list[int]] = {}
hokm_rooms: dict[str, HokmGame] = {}  # اتاق‌های بازی حکم آنلاین (حافظه + TTL)
duel_rooms: dict[str, dict] = {}  # اتاق‌های دوئل ۱v۱


def _hokm_room_expiry() -> None:
    """اتاق‌های قدیمی‌تر از ۲ ساعت را پاک می‌کند."""
    now = time.time()
    expired = [rid for rid, game in hokm_rooms.items() if now - game.updated_at > 7200]
    for rid in expired:
        hokm_rooms.pop(rid, None)
reminder_sessions: set[int] = set()
ai_sessions: dict[int, dict] = {}
casual_chat_history: dict[int, list[dict[str, str]]] = {}
ai_request_locks: dict[int, asyncio.Lock] = {}
ticket_reply_sessions: dict[int, str] = {}
reschedule_sessions: dict[int, str] = {}
manual_balance_sessions: dict[int, tuple[int, str]] = {}
service_shop_setting_sessions: dict[int, str] = {}
service_delivery_sessions: dict[int, str] = {}
service_receipt_sessions: dict[int, str] = {}
group_message_times: dict[tuple[int, int], list[float]] = {}
repost_sessions: set[int] = set()
repost_batches: dict[int, dict] = {}
instant_repost_sessions: dict[int, list[int]] = {}  # {user_id: [message_ids_to_delete]}
# مدیریت تک‌پست در گروه پیش‌نویس: {admin_id: index}
repost_edit_sessions: dict[int, int] = {}
# تغییر گروه زمان‌بندی‌شده فقط تا قبل از شروع انتشار مجاز است.
scheduled_add_sessions: dict[int, str] = {}
scheduled_edit_sessions: dict[int, tuple[str, int]] = {}
album_buffers: dict[tuple[int, str, str], dict] = {}
schedule_time_sessions: set[int] = set()

# ======== محدودیت اسپم (Flood Control) ========
FLOOD_COOLDOWN_SECONDS = 0.8
_last_action_at = {}

def is_flooding(user_id: int) -> bool:
    now = time.monotonic()
    last = _last_action_at.get(user_id, 0)
    _last_action_at[user_id] = now
    return (now - last) < FLOOD_COOLDOWN_SECONDS

def is_owner(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_admin(user_id: int) -> bool:
    return is_owner(user_id) or user_id in delegated_admins_cache


def admin_roles(user_id: int) -> set[str]:
    return {"owner"} if is_owner(user_id) else set(delegated_admins_cache.get(user_id, set()))


def admin_role(user_id: int) -> str | None:
    roles = admin_roles(user_id)
    return ",".join(sorted(roles)) if roles else None


def has_permission(user_id: int, permission: str) -> bool:
    roles = admin_roles(user_id)
    if not roles:
        return False
    permissions = set().union(*(ROLE_PERMISSIONS.get(role, set()) for role in roles))
    return "*" in permissions or permission in permissions


async def audit_admin_action(user_id: int, action: str, details: str = "", target: str | None = None):
    if not is_admin(user_id):
        return
    try:
        await admin_audit_col.insert_one({
            "admin_id": user_id, "role": admin_role(user_id), "action": action[:100],
            "target": target, "details": details[:1000], "created_at": datetime.now(timezone.utc),
        })
    except Exception as exc:
        log.warning("ثبت گزارش مدیریتی ناموفق بود: %s", exc)


async def refresh_required_channels():
    global required_channels_cache
    required_channels_cache = await required_channels_col.find({"active": {"$ne": False}}).sort("added_at", 1).to_list(length=50)


async def get_missing_channels(user_id: int) -> list[dict]:
    if is_admin(user_id) or not runtime_settings.get("force_join", True):
        return []
    missing: list[dict] = []
    for channel in required_channels_cache:
        try:
            member = await bot.get_chat_member(channel["_id"], user_id)
            if member.status == "restricted":
                joined = bool(getattr(member, "is_member", False))
            else:
                joined = member.status in ("member", "administrator", "creator")
            if not joined:
                missing.append(channel)
        except TelegramBadRequest as exc:
            log.warning("بررسی عضویت کانال %s ممکن نیست: %s", channel.get("_id"), exc)
            missing.append(channel)
        except Exception as exc:
            log.warning("خطا در بررسی عضویت %s در %s: %s", user_id, channel.get("_id"), exc)
            missing.append(channel)
    return missing


async def has_completed_engagement(user_id: int) -> bool:
    gate = engagement_gate_cache
    if not gate.get("enabled") or not gate.get("version"):
        return True
    user = await users_col.find_one({"_id": user_id}, {"engagement_gate_version": 1})
    return bool(user and user.get("engagement_gate_version") == gate["version"])


async def is_member(user_id: int) -> bool:
    """سازگاری با هندلرهای قبلی: عضویت همه کانال‌ها + مرحله تعامل."""
    if is_admin(user_id) or not runtime_settings.get("force_join", True):
        return True
    if await get_missing_channels(user_id):
        return False
    return await has_completed_engagement(user_id)


async def is_banned(user_id: int) -> bool:
    user = await users_col.find_one({"_id": user_id}, {"is_banned": 1, "bot_banned_until": 1})
    if not user:
        return False
    if user.get("is_banned"):
        return True
    banned_until = user.get("bot_banned_until")
    if banned_until:
        if banned_until.tzinfo is None:
            banned_until = banned_until.replace(tzinfo=timezone.utc)
        if banned_until > datetime.now(timezone.utc):
            return True
        await users_col.update_one({"_id": user_id}, {"$unset": {"bot_banned_until": ""}, "$set": {"private_warning_count": 0}})
    return False


async def log_activity(user_id: int, action: str, details: str = ""):
    now = datetime.now(timezone.utc)
    try:
        await activities_col.insert_one(
            {
                "user_id": user_id,
                "action": action[:80],
                "details": (details or "")[:500],
                "timestamp": now,
            }
        )
        await users_col.update_one({"_id": user_id}, {"$set": {"last_activity": now}})
    except Exception as exc:
        log.warning("خطا در ثبت فعالیت: %s", exc)


def required_admin_permission(event) -> str | None:
    if isinstance(event, types.CallbackQuery):
        data = event.data or ""
        mapping = {
            "economy": "finance", "withdraw": "finance", "admin_withdraw": "finance", "admin_finance": "finance",
            "admin_service": "finance", "svcapprove": "finance", "svcreject": "finance", "svccancel": "finance",
            "ticket": "support", "admin_ticket": "support", "review": "support",
            "repost": "content", "instant_repost": "content", "scheduled": "schedule", "sched": "schedule",
            "broadcast": "broadcast", "template": "templates", "admin_config": "configs", "cfg": "configs",
            "managed_chats": "moderation", "mchat": "moderation", "gfilter": "moderation", "gspam": "moderation",
            "glinks": "moderation", "gforwards": "moderation", "gwelcome": "moderation", "gpunish": "moderation", "gstats": "moderation", "ghelp": "moderation",
            "stats": "stats", "admin_analytics": "stats", "list_users": "users.view", "admin_user": "users.view",
            "admin_export": "backup", "admin_backup": "backup", "admin_health": "stats", "admin_audit": "stats",
            "admin_roles": "owner", "role": "owner", "aiquota": "owner", "promo": "content", "mission": "content",
            "raffle": "content", "prediction": "content", "pred": "content",
        }
        for prefix, permission in mapping.items():
            if data.startswith(prefix): return permission
    if isinstance(event, types.Message) and (event.text or "").startswith("/"):
        command = (event.text or "").split()[0].split("@", 1)[0].lstrip("/")
        mapping = {
            "admin": None, "channels": "owner", "repost": "content", "quickpost": "content", "configs": "configs",
            "search": "users.view", "activity": "users.view", "ban": "moderation", "unban": "moderation",
        }
        return mapping.get(command)
    return None


async def economy_reward_multiplier() -> float:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = await coin_transactions_col.aggregate([
        {"$match": {"status": "completed", "created_at": {"$gte": since}}},
        {"$group": {"_id": "$direction", "amount": {"$sum": "$amount"}}},
    ]).to_list(length=5)
    totals = {row["_id"]: int(row["amount"]) for row in rows}
    minted = totals.get("mint", 0); burned = totals.get("burn", 0)
    target = int(economy_settings["daily_emission_target"])
    return max(float(economy_settings["min_reward_multiplier"]), min(1.0, (target + burned) / max(target, minted, 1)))


async def coin_balance(user_id: int) -> int:
    user = await users_col.find_one({"_id": user_id}, {"coins": 1}) or {}
    return max(0, int(user.get("coins", 0)))


async def apply_coin_transaction(user_id: int, amount: int, reason: str, idempotency_key: str, metadata: dict | None = None, apply_multiplier: bool = False) -> dict:
    if amount == 0: return {"ok": True, "amount": 0, "balance": await coin_balance(user_id), "duplicate": False}
    original_amount = amount
    if amount > 0 and apply_multiplier:
        amount = max(1, math.floor(amount * await economy_reward_multiplier()))
        day = today_str()
        user = await users_col.find_one({"_id": user_id}, {"coin_reward_date": 1, "coin_reward_today": 1}) or {}
        daily = int(user.get("coin_reward_today", 0)) if user.get("coin_reward_date") == day else 0
        amount = min(amount, max(0, int(economy_settings["daily_coin_cap"]) - daily))
        if amount <= 0: return {"ok": True, "amount": 0, "balance": await coin_balance(user_id), "daily_limit": True}
    document = {
        "_id": idempotency_key, "user_id": user_id, "amount": amount, "base_amount": original_amount,
        "direction": "mint" if amount > 0 else "burn", "reason": reason,
        "metadata": metadata or {}, "status": "pending", "created_at": datetime.now(timezone.utc),
    }
    try: await coin_transactions_col.insert_one(document)
    except DuplicateKeyError:
        old = await coin_transactions_col.find_one({"_id": idempotency_key}) or {}
        return {"ok": old.get("status") == "completed", "amount": int(old.get("amount", 0)), "balance": await coin_balance(user_id), "duplicate": True}
    update = {"$inc": {"coins": amount}, "$set": {"last_coin_tx_at": datetime.now(timezone.utc)}}
    if amount > 0 and apply_multiplier:
        update["$set"]["coin_reward_date"] = today_str(); update["$inc"]["coin_reward_today"] = amount
    query = {"_id": user_id}
    if amount < 0: query["coins"] = {"$gte": -amount}
    result = await users_col.update_one(query, update, upsert=amount > 0)
    if not result.modified_count and not result.upserted_id:
        await coin_transactions_col.update_one({"_id": idempotency_key}, {"$set": {"status": "failed", "failure": "insufficient_balance"}})
        return {"ok": False, "amount": 0, "balance": await coin_balance(user_id), "insufficient": True}
    await coin_transactions_col.update_one({"_id": idempotency_key}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}})
    return {"ok": True, "amount": amount, "balance": await coin_balance(user_id), "duplicate": False}


async def record_score_event(user_id: int, points: int, source: str, event_key: str, metadata: dict | None = None):
    try:
        await score_events_col.insert_one({"_id": event_key, "user_id": user_id, "points": max(0, int(points)), "source": source, "metadata": metadata or {}, "created_at": datetime.now(timezone.utc)})
    except DuplicateKeyError:
        pass


async def mark_maintenance_waiter(user: types.User) -> None:
    now = datetime.now(timezone.utc)
    try:
        await users_col.update_one(
            {"_id": user.id},
            {
                "$set": {
                    "name": (user.full_name or "Telegram User")[:120],
                    "username": user.username,
                    "maintenance_notify_pending": True,
                    "maintenance_last_attempt_at": now,
                },
                "$setOnInsert": {
                    "joined_at": now,
                    "last_activity": now,
                    "is_banned": False,
                    "coins": 0,
                    "xp": 0,
                    "streak": 0,
                    "games_played": 0,
                    "games_won": 0,
                    "referral_count": 0,
                },
            },
            upsert=True,
        )
    except Exception as exc:
        log.warning("ثبت انتظار پایان تعمیرات ممکن نشد: %s", exc)


async def notify_maintenance_waiters() -> int:
    if runtime_settings.get("maintenance"):
        return 0
    sent = 0
    async with maintenance_notification_lock:
        while True:
            users = await users_col.find(
                {"maintenance_notify_pending": True}, {"_id": 1}
            ).limit(100).to_list(length=100)
            if not users:
                break
            for item in users:
                user_id = int(item["_id"])
                try:
                    await bot.send_message(
                        user_id,
                        "✅ <b>Ajorpareh دوباره آنلاین شد!</b>\n\n"
                        "بروزرسانی تموم شده و الان می‌تونی از ربات و Mini App استفاده کنی 🚀",
                        parse_mode="HTML",
                        reply_markup=chat_reply_menu(user_id),
                    )
                    await users_col.update_one(
                        {"_id": user_id},
                        {"$set": {"maintenance_notify_pending": False, "maintenance_notified_at": datetime.now(timezone.utc)}},
                    )
                    sent += 1
                except (TelegramForbiddenError, TelegramBadRequest):
                    await users_col.update_one(
                        {"_id": user_id}, {"$set": {"maintenance_notify_pending": False}}
                    )
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after + 1)
                except Exception as exc:
                    log.warning("اعلان پایان تعمیرات برای %s ارسال نشد: %s", user_id, exc)
                await asyncio.sleep(0.05)
            if len(users) < 100:
                break
    return sent


async def maintenance_recovery_worker():
    await asyncio.sleep(15)
    while True:
        try:
            if not runtime_settings.get("maintenance"):
                await notify_maintenance_waiters()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("worker اعلان پایان تعمیرات ناموفق بود: %s", exc)
        await asyncio.sleep(45)


class AccessMiddleware(BaseMiddleware):
    """کنترل بن، تعمیرات و سطح دسترسی مدیران."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)
        if is_owner(user.id):
            result = await handler(event, data)
            permission = required_admin_permission(event)
            action = event.data if isinstance(event, types.CallbackQuery) else (event.text or "").split()[0] if isinstance(event, types.Message) and event.text else ""
            if permission is not None or action in {"admin_panel", "/admin"}:
                await audit_admin_action(user.id, action)
            return result
        if user.id in delegated_admins_cache:
            permission = required_admin_permission(event)
            if permission == "owner" or (permission and not has_permission(user.id, permission)):
                text = "⛔ نقش مدیریتی شما به این بخش دسترسی ندارد."
                if isinstance(event, types.CallbackQuery): await event.answer(text, show_alert=True)
                else: await event.answer(text)
                return None
            result = await handler(event, data)
            action = event.data if isinstance(event, types.CallbackQuery) else (event.text or "").split()[0]
            await audit_admin_action(user.id, action)
            return result
        if runtime_settings.get("maintenance"):
            await mark_maintenance_waiter(user)
            text = (
                "🛠 ربات برای چند دقیقه در حال بروزرسانی است. خیلی زود برمی‌گردیم!\n\n"
                "وقتی دوباره آنلاین شد، خودم بهت پیام می‌دم ✅"
            )
            if isinstance(event, types.CallbackQuery):
                await event.answer(text, show_alert=True)
            else:
                await event.answer(text)
            return None
        if await is_banned(user.id):
            text = "🚫 دسترسی شما به ربات محدود شده است. برای پیگیری با پشتیبانی تماس بگیرید."
            if isinstance(event, types.CallbackQuery):
                await event.answer(text, show_alert=True)
            else:
                await event.answer(text)
            return None

        # تیکت پشتیبانی حتی قبل از تکمیل عضویت هم قابل ارسال است.
        if isinstance(event, types.Message) and user.id in support_sessions:
            return await handler(event, data)

        # تمام امکانات، حتی دکمه‌های پیام‌های قدیمی، پشت گیت عضویت قرار می‌گیرند.
        if runtime_settings.get("force_join", True):
            if isinstance(event, types.CallbackQuery):
                if event.data not in {"check_join", "engagement_done"} and not await is_member(user.id):
                    await event.message.answer(
                        "🔒 برای استفاده از این بخش، اول مراحل عضویت و دسترسی رو کامل کن:",
                        reply_markup=channel_check_menu(),
                    )
                    await event.answer("ابتدا عضویت اجباری را کامل کن.", show_alert=True)
                    return None
            elif isinstance(event, types.Message):
                command = (event.text or "").split(maxsplit=1)[0].split("@", 1)[0]
                plain_text = normalize_chat_text(event.text or "")
                panel_request = plain_text in {"پنل", "پنل مدیریت", "مدیریت"}
                profanity_warning = bool(detect_profanity(event.text or ""))
                if not panel_request and not profanity_warning and command not in {"/start", "/help", "/cancel"} and not await is_member(user.id):
                    await event.answer(
                        "🔒 اول مراحل عضویت و دسترسی رو کامل کن:",
                        reply_markup=channel_check_menu(),
                    )
                    return None
        return await handler(event, data)


dp.message.outer_middleware(AccessMiddleware())
dp.callback_query.outer_middleware(AccessMiddleware())


async def is_chat_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except (TelegramForbiddenError, TelegramBadRequest):
        return False


def full_chat_permissions() -> types.ChatPermissions:
    return types.ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=False,
        can_invite_users=True,
        can_pin_messages=False,
        can_manage_topics=False,
    )


async def get_group_settings(chat_id: int) -> dict:
    settings = await group_settings_col.find_one({"_id": chat_id}) or {}
    return {
        "anti_profanity": settings.get("anti_profanity", True),
        "anti_spam": settings.get("anti_spam", True),
        "block_links": settings.get("block_links", False),
        "block_forwards": settings.get("block_forwards", False),
        "welcome_enabled": settings.get("welcome_enabled", True),
        "welcome_text": settings.get("welcome_text"),
        "blocked_words": settings.get("blocked_words", []),
        "trusted_users": settings.get("trusted_users", []),
        "allowed_domains": settings.get("allowed_domains", []),
        "punishment": settings.get("punishment", "mute"),
        "mute_minutes": int(settings.get("mute_minutes", 60)),
        "warning_limit": int(settings.get("warning_limit", 3)),
    }


async def resolve_target(message: types.Message) -> tuple[int, str] | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.full_name
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        return int(parts[1]), parts[1]
    return None


async def ensure_moderatable(chat_id: int, target_id: int) -> tuple[bool, str]:
    if target_id == (await bot.get_me()).id:
        return False, "نمی‌تونم خودم رو مجازات کنم!"
    try:
        member = await bot.get_chat_member(chat_id, target_id)
        if member.status in ("administrator", "creator"):
            return False, "ادمین‌ها و سازنده گروه قابل مجازات نیستند."
    except TelegramBadRequest:
        pass
    return True, ""


async def apply_group_punishment(chat_id: int, user_id: int, punishment: str, minutes: int = 60):
    if punishment == "ban":
        await bot.ban_chat_member(chat_id, user_id)
        return "بن دائمی"
    if punishment == "kick":
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        return "حذف از گروه"
    until = datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes))
    await bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False), until_date=until)
    return f"سکوت {minutes} دقیقه‌ای"


async def issue_group_warning(message: types.Message, reason: str, automatic: bool = False, target_user=None):
    user = target_user or message.from_user
    if not user:
        return
    settings = await get_group_settings(message.chat.id)
    key = f"{message.chat.id}:{user.id}"
    warning = await warnings_col.find_one_and_update(
        {"_id": key},
        {
            "$inc": {"count": 1, "total_warnings": 1},
            "$set": {"chat_id": message.chat.id, "user_id": user.id, "name": user.full_name, "updated_at": datetime.now(timezone.utc)},
            "$push": {"history": {"$each": [{"at": datetime.now(timezone.utc), "reason": reason[:150], "automatic": automatic}], "$slice": -20}},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    count = int(warning.get("count", 1))
    limit = settings["warning_limit"]
    mention = f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'
    if count < limit:
        await bot.send_message(message.chat.id, f"⚠️ {mention}\nهشدار <b>{count} از {limit}</b>\nدلیل: {html.escape(reason)}", parse_mode="HTML")
        return
    allowed, error = await ensure_moderatable(message.chat.id, user.id)
    if not allowed:
        await bot.send_message(message.chat.id, f"⚠️ {mention} به سقف هشدار رسید، اما {error}", parse_mode="HTML")
        return
    try:
        result = await apply_group_punishment(message.chat.id, user.id, settings["punishment"], settings["mute_minutes"])
        await warnings_col.update_one({"_id": key}, {"$set": {"count": 0, "last_punishment": result}, "$inc": {"punishments": 1}})
        await bot.send_message(message.chat.id, f"🚨 {mention} به {limit} هشدار رسید.\nمجازات: <b>{result}</b>", parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        log.warning("مجازات گروهی اجرا نشد: %s", exc)
        await bot.send_message(message.chat.id, "❌ مجازات اجرا نشد؛ دسترسی Restrict/Ban ربات را بررسی کنید.")


async def issue_private_warning(message: types.Message, matches: set[str]):
    user_id = message.from_user.id
    user = await users_col.find_one_and_update(
        {"_id": user_id},
        {
            "$inc": {"private_warning_count": 1, "private_total_warnings": 1},
            "$set": {"private_warning_updated_at": datetime.now(timezone.utc)},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    count = int(user.get("private_warning_count", 1))
    if count < 3:
        await message.answer(
            f"⚠️ لطفاً مؤدب باش. استفاده از الفاظ نامناسب مجاز نیست.\n"
            f"هشدار <b>{count} از 3</b>؛ هشدار سوم باعث بن ۲۴ ساعته از ربات می‌شود.",
            parse_mode="HTML",
        )
        return
    banned_until = datetime.now(timezone.utc) + timedelta(hours=24)
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"bot_banned_until": banned_until, "private_warning_count": 0, "ban_reason": "تکرار الفاظ نامناسب"}},
    )
    await message.answer("🚫 به‌دلیل دریافت ۳ هشدار، دسترسی شما به ربات برای ۲۴ ساعت مسدود شد.")
    alert = (
        f"🚨 <b>بن خودکار در ربات</b>\n"
        f"کاربر: {html.escape(message.from_user.full_name)}\n"
        f"آیدی: <code>{user_id}</code>\n"
        f"یوزرنیم: @{html.escape(message.from_user.username or 'ندارد')}\n"
        f"واژه‌های شناسایی‌شده: <code>{html.escape(', '.join(sorted(matches)))}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, alert, parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


AI_BASE_SYSTEM_PROMPT = (
    "تو دستیار هوش مصنوعی Ajorpareh هستی؛ فارسی، صمیمی، پرانرژی، دقیق و محترم جواب بده. "
    "لحن طبیعی و محاوره‌ای ایرانی داشته باش، خشک و اداری نباش و از ایموجی به‌اندازه استفاده کن. "
    "هرگز منبع، عدد یا واقعیتی را از خودت نساز؛ وقتی مطمئن نیستی شفاف بگو. "
    "در موضوعات پزشکی، حقوقی و مالی تشخیص یا تضمین قطعی نده و در موارد پرخطر مراجعه به متخصص را پیشنهاد کن. "
    "حریم خصوصی کاربر را رعایت کن و از او رمز، کد ورود، کلید API یا اطلاعات بانکی نخواه. "
    "پاسخ را کاربردی و متناسب با درخواست بنویس و از مقدمه‌های طولانی دوری کن."
)

CASUAL_AI_SYSTEM_PROMPT = (
    AI_BASE_SYSTEM_PROMPT +
    " در گپ روزمره مثل یک رفیق فارسی‌زبان گرم، شوخ و باحال حرف بزن. "
    "جواب معمولاً یک تا چهار جمله باشد، حرف کاربر را ادامه بده و بی‌دلیل مدام منو یا قابلیت‌های ربات را تبلیغ نکن. "
    "اگر کاربر ناراحت است اول همدلی کن؛ شوخی را فقط وقتی فضا مناسب است انجام بده."
)

AI_MODE_CONFIG = {
    "chat": {
        "title": "💬 چت هوشمند",
        "instruction": "هر سؤالی داری بفرست؛ گفت‌وگو چندمرحله‌ایه و پیام‌های قبلی همین نشست رو یادم می‌مونه.",
        "system": AI_BASE_SYSTEM_PROMPT + " معمولاً زیر ۳۵۰ کلمه جواب بده؛ اگر سؤال مبهم بود فقط یک سؤال روشن‌کننده بپرس.",
    },
    "image": {
        "title": "🎨 ساخت تصویر",
        "instruction": "تصویری که می‌خوای رو با جزئیات توصیف کن؛ سبک، رنگ، نور و نسبت تصویر رو هم می‌تونی بگی.",
    },
    "vision": {
        "title": "👁 تحلیل تصویر",
        "instruction": "یک عکس بفرست؛ اگر سؤال خاصی داری داخل کپشن عکس بنویس.",
    },
    "voice": {
        "title": "🎙 ویس به متن",
        "instruction": "یک پیام صوتی یا فایل صوتی تا ۱۹ مگابایت بفرست تا متن دقیق و قابل کپی تحویل بگیری.",
    },
    "edit_image": {
        "title": "🪄 ویرایش تصویر",
        "instruction": "عکس را همراه توضیح تغییرات داخل کپشن بفرست؛ مثلاً «پس‌زمینه را نئونی کن».",
    },
    "rewrite": {
        "title": "✍️ بازنویسی متن",
        "instruction": "متنت رو بفرست؛ اگر لحن خاصی می‌خوای بنویس: رسمی، صمیمی، تبلیغاتی یا کوتاه.",
        "system": AI_BASE_SYSTEM_PROMPT + " متن کاربر را روان و طبیعی بازنویسی کن؛ معنی را حفظ کن و در صورت مفید بودن دو نسخه متفاوت بده.",
    },
    "translate": {
        "title": "🌐 ترجمه حرفه‌ای",
        "instruction": "متن و زبان مقصد رو بفرست؛ مثال: «این متن رو انگلیسی رسمی کن: ...»",
        "system": AI_BASE_SYSTEM_PROMPT + " مترجم حرفه‌ای باش؛ لحن، اصطلاحات و قالب متن را حفظ کن و فقط در صورت ابهام توضیح کوتاه بده.",
    },
    "summary": {
        "title": "🧠 خلاصه‌سازی",
        "instruction": "متن بلند رو بفرست تا خلاصه، نکات کلیدی و نتیجه‌اش رو مرتب کنم.",
        "system": AI_BASE_SYSTEM_PROMPT + " متن را بدون افزودن ادعای تازه خلاصه کن؛ ابتدا خلاصه کوتاه، بعد نکات کلیدی بولت‌دار را بده.",
    },
    "study": {
        "title": "📚 کمک درسی",
        "instruction": "سؤال درسی یا مسئله‌ات رو بفرست؛ پایه یا سطح آموزشی رو هم بگی بهتر جواب می‌دم.",
        "system": AI_BASE_SYSTEM_PROMPT + " مثل معلم صبور آموزش بده؛ راه‌حل را مرحله‌به‌مرحله و قابل‌فهم توضیح بده و جواب نهایی را مشخص کن.",
    },
    "code": {
        "title": "💻 برنامه‌نویسی",
        "instruction": "کد، خطا یا ایده برنامه‌نویسی رو بفرست و زبان/فریم‌ورک رو هم مشخص کن.",
        "system": AI_BASE_SYSTEM_PROMPT + " مثل مهندس نرم‌افزار ارشد پاسخ بده؛ کد امن، قابل اجرا و کوتاه ارائه کن و علت خطا و روش تست را توضیح بده.",
    },
    "content": {
        "title": "📣 تولید محتوا",
        "instruction": "موضوع، شبکه اجتماعی و لحن رو بفرست تا کپشن، متن تبلیغاتی یا ایده پست بسازم.",
        "system": AI_BASE_SYSTEM_PROMPT + " برای شبکه‌های اجتماعی محتوای اصیل و جذاب بساز؛ سه نسخه متفاوت، CTA مناسب و هشتگ‌های مرتبط ارائه کن و ادعای گمراه‌کننده نساز.",
    },
    "ideas": {
        "title": "💡 ایده‌پردازی",
        "instruction": "موضوع و هدفت رو بگو تا چند ایده عملی و متفاوت پیشنهاد بدم.",
        "system": AI_BASE_SYSTEM_PROMPT + " ایده‌های متنوع، عملی و اولویت‌بندی‌شده پیشنهاد بده؛ برای سه ایده برتر قدم اول اجرا را هم بنویس.",
    },
}

AI_BUTTON_TO_MODE = {
    "💬 چت هوشمند": "chat",
    "🎨 ساخت تصویر": "image",
    "👁 تحلیل تصویر": "vision",
    "🎙 ویس به متن": "voice",
    "🪄 ویرایش تصویر": "edit_image",
    "✍️ بازنویسی متن": "rewrite",
    "🌐 ترجمه حرفه‌ای": "translate",
    "🧠 خلاصه‌سازی": "summary",
    "📚 کمک درسی": "study",
    "💻 برنامه‌نویسی": "code",
    "📣 تولید محتوا": "content",
    "💡 ایده‌پردازی": "ideas",
}


def ai_request_lock(user_id: int) -> asyncio.Lock:
    lock = ai_request_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        ai_request_locks[user_id] = lock
    return lock


async def ask_ai_detailed(
    query: str,
    *,
    user_id: int | None = None,
    feature: str = "general",
    system_prompt: str = AI_BASE_SYSTEM_PROMPT,
    history: list[dict[str, str]] | None = None,
    enforce_quota: bool = True,
) -> AIResult:
    result = await ai_service.ask_text(
        query,
        user_id=user_id,
        feature=feature,
        system_prompt=system_prompt,
        history=history,
        unlimited=bool(user_id is not None and is_admin(user_id)),
        enforce_quota=enforce_quota,
    )
    if result.ok and user_id is not None:
        await users_col.update_one(
            {"_id": user_id},
            {"$inc": {"ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    return result


async def ask_ai(
    query: str,
    *,
    user_id: int | None = None,
    feature: str = "general",
    system_prompt: str = AI_BASE_SYSTEM_PROMPT,
    history: list[dict[str, str]] | None = None,
    enforce_quota: bool = True,
) -> str | None:
    result = await ask_ai_detailed(
        query,
        user_id=user_id,
        feature=feature,
        system_prompt=system_prompt,
        history=history,
        enforce_quota=enforce_quota,
    )
    return result.text if result.ok else None


def ai_error_text(reason: str | None, image: bool = False) -> str:
    if reason == "quota":
        return "⏳ سهمیه امروزت تموم شده. از «📊 سهمیه من» زمان و تعداد باقی‌مانده رو ببین؛ فردا دوباره شارژ می‌شه."
    if reason in {"unconfigured", "image_generation_unavailable", "image_understanding_unavailable"}:
        return "🛠 این قابلیت هوش مصنوعی هنوز روی سرور فعال نشده. مدیر باید کلید سرویس مربوطه رو در Railway تنظیم کنه."
    if reason == "invalid_image":
        return "❌ این تصویر قابل پردازش نیست؛ یک عکس JPG یا PNG کم‌حجم‌تر بفرست."
    if reason == "invalid_audio":
        return "❌ فایل صوتی قابل پردازش نیست؛ ویس یا فایل صوتی کمتر از ۱۹ مگابایت بفرست."
    if reason == "empty_input":
        return "یک توضیح یا متن بفرست تا شروع کنیم."
    return (
        "🎨 سرویس ساخت تصویر فعلاً جواب نداد و سهمیه‌ای هم ازت کم نشد؛ چند دقیقه دیگه دوباره امتحان کن."
        if image
        else "🤖 سرویس‌های هوش مصنوعی موقتاً در دسترس نیستن و سهمیه‌ای هم ازت کم نشد؛ کمی بعد دوباره بزن."
    )


def split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


async def deliver_ai_text(
    message: types.Message,
    waiting: types.Message,
    text: str,
    reply_markup: ReplyKeyboardMarkup | None = None,
) -> None:
    chunks = split_telegram_text(text)
    if not chunks:
        chunks = ["پاسخی دریافت نشد."]
    try:
        await waiting.edit_text(chunks[0])
    except TelegramBadRequest:
        await message.answer(chunks[0])
    for chunk in chunks[1:]:
        await message.answer(chunk)
    if reply_markup is not None:
        await message.answer("برای ادامه، متن بعدی رو بفرست یا یک ابزار دیگه انتخاب کن:", reply_markup=reply_markup)


async def execute_ai_text_mode(message: types.Message, session_data: dict, text: str) -> None:
    user_id = message.from_user.id
    mode = session_data.get("mode", "chat")
    details = AI_MODE_CONFIG.get(mode, AI_MODE_CONFIG["chat"])
    lock = ai_request_lock(user_id)
    if lock.locked():
        return await message.answer("⏳ درخواست قبلیت هنوز در حال پردازشه؛ چند ثانیه صبر کن.", reply_markup=ai_reply_menu())

    async with lock:
        if mode == "image":
            waiting = await message.answer("🎨 دارم تصویرت رو می‌سازم؛ ممکنه تا یک دقیقه طول بکشه...")
            await bot.send_chat_action(message.chat.id, "upload_photo")
            result: AIImageResult = await ai_service.generate_image(
                text,
                user_id=user_id,
                unlimited=is_admin(user_id),
            )
            try:
                await waiting.delete()
            except TelegramBadRequest:
                pass
            if not result.ok or not result.image:
                return await message.answer(ai_error_text(result.reason, image=True), reply_markup=ai_reply_menu())
            extension = "jpg" if "jpeg" in result.mime_type else "webp" if "webp" in result.mime_type else "png"
            caption = "🎨 تصویر آماده شد!"
            if result.caption:
                caption += f"\n\n{result.caption[:800]}"
            upload = BufferedInputFile(result.image, filename=f"ajorpareh-ai.{extension}")
            if len(result.image) <= 9_500_000:
                await message.answer_photo(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
            else:
                await message.answer_document(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
            await users_col.update_one(
                {"_id": user_id},
                {"$inc": {"ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
            await log_activity(user_id, "ai_image", f"provider={result.provider or 'none'}")
            return

        waiting = await message.answer("🤖 دارم فکر می‌کنم...")
        history = session_data.get("history", []) if mode == "chat" else []
        result = await ask_ai_detailed(
            text,
            user_id=user_id,
            feature=mode,
            system_prompt=details.get("system", AI_BASE_SYSTEM_PROMPT),
            history=history,
        )
        if not result.ok or not result.text:
            try:
                await waiting.edit_text(ai_error_text(result.reason))
            except TelegramBadRequest:
                await message.answer(ai_error_text(result.reason), reply_markup=ai_reply_menu())
            return
        if mode == "chat":
            conversation = list(history)
            conversation.extend([
                {"role": "user", "content": text[:3000]},
                {"role": "assistant", "content": result.text[:3000]},
            ])
            session_data["history"] = conversation[-10:]
        session_data["last_used_at"] = time.monotonic()
        await deliver_ai_text(message, waiting, result.text, ai_reply_menu())
        await log_activity(user_id, f"ai_{mode}", f"provider={result.provider or 'none'}")


async def download_telegram_photo(message: types.Message) -> bytes:
    telegram_file = await bot.get_file(message.photo[-1].file_id)
    # در حالت سرور لوکال Bot API، file_path مطلق (مثل /tmp/tgapi/...) است
    # و دانلود از طریق HTTP کار نمی‌کند؛ مستقیم از دیسک خوانده می‌شود.
    if LOCAL_BOT_API and telegram_file.file_path and str(telegram_file.file_path).startswith("/"):
        local_path = Path(str(telegram_file.file_path))
        if local_path.exists():
            return local_path.read_bytes()
    output = io.BytesIO()
    await bot.download_file(telegram_file.file_path, destination=output)
    return output.getvalue()


async def download_telegram_media(file_id: str) -> bytes:
    telegram_file = await bot.get_file(file_id)
    if LOCAL_BOT_API and telegram_file.file_path and str(telegram_file.file_path).startswith("/"):
        local_path = Path(str(telegram_file.file_path))
        if local_path.exists():
            return local_path.read_bytes()
    output = io.BytesIO()
    await bot.download_file(telegram_file.file_path, destination=output)
    return output.getvalue()


async def handle_ai_audio_request(message: types.Message) -> None:
    user_id = message.from_user.id
    media = message.voice or message.audio
    if not media:
        return
    if int(media.file_size or 0) > 19 * 1024 * 1024:
        return await message.answer(ai_error_text("invalid_audio"), reply_markup=ai_reply_menu())
    lock = ai_request_lock(user_id)
    if lock.locked():
        return await message.answer("⏳ درخواست قبلیت هنوز در حال پردازشه؛ چند ثانیه صبر کن.")
    async with lock:
        waiting = await message.answer("🎙 دارم ویس رو به متن تبدیل می‌کنم...")
        try:
            audio_data = await download_telegram_media(media.file_id)
        except (TelegramBadRequest, TelegramForbiddenError, OSError):
            return await waiting.edit_text("❌ دانلود فایل صوتی از تلگرام ممکن نشد؛ دوباره ارسالش کن.")
        mime_type = getattr(media, "mime_type", None) or "audio/ogg"
        filename = getattr(media, "file_name", None) or ("voice.ogg" if message.voice else "audio.mp3")
        result = await ai_service.transcribe_audio(
            audio_data,
            mime_type,
            filename,
            user_id=user_id,
            unlimited=is_admin(user_id),
        )
        if not result.ok or not result.text:
            try:
                await waiting.edit_text(ai_error_text(result.reason))
            except TelegramBadRequest:
                await message.answer(ai_error_text(result.reason), reply_markup=ai_reply_menu())
            return
        await deliver_ai_text(message, waiting, f"🎙 متن ویس:\n\n{result.text}", ai_reply_menu())
        await users_col.update_one(
            {"_id": user_id},
            {"$inc": {"voice_transcriptions_count": 1, "ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        await log_activity(user_id, "ai_voice_transcription", f"provider={result.provider or 'none'}")


IMAGE_REFERENCE_PRESERVE_INSTRUCTION = (
    "Use the attached image as the identity and appearance reference. Preserve the person's "
    "actual gender, age range, facial structure, skin tone, hairstyle, beard/hairline, body proportions, "
    "jewelry and recognizable features. Do not change the person into another gender or another person; "
    "do not feminize or masculinize the face. Change only the scene, lighting, clothing or artistic style "
    "requested by the user. Keep anatomy natural and photorealistic.\n\n"
)


async def handle_prompt_reference_image(message: types.Message) -> None:
    """اجرای پرامپت کتابخانه روی عکس مرجع، با قفل هویت و جنسیت."""
    user_id = message.from_user.id
    prompt = prompt_image_sessions.pop(user_id, "").strip()
    extra = (message.caption or "").strip()
    if extra:
        prompt += f"\n\nAdditional user instructions:\n{extra[:1200]}"
    if not prompt:
        return await message.answer("❌ پرامپت مرجع پیدا نشد؛ دوباره از کتابخانهٔ پرامپت انتخاب کن.", reply_markup=ai_reply_menu())
    profanity = detect_profanity(prompt)
    if profanity:
        return await issue_private_warning(message, profanity)
    lock = ai_request_lock(user_id)
    if lock.locked():
        return await message.answer("⏳ درخواست قبلیت هنوز در حال پردازشه؛ چند ثانیه صبر کن.")
    async with lock:
        try:
            image_data = await download_telegram_photo(message)
        except (TelegramBadRequest, TelegramForbiddenError, OSError):
            return await message.answer("❌ دانلود عکس مرجع ممکن نشد؛ دوباره ارسالش کن.")
        waiting = await message.answer("🎨 پرامپت رو با حفظ چهره و هویت عکس اجرا می‌کنم…")
        await bot.send_chat_action(message.chat.id, "upload_photo")
        result = await ai_service.generate_image(
            IMAGE_REFERENCE_PRESERVE_INSTRUCTION + prompt,
            user_id=user_id,
            unlimited=is_admin(user_id),
            source_image=image_data,
            source_mime_type="image/jpeg",
        )
        try:
            await waiting.delete()
        except TelegramBadRequest:
            pass
        if not result.ok or not result.image:
            return await message.answer(ai_error_text(result.reason, image=True), reply_markup=ai_reply_menu())
        extension = "jpg" if "jpeg" in result.mime_type else "webp" if "webp" in result.mime_type else "png"
        upload = BufferedInputFile(result.image, filename=f"ajorpareh-prompt-edit.{extension}")
        caption = "🎨 اجرای پرامپت روی عکس آماده شد!"
        if result.caption:
            caption += f"\n\n{result.caption[:800]}"
        if len(result.image) <= 9_500_000:
            await message.answer_photo(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
        else:
            await message.answer_document(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
        await users_col.update_one(
            {"_id": user_id},
            {"$inc": {"ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        await log_activity(user_id, "ai_prompt_image", f"prompt={prompt[:120]}")


async def handle_ai_photo_request(message: types.Message, mode: str) -> None:
    user_id = message.from_user.id
    prompt = (message.caption or "").strip()
    if mode == "edit_image" and not prompt:
        return await message.answer(
            "🪄 عکس رو دوباره بفرست و تغییرات دلخواهت رو داخل کپشن همون عکس بنویس.",
            reply_markup=ai_reply_menu(),
        )
    profanity = detect_profanity(prompt)
    if profanity:
        return await issue_private_warning(message, profanity)
    lock = ai_request_lock(user_id)
    if lock.locked():
        return await message.answer("⏳ درخواست قبلیت هنوز در حال پردازشه؛ چند ثانیه صبر کن.")
    async with lock:
        try:
            image_data = await download_telegram_photo(message)
        except (TelegramBadRequest, TelegramForbiddenError, OSError):
            return await message.answer("❌ دانلود عکس از تلگرام ممکن نشد؛ دوباره ارسالش کن.")
        if mode == "vision":
            waiting = await message.answer("👁 دارم تصویر رو بررسی می‌کنم...")
            result = await ai_service.analyze_image(
                image_data,
                "image/jpeg",
                prompt or "این تصویر را دقیق توصیف کن، نکات مهمش را بگو و اگر متنی داخل آن است بخوان.",
                user_id=user_id,
                system_prompt=AI_BASE_SYSTEM_PROMPT + " در تحلیل تصویر فقط چیزهایی را بگو که واقعاً قابل مشاهده است و عدم قطعیت را مشخص کن.",
                unlimited=is_admin(user_id),
            )
            if not result.ok or not result.text:
                try:
                    await waiting.edit_text(ai_error_text(result.reason))
                except TelegramBadRequest:
                    await message.answer(ai_error_text(result.reason), reply_markup=ai_reply_menu())
                return
            await deliver_ai_text(message, waiting, result.text, ai_reply_menu())
            await users_col.update_one(
                {"_id": user_id},
                {"$inc": {"ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
            await log_activity(user_id, "ai_vision", f"provider={result.provider or 'none'}")
            return

        waiting = await message.answer("🪄 دارم تصویر رو با توضیحت ویرایش می‌کنم...")
        await bot.send_chat_action(message.chat.id, "upload_photo")
        result = await ai_service.generate_image(
            IMAGE_REFERENCE_PRESERVE_INSTRUCTION + prompt,
            user_id=user_id,
            unlimited=is_admin(user_id),
            source_image=image_data,
            source_mime_type="image/jpeg",
        )
        try:
            await waiting.delete()
        except TelegramBadRequest:
            pass
        if not result.ok or not result.image:
            return await message.answer(ai_error_text(result.reason, image=True), reply_markup=ai_reply_menu())
        extension = "jpg" if "jpeg" in result.mime_type else "webp" if "webp" in result.mime_type else "png"
        upload = BufferedInputFile(result.image, filename=f"ajorpareh-ai-edit.{extension}")
        caption = "🪄 ویرایش تصویر آماده شد!"
        if result.caption:
            caption += f"\n\n{result.caption[:800]}"
        if len(result.image) <= 9_500_000:
            await message.answer_photo(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
        else:
            await message.answer_document(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
        await users_col.update_one(
            {"_id": user_id},
            {"$inc": {"ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        await log_activity(user_id, "ai_image_edit", f"provider={result.provider or 'none'}")

def get_tehran_time():
    return datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)

def today_str() -> str:
    """تاریخ امروز به وقت تهران، برای پاداش و محتوای روزانه."""
    return get_tehran_time().strftime("%Y-%m-%d")


def yesterday_str() -> str:
    return (get_tehran_time() - timedelta(days=1)).strftime("%Y-%m-%d")


def mask_card(card: str) -> str:
    digits = re.sub(r"\D", "", card)
    return f"{digits[:4]}-****-****-{digits[-4:]}" if len(digits) >= 8 else "نامعتبر"


def is_valid_card_number(card: str) -> bool:
    """اعتبارسنجی پایه شماره کارت ۱۶ رقمی ایران."""
    digits = re.sub(r"\D", "", card)
    if len(digits) != 16 or len(set(digits)) == 1:
        return False
    total = 0
    for index, digit in enumerate(map(int, digits)):
        value = digit * (2 if index % 2 == 0 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


async def record_game(user_id: int, game_name: str, won: bool = False, xp: int = 0):
    update = {
        "$inc": {
            "games_played": 1,
            "games_won": 1 if won else 0,
            "xp": max(0, xp),
            "daily_games": 1,
        },
        "$set": {"last_game": game_name, "last_game_at": datetime.now(timezone.utc)},
    }
    user = await users_col.find_one({"_id": user_id}, {"daily_games_date": 1})
    if not user or user.get("daily_games_date") != today_str():
        update["$set"]["daily_games_date"] = today_str()
        update["$set"]["daily_games"] = 1
        update["$inc"].pop("daily_games", None)
    await users_col.update_one({"_id": user_id}, update, upsert=True)
    await log_activity(user_id, f"game_{game_name}", f"won={won}, xp={xp}")


# ======== ماشین‌حساب امن (بدون eval) ========
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if abs(node.value) > 1_000_000_000:
            raise ValueError("عدد بیش از حد بزرگ است")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 1_000_000):
            raise ValueError("توان بیش از حد بزرگ است")
        result = _ALLOWED_OPERATORS[type(node.op)](left, right)
        if abs(result) > 1_000_000_000_000_000:
            raise ValueError("نتیجه بیش از حد بزرگ است")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("عبارت نامعتبر")

def safe_eval(expr: str):
    if len(expr) > 100:
        raise ValueError("عبارت خیلی طولانی است")
    node = ast.parse(expr, mode="eval").body
    result = _eval_node(node)
    if isinstance(result, complex) or (isinstance(result, float) and not math.isfinite(result)):
        raise ValueError("نتیجه نامعتبر")
    return result

# ======== منوها ========
def main_menu(user_id: int | None = None):
    rows = [
        [InlineKeyboardButton(text="🎮 باز کردن Ajorpareh Mini App", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton(text="🔥 جایزه روزانه", callback_data="daily_reward"),
         InlineKeyboardButton(text="🏆 رتبه‌بندی", callback_data="leaderboard")],
        [InlineKeyboardButton(text="🎯 بازی و سرگرمی", callback_data="game"),
         InlineKeyboardButton(text="🎁 دعوت دوستان", callback_data="invite")],
        [InlineKeyboardButton(text="🎭 حال‌سنج امروز", callback_data="mood_meter"),
         InlineKeyboardButton(text="🧠 کوئیز فوری", callback_data="quick_quiz")],
        [InlineKeyboardButton(text="✨ کپشن‌ساز وایرال", callback_data="caption_maker"),
         InlineKeyboardButton(text="🎭 جرأت یا حقیقت", callback_data="truth_dare")],
        [InlineKeyboardButton(text="🎬 دانلود یوتیوب", callback_data="youtube"),
         InlineKeyboardButton(text="🧮 ماشین‌حساب", callback_data="open_calc")],
        [InlineKeyboardButton(text="🌐 پروکسی تلگرام", callback_data="get_proxy"),
         InlineKeyboardButton(text="🔐 کانفیگ اختصاصی", callback_data="config_menu")],
        [InlineKeyboardButton(text="💳 کیف پول", callback_data="wallet"),
         InlineKeyboardButton(text="👤 پروفایل من", callback_data="profile_user")],
        [InlineKeyboardButton(text="🎟 کد هدیه", callback_data="gift_help"),
         InlineKeyboardButton(text="🎯 مأموریت‌های جایزه", callback_data="user_missions")],
        [InlineKeyboardButton(text="📖 معرفی سوپرربات", callback_data="about_bot")],
        [InlineKeyboardButton(text="💬 پشتیبانی و پیشنهاد", callback_data="support"),
         InlineKeyboardButton(text="📣 کانال داغ‌ها", url=CHANNEL_LINK)],
    ]
    if user_id is not None and is_admin(user_id):
        rows.append([InlineKeyboardButton(text="⚙️ پنل مدیریت حرفه‌ای", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_reply_menu(user_id: int | None = None) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🎮 بازی‌ها"), KeyboardButton(text="🎁 جوایز و کیف پول")],
        [KeyboardButton(text="📰 اخبار و ترندها"), KeyboardButton(text="🧰 ابزارهای ربات")],
        [KeyboardButton(text="🎨 گیف و استیکرساز")],
        [KeyboardButton(text="🤖 هوش مصنوعی"), KeyboardButton(text="🛍 سرویس اختصاصی")],
        [KeyboardButton(text="💬 پشتیبانی")],
    ]
    if user_id is not None and is_admin(user_id):
        rows.append([KeyboardButton(text="⚙️ پنل مدیریت")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="یکی از گزینه‌های منو را انتخاب کن...",
    )


def persistent_keyboard(rows: list[list[str]], placeholder: str = "یک گزینه را انتخاب کن...") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in rows],
        resize_keyboard=True, is_persistent=True, one_time_keyboard=False,
        input_field_placeholder=placeholder,
    )


def games_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🏃 بزن در رو", "🧠 کوئیز فوری"], ["🎲 تاس", "🎯 دارت"],
        ["🪨 سنگ‌کاغذ‌قیچی", "🪙 شیر یا خط"], ["🔢 حدس عدد", "🎭 جرأت یا حقیقت"],
        ["🧠 جورچین حافظه", "🃏 بیست و یک"],
        ["🏠 منوی اصلی"],
    ], "یک بازی انتخاب کن...")


def rps_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([["🪨 سنگ", "📄 کاغذ", "✂️ قیچی"], ["↩️ بازی‌ها", "🏠 منوی اصلی"]])


def coin_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([["🪙 شیر", "🪙 خط"], ["↩️ بازی‌ها", "🏠 منوی اصلی"]])


def truth_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([["💬 حقیقت", "🔥 جرأت"], ["❤️ کاپلی", "🎲 شانسی"], ["↩️ بازی‌ها", "🏠 منوی اصلی"]])


def rewards_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🔥 جایزه روزانه", "💳 کیف پول"], ["🎁 دعوت دوستان", "🎟 کد هدیه"],
        ["🎯 مأموریت‌های جایزه", "🏆 رتبه‌بندی"], ["🏠 منوی اصلی"],
    ], "جوایز و کیف پول...")


def service_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🚀 خرید سرویس جدید"],
        ["♻️ تمدید سرویس", "📱 سرویس‌های من"],
        ["💰 اعتبار من", "🎁 تخفیف و آفر ویژه"],
        ["🏆 کاربران برتر", "👥 معرفی به دوستان"],
        ["💡 آموزش استفاده", "👨‍💻 تماس با پشتیبانی"],
        ["📊 وضعیت سفارش", "🏠 منوی اصلی"],
    ], "مرکز سرویس اختصاصی...")


def news_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["📰 اخبار زنده", "😂 جوک تازه"],
        ["🧠 دانستنی عجیب", "🧩 معمای فوری"],
        ["🎭 این یا اون", "⚡ چالش ۳۰ ثانیه"],
        ["🤡 میم متنی", "🔮 فال فان امروز"],
        ["✨ جمله انگیزشی", "🔥 داغ‌های کانال"],
        ["📣 کانال Ajorpareh", "🏠 منوی اصلی"],
    ], "خبر، فان یا چالش...")


def live_news_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🇮🇷 اخبار ایران", "🌍 اخبار جهان"],
        ["💻 اخبار فناوری", "🔄 تازه‌ترین خبرها"],
        ["↩️ خبر و سرگرمی", "🏠 منوی اصلی"],
    ], "دسته خبر را انتخاب کن...")


def tools_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["📥 مرکز دانلود و آپلود", "🎨 گیف و استیکرساز"],
        ["🎵 موسیقی", "📱 QR ساز"], ["🕛 00:00", "🌅 صبح بخیر"],
        ["🧠 پرامپت‌ها", "✨ کپشن‌ساز"],
        ["🧮 ماشین‌حساب", "🎭 حال‌سنج"],
        ["⏰ یادآور هوشمند"],
        ["🛡 بررسی امنیت لینک", "📅 تقویم شمسی"],
        ["🌍 دانش و اطلاعات", "🎤 تبدیل متن به صدا"],
        ["🧩 API شکلک سفارشی", "🌐 پروکسی"], ["🔐 کانفیگ", "🏠 منوی اصلی"],
    ], "ابزار موردنظرت...")


def info_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["☀️ آب‌وهوا", "💱 نرخ ارز"], ["🪙 قیمت کریپتو", "🕐 ساعت جهانی"],
        ["🕌 اوقات شرعی", "🍷 فال حافظ"],
        ["🕌 اذان‌گوی شخصی", "🔔 فال روزانه"], ["📚 خلاصه ویکی‌پدیا", "📖 جستجوی کتاب"],
        ["🌍 اطلاعات کشورها", "🧠 کوئیز جهانی"],
        ["🔐 بررسی امنیت رمز", "↩️ ابزارهای ربات"],
        ["🏠 منوی اصلی"],
    ], "چی می‌خوای بدونی؟...")


def media_download_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["📸 دانلود اینستاگرام", "🖼 پروفایل اینستاگرام"],
        ["🎵 دانلود تیک‌تاک", "▶️ دانلود یوتیوب"],
        ["🌐 دانلود سایر شبکه‌ها", "🔗 آپلود فایل از URL"],
        ["🛡 بررسی امنیت لینک", "💬 کپی متن کامنت اینستاگرام"],
        ["🎵 موسیقی", "📋 دانلودهای اخیر"],
        ["🔄 ویدئو به دایره‌ای", "📊 سهمیه دانلود"],
        ["ℹ️ راهنمای دانلود"],
        ["↩️ ابزارهای ربات"],
        ["🏠 منوی اصلی"],
    ], "اول نوع دریافت رو انتخاب کن، بعد لینک رو بفرست...")


def music_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🔎 جستجوی آهنگ", "🔥 آهنگ‌های ترند"],
        ["🇮🇷 ترند ایرانی", "🎚 ریمیکس ایرانی"],
        ["📅 موزیک امروز", "📚 پلی‌لیست ایرانی"],
        ["📤 آپلود گروهی موسیقی"],
        ["🎤 تشخیص آهنگ با تکه صدا", "📖 راهنمای موسیقی"],
        ["↩️ ابزارهای ربات", "🏠 منوی اصلی"],
    ], "🎵 بخش موسیقی — چی کار کنم؟")


def media_maker_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🪄 ساخت استیکر", "🎞 ساخت گیف"],
        ["📦 پک استیکرهای من", "ℹ️ راهنمای گیف و استیکر"],
        ["↩️ ابزارهای ربات", "🏠 منوی اصلی"],
    ], "گیف یا استیکر بساز...")


def reminder_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["➕ یادآور جدید", "📋 یادآورهای من"],
        ["↩️ ابزارهای ربات", "🏠 منوی اصلی"],
    ], "یادآور روزمره...")


def ai_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["💬 چت هوشمند", "🎨 ساخت تصویر"],
        ["🎙 ویس به متن", "👁 تحلیل تصویر"],
        ["🪄 ویرایش تصویر", "✍️ بازنویسی متن"],
        ["🌐 ترجمه حرفه‌ای", "🧠 خلاصه‌سازی"],
        ["📚 کمک درسی", "💻 برنامه‌نویسی"],
        ["📣 تولید محتوا", "💡 ایده‌پردازی"],
        ["🧠 پرامپت‌ها", "📊 سهمیه من"],
        ["🧹 پاک‌کردن گفتگو"],
        ["🏠 منوی اصلی"],
    ], "یک ابزار هوش مصنوعی انتخاب کن...")


async def show_ai_menu(message: types.Message) -> None:
    if getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("🤖 ابزارهای هوش مصنوعی داخل گفت‌وگوی خصوصی ربات فعاله:\nhttps://t.me/Ajorparehbot")
        return
    user_id = message.from_user.id
    status = ai_service.public_status()
    quota = await ai_service.quota_snapshot(user_id, unlimited=is_admin(user_id))
    provider_labels = {
        "gemini": "Gemini",
        "groq": "Groq",
        "cerebras": "Cerebras",
        "openrouter": "OpenRouter",
    }
    providers = " ← ".join(provider_labels.get(item, item) for item in status["text_providers"])
    if quota["unlimited"]:
        quota_line = "♾ سهمیه مدیریت: نامحدود"
    else:
        quota_line = (
            f"📝 متن: {quota['text_remaining']} از {quota['text_limit']} باقی‌مانده · "
            f"🎨 تصویر: {quota['image_remaining']} از {quota['image_limit']}"
        )
        if quota.get("text_bonus") or quota.get("image_bonus"):
            quota_line += (
                f"\n🎁 سهمیه اضافه: +{quota.get('text_bonus', 0)} متن"
                f" · +{quota.get('image_bonus', 0)} تصویر"
            )
    await message.answer(
        "🤖 <b>مرکز هوش مصنوعی Ajorpareh</b>\n\n"
        f"🔌 سرویس متن: {html.escape(providers) if providers else 'در انتظار فعال‌سازی'}\n"
        f"🖼 ساخت تصویر: {'فعال' if status['image_generation'] else 'در انتظار فعال‌سازی'}\n"
        f"🪄 ویرایش تصویر: وابسته به سهمیه تصویری Gemini\n"
        f"{quota_line}\n\n"
        "یک ابزار رو از منوی پایین انتخاب کن. برای امنیت، رمز، کد ورود، اطلاعات بانکی یا متن محرمانه نفرست؛ "
        "درخواست‌ها برای پردازش به ارائه‌دهنده هوش مصنوعی ارسال می‌شن.",
        reply_markup=ai_reply_menu(),
        parse_mode="HTML",
    )


def support_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["✍️ ارسال پیام پشتیبانی", "💬 نظرات کاربران"],
        ["👤 پروفایل من", "❓ راهنمای ربات"],
        ["📖 معرفی ربات", "🔄 بروزرسانی و رفع مشکل"],
        ["🏠 منوی اصلی"],
    ], "پشتیبانی Ajorpareh...")


def reviews_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["👀 دیدن نظرات", "✍️ نوشتن نظر"],
        ["↩️ پشتیبانی", "🏠 منوی اصلی"],
    ], "نظرات Ajorpareh...")


def admin_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["📊 آمار و گزارش", "👥 کاربران و تیکت‌ها"],
        ["📡 رصد فعالیت‌ها", "🔥 کاربران فعال"],
        ["📢 محتوا و انتشار", "💰 مالی و اقتصاد"],
        ["🌐 کانفیگ و فایل‌ها", "🛡 گروه و کانال"],
        ["🎯 کمپین و جوایز", "👮 مدیران و امنیت"],
        ["🩺 سلامت و پشتیبان", "🏠 منوی اصلی"],
    ], "پنل مدیریت...")


def admin_content_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["⚡ انتشار فوری", "♻️ بازنشر گروهی"], ["⏰ پست زمان‌دار", "✍️ متن دعوت بازنشر"],
        ["📢 پیام همگانی", "📝 قالب‌های محتوا"],
        ["📤 گروه فایل جدید", "✅ انتشار گروه فایل"],
        ["📁 مدیریت فایل‌ها", "📊 آمار رسانه"],
        ["🍷 فال روزانه صبحگاهی", "📈 پست خودکار نرخ ارز"],
        ["🕌 پست اذان روزانه در کانال"],
        ["🧹 پاکسازی صف رسانه", "↩️ پنل مدیریت"],
    ])


def admin_finance_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["💰 افزایش موجودی کاربر", "💸 برداشت‌های در انتظار"],
        ["💰 تنظیمات اقتصاد", "📊 گزارش مالی و ضدتقلب"],
        ["🛒 فروش و سفارش سرویس"],
        ["📊 آمار مالی هفتگی در کانال", "📤 ارسال گزارش مالی به کانال"],
        ["↩️ پنل مدیریت"],
    ], "کاربر یا عملیات مالی را انتخاب کن...")


def admin_files_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🌐 مدیریت پروکسی و کانفیگ", "📁 مدیریت فایل‌ها"],
        ["📤 گروه فایل جدید", "✅ انتشار گروه فایل"], ["↩️ پنل مدیریت"],
    ])


def admin_groups_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🛡 گروه‌ها و کانال‌ها", "📣 کانال‌های عضویت اجباری"], ["↩️ پنل مدیریت"],
    ])


def admin_campaign_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🎟 کدهای جایزه", "🎯 مأموریت‌ها"], ["🎡 قرعه‌کشی‌ها", "📈 پیش‌بینی ترند"], ["↩️ پنل مدیریت"],
    ])


def admin_security_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["👮 نقش مدیران", "📜 گزارش فعالیت مدیران"], ["🟢/🔴 حالت تعمیرات", "✅/☑️ عضویت اجباری"], ["↩️ پنل مدیریت"],
    ])


def admin_health_reply_menu() -> ReplyKeyboardMarkup:
    return persistent_keyboard([
        ["🩺 سلامت ربات", "🤖 وضعیت هوش مصنوعی"],
        ["💾 دریافت پشتیبان", "🔄 خودترمیم و بروزرسانی"],
        ["↩️ پنل مدیریت"],
    ])


def reply_keyboard_labels(markup: ReplyKeyboardMarkup) -> set[str]:
    return {
        button.text
        for row in markup.keyboard
        for button in row
        if getattr(button, "text", None)
    }


def bot_control_texts(user_id: int) -> set[str]:
    keyboards = [
        chat_reply_menu(user_id), games_reply_menu(), rps_reply_menu(), coin_reply_menu(),
        truth_reply_menu(), rewards_reply_menu(), news_reply_menu(), live_news_reply_menu(),
        tools_reply_menu(), media_download_reply_menu(), media_maker_reply_menu(), reminder_reply_menu(), ai_reply_menu(), support_reply_menu(),
        reviews_reply_menu(), service_reply_menu(), admin_reply_menu(), admin_content_reply_menu(),
        admin_finance_reply_menu(), admin_files_reply_menu(), admin_groups_reply_menu(),
        admin_campaign_reply_menu(), admin_security_reply_menu(), admin_health_reply_menu(),
    ]
    labels = {label for keyboard in keyboards for label in reply_keyboard_labels(keyboard)}
    labels.update({"منو", "menu", "منوی اصلی", "نمایش منو", "پنل", "پنل مدیریت", "مدیریت", "🪄 استیکرساز"})
    return labels


def is_publication_control_text(text: str, user_id: int) -> bool:
    stripped = str(text or "").strip()
    return stripped.startswith("/") or stripped in bot_control_texts(user_id)


async def pause_publication_for_control(message: types.Message) -> bool:
    user_id = message.from_user.id
    if user_id not in instant_repost_sessions and user_id not in repost_sessions:
        return False
    if not is_publication_control_text(message.text or "", user_id):
        return False
    was_instant = user_id in instant_repost_sessions
    instant_repost_sessions.pop(user_id, None)
    repost_sessions.discard(user_id)
    cancel_album_buffers(user_id)
    await message.answer(
        "🧭 این پیام دستور خود ربات بود و داخل کانال منتشر نشد.\n"
        + ("حالت انتشار فوری متوقف شد." if was_instant else "گروه بازنشر ذخیره موند و حالت دریافت پست موقتاً متوقف شد."),
        reply_markup=chat_reply_menu(user_id),
    )
    return True


def rewards_chat_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 باشگاه جوایز", web_app=WebAppInfo(url=f"{MINI_APP_URL}#rewards"))],
        [InlineKeyboardButton(text="💳 کیف پول و برداشت", web_app=WebAppInfo(url=f"{MINI_APP_URL}#profile"))],
        [InlineKeyboardButton(text="🔥 جایزه روزانه", callback_data="daily_reward"), InlineKeyboardButton(text="🎁 لینک دعوت", callback_data="invite")],
        [InlineKeyboardButton(text="🎟 کد هدیه", callback_data="gift_help"), InlineKeyboardButton(text="🎯 مأموریت‌ها", callback_data="user_missions")],
        [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="back_main")],
    ])


def news_chat_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📰 خبرها و جوک‌ها", web_app=WebAppInfo(url=f"{MINI_APP_URL}#news"))],
        [InlineKeyboardButton(text="📣 کانال @Ajor_pareh", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="😂 یک جوک", callback_data="joke_again"), InlineKeyboardButton(text="✨ جمله انگیزشی", callback_data="quote_again")],
        [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="back_main")],
    ])


def tools_chat_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ کپشن‌ساز وایرال", callback_data="caption_maker"), InlineKeyboardButton(text="🧮 ماشین‌حساب", callback_data="open_calc")],
        [InlineKeyboardButton(text="🎬 دانلود یوتیوب", callback_data="youtube")],
        [InlineKeyboardButton(text="🌐 پروکسی تلگرام", callback_data="get_proxy"), InlineKeyboardButton(text="🔐 کانفیگ اختصاصی", callback_data="config_menu")],
        [InlineKeyboardButton(text="🎭 حال‌سنج", callback_data="mood_meter"), InlineKeyboardButton(text="🧠 کوئیز", callback_data="quick_quiz")],
        [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="back_main")],
    ])


def generate_qr_png(content: str) -> bytes:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=12, border=4)
    qr.add_data(content); qr.make(fit=True)
    image = qr.make_image(fill_color="#111015", back_color="#ffffff").convert("RGB")
    output = io.BytesIO(); image.save(output, format="PNG", optimize=True); return output.getvalue()


def make_sticker_webp(source: bytes) -> bytes:
    with Image.open(io.BytesIO(source)) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((512 - image.width) // 2, (512 - image.height) // 2))
        for quality in (90, 82, 74, 65):
            output = io.BytesIO(); canvas.save(output, format="WEBP", quality=quality, method=6)
            if output.tell() <= 512 * 1024: return output.getvalue()
        return output.getvalue()


async def send_qr_result(message: types.Message, content: str):
    content = content.strip()
    if not content or len(content) > 1500:
        return await message.answer("متن یا لینک باید بین ۱ تا ۱۵۰۰ کاراکتر باشد.")
    data = await asyncio.to_thread(generate_qr_png, content)
    await message.answer_photo(BufferedInputFile(data, filename="ajorpareh-qr.png"), caption="📱 QR شما آماده‌ست. برای ساخت یکی دیگه دوباره گزینه QR ساز رو بزن.")


async def make_telegram_animation(source: bytes, suffix: str, from_photo: bool = False) -> bytes:
    if shutil.which("ffmpeg") is None:
        raise ValueError("موتور تبدیل گیف روی سرور در دسترس نیست")
    if not source or len(source) > 19 * 1024 * 1024:
        raise ValueError("فایل ورودی باید کمتر از ۱۹ مگابایت باشد")
    safe_suffix = suffix.lower() if re.fullmatch(r"\.[a-z0-9]{2,5}", suffix.lower()) else ".bin"
    with tempfile.TemporaryDirectory(prefix="ajor-gif-") as folder:
        input_path = Path(folder) / f"input{safe_suffix}"
        output_path = Path(folder) / "animation.mp4"
        input_path.write_bytes(source)
        if from_photo:
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-i", str(input_path), "-t", "3",
                "-vf", (
                    "scale=720:720:force_original_aspect_ratio=decrease,"
                    "pad=720:720:(ow-iw)/2:(oh-ih)/2:color=0x0b0a0f,"
                    "zoompan=z='min(zoom+0.0015,1.10)':"
                    "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=72:s=720x720:fps=24"
                ),
            ]
        else:
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(input_path), "-t", "12",
                "-vf", (
                    "scale=720:720:force_original_aspect_ratio=decrease,"
                    "pad=720:720:(ow-iw)/2:(oh-ih)/2:color=0x0b0a0f,fps=24"
                ),
            ]
        command.extend([
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path),
        ])
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=90)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise ValueError("تبدیل گیف بیش از حد طول کشید") from exc
        if process.returncode != 0 or not output_path.exists():
            log.warning("ffmpeg animation failed: %s", stderr.decode(errors="ignore")[:500])
            raise ValueError("فرمت رسانه برای ساخت گیف پشتیبانی نمی‌شود")
        result = output_path.read_bytes()
        if not result or len(result) > 19 * 1024 * 1024:
            raise ValueError("خروجی گیف بیش از حد بزرگ شد")
        return result


async def download_telegram_media_to_path(file_id: str, dest_path: str) -> str:
    """دانلود فایل تلگرام مستقیم به دیسک (استریم) — بدون کپی کامل در حافظه.

    در حالت سرور لوکال Bot API، file_path مطلق است و مستقیم از دیسک کپی می‌شود؛
    در غیر این صورت با دانلود استریمی aiohttp روی دیسک نوشته می‌شود.
    این روش برای فایل‌های بزرگ (ویدئو، سند) حیاتی است تا RAM سرور منفجر نشود.
    """
    telegram_file = await bot.get_file(file_id)
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_BOT_API and telegram_file.file_path and str(telegram_file.file_path).startswith("/"):
        local_path = Path(str(telegram_file.file_path))
        if local_path.exists():
            shutil.copyfile(local_path, dest)
            return str(dest)
    await bot.download_file(telegram_file.file_path, destination=dest)
    return str(dest)


async def convert_video_to_round(input_path: str, output_path: str, progress_callback=None) -> str:
    """تبدیل ویدئو به ویدئو مسیج دایره‌ای تلگرام (video_note) — بدون کپی در حافظه.

    - خروجی: MP4 مربع (640x640) + H.264 + AAC — مناسب send_video_note
    - همه‌ی پردازش روی دیسک انجام می‌شود؛ فقط مسیر فایل‌ها جابه‌جا می‌شود.
    - progress_callback(percent, stage): درصد آماده‌سازی ۰ تا ۱۰۰
    """
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise ValueError("موتور تبدیل ویدئو روی سرور در دسترس نیست")
    input_path = str(input_path)
    output_path = str(output_path)
    if not Path(input_path).exists() or Path(input_path).stat().st_size == 0:
        raise ValueError("فایل ورودی خالی است")
    if progress_callback:
        await progress_callback(5, "در حال بررسی ویدئو")

    # مدت‌زمان ویدئو با ffprobe (برای محاسبه‌ی درصد دقیق)
    duration = 0.0
    try:
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(probe.communicate(), timeout=30)
        duration = float((stdout or b"").decode(errors="ignore").strip() or 0)
    except Exception:
        duration = 0.0
    if duration <= 0:
        duration = 60.0  # اگر نتوانستیم بفهمیم، فرض می‌کنیم ۶۰ ثانیه است

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", input_path, "-t", "60",
        "-vf", (
            "scale=640:640:force_original_aspect_ratio=decrease,"
            "pad=640:640:(ow-iw)/2:(oh-ih)/2:color=black,fps=30"
        ),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k", "-ar", "44100",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        output_path,
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        # stderr به DEVNULL می‌رود تا بافر پر نشود و deadlock رخ ندهد؛
        # در صورت خطا فقط returncode بررسی می‌شود.
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        last_time = 0.0
        async for line in process.stdout:
            try:
                text = line.decode(errors="ignore").strip()
                if text.startswith("out_time_us="):
                    us = int(text.split("=", 1)[1])
                    current = us / 1_000_000
                    if current >= last_time:
                        last_time = current
                        percent = min(95, int(5 + (current / max(duration, 1)) * 90))
                        if progress_callback:
                            await progress_callback(percent, "در حال آماده‌سازی ویدئو")
            except (ValueError, AttributeError):
                pass
        await process.wait()
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise ValueError("تبدیل ویدئو بیش از حد طول کشید") from exc
    if process.returncode != 0 or not Path(output_path).exists():
        raise ValueError("تبدیل ویدئو به دایره‌ای ناموفق بود؛ فرمت ویدئو را بررسی کن")
    if Path(output_path).stat().st_size == 0:
        raise ValueError("خروجی تبدیل ویدئو خالی است")
    if progress_callback:
        await progress_callback(100, "آماده شد")
    return output_path


async def send_gif_result(message: types.Message, media, suffix: str, from_photo: bool = False):
    wait = await message.answer("🎞 دارم گیف تلگرامی می‌سازم؛ چند لحظه صبر کن...")
    try:
        source = io.BytesIO()
        await bot.download(media, destination=source)
        data = await make_telegram_animation(source.getvalue(), suffix, from_photo=from_photo)
        filename = f"ajorpareh-gif-{message.from_user.id}-{int(time.time())}.mp4"
        animation = await message.answer_animation(
            BufferedInputFile(data, filename=filename),
            caption=(
                "🎞 <b>گیف تلگرامی آماده شد!</b>\n\n"
                "روی گیف بزن یا منوی سه‌نقطه را باز کن و <b>Save GIF / ذخیره در گیف‌ها</b> را انتخاب کن."
            ),
            parse_mode="HTML",
        )
        await message.answer_document(
            BufferedInputFile(data, filename=filename),
            caption="📥 فایل MP4 قابل دانلود گیف",
            disable_content_type_detection=True,
        )
        await users_col.update_one(
            {"_id": message.from_user.id},
            {"$inc": {"gifs_created": 1}, "$set": {"last_gif_created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        await wait.edit_text(
            "✅ آماده شد! پیام Animation برای ذخیره در بخش GIFهای تلگرام و فایل دوم برای دانلود مستقیمه."
        )
        return animation
    except Exception as exc:
        log.warning("ساخت گیف ناموفق بود: %s", exc)
        await wait.edit_text(
            "❌ ساخت گیف ناموفق بود. یک عکس، ویدئو یا GIF کمتر از ۱۹ مگابایت بفرست؛ حداکثر ۱۲ ثانیه اول استفاده می‌شه."
        )
        return None


def user_sticker_pack_name(user_id: int, index: int, bot_username: str) -> str:
    username = re.sub(r"[^a-z0-9_]", "", bot_username.lower().lstrip("@"))[:24] or "ajorparehbot"
    return f"ajor_{user_id}_{max(1, index)}_by_{username}"[:64]


async def add_sticker_to_user_pack(user_id: int, data: bytes) -> tuple[str, str, int]:
    bot_info = await bot.get_me()
    user = await users_col.find_one({"_id": user_id}, {"sticker_pack_index": 1}) or {}
    index = max(1, int(user.get("sticker_pack_index", 1) or 1))
    for _ in range(5):
        name = user_sticker_pack_name(user_id, index, bot_info.username or "ajorparehbot")
        sticker_set = None
        try:
            sticker_set = await bot.get_sticker_set(name)
        except TelegramBadRequest as exc:
            if "STICKERSET_INVALID" not in str(exc).upper():
                raise
        if sticker_set and len(sticker_set.stickers) >= 120:
            index += 1
            continue
        input_sticker = InputSticker(
            sticker=BufferedInputFile(data, filename=f"ajorpareh-{user_id}.webp"),
            format="static",
            emoji_list=["✨"],
            keywords=["Ajorpareh", "آجرپاره"],
        )
        if sticker_set is None:
            await bot.create_new_sticker_set(
                user_id=user_id,
                name=name,
                title=f"Ajorpareh | پک {index}",
                stickers=[input_sticker],
                sticker_type="regular",
            )
        else:
            await bot.add_sticker_to_set(user_id=user_id, name=name, sticker=input_sticker)
        updated_set = await bot.get_sticker_set(name)
        if not updated_set.stickers:
            raise RuntimeError("Telegram returned an empty sticker set")
        sticker = updated_set.stickers[-1]
        await users_col.update_one(
            {"_id": user_id},
            {"$set": {
                "sticker_pack_index": index,
                "last_sticker_pack": name,
                "last_sticker_created_at": datetime.now(timezone.utc),
            }, "$inc": {"stickers_created": 1}},
            upsert=True,
        )
        return sticker.file_id, name, len(updated_set.stickers)
    raise RuntimeError("All user sticker packs are full")


async def send_sticker_result(message: types.Message):
    wait = await message.answer("🪄 دارم عکست رو به استیکر تبدیل و به پک تلگرامت اضافه می‌کنم...")
    try:
        source = io.BytesIO()
        await bot.download(message.photo[-1], destination=source)
        data = await asyncio.to_thread(make_sticker_webp, source.getvalue())
        filename = f"ajorpareh-sticker-{message.from_user.id}-{int(time.time())}.webp"
        pack_error = None
        try:
            sticker_file_id, pack_name, pack_count = await add_sticker_to_user_pack(message.from_user.id, data)
            await message.answer_sticker(sticker_file_id)
            pack_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="➕ افزودن/بازکردن پک در تلگرام",
                    url=f"https://t.me/addstickers/{pack_name}",
                )
            ]])
            await message.answer(
                f"✅ استیکر داخل پک واقعی تلگرام ذخیره شد.\n"
                f"تعداد استیکرهای این پک: <b>{pack_count}</b>\n\n"
                "روی دکمه زیر بزن و <b>Add Stickers</b> را انتخاب کن؛ بعد استیکر در بخش استیکرهای تلگرامت می‌مونه.",
                parse_mode="HTML",
                reply_markup=pack_keyboard,
            )
        except Exception as exc:
            pack_error = exc
            log.warning("افزودن استیکر به پک کاربر %s ناموفق بود: %s", message.from_user.id, exc)
            await message.answer_sticker(BufferedInputFile(data, filename=filename))
        await message.answer_document(
            BufferedInputFile(data, filename=filename),
            caption=(
                "📥 <b>فایل قابل دانلود استیکر</b>\n\n"
                "این فایل WEBP را می‌تونی دانلود یا برای ساخت پک‌های دیگر استفاده کنی."
            ),
            parse_mode="HTML",
            disable_content_type_detection=True,
        )
        await wait.edit_text(
            "✅ استیکر آماده شد و داخل پک تلگرام قرار گرفت!"
            if pack_error is None else
            "✅ استیکر و فایل WEBP آماده شدند؛ ساخت پک تلگرام موقتاً انجام نشد، بعداً دوباره امتحان کن."
        )
    except Exception as exc:
        log.warning("ساخت استیکر ناموفق بود: %s", exc)
        await wait.edit_text("❌ ساخت استیکر ناموفق بود؛ یک عکس JPG یا PNG دیگه بفرست.")


class ReplyCallbackAdapter:
    def __init__(self, message: types.Message, data: str):
        self.message = message
        self.from_user = message.from_user
        self.data = data

    async def answer(self, text: str | None = None, show_alert: bool = False, **kwargs):
        if text and show_alert:
            await self.message.answer(text)
        return True


async def run_callback_from_reply(message: types.Message, data: str, handler):
    return await handler(ReplyCallbackAdapter(message, data))


def game_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏃 بزن در رو", callback_data="hit_run_start"),
         InlineKeyboardButton(text="🧠 کوئیز فوری", callback_data="quick_quiz")],
        [InlineKeyboardButton(text="🎲 تاس", callback_data="dice"),
         InlineKeyboardButton(text="🎯 دارت", callback_data="dart")],
        [InlineKeyboardButton(text="🪨 سنگ‌کاغذ‌قیچی", callback_data="rps"),
         InlineKeyboardButton(text="🪙 شیر یا خط", callback_data="coin_flip")],
        [InlineKeyboardButton(text="🔢 حدس عدد", callback_data="guess_game"),
         InlineKeyboardButton(text="🧠 جورچین حافظه", callback_data="mem_start")],
        [InlineKeyboardButton(text="🃏 بیست و یک", callback_data="bj_start")],
        [InlineKeyboardButton(text="🕹 ورود به آرکید کامل", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back_main")],
    ])

def rps_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪨 سنگ", callback_data="rps_stone")],
        [InlineKeyboardButton(text="📄 کاغذ", callback_data="rps_paper")],
        [InlineKeyboardButton(text="✂️ قیچی", callback_data="rps_scissors")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back_game")],
    ])

def coin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 شیر", callback_data="coin_heads")],
        [InlineKeyboardButton(text="🪙 خط", callback_data="coin_tails")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back_game")],
    ])


def hit_run_keyboard(target: int | None = None):
    target = random.randrange(9) if target is None else target
    rows = []
    for row in range(3):
        buttons = []
        for col in range(3):
            position = row * 3 + col
            if position == target:
                buttons.append(InlineKeyboardButton(text="🏃 بزن منو!", callback_data="hit_run_hit"))
            else:
                buttons.append(InlineKeyboardButton(text="·", callback_data="hit_run_miss"))
        rows.append(buttons)
    rows.append([InlineKeyboardButton(text="❌ پایان بازی", callback_data="hit_run_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu():
    maintenance_label = "🟢 ربات فعال" if not runtime_settings.get("maintenance") else "🔴 حالت تعمیرات"
    force_label = "✅ عضویت اجباری" if runtime_settings.get("force_join") else "☑️ عضویت اختیاری"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 داشبورد زنده", callback_data="stats"),
         InlineKeyboardButton(text="📈 گزارش ۷ روزه", callback_data="admin_analytics")],
        [InlineKeyboardButton(text="👥 مدیریت کاربران", callback_data="list_users"),
         InlineKeyboardButton(text="🔎 جستجوی کاربر", callback_data="admin_search_user")],
        [InlineKeyboardButton(text="📡 رصد زنده فعالیت‌ها", callback_data="admin_live_activity"),
         InlineKeyboardButton(text="🕵️ فعالیت یک کاربر", callback_data="admin_activity_user")],
        [InlineKeyboardButton(text="🔥 کاربران فعال امروز", callback_data="admin_active_users"),
         InlineKeyboardButton(text="📥 خروجی CSV", callback_data="admin_export_users")],
        [InlineKeyboardButton(text="🎫 تیکت‌های پشتیبانی", callback_data="admin_tickets")],
        [InlineKeyboardButton(text="📢 پیام همگانی", callback_data="broadcast_menu"),
         InlineKeyboardButton(text="📬 گزارش ارسال‌ها", callback_data="broadcast_history")],
        [InlineKeyboardButton(text="♻️ بازنشر گروهی", callback_data="repost_start"),
         InlineKeyboardButton(text="⚡ انتشار فوری", callback_data="instant_repost_start")],
        [InlineKeyboardButton(text="⏰ پست‌های زمان‌دار", callback_data="scheduled_posts"),
         InlineKeyboardButton(text="✍️ متن دعوت بازنشر", callback_data="repost_cta_settings")],
        [InlineKeyboardButton(text="💰 افزایش موجودی کاربر", callback_data="admin_balance_user"),
         InlineKeyboardButton(text="💸 درخواست‌های برداشت", callback_data="admin_withdrawals")],
        [InlineKeyboardButton(text="💰 تنظیمات اقتصاد", callback_data="economy_settings")],
        [InlineKeyboardButton(text="📊 گزارش مالی و ضدتقلب", callback_data="admin_finance")],
        [InlineKeyboardButton(text="📤 گروه جدید", callback_data="upload_file"),
         InlineKeyboardButton(text="✅ انتشار گروه", callback_data="publish_group")],
        [InlineKeyboardButton(text="📁 مدیریت فایل‌ها", callback_data="manage_groups"),
         InlineKeyboardButton(text="📊 آمار رسانه", callback_data="admin_media_stats")],
        [InlineKeyboardButton(text="🧹 پاکسازی صف رسانه", callback_data="admin_media_cleanup"),
         InlineKeyboardButton(text="🌐 پروکسی/کانفیگ", callback_data="admin_config_panel")],
        [InlineKeyboardButton(text="📈 آمار هوش مصنوعی", callback_data="admin_ai_stats")],
        [InlineKeyboardButton(text="🛡 مدیریت گروه‌ها و کانال‌ها", callback_data="managed_chats"),
         InlineKeyboardButton(text="📣 کانال‌های اجباری", callback_data="admin_required_channels")],
        [InlineKeyboardButton(text="🎟 کدهای جایزه", callback_data="promo_manage"),
         InlineKeyboardButton(text="🎯 مأموریت‌ها", callback_data="mission_manage")],
        [InlineKeyboardButton(text="🎡 قرعه‌کشی‌ها", callback_data="raffle_manage"),
         InlineKeyboardButton(text="📈 پیش‌بینی ترند", callback_data="prediction_manage")],
        [InlineKeyboardButton(text="📝 قالب‌های محتوا", callback_data="template_manage"),
         InlineKeyboardButton(text="🗓 تقویم محتوا", callback_data="scheduled_posts")],
        [InlineKeyboardButton(text="👮 نقش مدیران", callback_data="admin_roles"),
         InlineKeyboardButton(text="📜 گزارش مدیران", callback_data="admin_audit")],
        [InlineKeyboardButton(text="🩺 سلامت ربات", callback_data="admin_health"),
         InlineKeyboardButton(text="💾 پشتیبان‌گیری", callback_data="admin_backup")],
        [InlineKeyboardButton(text=maintenance_label, callback_data="toggle_maintenance"),
         InlineKeyboardButton(text=force_label, callback_data="toggle_force_join")],
        [InlineKeyboardButton(text="📈 پست خودکار نرخ ارز در کانال", callback_data="toggle_auto_rates")],
        [InlineKeyboardButton(text="⭐ تنظیمات پرداخت ستاره", callback_data="admin_stars_settings"),
         InlineKeyboardButton(text="🍷 فال روزانه صبحگاهی", callback_data="toggle_daily_fal")],
        [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="back_main")],
    ])


def required_channels_admin_menu():
    rows = []
    for channel in required_channels_cache:
        chat_id = channel["_id"]
        title = str(channel.get("title") or channel.get("username") or chat_id)[:26]
        rows.append([
            InlineKeyboardButton(text=f"✅ {title}", callback_data=f"reqch_info:{chat_id}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"reqch_delete:{chat_id}"),
        ])
    if not rows:
        rows.append([InlineKeyboardButton(text="— هیچ کانالی ثبت نشده —", callback_data="reqch_noop")])
    gate_label = "🟢 مرحله تعامل فعال" if engagement_gate_cache.get("enabled") else "⚪ مرحله تعامل خاموش"
    rows.extend([
        [InlineKeyboardButton(text="➕ افزودن کانال", callback_data="reqch_add")],
        [InlineKeyboardButton(text=gate_label, callback_data="engagement_config")],
        [InlineKeyboardButton(text="🗑 حذف مرحله تعامل", callback_data="engagement_remove")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 همه کاربران", callback_data="broadcast_all")],
        [InlineKeyboardButton(text="🟢 فعال‌های ۷ روز اخیر", callback_data="broadcast_active")],
        [InlineKeyboardButton(text="🌙 غیرفعال‌ها", callback_data="broadcast_inactive")],
        [InlineKeyboardButton(text="⚡ بالای ۱۰۰۰ امتیاز", callback_data="broadcast_highpoints")],
        [InlineKeyboardButton(text="🎁 بدون رفرال", callback_data="broadcast_noreferral")],
        [InlineKeyboardButton(text="💸 برداشت در انتظار", callback_data="broadcast_pending")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])


def support_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ ثبت پیام برای ادمین", callback_data="support_new")],
        [InlineKeyboardButton(text="❓ راهنمای ربات", callback_data="support_faq"), InlineKeyboardButton(text="📖 معرفی ربات", callback_data="about_bot")],
        [InlineKeyboardButton(text="🎮 ورود به Mini App", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back_main")],
    ])


def truth_dare_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 حقیقت", callback_data="td_truth"),
         InlineKeyboardButton(text="🔥 جرأت", callback_data="td_dare")],
        [InlineKeyboardButton(text="❤️ نسخه کاپلی", callback_data="td_couple"),
         InlineKeyboardButton(text="🎲 شانسی", callback_data="td_random")],
        [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
    ])


def config_type_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ V2Ray", callback_data="get_config_v2ray")],
        [InlineKeyboardButton(text="🌀 NPV (NapsternetV)", callback_data="get_config_npv")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back_main")],
    ])

def admin_config_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 آپلود پروکسی", callback_data="admin_upload_proxy")],
        [InlineKeyboardButton(text="⚡️ آپلود کانفیگ V2Ray", callback_data="admin_upload_v2ray")],
        [InlineKeyboardButton(text="🌀 آپلود کانفیگ NPV", callback_data="admin_upload_npv")],
        [InlineKeyboardButton(text="📋 لیست و حذف موارد", callback_data="admin_config_manage")],
        [InlineKeyboardButton(text="🧹 حذف منقضی‌ها", callback_data="config_purge_expired")],
        [InlineKeyboardButton(text="📊 آمار امروز", callback_data="admin_config_stats")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_panel")],
    ])


def config_manage_categories_menu(counts: dict[str, int] | None = None):
    counts = counts or {}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌐 پروکسی‌ها ({counts.get('proxy', 0)})", callback_data="cfglist:proxy:0")],
        [InlineKeyboardButton(text=f"⚡ V2Ray ({counts.get('v2ray', 0)})", callback_data="cfglist:v2ray:0")],
        [InlineKeyboardButton(text=f"🌀 NPV ({counts.get('npv', 0)})", callback_data="cfglist:npv:0")],
        [InlineKeyboardButton(text="🔙 مدیریت کانفیگ", callback_data="admin_config_panel")],
    ])

def channel_check_menu(channels: list[dict] | None = None):
    channels = required_channels_cache if channels is None else channels
    rows = []
    for index, channel in enumerate(channels, 1):
        title = str(channel.get("title") or channel.get("username") or f"کانال {index}")[:35]
        join_url = channel.get("join_url")
        if join_url:
            rows.append([InlineKeyboardButton(text=f"📢 عضویت در {title}", url=join_url)])
    if engagement_gate_cache.get("enabled") and engagement_gate_cache.get("url"):
        rows.append([InlineKeyboardButton(text="👀 مشاهده پست‌های خواسته‌شده", url=engagement_gate_cache["url"])])
    rows.append([InlineKeyboardButton(text="✅ بررسی عضویت و ادامه", callback_data="check_join")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def engagement_gate_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 بازکردن کانال / پست", url=engagement_gate_cache["url"])],
        [InlineKeyboardButton(text="✅ دیدم و واکنش زدم", callback_data="engagement_done")],
    ])

def wallet_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💱 تبدیل ۱۰۰۰ امتیاز", callback_data="convert_coins")],
        [InlineKeyboardButton(text="💳 کیف پول و برداشت", web_app=WebAppInfo(url=f"{MINI_APP_URL}#profile"))],
        [InlineKeyboardButton(text="🎁 لینک دعوت", callback_data="invite")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="back_main")],
    ])

def get_calc_keyboard(expression=""):
    display_text = expression if expression else "0"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🖥 {display_text}", callback_data="calc_ignore")],
        [
            InlineKeyboardButton(text="C", callback_data="calc_clear"),
            InlineKeyboardButton(text="⌫", callback_data="calc_backspace"),
            InlineKeyboardButton(text="%", callback_data="calc_app_%"),
            InlineKeyboardButton(text="÷", callback_data="calc_app_/"),
        ],
        [
            InlineKeyboardButton(text="7", callback_data="calc_app_7"),
            InlineKeyboardButton(text="8", callback_data="calc_app_8"),
            InlineKeyboardButton(text="9", callback_data="calc_app_9"),
            InlineKeyboardButton(text="×", callback_data="calc_app_*"),
        ],
        [
            InlineKeyboardButton(text="4", callback_data="calc_app_4"),
            InlineKeyboardButton(text="5", callback_data="calc_app_5"),
            InlineKeyboardButton(text="6", callback_data="calc_app_6"),
            InlineKeyboardButton(text="-", callback_data="calc_app_-"),
        ],
        [
            InlineKeyboardButton(text="1", callback_data="calc_app_1"),
            InlineKeyboardButton(text="2", callback_data="calc_app_2"),
            InlineKeyboardButton(text="3", callback_data="calc_app_3"),
            InlineKeyboardButton(text="+", callback_data="calc_app_+"),
        ],
        [
            InlineKeyboardButton(text="00", callback_data="calc_app_00"),
            InlineKeyboardButton(text="0", callback_data="calc_app_0"),
            InlineKeyboardButton(text=".", callback_data="calc_app_."),
            InlineKeyboardButton(text="=", callback_data="calc_calculate"),
        ],
        [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="back_main")],
    ])

async def send_group_files(message: types.Message, group_uuid: str):
    group = await groups_col.find_one({"group_uuid": group_uuid})
    files = await files_col.find({"group_uuid": group_uuid}).sort("uploaded_at", 1).to_list(length=500)
    if not files:
        await message.answer("❌ این گروه فایلی ندارد.")
        return
    title = str((group or {}).get("title") or "فایل‌های اشتراکی")
    await message.answer(f"📂 <b>{html.escape(title)}</b>\n{len(files)} فایل یافت شد؛ در حال ارسال...", parse_mode="HTML")
    for f in files:
        file_id = f["file_id"]
        file_type = f["type"]
        caption = f.get("caption", DEFAULT_CAPTION)
        try:
            if file_type == "photo":
                await message.answer_photo(file_id, caption=caption)
            elif file_type == "video":
                await message.answer_video(file_id, caption=caption)
            else:
                await message.answer_document(file_id, caption=caption)
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"خطا در ارسال فایل {f.get('uuid')}: {e}")
    await message.answer("✅ **همه فایل‌های این گروه ارسال شدند!**")

CONFIG_LABELS = {"proxy": "پروکسی تلگرام", "v2ray": "کانفیگ V2Ray", "npv": "کانفیگ NPV"}
CONFIG_BRAND_LINE = "📣 کانفیگ‌های بروز: @Ajor_pareh"


def sanitize_config_text(content: str) -> str:
    """برندینگ امن کانفیگ بدون خراب‌کردن userinfo یا host پروکسی.

    قبلاً جایگزینی سراسری ``@username`` می‌توانست بخش user@host در
    socks/vless را هم خراب کند؛ حالا فقط remark/متن عادی تغییر می‌کند.
    """
    branded_lines = []
    uri_schemes = r"(?:vless|vmess|trojan|ss|ssr|hysteria2?|tuic|wireguard|npv|socks5?|mtproto|tg)"
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("vmess://"):
            encoded = line[8:].split("#", 1)[0]
            try:
                decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
                data = json.loads(decoded)
                if isinstance(data, dict):
                    data["ps"] = "@Ajor_pareh"
                    for key in ("name", "remark", "remarks"):
                        if key in data:
                            data[key] = "@Ajor_pareh"
                    encoded = base64.b64encode(
                        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
                    ).decode()
                    line = f"vmess://{encoded}"
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        elif re.match(rf"^{uri_schemes}://", line, flags=re.I):
            # user:password@host را نگه می‌داریم و فقط fragment/remark را برند می‌کنیم.
            line = line.split("#", 1)[0] + "#%40Ajor_pareh"
        else:
            line = re.sub(
                r"https?://(?:t\.me|telegram\.me)/(?:s/)?[A-Za-z0-9_]+(?:/\d+)?",
                "https://t.me/Ajor_pareh",
                line,
                flags=re.I,
            )
            line = re.sub(r"(?<![\w@])@[A-Za-z0-9_]{5,}", "@Ajor_pareh", line)
        branded_lines.append(line)
    return "\n".join(branded_lines)


def branded_config_caption(title: str) -> str:
    return f"{title}\n\n{CONFIG_BRAND_LINE}"


async def get_random_config(category: str):
    """یک پروکسی/کانفیگ رندوم از موارد آپلودشده در «همین امروز» (به وقت تهران) برمی‌گرداند."""
    items = await configs_col.find({"category": category, "active": {"$ne": False}, "$or": [{"expires_at": {"$gt": datetime.now(timezone.utc)}}, {"expires_at": {"$exists": False}}]}).sort("uploaded_at",-1).limit(500).to_list(length=500)
    if not items:return None
    item=random.choice(items);await configs_col.update_one({"_id":item["_id"]},{"$inc":{"downloads":1},"$set":{"last_downloaded_at":datetime.now(timezone.utc)}});return item

async def send_config_item(message: types.Message, item: dict, title: str):
    if item.get("content_type") == "document":
        await message.answer_document(item["file_id"], caption=branded_config_caption(title))
    else:
        content = sanitize_config_text(item.get("text", ""))
        await message.answer(f"{branded_config_caption(title)}\n\n<code>{html.escape(content)}</code>", parse_mode="HTML")

async def ensure_user(
    user_id: int,
    name: str,
    referred_by: int | None = None,
    username: str | None = None,
):
    now = datetime.now(timezone.utc)
    now_mono = time.monotonic()
    # کش سریع: اگه کاربر تو ۶۰ ثانیه اخیر چک شده، فقط آپدیت کن
    cached = _user_cache.get(user_id)
    if cached and now_mono - cached[0] < _USER_CACHE_TTL:
        existing = cached[1]
        await users_col.update_one(
            {"_id": user_id},
            {"$set": {"name": name[:120], "username": username, "last_seen": now}},
        )
        return existing
    existing = await users_col.find_one({"_id": user_id})
    _user_cache[user_id] = (now_mono, existing or {})
    if not existing:
        doc = {
            "_id": user_id,
            "name": name[:120],
            "username": username,
            "joined_at": now,
            "last_activity": now,
            "is_banned": False,
            "coins": 0,
            "xp": 0,
            "streak": 0,
            "games_played": 0,
            "games_won": 0,
            "referral_count": 0,
            "referred_by": referred_by,
        }
        await users_col.insert_one(doc)
        return doc
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"name": name[:120], "username": username, "last_seen": now}},
    )
    return existing


async def finalize_referral_reward(user_id: int):
    referred = await users_col.find_one_and_update(
        {"_id": user_id, "referral_pending": True, "referral_rewarded": {"$ne": True}, "referral_captcha_verified": True, "referred_by": {"$type": "number"}},
        {"$set": {"referral_rewarded": True, "referral_pending": False, "referral_completed_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.BEFORE,
    )
    if not referred: return
    referrer_id = referred.get("referred_by")
    if not isinstance(referrer_id, int) or referrer_id == user_id: return
    event_key = f"referral:{referrer_id}:{user_id}"
    try:
        await referral_events_col.insert_one({"_id": event_key, "referrer_id": referrer_id, "referred_user_id": user_id, "risk": referred.get("referral_risk", []), "created_at": datetime.now(timezone.utc)})
    except DuplicateKeyError:
        return
    points = int(economy_settings["referral_points"])
    ai_bonus_each = max(0, min(5, int(economy_settings.get("referral_ai_text_bonus", 1))))
    ai_bonus_cap = max(
        0,
        min(ai_service.config.max_referral_text_bonus, int(economy_settings.get("referral_ai_bonus_cap", 10))),
    )
    referrer_before = await users_col.find_one_and_update(
        {"_id": referrer_id},
        [{"$set": {
            "xp": {"$add": [{"$ifNull": ["$xp", 0]}, points]},
            "referral_count": {"$add": [{"$ifNull": ["$referral_count", 0]}, 1]},
            "ai_referral_text_bonus": {
                "$min": [
                    ai_bonus_cap,
                    {"$add": [{"$ifNull": ["$ai_referral_text_bonus", 0]}, ai_bonus_each]},
                ]
            },
            "last_referral_at": datetime.now(timezone.utc),
        }}],
        return_document=ReturnDocument.BEFORE,
    )
    previous_ai_bonus = int((referrer_before or {}).get("ai_referral_text_bonus", 0) or 0)
    ai_bonus_awarded = max(0, min(ai_bonus_each, ai_bonus_cap - previous_ai_bonus))
    await referral_events_col.update_one(
        {"_id": event_key},
        {"$set": {"ai_text_daily_bonus": ai_bonus_awarded, "ai_text_bonus_cap": ai_bonus_cap}},
    )
    await users_col.update_one({"_id": user_id}, {"$inc": {"xp": 25}})
    inviter_coin = await apply_coin_transaction(referrer_id, int(economy_settings["referrer_coins"]), "referral_inviter", f"coin:{event_key}:inviter", {"referred_user_id": user_id}, apply_multiplier=True)
    invited_coin = await apply_coin_transaction(user_id, int(economy_settings["referred_coins"]), "referral_invited", f"coin:{event_key}:invited", {"referrer_id": referrer_id}, apply_multiplier=True)
    await record_score_event(referrer_id, points, "referral", f"score:{event_key}:inviter")
    await record_score_event(user_id, 25, "referral_welcome", f"score:{event_key}:invited")
    try:
        ai_bonus_line = (
            f"\n🤖 سهمیه روزانه هوش مصنوعی: <b>+{ai_bonus_awarded} پیام</b>"
            if ai_bonus_awarded > 0 else ""
        )
        download_bonus_line = f"\n🎟 سهمیه دانلود: <b>+{DOWNLOAD_TOKENS_PER_REFERRAL} توکن در هر ۲۴ ساعت</b>"
        await bot.send_message(
            referrer_id,
            f"🎉 رفرال تأیید شد؛ <b>{points} امتیاز</b> و <b>{inviter_coin.get('amount', 0)} سکه</b> گرفتی!{ai_bonus_line}{download_bonus_line}",
            parse_mode="HTML",
        )
        await bot.send_message(user_id, f"🎁 خوش اومدی! <b>۲۵ امتیاز</b> و <b>{invited_coin.get('amount', 0)} سکه</b> هدیه شروع گرفتی.", parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


async def reward_referrer_once(user_id: int):
    user = await users_col.find_one({"_id": user_id}) or {}
    if not user.get("referral_pending") or user.get("referral_rewarded"): return
    if user.get("referral_captcha_verified"):
        return await finalize_referral_reward(user_id)
    risk = []
    if not user.get("username"): risk.append("no_username")
    joined = user.get("joined_at")
    if isinstance(joined, datetime):
        if joined.tzinfo is None: joined = joined.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - joined < timedelta(seconds=30): risk.append("too_fast")
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count == 0: risk.append("no_profile_photo")
    except (TelegramBadRequest, TelegramForbiddenError):
        risk.append("profile_check_failed")
    if "no_username" in risk:
        await users_col.update_one({"_id": user_id}, {"$set": {"referral_risk": risk}})
        try: await bot.send_message(user_id, "⚠️ برای دریافت پاداش رفرال، ابتدا در تنظیمات تلگرام یک Username بساز و دوباره /start بزن.")
        except Exception: pass
        return
    left, right = random.randint(2, 9), random.randint(2, 9); answer = left + right
    choices = {answer}
    while len(choices) < 4: choices.add(max(1, answer + random.choice([-5, -3, -2, 2, 3, 5])))
    options = list(choices); random.shuffle(options)
    await users_col.update_one({"_id": user_id}, {"$set": {"referral_risk": risk, "referral_captcha_answer": answer, "referral_captcha_expires": datetime.now(timezone.utc) + timedelta(minutes=10), "referral_captcha_attempts": 0}})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(value), callback_data=f"refcaptcha:{value}") for value in options[:2]], [InlineKeyboardButton(text=str(value), callback_data=f"refcaptcha:{value}") for value in options[2:]]])
    try: await bot.send_message(user_id, f"🧩 برای فعال‌شدن پاداش دوطرفه رفرال جواب بده:\n<b>{left} + {right} = ؟</b>", reply_markup=keyboard, parse_mode="HTML")
    except Exception: pass


@dp.callback_query(F.data.startswith("refcaptcha:"))
async def referral_captcha_callback(callback: types.CallbackQuery):
    try: selected = int(callback.data.split(":", 1)[1])
    except ValueError: return await callback.answer("پاسخ نامعتبر.", show_alert=True)
    user = await users_col.find_one({"_id": callback.from_user.id}) or {}; expires = user.get("referral_captcha_expires")
    if expires and expires.tzinfo is None: expires = expires.replace(tzinfo=timezone.utc)
    if not expires or expires < datetime.now(timezone.utc): return await callback.answer("کپچا منقضی شد؛ /start را دوباره بزن.", show_alert=True)
    if selected != int(user.get("referral_captcha_answer", -1)):
        attempts = int(user.get("referral_captcha_attempts", 0)) + 1
        await users_col.update_one({"_id": callback.from_user.id}, {"$set": {"referral_captcha_attempts": attempts}})
        return await callback.answer("جواب اشتباهه؛ دوباره تلاش کن." if attempts < 3 else "تلاش زیاد بود؛ ۱۰ دقیقه بعد دوباره امتحان کن.", show_alert=True)
    await users_col.update_one({"_id": callback.from_user.id}, {"$set": {"referral_captcha_verified": True}, "$unset": {"referral_captcha_answer": "", "referral_captcha_expires": ""}})
    await callback.message.edit_text("✅ کپچا تأیید شد؛ پاداش رفرال در حال ثبت است.")
    await finalize_referral_reward(callback.from_user.id)
    await callback.answer("تأیید شد 🎉")


async def reward_sponsor_channels(user_id: int):
    for channel in required_channels_cache:
        reward = int(channel.get("sponsor_reward", economy_settings["sponsor_join_coins"]))
        if reward <= 0: continue
        key = f"sponsor:{channel['_id']}:{user_id}"
        try: await sponsor_rewards_col.insert_one({"_id": key, "user_id": user_id, "channel_id": channel["_id"], "reward": reward, "created_at": datetime.now(timezone.utc)})
        except DuplicateKeyError: continue
        await apply_coin_transaction(user_id, reward, "sponsor_join", f"coin:{key}", {"channel_id": channel["_id"]}, apply_multiplier=True)


async def send_onboarding_welcome(message: types.Message, user: types.User | None = None) -> None:
    actor = user or message.from_user
    name = html.escape(actor.full_name or "رفیق")
    await message.answer(
        f"👋 <b>{name}، به Ajorpareh خوش اومدی!</b>\n\n"
        "اینجا فقط یه ربات ساده نیست؛ یک سوپرربات فارسیه با:\n"
        "🤖 هوش مصنوعی و ساخت تصویر · 📥 دانلود Instagram/TikTok/YouTube · 🔗 آپلود فایل از URL\n"
        "🎮 بازی و چالش · 🎙 ویس به متن · 🎨 گیف و استیکرساز · ⏰ یادآور\n"
        "📰 خبر زنده و سرگرمی · 🛍 سرویس اختصاصی · 💰 کیف پول و جایزه\n\n"
        "👇 <b>قدم اول برای فعال‌شدن منو:</b>\n"
        "دکمهٔ منو/کیبورد کنار کادر پیام (☰ یا چهارخانه) رو بزن و یکی از گزینه‌ها رو انتخاب کن. "
        "اگر منو رو ندیدی، فقط <code>/menu</code> بفرست.",
        parse_mode="HTML",
        reply_markup=chat_reply_menu(actor.id),
    )
    await users_col.update_one(
        {"_id": actor.id},
        {"$set": {"onboarding_shown": True, "onboarding_shown_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def handle_menu_trigger(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name

    await ensure_user(user_id, name, username=message.from_user.username)

    if await is_banned(user_id):
        return await message.answer("🚫 شما از ربات بن شده‌اید.")

    await log_activity(user_id, "menu", "درخواست منو")

    if not await is_member(user_id):
        await message.answer("👋 سلام فدات شم!\nبرای استفاده از ربات، مراحل عضویت زیر رو کامل کن:", reply_markup=channel_check_menu())
        return

    await message.answer(
        f"🚀 سلام {name} عزیز!\nمنوی اصلی همیشه پایین چت در دسترسه؛ یکی از گزینه‌ها رو انتخاب کن 👇",
        reply_markup=chat_reply_menu(message.from_user.id),
    )

@dp.message(Command("menu"))
async def menu_command(message: types.Message):
    await handle_menu_trigger(message)


@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    text_parts = message.text.split()

    referrer_id = None
    if len(text_parts) > 1 and text_parts[1].startswith("ref_"):
        try:
            referrer_id = int(text_parts[1].split("_")[1])
        except (IndexError, ValueError):
            pass

    existing_user = await users_col.find_one({"_id": user_id})
    is_new = not existing_user
    await ensure_user(user_id, name, referrer_id, message.from_user.username)

    if is_new and referrer_id and referrer_id != user_id:
        await users_col.update_one({"_id": user_id}, {"$set": {"referral_pending": True}})

    if await is_banned(user_id):
        return await message.answer("🚫 شما از ربات بن شده‌اید.")

    if len(text_parts) > 1:
        if text_parts[1].startswith("support"):
            support_sessions.add(user_id)
            await message.answer(
                "💬 پیام پشتیبانی یا گزارش خطات رو در یک پیام بفرست.\n"
                f"آیدی شما برای پیگیری: <code>{user_id}</code>\n"
                "پیام مستقیم برای مدیر ارسال می‌شود. برای انصراف /cancel",
                parse_mode="HTML",
            )
            return
        if text_parts[1] == "iran_playlist":
            await show_public_music_playlist(message, 0, admin=is_admin(user_id))
            return
        if text_parts[1] in {"midnight_greeting", "morning_greeting"}:
            if is_admin(user_id):
                await show_scheduled_greeting_control(message, "midnight" if text_parts[1].startswith("midnight") else "morning")
            else:
                await message.answer("🌅 این دو زمان‌بندی برای مدیریت مقصد و جمله‌ها داخل ربات مدیر فعال هستند.", reply_markup=tools_reply_menu())
            return
        if text_parts[1] == "daily_music":
            if is_admin(user_id):
                await show_daily_music_control(message)
            else:
                await show_public_music_playlist(message, 0)
            return
        if text_parts[1] == "daily_fal":
            await fal_command(message)
            return
        if text_parts[1].startswith("song_"):
            query = text_parts[1][len("song_"):].strip()
            if query and not await is_banned(user_id):
                await message.answer(f"🔎 در حال جستجوی «{html.escape(query[:80])}»…", parse_mode="HTML")
                return await present_music_results(user_id, query)
        if text_parts[1].startswith("group_"):
            group_uuid = text_parts[1].split("_", 1)[1]
            if not await is_member(user_id):
                await message.answer("👋 سلام عزیزم!\nبرای دریافت فایل‌ها اول مراحل عضویت رو کامل کن:", reply_markup=channel_check_menu())
                return
            await groups_col.update_one({"group_uuid": group_uuid}, {"$inc": {"views": 1}})
            await send_group_files(message, group_uuid)
            return

        if text_parts[1].startswith("file_"):
            file_uuid = text_parts[1].split("_", 1)[1]
            file_data = await files_col.find_one({"uuid": file_uuid})
            if file_data:
                if not await is_member(user_id):
                    await message.answer("👋 سلام عزیزم!\nبرای دریافت این فایل، اول مراحل عضویت رو کامل کن:", reply_markup=channel_check_menu())
                    return
                file_id = file_data["file_id"]
                file_type = file_data["type"]
                caption = file_data.get("caption", DEFAULT_CAPTION)
                if file_type == "photo":
                    await message.answer_photo(file_id, caption=caption)
                elif file_type == "video":
                    await message.answer_video(file_id, caption=caption)
                else:
                    await message.answer_document(file_id, caption=caption)
                return
            else:
                await message.answer("❌ فایل مورد نظر یافت نشد.")
                return

    await log_activity(user_id, "start", "استارت ربات")

    if not await is_member(user_id):
        await message.answer("👋 سلام فدات شم!\nبرای استفاده از ربات، مراحل عضویت زیر رو کامل کن:", reply_markup=channel_check_menu())
        return

    await reward_sponsor_channels(user_id)
    await reward_referrer_once(user_id)
    current_user = await users_col.find_one({"_id": user_id}, {"onboarding_shown": 1}) or {}
    if is_new or not current_user.get("onboarding_shown"):
        await send_onboarding_welcome(message)
    else:
        await message.answer(
            f"🚀 سلام {name} عزیز! خوش برگشتی؛ منوی دائمی پایین چت آماده‌ست 👇",
            reply_markup=chat_reply_menu(message.from_user.id),
        )

@dp.callback_query(F.data == "check_join")
async def check_join(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    missing = await get_missing_channels(user_id)
    if missing:
        await callback.message.answer(
            f"❌ هنوز عضو {len(missing)} کانال نشدی. اول از دکمه‌های زیر عضو شو:",
            reply_markup=channel_check_menu(missing),
        )
        return await callback.answer("عضویت همه کانال‌ها کامل نشده.", show_alert=True)

    await reward_sponsor_channels(user_id)
    if not await has_completed_engagement(user_id):
        gate = engagement_gate_cache
        await users_col.update_one(
            {"_id": user_id},
            {"$set": {
                "engagement_gate_opened_at": datetime.now(timezone.utc),
                "engagement_gate_opened_version": gate["version"],
            }},
            upsert=True,
        )
        await callback.message.answer(
            "✅ عضویت کانال‌ها تأیید شد.\n\n"
            f"👀 <b>مرحله آخر:</b> {html.escape(gate.get('instruction', 'پست‌های کانال را ببین.'))}\n\n"
            f"حداقل {gate.get('wait_seconds', 15)} ثانیه داخل کانال بمان، بعد برگرد و دکمه تأیید را بزن.",
            reply_markup=engagement_gate_menu(),
            parse_mode="HTML",
        )
        return await callback.answer("عضویت تأیید شد؛ مرحله آخر رو انجام بده 👀")

    await reward_referrer_once(user_id)
    await callback.message.edit_text("✅ همه مراحل تأیید شد؛ خوش اومدی!")
    user_state = await users_col.find_one({"_id": user_id}, {"onboarding_shown": 1}) or {}
    if not user_state.get("onboarding_shown"):
        await send_onboarding_welcome(callback.message, callback.from_user)
    else:
        await callback.message.answer("🚀 منوی اصلی پایین چت فعال شد:", reply_markup=chat_reply_menu(user_id))
    await callback.answer("تأیید شد ✅")


async def track_reward_channel_reaction(event: types.MessageReactionUpdated, user: types.User) -> None:
    if event.chat.id != CHANNEL_ID:
        return
    key = f"reaction:{event.chat.id}:{event.message_id}:{user.id}"
    if event.new_reaction:
        latest = await channel_posts_col.find({}, {"_id": 1}).sort("_id", -1).limit(5).to_list(length=5)
        if event.message_id not in {int(item["_id"]) for item in latest}:
            return
        try:
            await channel_reaction_events_col.insert_one({
                "_id": key,
                "user_id": user.id,
                "chat_id": event.chat.id,
                "message_id": event.message_id,
                "created_at": datetime.now(timezone.utc),
            })
        except DuplicateKeyError:
            return
        await users_col.update_one(
            {"_id": user.id},
            {"$inc": {"channel_reaction_count": 1}, "$set": {"last_channel_reaction_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    else:
        removed = await channel_reaction_events_col.delete_one({"_id": key})
        if removed.deleted_count:
            await users_col.update_one(
                {"_id": user.id, "channel_reaction_count": {"$gt": 0}},
                {"$inc": {"channel_reaction_count": -1}},
            )


@dp.message_reaction()
async def required_channel_reaction(event: types.MessageReactionUpdated):
    """واکنش‌های مأموریت را ثبت می‌کند و در صورت نیاز گیت عضویت را هم تکمیل می‌کند."""
    user = event.user
    if not user:
        return
    await track_reward_channel_reaction(event, user)
    gate = engagement_gate_cache
    if not event.new_reaction or not gate.get("enabled") or not gate.get("version"):
        return
    if event.chat.id not in {channel["_id"] for channel in required_channels_cache}:
        return
    if await get_missing_channels(user.id):
        return
    await users_col.update_one(
        {"_id": user.id},
        {"$set": {
            "engagement_gate_version": gate["version"],
            "engagement_completed_at": datetime.now(timezone.utc),
            "engagement_reaction_chat_id": event.chat.id,
            "engagement_reaction_message_id": event.message_id,
        }},
        upsert=True,
    )
    await reward_referrer_once(user.id)
    await log_activity(user.id, "engagement_reaction_verified", f"chat={event.chat.id},message={event.message_id}")
    try:
        await bot.send_message(
            user.id,
            "✅ واکنشت در کانال ثبت شد و دسترسی ربات باز شد! منو پایین چت آماده‌ست.",
            reply_markup=chat_reply_menu(user.id),
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


@dp.callback_query(F.data == "engagement_done")
async def engagement_done_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    missing = await get_missing_channels(user_id)
    if missing:
        return await callback.answer("اول عضویت همه کانال‌ها رو کامل کن.", show_alert=True)
    gate = engagement_gate_cache
    if not gate.get("enabled") or not gate.get("version"):
        await callback.message.answer("🚀 منوی اصلی پایین چت فعال شد:", reply_markup=chat_reply_menu(user_id))
        return await callback.answer("مرحله تعامل غیرفعاله؛ خوش اومدی ✅")
    if await has_completed_engagement(user_id):
        await callback.message.answer("🚀 دسترسی قبلاً تأیید شده:", reply_markup=main_menu(user_id))
        return await callback.answer("واکنشت تأیید شده بود ✅")
    user = await users_col.find_one(
        {"_id": user_id},
        {"engagement_gate_opened_at": 1, "engagement_gate_opened_version": 1},
    ) or {}
    opened_at = user.get("engagement_gate_opened_at")
    if not opened_at or user.get("engagement_gate_opened_version") != gate["version"]:
        await users_col.update_one(
            {"_id": user_id},
            {"$set": {"engagement_gate_opened_at": datetime.now(timezone.utc), "engagement_gate_opened_version": gate["version"]}},
            upsert=True,
        )
        return await callback.answer("اول کانال رو باز کن؛ چند ثانیه بعد برگرد.", show_alert=True)
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - opened_at).total_seconds()
    wait_seconds = int(gate.get("wait_seconds", 15))
    if elapsed < wait_seconds:
        return await callback.answer(f"هنوز زوده؛ {max(1, wait_seconds - int(elapsed))} ثانیه دیگه برگرد.", show_alert=True)
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"engagement_gate_version": gate["version"], "engagement_completed_at": datetime.now(timezone.utc)}},
    )
    await reward_referrer_once(user_id)
    await log_activity(user_id, "engagement_gate_completed", str(gate["version"]))
    await callback.message.edit_text("✅ عضویت و مرحله مشاهده پست‌ها تأیید شد!")
    user_state = await users_col.find_one({"_id": user_id}, {"onboarding_shown": 1}) or {}
    if not user_state.get("onboarding_shown"):
        await send_onboarding_welcome(callback.message, callback.from_user)
    else:
        await callback.message.answer("🚀 حالا همه امکانات برات بازه:", reply_markup=chat_reply_menu(user_id))
    await callback.answer("دسترسی کامل شد 🎉")

@dp.callback_query(F.data == "invite")
async def invite_callback(callback: types.CallbackQuery):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    points = int(economy_settings["referral_points"])
    await callback.message.answer(
        f"🎁 <b>لینک دعوت اختصاصی شما:</b>\n\n<code>{link}</code>\n\n"
        f"به‌ازای هر کاربر واقعی که مراحل عضویت و ضدتقلب را کامل کند:\n"
        f"⚡ <b>{points} امتیاز</b> · 🪙 سکه · 🤖 <b>+{int(economy_settings['referral_ai_text_bonus'])} پیام AI روزانه</b>\n"
        f"🎟 <b>+{DOWNLOAD_TOKENS_PER_REFERRAL} توکن دانلود در هر ۲۴ ساعت</b> برای هر دعوت موفق\n"
        f"سقف هدیه رفرال AI: <b>+{int(economy_settings['referral_ai_bonus_cap'])} پیام</b>\n"
        f"حداقل تبدیل به کیف پول: <b>{economy_settings['min_convert_points']} امتیاز</b>",
        parse_mode="HTML",
    )
    await callback.answer()

@dp.callback_query(F.data == "daily_reward")
async def daily_reward_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await users_col.find_one({"_id": user_id}) or {}
    if user.get("daily_reward_date") == today_str():
        return await callback.answer("جایزه امروزت رو گرفتی؛ فردا دوباره بیا! 🔥", show_alert=True)

    previous_streak = int(user.get("streak", 0))
    streak = previous_streak + 1 if user.get("daily_reward_date") == yesterday_str() else 1
    cycle_day = ((streak - 1) % 7) + 1
    xp_reward = min(20 + cycle_day * 5, 75)
    coin_schedule = [10, 15, 25, 40, 60, 90, 140]
    result = await users_col.update_one(
        {"_id": user_id, "daily_reward_date": {"$ne": today_str()}},
        {"$set": {"daily_reward_date": today_str(), "streak": streak}, "$inc": {"xp": xp_reward}},
    )
    if result.modified_count == 0:
        return await callback.answer("جایزه امروز قبلاً ثبت شده است.", show_alert=True)
    coin_tx = await apply_coin_transaction(user_id, coin_schedule[cycle_day - 1], "daily_checkin", f"daily:{user_id}:{today_str()}", {"streak": streak, "cycle_day": cycle_day}, apply_multiplier=True)
    await record_score_event(user_id, xp_reward, "daily_checkin", f"score:daily:{user_id}:{today_str()}")
    await callback.message.answer(
        f"🎁 جایزه روز {cycle_day} از چرخه هفت‌روزه رو گرفتی!\n\n"
        f"⚡ +{xp_reward} امتیاز\n🪙 +{coin_tx.get('amount', 0)} سکه\n🔥 استریک فعلی: {streak} روز\n"
        f"فردا جایزه پایه: {coin_schedule[cycle_day] if cycle_day < 7 else coin_schedule[0]} سکه"
    )
    await log_activity(user_id, "daily_reward", f"streak={streak}, xp={xp_reward}, coins={coin_tx.get('amount', 0)}")
    await callback.answer("جایزه اضافه شد! 🎉")


@dp.callback_query(F.data == "leaderboard")
async def leaderboard_callback(callback: types.CallbackQuery):
    leaders = await users_col.find(
        {"is_banned": {"$ne": True}},
        {"name": 1, "username": 1, "xp": 1, "games_won": 1},
    ).sort([("xp", -1), ("games_won", -1)]).limit(10).to_list(length=10)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>جدول خفن‌های Ajorpareh</b>", ""]
    for index, user in enumerate(leaders, 1):
        badge = medals[index - 1] if index <= 3 else f"{index}."
        name = html.escape(user.get("name") or "بازیکن ناشناس")
        lines.append(f"{badge} {name} — <b>{int(user.get('xp', 0)):,} XP</b>")
    me = await users_col.find_one({"_id": callback.from_user.id}) or {}
    higher = await users_col.count_documents({"xp": {"$gt": int(me.get("xp", 0))}, "is_banned": {"$ne": True}})
    lines.extend(["", f"📍 رتبه تو: <b>#{higher + 1}</b> · {int(me.get('xp', 0)):,} XP"])
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "mood_meter")
async def mood_meter_callback(callback: types.CallbackQuery):
    seed = f"{callback.from_user.id}:{today_str()}"
    index = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(MOOD_RESULTS)
    score = 70 + (int(hashlib.sha256(f"mood:{seed}".encode()).hexdigest(), 16) % 30)
    await callback.message.answer(
        f"🎭 <b>حال‌سنج امروزت</b>\n\n{MOOD_RESULTS[index]}\n\nشاخص حال خوب: <b>{score}%</b>",
        parse_mode="HTML",
    )
    await log_activity(callback.from_user.id, "mood_meter", f"score={score}")
    await callback.answer("اسکن مود کامل شد ✨")


@dp.callback_query(F.data == "quick_quiz")
async def quick_quiz_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    recent = quick_quiz_recent.get(user_id, [])
    available = [index for index in range(len(QUIZ_QUESTIONS)) if index not in recent]
    if not available:
        recent = []
        available = list(range(len(QUIZ_QUESTIONS)))
    question_index = random.choice(available)
    recent.append(question_index)
    quick_quiz_recent[user_id] = recent[-min(30, len(QUIZ_QUESTIONS) - 1):]
    question, options, correct, explanation = QUIZ_QUESTIONS[question_index]
    await callback.message.answer_poll(
        question=question,
        options=options,
        type="quiz",
        correct_option_id=correct,
        explanation=explanation,
        is_anonymous=False,
    )
    await record_game(callback.from_user.id, "quiz", False, 5)
    await callback.answer()


@dp.callback_query(F.data == "caption_maker")
async def caption_maker_callback(callback: types.CallbackQuery):
    caption_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "✨ <b>کپشن‌ساز وایرال</b>\n\nموضوع عکس یا پستت رو کوتاه بفرست؛ مثلاً:\n"
        "<code>سفر شمال با رفیقا</code>\n\nمن برات کپشن محاوره‌ای، ایموجی و هشتگ می‌سازم. برای انصراف /cancel",
        parse_mode="HTML",
    )
    await callback.answer("موضوع پستت رو بفرست ✨")


@dp.callback_query(F.data == "truth_dare")
async def truth_dare_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "🎭 <b>جرأت یا حقیقت؟</b>\n\nانتخاب کن؛ پیچوندن هم نداریم! 😏",
        reply_markup=truth_dare_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.in_({"td_truth", "td_dare", "td_random", "td_couple"}))
async def truth_dare_play(callback: types.CallbackQuery):
    choice = callback.data
    if choice == "td_random":
        choice = random.choice(["td_truth", "td_dare", "td_couple"])
    if choice == "td_couple":
        if random.random() < 0.5:
            title, prompt = "💬 حقیقت کاپلی ❤️", random.choice(COUPLE_TRUTH)
        else:
            title, prompt = "🔥 جرأت کاپلی ❤️", random.choice(COUPLE_DARE)
    elif choice == "td_truth":
        title, prompt = "💬 حقیقت", random.choice(TRUTH_QUESTIONS)
    else:
        title, prompt = "🔥 جرأت", random.choice(DARE_CHALLENGES)
    await callback.message.answer(
        f"{title}\n\n<b>{html.escape(prompt)}</b>",
        reply_markup=truth_dare_menu(),
        parse_mode="HTML",
    )
    await log_activity(callback.from_user.id, choice, prompt)
    await callback.answer("انتخاب شد! 🎲")


def about_bot_text() -> str:
    return (
        "👾 <b>Ajorpareh؛ سوپرربات سرگرمی و ابزارهای تلگرام</b>\n\n"
        "🎮 بازی‌ها: بزن‌دررو، حدس عدد، سنگ‌کاغذقیچی، تاس، دارت، شیر یا خط و Mini App\n"
        "🧠 کوئیز، جرأت یا حقیقت، حال‌سنج و کپشن‌ساز وایرال\n"
        "🤖 چت هوشمند، ساخت/ویرایش تصویر، تحلیل عکس، ترجمه، خلاصه، کمک درسی و برنامه‌نویسی\n"
        "🎙 تبدیل ویس به متن و ⏰ یادآور شخصی در ربات و Mini App\n"
        "📰 خبر روز، جوک و جملات انگیزشی\n"
        "🎬 دانلود ویدئوی یوتیوب\n🌐 دریافت Proxy، V2Ray و NPV برندشده\n"
        "🎁 رفرال: امتیاز، سکه و سهمیه روزانه بیشتر برای AI\n💰 کیف پول، تبدیل امتیاز به تومان و برداشت کارت/USDT\n"
        "👤 پروفایل، رتبه‌بندی، XP، استریک و جایزه روزانه\n💬 پشتیبانی و ثبت گزارش خطا\n\n"
        "دستورات سریع:\n/start · /menu · /app · /ai · /voice · /remind · /reminders · /games · /profile · /joke · /quote · /caption · /truth · /help\n\n"
        "حالا چطور می‌تونم کمکت کنم؟ 😎"
    )


@dp.callback_query(F.data == "about_bot")
async def about_bot_callback(callback: types.CallbackQuery):
    await callback.message.answer(about_bot_text(), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_main")]]), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "💬 <b>مرکز پشتیبانی Ajorpareh</b>\n\nهمه گزینه‌های پشتیبانی در منوی پایین چت باز شدند.",
        reply_markup=support_reply_menu(), parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("review:"))
async def review_moderation_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "support"):
        return await callback.answer("⛔ دسترسی بررسی نظرها را نداری.", show_alert=True)
    try:
        _, action, review_id = callback.data.split(":", 2)
    except ValueError:
        return await callback.answer("درخواست نامعتبر است.", show_alert=True)
    if action not in {"approve", "reject"} or not re.fullmatch(r"[a-f0-9]{12}", review_id):
        return await callback.answer("درخواست نامعتبر است.", show_alert=True)
    review = await reviews_col.find_one_and_update(
        {"_id": review_id, "status": "pending"},
        {"$set": {
            "status": "published" if action == "approve" else "rejected",
            "reviewed_at": datetime.now(timezone.utc),
            "published_at": datetime.now(timezone.utc) if action == "approve" else None,
            "reviewed_by": callback.from_user.id,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not review:
        return await callback.answer("این نظر قبلاً بررسی شده.", show_alert=True)
    try:
        await bot.send_message(
            review["user_id"],
            "✅ نظرت تأیید و منتشر شد. ممنون که کمک کردی Ajorpareh بهتر بشه!"
            if action == "approve" else
            "ℹ️ نظرت بررسی شد اما برای نمایش عمومی تأیید نشد. می‌تونی فردا نظر تازه‌ای ثبت کنی.",
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    await audit_admin_action(callback.from_user.id, f"review_{action}", review_id, str(review["user_id"]))
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer("منتشر شد ✅" if action == "approve" else "رد شد", show_alert=True)


@dp.callback_query(F.data == "support_faq")
async def support_faq_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "❓ <b>راهنمای سریع</b>\n\n"
        "• بازی باز نمی‌شود؟ تلگرام را بروزرسانی کن و Mini App را دوباره باز کن.\n"
        "• امتیاز ثبت نشد؟ زمان بازی و نوع بازی را برای پشتیبانی بفرست.\n"
        "• استریک با دریافت جایزه روزانه حفظ می‌شود.\n"
        "• برای لغو هر عملیات /cancel را بفرست.",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "support_new")
async def support_new_callback(callback: types.CallbackQuery):
    support_sessions.add(callback.from_user.id)
    await callback.message.answer("✍️ پیام، پیشنهاد یا گزارش باگت رو در یک پیام بفرست. برای انصراف /cancel")
    await callback.answer()


@dp.callback_query(F.data == "wallet")
async def wallet_callback(callback: types.CallbackQuery):
    data = await wallet_snapshot(callback.from_user.id)
    await callback.message.answer(
        "💳 <b>کیف پول شما</b>\n\n"
        f"⚡ امتیاز: <b>{data['points']:,}</b>\n"
        f"💵 موجودی: <b>{data['wallet_toman']:,} تومان</b>\n"
        f"🎁 رفرال موفق: <b>{data['referral_count']}</b>\n\n"
        f"هر امتیاز {data['point_toman_rate']:,} تومان · حداقل تبدیل {data['min_convert_points']:,} امتیاز",
        reply_markup=wallet_menu(), parse_mode="HTML",
    )
    await callback.answer()

@dp.callback_query(F.data == "convert_coins")
async def convert_coins_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    points = int(economy_settings["min_convert_points"])
    amount = points * int(economy_settings["point_toman_rate"])
    result = await users_col.update_one({"_id": user_id, "xp": {"$gte": points}}, {"$inc": {"xp": -points, "wallet_toman": amount}})
    if not result.modified_count:
        return await callback.answer(f"حداقل {points:,} امتیاز لازم داری.", show_alert=True)
    await wallet_transactions_col.insert_one({"user_id": user_id, "type": "points_to_toman", "points": -points, "amount_toman": amount, "rate": economy_settings["point_toman_rate"], "created_at": datetime.now(timezone.utc)})
    await callback.message.answer(f"✅ {points:,} امتیاز تبدیل شد و {amount:,} تومان به کیف پولت اضافه شد.", reply_markup=wallet_menu())
    await callback.answer("تبدیل انجام شد ✅")

@dp.callback_query(F.data == "profile_user")
async def profile_user_callback(callback: types.CallbackQuery):
    user = callback.from_user
    db_user = await users_col.find_one({"_id": user.id}) or {}
    wallet_toman = int(db_user.get("wallet_toman", 0))
    xp = int(db_user.get("xp", 0))
    games = int(db_user.get("games_played", 0))
    wins = int(db_user.get("games_won", 0))
    win_rate = round(wins * 100 / games) if games else 0
    higher = await users_col.count_documents({"xp": {"$gt": xp}, "is_banned": {"$ne": True}})
    await callback.message.answer(
        f"👤 <b>{html.escape(user.full_name)}</b>\n"
        f"🆔 <code>{user.id}</code>\n\n"
        f"⚡ XP: <b>{xp:,}</b>\n🏆 رتبه: <b>#{higher + 1}</b>\n"
        f"🎮 بازی‌ها: {games} · برد: {wins} ({win_rate}٪)\n"
        f"🔥 استریک: {int(db_user.get('streak', 0))} روز\n"
        f"💵 کیف پول: {wallet_toman:,} تومان · دعوت موفق: {int(db_user.get('referral_count', 0))}",
        parse_mode="HTML",
    )
    await callback.answer()

@dp.callback_query(F.data == "open_calc")
async def open_calculator(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    user_id = callback.from_user.id
    calculator_sessions[user_id] = ""
    await callback.message.edit_text("🧮 **ماشین حساب پیشرفته و جذاب**\n\nاز دکمه‌های زیر برای محاسبه استفاده کنید:", reply_markup=get_calc_keyboard(""))
    await callback.answer()

@dp.callback_query(F.data.startswith("calc_"))
async def calculator_actions(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data.replace("calc_", "")

    if user_id not in calculator_sessions:
        calculator_sessions[user_id] = ""

    current_expr = calculator_sessions[user_id]

    if action == "ignore":
        await callback.answer()
        return
    elif action == "clear":
        calculator_sessions[user_id] = ""
        current_expr = ""
    elif action == "backspace":
        current_expr = current_expr[:-1]
        calculator_sessions[user_id] = current_expr
    elif action.startswith("app_"):
        char = action.replace("app_", "")
        if len(current_expr) < 50:
            current_expr += char
            calculator_sessions[user_id] = current_expr
    elif action == "calculate":
        if not current_expr:
            await callback.answer("⚠️ عبارتی وارد نشده است!", show_alert=True)
            return
        try:
            eval_expr = current_expr.replace("×", "*").replace("÷", "/")
            result = safe_eval(eval_expr)
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            current_expr = str(result)
            calculator_sessions[user_id] = current_expr
            await log_activity(user_id, "calculator", f"محاسبه موفق: {eval_expr} = {result}")
        except ZeroDivisionError:
            await callback.answer("❌ تقسیم بر صفر ممکن نیست!", show_alert=True)
            return
        except Exception:
            await callback.answer("❌ خطا در محاسبه! عبارت نامعتبر است.", show_alert=True)
            return

    try:
        await callback.message.edit_text("🧮 **ماشین حساب پیشرفته و جذاب**\n\nاز دکمه‌های زیر برای محاسبه استفاده کنید:", reply_markup=get_calc_keyboard(current_expr))
    except TelegramBadRequest:
        pass
    await callback.answer()

MEDIA_JOB_DAILY_LIMIT = 10  # سازگاری با گزارش‌های قدیمی؛ سهمیه واقعی از توکن ۲۴ساعته می‌آید.
DOWNLOAD_BASE_TOKENS = 10
DOWNLOAD_TOKENS_PER_REFERRAL = 10
DOWNLOAD_TOKEN_WINDOW = timedelta(hours=24)
# الگوی خودکار: از فهرست کامل دامنه‌های پشتیبانی‌شده ساخته می‌شود
_SOCIAL_DOMAIN_ALTS = "|".join(
    re.escape(domain) for domain in sorted(SUPPORTED_SOCIAL_DOMAINS, key=len, reverse=True)
)
SOCIAL_MEDIA_URL_RE = re.compile(
    rf"https?://(?:[^/\s]*\.)?(?:{_SOCIAL_DOMAIN_ALTS})(?:/[^\s]*)?",
    re.IGNORECASE,
)
# لینک مستقیم به فایل رسانه/بایگانی با پسوند شناخته‌شده
DIRECT_MEDIA_URL_RE = re.compile(
    r"https?://[^\s<>\"']+\.(?:mp4|webm|mkv|mov|m4v|3gp|mp3|m4a|ogg|opus|wav|flac|aac|"
    r"zip|rar|7z|tar|gz|bz2|xz|apk|aab|xapk|exe|msi|deb|pdf|epub|mobi|doc|docx|xls|xlsx|"
    r"ppt|pptx|json|csv|ttf|otf|woff|woff2|srt|vtt)(?:\?[^\s]*)?$",
    re.IGNORECASE,
)
SOCIAL_MEDIA_URL_PATTERN = SOCIAL_MEDIA_URL_RE.pattern


def extract_first_url(text: str) -> str:
    """اولین URL را از متن تلگرام جدا و علائم نگارشی انتهایی را حذف می‌کند."""
    value = str(text or "").strip()
    match = re.search(r"https?://[^\s<>\"']+", value, flags=re.IGNORECASE)
    if not match:
        return value
    return match.group(0).rstrip(".,!?;:)]}>،؛؟")


def contains_media_link(text: str) -> bool:
    """آیا متن یک لینک رسانه/فایل دارد؟ دانلود فقط با سشن فعال انجام می‌شود."""
    value = extract_first_url(text)
    return bool(SOCIAL_MEDIA_URL_RE.search(value) or DIRECT_MEDIA_URL_RE.search(value))


async def download_quota_snapshot(user_id: int) -> dict:
    """سهمیهٔ یک پنجرهٔ غلتان ۲۴ساعته را بدون مصرف توکن برمی‌گرداند."""
    if is_admin(user_id):
        return {
            "limit": None,
            "used": 0,
            "remaining": None,
            "referrals": 0,
            "bonus": 0,
            "unlimited": True,
        }
    user = await users_col.find_one(
        {"_id": user_id},
        {"download_window_started_at": 1, "download_tokens_used": 1, "referral_count": 1},
    ) or {}
    now = datetime.now(timezone.utc)
    started = user.get("download_window_started_at")
    if not isinstance(started, datetime) or started.tzinfo is None:
        used = 0
    elif now - started >= DOWNLOAD_TOKEN_WINDOW:
        used = 0
    else:
        used = max(0, int(user.get("download_tokens_used", 0) or 0))
    referrals = max(0, int(user.get("referral_count", 0) or 0))
    bonus = referrals * DOWNLOAD_TOKENS_PER_REFERRAL
    limit = DOWNLOAD_BASE_TOKENS + bonus
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "referrals": referrals,
        "bonus": bonus,
        "unlimited": False,
        "window_started_at": started,
    }


async def consume_download_token(user_id: int) -> dict:
    """مصرف اتمیک یک توکن مشترک برای Instagram/YouTube/URL/موسیقی."""
    if is_admin(user_id):
        return await download_quota_snapshot(user_id)
    now = datetime.now(timezone.utc)
    cutoff = now - DOWNLOAD_TOKEN_WINDOW
    # پنجرهٔ منقضی‌شده را اتمیک ریست می‌کنیم؛ درخواست‌های هم‌زمان دوباره سهمیه نمی‌سازند.
    await users_col.update_one(
        {
            "_id": user_id,
            "$or": [
                {"download_window_started_at": {"$exists": False}},
                {"download_window_started_at": {"$lte": cutoff}},
            ],
        },
        {"$set": {"download_window_started_at": now, "download_tokens_used": 0}},
        upsert=True,
    )
    quota = await users_col.find_one_and_update(
        {
            "_id": user_id,
            "download_window_started_at": {"$gt": cutoff},
            "$expr": {
                "$lt": [
                    {"$ifNull": ["$download_tokens_used", 0]},
                    {
                        "$add": [
                            DOWNLOAD_BASE_TOKENS,
                            {"$multiply": [{"$ifNull": ["$referral_count", 0]}, DOWNLOAD_TOKENS_PER_REFERRAL]},
                        ]
                    },
                ]
            },
        },
        {"$inc": {"download_tokens_used": 1}, "$set": {"last_download_token_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not quota:
        snapshot = await download_quota_snapshot(user_id)
        raise MediaServiceError(
            "download_quota",
            f"سهمیهٔ دانلودت تمام شده: {snapshot['limit']} توکن در هر ۲۴ ساعت.\n"
            "برای هر دعوت موفق، ۱۰ توکن دانلود اضافه می‌گیری؛ از بخش «🎁 دعوت دوستان» لینک دعوتت را بفرست.",
        )
    referrals = max(0, int(quota.get("referral_count", 0) or 0))
    limit = DOWNLOAD_BASE_TOKENS + referrals * DOWNLOAD_TOKENS_PER_REFERRAL
    used = int(quota.get("download_tokens_used", 0) or 0)
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "referrals": referrals,
        "bonus": referrals * DOWNLOAD_TOKENS_PER_REFERRAL,
        "unlimited": False,
    }


async def enqueue_media_job(user_id: int, url: str, mode: str, source: str = "bot", extra: dict | None = None) -> dict:
    if mode not in {"social", "direct", "audio", "music"}:
        raise MediaServiceError("invalid_mode", "نوع درخواست رسانه نامعتبر است.")
    normalized_url = normalize_youtube_url(str(url).strip()) if mode in {"social", "audio"} else str(url).strip()
    if mode == "music":
        # جستجوی آهنگ: نشانی می‌تواند شناسهٔ آدیوس یا لینک یوتیوب باشد؛ SSRF همچنان بررسی می‌شود
        if normalized_url.startswith(("http://", "https://")):
            await validate_public_url(normalized_url)
    elif mode in {"social", "audio"}:
        # هر دامنهٔ عمومی می‌تواند رسانه داشته باشد؛ موتور yt-dlp تلاش می‌کند
        await validate_public_url(normalized_url, social_only=True, allow_generic=True)
    else:
        await validate_public_url(normalized_url)
    active = await media_jobs_col.count_documents({
        "user_id": user_id, "status": {"$in": ["queued", "processing"]}
    })
    if active >= 2:
        raise MediaServiceError("queue_limit", "حداکثر دو درخواست هم‌زمان مجاز است؛ کمی صبر کن.")
    quota = await consume_download_token(user_id)
    day = today_str()
    user = await users_col.find_one({"_id": user_id}, {"media_job_day": 1, "media_job_count": 1}) or {}
    job: dict = {
        "_id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "url": normalized_url[:3000],
        "mode": mode,
        "source": source,
        "status": "queued",
        "download_tokens_remaining": quota.get("remaining"),
        "download_tokens_unlimited": bool(quota.get("unlimited")),
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
    }
    if extra:
        job.update({k: v for k, v in extra.items() if v is not None})
    await media_jobs_col.insert_one(job)
    update: dict = {"$set": {"media_job_day": day, "last_media_job_at": datetime.now(timezone.utc)}}
    if user.get("media_job_day") == day:
        update["$inc"] = {"media_job_count": 1}
    else:
        update["$set"]["media_job_count"] = 1
    await users_col.update_one({"_id": user_id}, update, upsert=True)
    return job


# فایل‌های خیلی بزرگ (تا ۲ گیگابایت) زمان آپلود بیشتری می‌خواهند؛
# در حالت سرور لوکال Bot API تا ۱ ساعت برای ارسال صبر می‌کنیم.
MEDIA_UPLOAD_TIMEOUT = 3600 if LOCAL_BOT_API else 300


async def send_downloaded_media(user_id: int, item: DownloadedMedia, caption: str) -> types.Message:
    # ارسال مستقیم از دیسک (بدون کپی کامل در حافظه) → شروع آپلود سریع‌تر
    upload = FSInputFile(item.path, filename=item.filename)
    try:
        if item.kind == "photo" and item.size <= 10 * 1024 * 1024:
            return await bot.send_photo(user_id, upload, caption=caption[:1024])
        if item.kind == "video":
            return await bot.send_video(
                user_id, upload, caption=caption[:1024], supports_streaming=True,
                request_timeout=MEDIA_UPLOAD_TIMEOUT,
            )
        if item.kind == "animation":
            return await bot.send_animation(user_id, upload, caption=caption[:1024], request_timeout=MEDIA_UPLOAD_TIMEOUT)
        if item.kind == "audio":
            return await bot.send_audio(user_id, upload, caption=caption[:1024], title=item.title[:64], request_timeout=MEDIA_UPLOAD_TIMEOUT)
    except TelegramBadRequest:
        upload = FSInputFile(item.path, filename=item.filename)
    return await bot.send_document(
        user_id, upload, caption=caption[:1024],
        disable_content_type_detection=True, request_timeout=MEDIA_UPLOAD_TIMEOUT,
    )


async def send_media_preview_fallback(job: dict, exc: MediaServiceError) -> bool:
    if job.get("mode") not in {"social", "audio", "music"} or exc.reason not in {"platform_blocked", "private_or_restricted"}:
        return False
    user_id = int(job["user_id"])
    preview_url = re.sub(r"[\x00-\x20\x7f]+", "", str(job.get("url", "")))[:2000]
    host = normalized_host(preview_url)
    is_youtube = "youtube" in host or "youtu.be" in host
    preview_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ تماشای آنلاین", url=preview_url[:2000])],
    ])
    if job.get("mode") == "music":
        music_title = str(job.get("music_title") or "آهنگ")
        music_artist = str(job.get("music_artist") or "")
        if is_youtube:
            text = (
                f"🎵 <b>{html.escape(music_title)}</b>{' · ' + html.escape(music_artist) if music_artist else ''}\n\n"
                "⚠️ دانلود مستقیم از یوتیوب روی IP سرور موقتاً محدود شد، ولی می‌تونی همین الان <b>آنلاین تماشا کنی</b>:\n"
                f"{preview_url}\n\n"
                "💡 اگه فقط صوت می‌خوای، با جستجوی دوباره نسخهٔ دانلودی (آدیوس/دیزر) رو امتحان کن."
            )
        else:
            text = (
                f"⚠️ دانلود مستقیم این آهنگ روی IP سرور موقتاً محدود شد.\n\n"
                f"🎵 {html.escape(music_title)}{' · ' + html.escape(music_artist) if music_artist else ''}\n"
                f"▶️ نسخهٔ قابل‌تماشا:\n{preview_url}\n\n"
                "ربات هیچ رمز، کوکی یا روش دورزدن دسترسی استفاده نمی‌کند؛ می‌تونی با جستجوی دوباره نسخهٔ دیگه‌ای رو هم امتحان کنی."
            )
        try:
            try:
                sent = await bot.send_message(
                    user_id, text, parse_mode="HTML",
                    link_preview_options=types.LinkPreviewOptions(is_disabled=False, prefer_large_media=True, show_above_text=True),
                    reply_markup=preview_keyboard,
                )
            except TelegramBadRequest:
                sent = await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=preview_keyboard)
        except (TelegramForbiddenError, TelegramBadRequest) as fallback_exc:
            log.warning("music preview fallback %s failed: %s", job["_id"], fallback_exc)
            return False
        await media_jobs_col.update_one(
            {"_id": job["_id"]},
            {"$set": {"status": "preview", "failure": exc.reason, "preview_only": True,
                      "item_count": 0, "message_ids": [sent.message_id], "completed_at": datetime.now(timezone.utc)}},
        )
        await log_activity(user_id, "media_music_preview", f"job={job['_id']}")
        return True
    platform = (
        "YouTube" if "youtu" in host else
        "Instagram" if "instagram" in host else
        "TikTok" if "tiktok" in host else
        "Dailymotion" if "dailymotion" in host else
        "Twitch" if "twitch" in host else
        "SoundCloud" if "soundcloud" in host else
        "Google Drive" if "drive.google.com" in host else
        "سایت مقصد"
    )
    if is_youtube:
        text = (
            f"⚠️ دانلود مستقیم این ویدئوی {platform} روی IP سرور موقتاً محدود شد، ولی می‌تونی همین الان <b>آنلاین تماشا کنی</b>:\n\n"
            f"{preview_url}\n\n"
            "💡 اگه فقط صوت می‌خوای، از مرکز موزیک استفاده کن."
        )
    else:
        if exc.reason == "private_or_restricted" and platform == "Instagram":
            text = (
                "⚠️ Instagram برای این Reel هیچ URL عمومیِ فایل ویدئو به ربات نداده است.\n\n"
                f"🔗 لینک اصلی پست:\n{preview_url}\n\n"
                "اگر این Reel فقط داخل اپ Instagram یا بعد از ورود باز می‌شود، ربات بدون حساب، رمز و کوکی نمی‌تواند فایلش را دریافت کند. "
                "ربات روش دورزدن دسترسی استفاده نمی‌کند."
            )
        else:
            text = (
                f"⚠️ دانلود مستقیم این لینک {platform} روی IP سرور موقتاً محدود شد.\n\n"
                f"▶️ نسخهٔ عمومی قابل‌تماشا:\n{preview_url}\n\n"
                "ربات هیچ رمز، کوکی یا روش دورزدن دسترسی استفاده نمی‌کند؛ اگر پیش‌نمایش باز نشد، لینک را مستقیم باز کن."
            )
    try:
        try:
            sent = await bot.send_message(
                user_id,
                text,
                parse_mode="HTML",
                link_preview_options=types.LinkPreviewOptions(
                    is_disabled=False, prefer_large_media=True, show_above_text=True,
                ),
                reply_markup=preview_keyboard,
            )
        except TelegramBadRequest:
            sent = await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=preview_keyboard)
        await media_jobs_col.update_one(
            {"_id": job["_id"]},
            {"$set": {
                "status": "preview", "failure": exc.reason, "preview_only": True,
                "item_count": 0, "message_ids": [sent.message_id],
                "completed_at": datetime.now(timezone.utc),
            }},
        )
        await log_activity(user_id, "media_preview", f"job={job['_id']},host={host}")
        return True
    except (TelegramForbiddenError, TelegramBadRequest) as fallback_exc:
        log.warning("media preview fallback %s failed: %s", job["_id"], fallback_exc)
        return False


def media_progress_bar(percent: int) -> str:
    """نوار پیشرفت متنی از ۰ تا ۱۰۰ درصد."""
    percent = max(0, min(100, int(percent)))
    filled = round(percent / 10)
    bar = "▓" * filled + "░" * (10 - filled)
    return f"{bar} {percent}%"


async def _safe_edit_progress(msg, pct: int, size_text: str = "") -> None:
    """ویرایش امن پیام پیشرفت (از thread sync صدا زده می‌شه)."""
    if msg is None:
        return
    try:
        await msg.edit_text(
            "⏳ <b>در حال دریافت رسانه…</b>\n"
            f"<code>{media_progress_bar(pct)}</code>\n"
            f"{size_text}\n\n"
            "⚠️ فایل و پیام‌ها بعد از <b>۳۰ ثانیه</b> خودکار پاک می‌شن.\n"
            "برای نگهداشتن، بعد از دریافت فایل رو به «پیام‌های ذخیره‌شده» (Saved Messages) فوروارد کن.",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def auto_delete_media_messages(user_id: int, message_ids: list[int], delay: int = 30) -> None:
    """پس از تأخیر، پیام‌های فایل را پاک می‌کند (فقط برای کاربران عادی؛ ادمین مستثنی است)."""
    await asyncio.sleep(delay)
    for message_id in message_ids:
        try:
            await bot.delete_message(user_id, message_id)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


async def process_media_job(job: dict) -> None:
    user_id = int(job["user_id"])
    with tempfile.TemporaryDirectory(prefix=f"ajor-media-{job['_id']}-") as folder:
        try:
            mode_label = {
                "social": "در حال دریافت ویدئو از سایت",
                "audio": "در حال استخراج صوت",
                "direct": "در حال دریافت فایل",
                "music": "در حال دریافت و آماده‌سازی آهنگ",
            }.get(job.get("mode"), "در حال پردازش")
            try:
                await bot.send_message(
                    user_id,
                    f"⏳ <b>{mode_label}…</b>\n<code>{job['_id']}</code>\n"
                    "ویدئوهای بزرگ بعد از دریافت، خودکار فشرده‌سازی می‌شن و ممکنه چند دقیقه طول بکشه.",
                    parse_mode="HTML",
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
            progress_message = None
            last_progress = {"percent": -1, "at": 0.0}
            if job["mode"] == "music":
                if http_session is None:
                    raise MediaServiceError("unavailable", "سرویس دریافت آهنگ آماده نیست.")
                if job.get("music_source") == "audius":
                    track = {
                        "id": job.get("url", ""),
                        "title": job.get("music_title") or "آهنگ",
                        "artist": job.get("music_artist") or "",
                    }
                    quality = str(job.get("music_quality") or "original")
                    try:
                        await bot.send_chat_action(user_id, "upload_audio")
                    except (TelegramForbiddenError, TelegramBadRequest):
                        pass
                    item = await download_audius_track(http_session, track, folder, quality=quality)
                    title, items = item.title, [item]
                elif job.get("music_source") == "youtube":
                    # دانلود صوت یوتیوب از طریق سرویس عمومی Cobalt
                    try:
                        await bot.send_chat_action(user_id, "upload_audio")
                    except (TelegramForbiddenError, TelegramBadRequest):
                        pass
                    try:
                        item = await download_youtube_audio_cobalt(http_session, job.get("url", ""), folder)
                        title, items = item.title, [item]
                    except MediaServiceError as cobalt_exc:
                        if cobalt_exc.reason == "platform_blocked":
                            raise
                        log.warning("cobalt youtube audio failed: %s", cobalt_exc.message)
                        raise MediaServiceError(
                            "platform_blocked",
                            "دانلود صوت از یوتیوب موقتاً محدود شده؛ نسخهٔ قابل‌تماشا فرستاده می‌شود.",
                        ) from cobalt_exc
                else:
                    results = await search_songs(http_session, job.get("url", ""), 4)
                    audius_track = next((t for t in results if t.get("source") == "audius"), None)
                    if audius_track:
                        item = await download_audius_track(http_session, audius_track, folder)
                        title, items = item.title, [item]
                    else:
                        raise MediaServiceError(
                            "platform_blocked",
                            "نسخهٔ دانلودی از منبع عمومی پیدا نشد؛ لینک تماشا فرستاده می‌شود.",
                        )
            elif job["mode"] == "social":
                # پیام پیشرفت واقعی برای دانلود شبکه اجتماعی
                is_owner_user = is_owner(user_id)
                last_social_pct = {"pct": -1, "at": 0.0}
                if not is_owner_user:
                    try:
                        progress_message = await bot.send_message(
                            user_id,
                            "⏳ <b>در حال دریافت ویدئو از سایت…</b>\n"
                            f"<code>{media_progress_bar(0)}</code>\n\n"
                            "⚠️ فایل و پیام‌ها بعد از <b>۳۰ ثانیه</b> خودکار پاک می‌شن.\n"
                            "برای نگهداشتن، بعد از دریافت فایل رو به «پیام‌های ذخیره‌شده» (Saved Messages) فوروارد کن.",
                            parse_mode="HTML",
                        )
                    except (TelegramForbiddenError, TelegramBadRequest):
                        progress_message = None

                    def on_social_progress(pct: int, received: int, total: int):
                        if progress_message is None:
                            return
                        now = time.monotonic()
                        if pct == last_social_pct["pct"] and now - last_social_pct["at"] < 1.5:
                            return
                        last_social_pct["pct"] = pct
                        last_social_pct["at"] = now
                        size_text = ""
                        if received > 0:
                            size_text = f"{received / 1024 / 1024:.1f} MB"
                            if total > 0:
                                size_text += f" از {total / 1024 / 1024:.1f} MB"
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    _safe_edit_progress(progress_message, pct, size_text),
                                    loop,
                                )
                        except Exception:
                            pass
                else:
                    on_social_progress = None
                try:
                    title, items = await download_social_media(job["url"], folder, MAX_MEDIA_BYTES, progress_callback=on_social_progress)
                except MediaServiceError as social_exc:
                    if social_exc.reason not in {"platform_blocked", "no_media", "download_failed", "too_large_or_empty"}:
                        raise
                    host_now = normalized_host(str(job.get("url", "")))
                    if "youtube" not in host_now and "youtu.be" not in host_now:
                        raise
                    log.info("trying cobalt video fallback for %s", job["_id"])
                    try:
                        item = await download_youtube_video_cobalt(http_session, job.get("url", ""), folder, quality="360")
                        title, items = item.title, [item]
                    except Exception as cobalt_video_exc:
                        log.warning("cobalt video fallback failed: %s", cobalt_video_exc)
                        raise social_exc from None
                finally:
                    if not is_owner_user and progress_message:
                        try:
                            await progress_message.edit_text(
                                "✅ <b>دریافت کامل شد!</b>\n"
                                f"<code>{media_progress_bar(100)}</code>",
                                parse_mode="HTML",
                            )
                        except TelegramBadRequest:
                            pass
            elif job["mode"] == "audio":
                title, items = await download_audio_track(job["url"], folder, MAX_MEDIA_BYTES)
            else:
                if http_session is None:
                    raise MediaServiceError("unavailable", "سرویس دریافت فایل آماده نیست.")
                is_owner_user = is_owner(user_id)
                if not is_owner_user:
                    # پیام پیشرفت با نوار درصدی (فقط برای کاربران عادی؛ ادمین مستثنی است)
                    try:
                        progress_message = await bot.send_message(
                            user_id,
                            "⏳ <b>در حال دریافت فایل…</b>\n"
                            f"<code>{media_progress_bar(0)}</code>\n\n"
                            "⚠️ فایل و پیام‌ها بعد از <b>۳۰ ثانیه</b> خودکار پاک می‌شن.\n"
                            "برای نگهداشتن، بعد از دریافت فایل رو به «پیام‌های ذخیره‌شده» (Saved Messages) فوروارد کن.",
                            parse_mode="HTML",
                        )
                    except (TelegramForbiddenError, TelegramBadRequest):
                        progress_message = None

                    async def on_progress(percent: int, received: int, total: int) -> None:
                        if progress_message is None:
                            return
                        now = time.monotonic()
                        if percent == last_progress["percent"] and now - last_progress["at"] < 0.7:
                            return
                        last_progress["percent"] = percent
                        last_progress["at"] = now
                        size_text = f"{received / 1024 / 1024:.1f} MB"
                        if total:
                            size_text += f" از {total / 1024 / 1024:.1f} MB"
                        try:
                            await progress_message.edit_text(
                                "⏳ <b>در حال دریافت فایل…</b>\n"
                                f"<code>{media_progress_bar(percent)}</code>\n"
                                f"{size_text}\n\n"
                                "⚠️ فایل و پیام‌ها بعد از <b>۳۰ ثانیه</b> خودکار پاک می‌شن.\n"
                                "برای نگهداشتن، بعد از دریافت فایل رو به «پیام‌های ذخیره‌شده» (Saved Messages) فوروارد کن.",
                                parse_mode="HTML",
                            )
                        except TelegramBadRequest:
                            pass

                    item = await download_direct_file(
                        http_session, job["url"], folder, MAX_MEDIA_BYTES,
                        progress_callback=on_progress,
                    )
                else:
                    item = await download_direct_file(http_session, job["url"], folder, MAX_MEDIA_BYTES)
                title, items = item.title, [item]
            # متادیتای عمومی پست/ریلز اینستاگرام (کپشن، لایک، ویو و…) از مسیر embed — بدون ورود
            instagram_meta: dict = {}
            if job["mode"] == "social" and "instagram" in normalized_host(str(job.get("url", ""))) and http_session is not None:
                try:
                    instagram_meta = await fetch_instagram_metadata(http_session, str(job.get("url", ""))) or {}
                except Exception as meta_exc:
                    log.warning("instagram metadata fetch failed: %s", meta_exc)
                    instagram_meta = {}
            instagram_info_lines: list[str] = []
            if instagram_meta.get("username"):
                instagram_info_lines.append(f"👤 @{instagram_meta['username']}")
            stat_bits = []
            if instagram_meta.get("likes"):
                stat_bits.append(f"❤️ {instagram_meta['likes']} لایک")
            if instagram_meta.get("views"):
                stat_bits.append(f"👁 {instagram_meta['views']} بازدید")
            if instagram_meta.get("comments"):
                stat_bits.append(f"💬 {instagram_meta['comments']} کامنت")
            if stat_bits:
                instagram_info_lines.append(" · ".join(stat_bits))
            # کپشن پست را برای فلوی «متن پست» و دکمهٔ کپی روی اولین آیتم بگذار
            if instagram_meta.get("caption") and items and not getattr(items[0], "caption", ""):
                try:
                    items[0].caption = instagram_meta["caption"][:2000]
                except Exception:
                    pass
            sent_ids = []
            for index, item in enumerate(items, 1):
                prefix = "🎵" if job["mode"] == "audio" else "📥"
                info_block = ("\n".join(instagram_info_lines) + "\n") if (index == 1 and instagram_info_lines) else ""
                caption = (
                    f"{prefix} {title[:180]}\n"
                    f"{info_block}"
                    f"فایل {index}/{len(items)} · {item.size / 1024 / 1024:.1f} MB\n\n"
                    "⚠️ فقط برای محتوای عمومی و استفاده مجاز/شخصی؛ حقوق صاحب اثر را رعایت کن."
                )
                sent = await send_downloaded_media(user_id, item, caption)
                sent_ids.append(sent.message_id)
            await media_jobs_col.update_one(
                {"_id": job["_id"]},
                {"$set": {
                    "status": "completed", "title": title[:300],
                    "item_count": len(items), "message_ids": sent_ids,
                    "completed_at": datetime.now(timezone.utc),
                }},
            )
            await log_activity(user_id, f"media_{job['mode']}", f"job={job['_id']},items={len(items)}")
            # ارسال کپشن/متن پست اگه موجود باشه و نگه‌داشتن آن برای دکمه کپی
            first_item = items[0] if items else None
            post_caption = getattr(first_item, "caption", "") or getattr(first_item, "description", "") or ""
            clean_caption = post_caption.strip()[:1500] if post_caption and len(post_caption.strip()) > 10 else ""
            if clean_caption:
                await media_jobs_col.update_one(
                    {"_id": job["_id"]},
                    {"$set": {"post_caption": clean_caption}},
                )
                try:
                    await bot.send_message(
                        user_id,
                        f"📝 <b>متن پست:</b>\n\n{html.escape(clean_caption)}",
                        parse_mode="HTML",
                    )
                except (TelegramForbiddenError, TelegramBadRequest):
                    pass

            result_buttons: list[list[InlineKeyboardButton]] = []
            if job["mode"] == "music":
                result_buttons.append([InlineKeyboardButton(
                    text="🔎 جستجوی آهنگ دیگر", callback_data="music_search_again",
                )])
            if job["mode"] == "social":
                if clean_caption:
                    result_buttons.append([InlineKeyboardButton(
                        text="📝 کپی متن پست", callback_data=f"media_caption:{job['_id']}",
                    )])
                result_buttons.append([InlineKeyboardButton(
                    text="🎵 استخراج صوت (MP3)", callback_data=f"media_audio:{job['_id']}",
                )])
                result_buttons.append([InlineKeyboardButton(
                    text="🎤 شناسایی آهنگ", callback_data=f"media_identify:{job['_id']}",
                )])
            elif job["mode"] == "audio":
                result_buttons.append([InlineKeyboardButton(
                    text="🎬 دریافت ویدئو", callback_data=f"media_video:{job['_id']}",
                )])
            job_url = str(job.get("url", "")).strip()
            if job_url.startswith(("http://", "https://")):
                result_buttons.append([InlineKeyboardButton(text="🌐 لینک اصلی", url=job_url[:2000])])
            done_message = await bot.send_message(
                user_id,
                f"✅ درخواست رسانه <code>{job['_id']}</code> کامل شد؛ {len(items)} فایل فرستادم."
                + (
                    "\n\n⚠️ فایل و پیام‌ها بعد از <b>۳۰ ثانیه</b> خودکار پاک می‌شن. "
                    "برای نگهداشتن، فایل رو به «پیام‌های ذخیره‌شده» (Saved Messages) فوروارد کن."
                    if progress_message is not None else ""
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=result_buttons)
                if result_buttons else media_download_reply_menu(),
            )
            # پاک‌سازی خودکار برای کاربران عادی (ادمین مستثنی است)
            if progress_message is not None and not is_owner(user_id):
                all_ids = ([progress_message.message_id] if progress_message else []) + sent_ids + [done_message.message_id]
                asyncio.create_task(auto_delete_media_messages(user_id, all_ids, 30))
        except MediaServiceError as exc:
            if await send_media_preview_fallback(job, exc):
                return
            await media_jobs_col.update_one(
                {"_id": job["_id"]},
                {"$set": {
                    "status": "failed", "failure": exc.reason,
                    "failure_message": exc.message[:300], "failed_at": datetime.now(timezone.utc),
                }},
            )
            try:
                await bot.send_message(
                    user_id,
                    f"❌ درخواست <code>{job['_id']}</code> انجام نشد.\n{html.escape(exc.message)}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔁 تلاش دوباره", callback_data=f"media_retry:{job['_id']}"),
                    ]]),
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
        except Exception as exc:
            log.exception("media job %s failed: %s", job["_id"], exc)
            await media_jobs_col.update_one(
                {"_id": job["_id"]},
                {"$set": {"status": "failed", "failure": type(exc).__name__, "failed_at": datetime.now(timezone.utc)}},
            )
            try:
                await bot.send_message(
                    user_id,
                    f"❌ دریافت رسانه <code>{job['_id']}</code> ناموفق بود؛ لینک یا حجم فایل را بررسی کن.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔁 تلاش دوباره", callback_data=f"media_retry:{job['_id']}"),
                    ]]),
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass


async def media_jobs_worker():
    await media_jobs_col.update_many(
        {"status": "processing", "processing_started_at": {"$lt": datetime.now(timezone.utc) - timedelta(minutes=15)}},
        {"$set": {"status": "queued"}, "$unset": {"processing_started_at": ""}},
    )
    while True:
        try:
            job = await media_jobs_col.find_one_and_update(
                {"status": "queued"},
                {"$set": {"status": "processing", "processing_started_at": datetime.now(timezone.utc)}},
                sort=[("created_at", 1)], return_document=ReturnDocument.AFTER,
            )
            if not job:
                await asyncio.sleep(3)
                continue
            await process_media_job(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("media worker failed: %s", exc)
            await asyncio.sleep(8)


async def send_link_inspection(message: types.Message, url: str) -> None:
    url = extract_first_url(url)
    try:
        report = await inspect_link(url)
    except MediaServiceError as exc:
        return await message.answer(f"❌ {exc.message}", reply_markup=media_download_reply_menu())
    icons = {"کم": "🟢", "متوسط": "🟡", "بالا": "🔴"}
    signals = "\n".join(f"• {html.escape(signal)}" for signal in report["signals"])
    await message.answer(
        "🛡 <b>گزارش ساختار لینک</b>\n\n"
        f"دامنه: <code>{html.escape(report['host'])}</code>\n"
        f"HTTPS: {'✅' if report['scheme'] == 'https' else '❌'}\n"
        f"ریسک ساختاری: {icons[report['risk_level']]} <b>{report['risk_level']}</b> ({report['risk_score']}/100)\n"
        f"پشتیبانی دانلود رسانه: {'✅' if report['social_supported'] else '—'}\n\n"
        f"{signals}\n\n"
        "این بررسی جایگزین آنتی‌ویروس یا تضمین امنیت سایت نیست؛ رمز و کد ورودت رو هیچ‌جا وارد نکن.",
        parse_mode="HTML", reply_markup=media_download_reply_menu(),
    )


async def queue_media_from_message(message: types.Message, mode: str) -> None:
    url = extract_first_url(message.text or "")
    try:
        job = await enqueue_media_job(message.from_user.id, url, mode, "bot")
    except MediaServiceError as exc:
        return await message.answer(f"❌ {exc.message}", reply_markup=media_download_reply_menu())
    quota_line = (
        "♾ سهمیه مدیر"
        if job.get("download_tokens_unlimited")
        else f"🎟 توکن باقی‌مانده: <b>{job.get('download_tokens_remaining', 0)}</b>"
    )
    await message.answer(
        f"✅ درخواست در صف قرار گرفت.\nشناسه: <code>{job['_id']}</code>\n{quota_line}\n"
        "نتیجه بعد از دریافت مستقیم به همین چت فرستاده می‌شه.",
        parse_mode="HTML", reply_markup=media_download_reply_menu(),
    )


async def show_media_jobs(message: types.Message) -> None:
    jobs = await media_jobs_col.find({"user_id": message.from_user.id}).sort("created_at", -1).limit(10).to_list(length=10)
    if not jobs:
        return await message.answer("📋 هنوز درخواست دانلود یا آپلودی نداری.", reply_markup=media_download_reply_menu())
    labels = {"queued": "در صف", "processing": "در حال دریافت", "completed": "کامل", "preview": "قابل تماشا", "failed": "ناموفق"}
    mode_labels = {"social": "شبکه/سایت", "direct": "آپلود URL", "audio": "استخراج صوت", "music": "آهنگ"}
    lines = ["📋 <b>دانلودها و آپلودهای اخیر</b>", ""]
    for job in jobs:
        lines.append(
            f"• <code>{job['_id']}</code> · {labels.get(job.get('status'), job.get('status'))}\n"
            f"  {mode_labels.get(job.get('mode'), job.get('mode'))} · {html.escape(normalized_host(job.get('url','')))}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=media_download_reply_menu())


@dp.callback_query(F.data == "media_center")
async def media_center_callback(callback: types.CallbackQuery):
    await callback.message.answer("📥 مرکز رسانه:", reply_markup=media_download_reply_menu())
    await callback.answer()


async def show_download_quota(message: types.Message) -> None:
    quota = await download_quota_snapshot(message.from_user.id)
    if quota.get("unlimited"):
        text = "🎟 <b>سهمیه دانلود</b>\n\n♾ برای مدیر ربات نامحدود است."
        markup = media_download_reply_menu()
    else:
        text = (
            "🎟 <b>سهمیهٔ دانلود ۲۴ساعته</b>\n\n"
            f"باقی‌مانده: <b>{quota['remaining']}</b> از <b>{quota['limit']}</b> توکن\n"
            f"مصرف‌شده: {quota['used']}\n"
            f"🎁 دعوت موفق: {quota['referrals']} نفر · پاداش رفرال: +{quota['bonus']} توکن\n\n"
            "هر دانلود Instagram، YouTube، آهنگ یا فایل URL یک توکن مصرف می‌کند.\n"
            "برای هر دعوت موفق، ۱۰ توکن به سهمیهٔ هر ۲۴ ساعت اضافه می‌شود."
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 دریافت لینک دعوت", callback_data="invite")],
            [InlineKeyboardButton(text="🔙 مرکز دانلود", callback_data="media_center")],
        ])
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


INSTAGRAM_COMMENT_BUTTON = "💬 کپی متن کامنت اینستاگرام"


def instagram_comment_keyboard(source_url: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if source_url:
        rows.append([InlineKeyboardButton(text="🌐 بازکردن کامنت در اینستاگرام", url=source_url[:2000])])
    rows.append([InlineKeyboardButton(text="💬 کامنت دیگر", callback_data="instagram_comment_again")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def start_instagram_comment_session(message: types.Message) -> None:
    user_id = message.from_user.id
    instagram_comment_sessions.add(user_id)
    media_request_sessions.pop(user_id, None)
    await message.answer(
        "💬 <b>کپی متن کامنت اینستاگرام</b>\n\n"
        "لینک خودِ همان کامنت را بفرست؛ مثلاً لینکی که از گزینهٔ «Copy link» کامنت اینستاگرام کپی کردی و داخلش <code>/c/...</code> یا <code>comment_id=...</code> دارد.\n\n"
        "فقط پست و کامنت عمومی قابل دریافت است؛ رمز، کوکی یا اطلاعات ورود لازم نیست. /cancel",
        parse_mode="HTML",
        reply_markup=media_download_reply_menu(),
    )


async def copy_instagram_comment_from_message(message: types.Message, url: str | None = None) -> None:
    user_id = message.from_user.id
    value = (url or message.text or "").strip()
    if not is_instagram_comment_url(value):
        instagram_comment_sessions.discard(user_id)
        return await message.answer(
            "❌ این لینک، لینک مستقیم یک کامنت اینستاگرام نیست.\n\n"
            "از خود کامنت روی «Copy link» بزن و لینک کامل را بفرست؛ لینک باید <code>/c/...</code> یا <code>comment_id=...</code> داشته باشد.",
            parse_mode="HTML",
            reply_markup=media_download_reply_menu(),
        )

    instagram_comment_sessions.discard(user_id)
    waiting = await message.answer("🔎 دارم متن کامنت عمومی رو از اینستاگرام پیدا می‌کنم…")
    try:
        result = await extract_instagram_comment(value)
    except InstagramCommentError as exc:
        try:
            await waiting.edit_text(
                f"❌ {html.escape(exc.message)}\n\n"
                "اگر لینک درست است، مطمئن شو پست عمومی است و کامنت حذف نشده.",
                parse_mode="HTML",
                reply_markup=instagram_comment_keyboard(),
            )
        except TelegramBadRequest:
            await message.answer(f"❌ {exc.message}", reply_markup=media_download_reply_menu())
        return
    except Exception as exc:
        log.warning("instagram comment extraction failed: %s", exc)
        try:
            await waiting.edit_text(
                "❌ دریافت متن کامنت ناموفق شد؛ چند لحظه بعد دوباره امتحان کن.",
                reply_markup=instagram_comment_keyboard(),
            )
        except TelegramBadRequest:
            await message.answer("❌ دریافت متن کامنت ناموفق شد.", reply_markup=media_download_reply_menu())
        return

    author = f"@{result.author.lstrip('@')[:120]}" if result.author else "کاربر اینستاگرام"
    answer = (
        "💬 متن کامنت اینستاگرام آماده شد\n"
        f"👤 نویسنده: {author}\n\n"
        f"{result.text[:3600]}\n\n"
        "📌 روی متن نگه دار و کپی کن."
    )
    try:
        await waiting.edit_text(
            answer,
            reply_markup=instagram_comment_keyboard(result.source_url),
        )
    except TelegramBadRequest:
        await message.answer(
            answer,
            reply_markup=instagram_comment_keyboard(result.source_url),
        )
    await log_activity(user_id, "instagram_comment_copy", f"comment={result.comment_id}")


@dp.callback_query(F.data == "instagram_comment_again")
async def instagram_comment_again_callback(callback: types.CallbackQuery):
    instagram_comment_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "💬 لینک کامنت بعدی اینستاگرام رو بفرست. /cancel",
        reply_markup=media_download_reply_menu(),
    )
    await callback.answer()


@dp.message(Command("igcomment"))
async def instagram_comment_command(message: types.Message):
    url = (message.text or "").partition(" ")[2].strip()
    if url:
        return await copy_instagram_comment_from_message(message, url)
    await start_instagram_comment_session(message)


@dp.message(Command("download"))
async def media_download_command(message: types.Message):
    url = (message.text or "").partition(" ")[2].strip()
    if url:
        return await queue_media_from_message(message, "social")
    media_request_sessions[message.from_user.id] = "social"
    await message.answer("📥 لینک عمومی شبکه اجتماعی، هر سایتی با ویدئو، یا لینک مستقیم فایل رو بفرست. /cancel", reply_markup=media_download_reply_menu())


@dp.message(Command("uploadurl"))
async def url_upload_command(message: types.Message):
    url = (message.text or "").partition(" ")[2].strip()
    if url:
        return await queue_media_from_message(message, "direct")
    media_request_sessions[message.from_user.id] = "direct"
    await message.answer(
        f"🔗 لینک مستقیم فایل یا فیلم رو بفرست. تقریباً هر فرمتی قبول می‌شه (APK، EXE، PDF، ZIP، Office، فونت، زیرنویس و…)؛ حداکثر {media_size_label()} و فقط لینک عمومی. /cancel",
        reply_markup=media_download_reply_menu(),
    )


@dp.message(Command("checklink"))
async def link_check_command(message: types.Message):
    url = (message.text or "").partition(" ")[2].strip()
    if url:
        return await send_link_inspection(message, url)
    media_request_sessions[message.from_user.id] = "inspect"
    await message.answer("🛡 لینک کامل رو بفرست. /cancel", reply_markup=media_download_reply_menu())


@dp.callback_query(F.data == "youtube")
async def youtube(callback: types.CallbackQuery):
    media_request_sessions[callback.from_user.id] = "social"
    await callback.message.answer(
        "📥 لینک عمومی ویدئو، پست یا YouTube Shorts رو بفرست. پشتیبانی: اینستاگرام، تیک‌تاک، یوتیوب، X، فیسبوک، ردیت، دیلی‌موشن، توییچ، ساندکلود، VK، گوگل‌درایو، دراپ‌باکس و ده‌ها پلتفرم دیگه + هر سایتی که ویدئو داشته باشه.\n\n"
        "ویدئوهای بزرگ خودکار فشرده می‌شن؛ بعدش دکمه استخراج صوت MP3 هم داری. /cancel",
        reply_markup=media_download_reply_menu(),
    )
    await callback.answer()


def format_music_item(item: dict, index: int = 0) -> str:
    duration = int(item.get("duration") or 0)
    minutes, seconds = divmod(duration, 60)
    duration_text = f"{minutes}:{seconds:02d}" if duration else "؟:؟?"
    provider = str(item.get("provider") or "")
    badge = f"{provider} " if provider else ""
    return (
        f"{badge}<b>{html.escape(str(item.get('title') or 'بدون عنوان'))}</b>\n"
        f"    {html.escape(str(item.get('artist') or 'ناشناس'))} · {duration_text}"
    )


def _music_session() -> aiohttp.ClientSession:
    """نشست HTTP برای سرویس موزیک؛ اگر نشست اصلی هنوز آماده نباشد موقت می‌سازد."""
    return http_session if http_session is not None else aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))


async def enqueue_music_job(user_id: int, track: dict, quality: str = "original") -> None:
    source = track.get("source")
    ref = str(track.get("id") or "")
    if source == "youtube":
        url = str(track.get("watch_url") or track.get("permalink") or f"https://www.youtube.com/watch?v={ref}")
    else:
        url = ref
    job = await enqueue_media_job(
        user_id, url, "music", "bot",
        extra={
            "music_source": source or "query",
            "music_title": str(track.get("title") or "")[:300],
            "music_artist": str(track.get("artist") or "")[:200],
            "music_quality": quality,
        },
    )
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["original"])
    await bot.send_message(
        user_id,
        f"✅ <b>در صف دانلود آهنگ</b>\n"
        f"🎵 {html.escape(str(track.get('title') or ''))} · {html.escape(str(track.get('artist') or ''))}\n"
        f"⚙️ کیفیت: {preset['label']}\n"
        f"شناسه: <code>{job['_id']}</code>\n"
        "⏳ به محض آماده‌شدن، فایل همین‌جا میاد.",
        parse_mode="HTML", reply_markup=music_reply_menu(),
    )


async def send_music_track_detail(user_id: int, index: int, edit_message_id: int | None = None) -> None:
    items = music_search_cache.get(user_id) or []
    if index < 0 or index >= len(items):
        await bot.send_message(user_id, "این نتیجه منقضی شده؛ دوباره جستجو کن.", reply_markup=music_reply_menu())
        return
    track = items[index]
    duration = int(track.get("duration") or 0)
    minutes, seconds = divmod(duration, 60)
    duration_text = f"{minutes}:{seconds:02d}" if duration else "؟:؟?"
    lines = [
        f"{track.get('provider') or '🎵'} <b>{html.escape(str(track.get('title') or ''))}</b>",
        f"👤 {html.escape(str(track.get('artist') or 'ناشناس'))} · {duration_text}",
    ]
    if track.get("album"):
        lines.append(f"💿 {html.escape(str(track['album']))}")
    rows: list[list[InlineKeyboardButton]] = []
    if track.get("downloadable"):
        lines.append("")
        lines.append("✅ نسخهٔ کامل قابل دانلوده:")
        rows.append([InlineKeyboardButton(text="🎧 کیفیت اصلی", callback_data=f"music_dl:{index}:original")])
        rows.append([
            InlineKeyboardButton(text="🔉 ۱۲۸k", callback_data=f"music_dl:{index}:high"),
            InlineKeyboardButton(text="🔈 ۶۴k", callback_data=f"music_dl:{index}:low"),
        ])
    else:
        lines.append("")
        lines.append("ℹ️ این منبع نسخهٔ دانلودی نداره؛ ولی می‌تونی:")
    if track.get("preview_url"):
        rows.append([InlineKeyboardButton(text="▶️ پخش پیش‌نمایش ۳۰ ثانیه", callback_data=f"music_preview:{index}")])
    if not track.get("downloadable"):
        rows.append([InlineKeyboardButton(text="🔎 جستجوی نسخهٔ دانلودی", callback_data=f"music_find:{index}")])
    if track.get("watch_url"):
        rows.append([InlineKeyboardButton(text="🌐 تماشا در یوتیوب", url=str(track["watch_url"])[:2000])])
    rows.append([
        InlineKeyboardButton(text="🔁 جستجوی دوباره", callback_data="music_search_again"),
        InlineKeyboardButton(text="🔙 لیست", callback_data="music_list"),
    ])
    text = "\n".join(lines)
    if edit_message_id:
        try:
            return await bot.edit_message_text(
                text, chat_id=user_id, message_id=edit_message_id,
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        except TelegramBadRequest:
            pass
    await bot.send_message(
        user_id, text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def present_music_results(user_id: int, query: str) -> None:
    session = _music_session()
    progress = await bot.send_message(user_id, "🔎 در حال جستجو در چند منبع موسیقی… (آدیوس، دیزر، اپل موزیک، یوتیوب)")
    try:
        items = await search_songs(session, query, 8)
    except MediaServiceError as exc:
        try:
            await progress.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest:
            await bot.send_message(user_id, f"❌ {exc.message}", reply_markup=music_reply_menu())
        return
    except Exception as exc:
        log.warning("music search failed: %s", exc)
        try:
            await progress.edit_text("❌ جستجوی آهنگ ناموفق بود؛ کمی بعد دوباره تلاش کن.")
        except TelegramBadRequest:
            await bot.send_message(user_id, "❌ جستجوی آهنگ ناموفق بود؛ کمی بعد دوباره تلاش کن.", reply_markup=music_reply_menu())
        return
    finally:
        if session is not http_session:
            await session.close()
    music_search_cache[user_id] = items
    lines = ["🎵 <b>نتیجه جستجو</b>", f"برای: <i>{html.escape(query[:100])}</i>", ""]
    for index, item in enumerate(items):
        lines.append(f"{index + 1}. {format_music_item(item)}")
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"{index + 1}. {str(item.get('title') or '')[:34]}", callback_data=f"music_pick:{index}")]
        for index, item in enumerate(items)
    ]
    rows.append([InlineKeyboardButton(text="🔁 جستجوی دوباره", callback_data="music_search_again")])
    try:
        await progress.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        await bot.send_message(user_id, "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def present_music_trending(user_id: int) -> None:
    session = _music_session()
    progress = await bot.send_message(user_id, "🔥 در حال دریافت آهنگ‌های ترند از چند منبع…")
    try:
        items = await trending_songs(session, 10)
    except MediaServiceError as exc:
        try:
            await progress.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest:
            await bot.send_message(user_id, f"❌ {exc.message}", reply_markup=music_reply_menu())
        return
    except Exception as exc:
        log.warning("music trending failed: %s", exc)
        try:
            await progress.edit_text("❌ دریافت آهنگ‌های ترند ناموفق بود؛ کمی بعد دوباره تلاش کن.")
        except TelegramBadRequest:
            await bot.send_message(user_id, "❌ دریافت آهنگ‌های ترند ناموفق بود؛ کمی بعد دوباره تلاش کن.", reply_markup=music_reply_menu())
        return
    finally:
        if session is not http_session:
            await session.close()
    music_search_cache[user_id] = items
    lines = ["🔥 <b>آهنگ‌های ترند</b>", "(آدیوس + دیزر چارت + اپل تاپ)", ""]
    for index, item in enumerate(items):
        lines.append(f"{index + 1}. {format_music_item(item)}")
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"{index + 1}. {str(item.get('title') or '')[:34]}", callback_data=f"music_pick:{index}")]
        for index, item in enumerate(items)
    ]
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی لیست", callback_data="music_trending")])
    try:
        await progress.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        await bot.send_message(user_id, "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def present_music_iranian(user_id: int, query: str, *, remix: bool = False) -> None:
    session = _music_session()
    progress = await bot.send_message(user_id, "🇮🇷 در حال جستجو در کاتالوگ ایرانی و منابع زنده…")
    try:
        items = await search_iranian_songs(session, query or ("ریمیکس ایرانی رپ پاپ سنتی" if remix else "ترند ایرانی"), 10)
    except Exception as exc:
        log.warning("iranian music search failed: %s", exc)
        try:
            await progress.edit_text("❌ جستجوی آهنگ ایرانی ناموفق بود؛ دوباره تلاش کن.")
        except TelegramBadRequest:
            await bot.send_message(user_id, "❌ جستجوی آهنگ ایرانی ناموفق بود.", reply_markup=music_reply_menu())
        return
    finally:
        if session is not http_session:
            await session.close()
    music_search_cache[user_id] = items
    title = "🎚 ریمیکس‌های ایرانی" if remix else "🇮🇷 نتیجهٔ آهنگ‌های ایرانی"
    lines = [f"<b>{title}</b>", "کاتالوگ ایرانی + دیزر + اپل موزیک + یوتیوب", ""]
    for index, item in enumerate(items):
        lines.append(f"{index + 1}. {format_music_item(item)}")
    rows = [[InlineKeyboardButton(text=f"{i + 1}. {str(item.get('title') or '')[:34]}", callback_data=f"music_pick:{i}")] for i, item in enumerate(items)]
    rows.append([InlineKeyboardButton(text="🔎 جستجوی ایرانی دیگر", callback_data="music_iranian_search_again")])
    try:
        await progress.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        await bot.send_message(user_id, "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def present_music_iranian_trending(user_id: int) -> None:
    session = _music_session()
    progress = await bot.send_message(user_id, "🇮🇷 در حال دریافت ترندهای ایرانی و ریمیکس‌های تازه…")
    try:
        items = await trending_iranian_songs(session, 10)
    except Exception as exc:
        log.warning("iranian trending failed: %s", exc)
        try:
            await progress.edit_text("❌ ترند ایرانی فعلاً در دسترس نیست؛ دوباره تلاش کن.")
        except TelegramBadRequest:
            await bot.send_message(user_id, "❌ ترند ایرانی فعلاً در دسترس نیست.", reply_markup=music_reply_menu())
        return
    finally:
        if session is not http_session:
            await session.close()
    music_search_cache[user_id] = items
    lines = ["🇮🇷 <b>موزیک ایرانی امروز و ترندها</b>", "رپ · پاپ · سنتی · تلفیقی · ریمیکس", ""]
    for index, item in enumerate(items):
        lines.append(f"{index + 1}. {format_music_item(item)}")
    rows = [[InlineKeyboardButton(text=f"{i + 1}. {str(item.get('title') or '')[:34]}", callback_data=f"music_pick:{i}")] for i, item in enumerate(items)]
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی ترند ایرانی", callback_data="music_iranian_trending")])
    try:
        await progress.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        await bot.send_message(user_id, "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.message(Command("song"))
async def song_command(message: types.Message):
    query = (message.text or "").partition(" ")[2].strip()
    if not query:
        music_search_sessions.add(message.from_user.id)
        return await message.answer(
            "🎵 اسم آهنگ یا خواننده رو بفرست. /cancel",
            reply_markup=music_reply_menu(),
        )
    await message.answer(f"🔎 در حال جستجوی «{html.escape(query[:80])}»…", parse_mode="HTML")
    await present_music_results(message.from_user.id, query)


@dp.message(F.chat.type == "private", F.text.regexp(r"^(🎵 موسیقی|🎵 جستجو و دانلود آهنگ)$"))
async def music_center_entry(message: types.Message):
    await message.answer(
        "🎵 <b>بخش موسیقی</b>\n\n"
        "🎧 از گزینه‌های زیر انتخاب کن:\n"
        "• 🔎 <b>جستجوی آهنگ</b> — فارسی، ایرانی و خارجی با چند منبع\n"
        "• 🇮🇷 <b>ترند ایرانی</b> — پاپ، رپ، سنتی و تلفیقی\n"
        "• 🎚 <b>ریمیکس ایرانی</b> — جستجوی ریمیکس‌های تازهٔ رپ/پاپ/سنتی\n"
        "• 📅 <b>موزیک امروز</b> — ارسال خودکار به کانال یا گروه\n"
        "• 📚 <b>پلی‌لیست ایرانی</b> — آپلود گروهی و دسترسی عمومی\n"
        "• 🎤 <b>تشخیص آهنگ</b> — با تکه صدا/کلیپ (مثل Shazam)\n\n"
        "اسم آهنگ یا خواننده رو هم مستقیم بفرست تا جستجو کنم.",
        parse_mode="HTML", reply_markup=music_reply_menu(),
    )


@dp.message(F.chat.type == "private", F.text.regexp(r"^📅 موزیک امروز$"))
async def daily_music_prompt(message: types.Message):
    await show_daily_music_control(message)


@dp.message(F.chat.type == "private", F.text.regexp(r"^📚 پلی‌لیست ایرانی$"))
async def public_music_playlist_prompt(message: types.Message):
    await show_public_music_playlist(message, 0, admin=is_admin(message.from_user.id))


@dp.message(F.chat.type == "private", F.text.regexp(r"^📤 آپلود گروهی موسیقی$"))
async def music_playlist_upload_prompt(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ آپلود پلی‌لیست فقط برای مدیر ربات فعال است.", reply_markup=music_reply_menu())
    await start_music_playlist_upload(message)


@dp.message(F.chat.type == "private", F.text.regexp(r"^(🔎 جستجوی آهنگ|🎵 جستجو و دانلود آهنگ)$"))
async def music_search_prompt(message: types.Message):
    music_search_sessions.add(message.from_user.id)
    await message.answer("🎵 اسم آهنگ یا خواننده رو بفرست. /cancel", reply_markup=music_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^🔥 آهنگ‌های ترند$"))
async def music_trending_prompt(message: types.Message):
    await message.answer("🔥 در حال دریافت آهنگ‌های ترند…")
    await present_music_trending(message.from_user.id)


@dp.message(F.chat.type == "private", F.text.regexp(r"^🇮🇷 ترند ایرانی$"))
async def music_iranian_trending_prompt(message: types.Message):
    await present_music_iranian_trending(message.from_user.id)


@dp.message(F.chat.type == "private", F.text.regexp(r"^🎚 ریمیکس ایرانی$"))
async def music_iranian_remix_prompt(message: types.Message):
    await present_music_iranian(message.from_user.id, "ریمیکس ایرانی رپ پاپ سنتی", remix=True)


@dp.message(F.chat.type == "private", F.text.regexp(r"^(🎤 تشخیص آهنگ|🎤 تشخیص آهنگ با تکه صدا)$"))
async def music_recognize_prompt(message: types.Message):
    music_recognize_sessions.add(message.from_user.id)
    await message.answer(
        "🎤 یه <b>ویس، فایل صوتی یا ویدئوی کوتاه</b> از همون آهنگ (۱۰ تا ۳۰ ثانیه) بفرست تا تشخیص بدم. /cancel\n\n"
        "اگه تشخیص فعال نباشه، حداقل اسمش رو بهم بگو تا جستجو کنم.",
        parse_mode="HTML", reply_markup=music_reply_menu(),
    )


@dp.message(F.chat.type == "private", F.text.regexp(r"^(ℹ️ راهنمای موزیک|📖 راهنمای موسیقی)$"))
async def music_guide(message: types.Message):
    await message.answer(
        "🎵 <b>مرکز موزیک</b>\n\n"
        "🔎 جستجوی خارجی و ایرانی: کاتالوگ ایرانی + آدیوس + دیزر + اپل موزیک + یوتیوب.\n"
        "🇮🇷 جستجوی ایرانی: پاپ، رپ، سنتی، تلفیقی و ریمیکس‌های رپ/پاپ/سنتی را جداگانه تقویت می‌کند.\n"
        "📅 موزیک امروز: یک موزیک ایرانی با کپشن «امروز موزیک چی گوش کنیم؟» به مقصد انتخابی می‌فرستد.\n"
        "📚 پلی‌لیست عمومی: مدیر می‌تواند چند آهنگ را پشت‌سرهم آپلود کند و بعد از پایان، همه برای کاربران در دسترس باشند.\n"
        "⚙️ کیفیت: برای نسخهٔ دانلودی می‌تونی کیفیت اصلی، ۱۲۸k یا ۶۴k انتخاب کنی.\n"
        "🎤 تشخیص آهنگ: یه تکه ۱۰-۳۰ ثانیه‌ای بفرست.\n\n"
        "📥 فقط محتوای عمومی و مجاز؛ هیچ رمز یا کوکی‌ای استفاده نمی‌شه. حقوق صاحب اثر رو رعایت کن.",
        parse_mode="HTML", reply_markup=music_reply_menu(),
    )


def _music_target_status() -> str:
    target_id = runtime_settings.get("daily_music_target_id")
    if not target_id or not runtime_settings.get("daily_music_target_enabled"):
        return "❌ مقصدی وصل نیست"
    title = str(runtime_settings.get("daily_music_target_title") or target_id)
    chat_type = str(runtime_settings.get("daily_music_target_type") or "مقصد")
    return f"✅ {html.escape(title[:70])} · {html.escape(chat_type)} · <code>{target_id}</code>"


def _daily_music_control_text() -> str:
    status = "✅ فعال" if runtime_settings.get("daily_music_enabled") else "⏸ غیرفعال"
    return (
        "📅 <b>مدیریت موزیک امروز</b>\n\n"
        f"وضعیت: <b>{status}</b>\n"
        f"زمان ارسال: <b>{runtime_settings.get('daily_music_time', '12:00')}</b> به وقت تهران\n"
        f"مقصد: {_music_target_status()}\n\n"
        "هر روز یک آهنگ ایرانی از پلی‌لیست عمومی یا منابع ایرانی انتخاب می‌شود و با کپشن «امروز موزیک چی گوش کنیم؟» ارسال می‌شود.\n"
        "برای شش ماه بدون تکرار از پلی‌لیست، حداقل ۱۸۳ آهنگ متفاوت و فعال لازم است."
    )


def _daily_music_control_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text="⏸ غیرفعال‌کردن" if runtime_settings.get("daily_music_enabled") else "✅ فعال‌کردن",
            callback_data="music_daily_toggle",
        )],
        [InlineKeyboardButton(text="🔗 اتصال یا تغییر مقصد", callback_data="music_daily_connect")],
        [InlineKeyboardButton(text="🕒 تغییر زمان ارسال", callback_data="music_daily_time")],
    ]
    if runtime_settings.get("daily_music_target_id"):
        rows.append([
            InlineKeyboardButton(text="📤 ارسال آزمایشی", callback_data="music_daily_test"),
            InlineKeyboardButton(text="🔌 قطع اتصال", callback_data="music_daily_disconnect"),
        ])
    rows.extend([
        [InlineKeyboardButton(text="📚 پلی‌لیست عمومی", callback_data="music_playlist_public")],
        [InlineKeyboardButton(text="➕ افزودن گروهی آهنگ", callback_data="music_playlist_add")],
        [InlineKeyboardButton(text="🛠 مدیریت پلی‌لیست", callback_data="music_playlist_manage:0")],
        [InlineKeyboardButton(text="🔙 موسیقی", callback_data="music_back")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_daily_music_control(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ مدیریت موزیک امروز فقط برای مدیر ربات فعال است.", reply_markup=music_reply_menu())
    await message.answer(_daily_music_control_text(), parse_mode="HTML", reply_markup=_daily_music_control_keyboard())


def _parse_daily_music_time(value: str) -> str:
    normalized = normalize_digits(str(value or "").strip())
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", normalized):
        raise ValueError("زمان باید با فرمت ساعت:دقیقه باشد؛ مثل 12:30")
    return normalized


def daily_music_due(now: datetime, configured_time: str) -> tuple[bool, str]:
    """پنجرهٔ دو ساعتهٔ ارسال را حتی برای زمان‌های نزدیک نیمه‌شب درست محاسبه می‌کند."""
    hour, minute = map(int, configured_time.split(":", 1))
    target = hour * 60 + minute
    current = now.hour * 60 + now.minute
    window_end = target + 120
    if window_end < 1440:
        return target <= current < window_end, now.strftime("%Y-%m-%d")
    if current >= target:
        return True, now.strftime("%Y-%m-%d")
    previous_day = now - timedelta(days=1)
    return current < window_end - 1440, previous_day.strftime("%Y-%m-%d")


async def connect_daily_music_target(message: types.Message, value: str) -> None:
    try:
        identifier = parse_daily_fal_target(value)
        chat = await bot.get_chat(identifier)
        chat_type = getattr(chat.type, "value", str(chat.type))
        if chat_type not in {"channel", "group", "supergroup"}:
            raise ValueError("این مقصد کانال، گروه یا سوپرگروه نیست")
        bot_info = await bot.get_me()
        member = await bot.get_chat_member(chat.id, bot_info.id)
        member_status = getattr(member.status, "value", str(member.status))
        if chat_type == "channel" and member_status not in {"administrator", "creator"}:
            raise ValueError("برای کانال، ربات باید ادمین یا سازنده باشد")
        if chat_type in {"group", "supergroup"} and member_status not in {"administrator", "creator", "member", "restricted"}:
            raise ValueError("ربات در این گروه اجازهٔ ارسال ندارد")
        if member_status == "restricted" and getattr(member, "can_send_messages", True) is False:
            raise ValueError("ربات در این گروه اجازهٔ ارسال پیام ندارد")
    except ValueError as exc:
        return await message.answer(f"❌ {exc}\nدوباره بفرست یا /cancel بزن.")
    except Exception as exc:
        log.warning("daily music target connection failed: %s", exc)
        return await message.answer("❌ مقصد پیدا نشد یا ربات دسترسی ارسال ندارد؛ آیدی/لینک را بررسی کن.")
    username = getattr(chat, "username", None)
    public_link = f"https://t.me/{username}" if username else ""
    runtime_settings.update({
        "daily_music_target_enabled": True,
        "daily_music_target_id": int(chat.id),
        "daily_music_target_title": str(getattr(chat, "title", None) or username or chat.id),
        "daily_music_target_type": chat_type,
        "daily_music_target_username": str(username or ""),
        "daily_music_target_link": public_link,
    })
    await settings_col.update_one(
        {"_id": "runtime"},
        {"$set": {
            "daily_music_target_enabled": True,
            "daily_music_target_id": int(chat.id),
            "daily_music_target_title": runtime_settings["daily_music_target_title"],
            "daily_music_target_type": chat_type,
            "daily_music_target_username": str(username or ""),
            "daily_music_target_link": public_link,
        }},
        upsert=True,
    )
    music_daily_target_sessions.discard(message.from_user.id)
    await message.answer("✅ مقصد موزیک امروز وصل شد.", reply_markup=music_reply_menu())


async def save_daily_music_time(message: types.Message, value: str) -> None:
    try:
        value = _parse_daily_music_time(value)
    except ValueError as exc:
        return await message.answer(f"❌ {exc}\nدوباره بفرست یا /cancel بزن.")
    runtime_settings["daily_music_time"] = value
    music_daily_time_sessions.discard(message.from_user.id)
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"daily_music_time": value}}, upsert=True)
    await message.answer(f"✅ زمان موزیک امروز روی <b>{value}</b> تنظیم شد.", parse_mode="HTML", reply_markup=music_reply_menu())


async def _playlist_entries(page: int = 0, limit: int = 8) -> tuple[list[dict], int]:
    total = await public_music_playlist_col.count_documents({"active": {"$ne": False}})
    total_pages = max(1, (total + limit - 1) // limit)
    page = max(0, min(page, total_pages - 1))
    items = await public_music_playlist_col.find({"active": {"$ne": False}}).sort("created_at", -1).skip(page * limit).limit(limit).to_list(length=limit)
    return items, total_pages


async def show_public_music_playlist(message: types.Message, page: int = 0, *, edit: bool = False, admin: bool = False) -> None:
    items, total_pages = await _playlist_entries(page)
    page = max(0, min(page, total_pages - 1))
    lines = ["📚 <b>پلی‌لیست عمومی موزیک ایرانی</b>", "", "هر آهنگ را انتخاب کن تا برایت ارسال شود.", ""]
    rows = []
    for index, item in enumerate(items, page * 8 + 1):
        title = str(item.get("title") or "آهنگ")[:36]
        artist = str(item.get("artist") or "")[:24]
        lines.append(f"{index}. {html.escape(title)}{f' · {html.escape(artist)}' if artist else ''}")
        rows.append([InlineKeyboardButton(text=f"🎵 {title}", callback_data=f"musicplaylist:{item['_id']}")])
    if not items:
        lines.append("هنوز آهنگی در پلی‌لیست عمومی ثبت نشده است.")
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"music_playlist_public:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="⏭ بعدی", callback_data=f"music_playlist_public:{page + 1}"))
    if nav:
        rows.append(nav)
    if admin:
        rows.append([InlineKeyboardButton(text="➕ افزودن گروهی آهنگ", callback_data="music_playlist_add")])
        rows.append([InlineKeyboardButton(text="🛠 مدیریت پلی‌لیست", callback_data="music_playlist_manage:0")])
    rows.append([InlineKeyboardButton(text="🔗 لینک اشتراک پلی‌لیست", url="https://t.me/Ajorparehbot?start=iran_playlist")])
    rows.append([InlineKeyboardButton(text="🔙 موسیقی", callback_data="music_back")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def show_music_playlist_manage(message: types.Message, page: int = 0, *, edit: bool = False) -> None:
    items, total_pages = await _playlist_entries(page)
    page = max(0, min(page, total_pages - 1))
    lines = ["🛠 <b>مدیریت پلی‌لیست عمومی</b>", f"صفحهٔ {page + 1} از {total_pages}", ""]
    rows = []
    for index, item in enumerate(items, page * 8 + 1):
        title = str(item.get("title") or "آهنگ")[:32]
        lines.append(f"{index}. {html.escape(title)} · {html.escape(str(item.get('artist') or ''))}")
        rows.append([InlineKeyboardButton(text=f"🗑 حذف {index} · {title}", callback_data=f"music_playlist_delete:{item['_id']}")])
    if not items:
        lines.append("پلی‌لیست خالی است.")
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"music_playlist_manage:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="⏭ بعدی", callback_data=f"music_playlist_manage:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="➕ افزودن گروهی آهنگ", callback_data="music_playlist_add")])
    rows.append([InlineKeyboardButton(text="🔙 موزیک امروز", callback_data="music_daily_control")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def _playlist_metadata(message: types.Message) -> tuple[str, str, str, str] | None:
    audio = message.audio
    document = message.document
    if not audio and not document:
        return None
    if document:
        mime = str(document.mime_type or "").lower()
        name = str(document.file_name or "").lower()
        if not mime.startswith("audio/") and not name.endswith((".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus")):
            return None
        file_id = document.file_id
        file_type = "document"
        default_title = Path(document.file_name or "آهنگ").stem
        default_artist = ""
    else:
        file_id = audio.file_id
        file_type = "audio"
        default_title = str(audio.title or "آهنگ")
        default_artist = str(audio.performer or "")
    parts = [part.strip() for part in str(message.caption or "").split("|", 1)]
    title_raw = parts[0] if parts and parts[0] else default_title
    artist_raw = parts[1] if len(parts) > 1 and parts[1] else default_artist
    try:
        title = sanitize_greeting_text(title_raw)[:180]
    except ValueError:
        title = "آهنگ ایرانی"
    try:
        artist = sanitize_greeting_text(artist_raw)[:120] if artist_raw else ""
    except ValueError:
        artist = ""
    return file_id, file_type, title, artist


async def start_music_playlist_upload(message: types.Message, user_id: int | None = None) -> None:
    owner_id = int(user_id if user_id is not None else message.from_user.id)
    music_playlist_upload_sessions[owner_id] = 0
    await message.answer(
        "📤 <b>آپلود گروهی پلی‌لیست ایرانی</b> فعال شد.\n"
        "فایل‌های Audio یا Document صوتی را یکی‌یکی بفرست؛ می‌توانی برای عنوان و خواننده کپشن <code>عنوان | خواننده</code> بگذاری.\n"
        "بعد از هر تعداد آهنگ، روی «✅ پایان آپلود» بزن یا /cancel بنویس. لینک و آیدی از نام/کپشن حذف می‌شود.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ پایان آپلود", callback_data="music_playlist_done"),
            InlineKeyboardButton(text="❌ لغو حالت", callback_data="music_playlist_done"),
        ]]),
    )


async def save_playlist_upload(message: types.Message) -> None:
    user_id = message.from_user.id
    metadata = await _playlist_metadata(message)
    if not metadata:
        return await message.answer("❌ یک فایل صوتی MP3/M4A/FLAC/OGG یا Audio تلگرام بفرست.")
    file_id, file_type, title, artist = metadata
    await public_music_playlist_col.insert_one({
        "_id": uuid.uuid4().hex[:14],
        "title": title,
        "artist": artist,
        "file_id": file_id,
        "file_type": file_type,
        "active": True,
        "uploaded_by": user_id,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    music_playlist_upload_sessions[user_id] = music_playlist_upload_sessions.get(user_id, 0) + 1
    await message.answer(
        f"✅ «{html.escape(title)}» به پلی‌لیست عمومی اضافه شد.\n"
        f"تعداد این نوبت: {music_playlist_upload_sessions[user_id]}\n"
        "آهنگ بعدی را بفرست یا «پایان آپلود» را بزن. لینک و آیدی از عنوان/کپشن حذف شد.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ پایان آپلود", callback_data="music_playlist_done"),
            InlineKeyboardButton(text="🛠 مدیریت پلی‌لیست", callback_data="music_playlist_manage:0"),
        ]]),
    )


async def send_playlist_item(user_id: int, item_id: str) -> None:
    item = await public_music_playlist_col.find_one({"_id": item_id, "active": {"$ne": False}})
    if not item:
        return await bot.send_message(user_id, "❌ این آهنگ دیگر در پلی‌لیست عمومی نیست.", reply_markup=music_reply_menu())
    caption = f"🎵 {item.get('title') or 'آهنگ'}"
    if item.get("artist"):
        caption += f" · {item['artist']}"
    caption += "\n📚 پلی‌لیست عمومی موزیک ایرانی"
    if item.get("file_type") == "audio":
        await bot.send_audio(user_id, item["file_id"], caption=caption)
    else:
        await bot.send_document(user_id, item["file_id"], caption=caption)


async def select_daily_music(date_key: str) -> tuple[dict, str, str]:
    history = await _recent_scheduled_history("daily_music")
    previous = [item.get("core_text") or item.get("text") or "" for item in history]
    playlist = await public_music_playlist_col.find({"active": {"$ne": False}}).sort("created_at", 1).to_list(length=500)
    safe_playlist = [
        item for item in playlist
        if not any(scheduled_messages_similar(f"{item.get('title')} {item.get('artist')}", old) for old in previous)
    ]
    if playlist:
        if not safe_playlist:
            raise MediaServiceError(
                "playlist_exhausted",
                "تمام آهنگ‌های پلی‌لیست در ۶ ماه اخیر استفاده شده‌اند؛ آهنگ‌های تازه اضافه کن تا تکرار نشود.",
            )
        digest = hashlib.sha256(f"playlist:{date_key}".encode()).digest()
        item = safe_playlist[int.from_bytes(digest[:4], "big") % len(safe_playlist)]
        core = f"{item.get('title') or 'آهنگ'} {item.get('artist') or ''}".strip()
        return item, core, "playlist"
    session = _music_session()
    try:
        items = await search_iranian_songs(session, "ترند ایرانی موزیک امروز", 12)
    finally:
        if session is not http_session:
            await session.close()
    candidates = [
        item for item in items
        if not any(scheduled_messages_similar(f"{item.get('title')} {item.get('artist')}", old) for old in previous)
    ] or items
    digest = hashlib.sha256(f"catalog:{date_key}".encode()).digest()
    item = candidates[int.from_bytes(digest[:4], "big") % len(candidates)]
    core = f"{item.get('title') or 'موزیک ایرانی'} {item.get('artist') or ''}".strip()
    return item, core, "catalog"


async def send_daily_music_item(target_id: int | str, item: dict, source: str, *, _retry: bool = True) -> tuple[bool, str]:
    title = str(item.get("title") or "موزیک ایرانی")
    artist = str(item.get("artist") or "")
    caption = f"🎵 امروز موزیک چی گوش کنیم؟\n\n{title}{f' · {artist}' if artist else ''}"
    try:
        if source == "playlist":
            if item.get("file_type") == "audio":
                await bot.send_audio(target_id, item["file_id"], caption=caption)
            else:
                await bot.send_document(target_id, item["file_id"], caption=caption)
        else:
            caption += "\n\n🇮🇷 یک پیشنهاد ایرانی از کاتالوگ امروز"
            url = str(item.get("watch_url") or item.get("permalink") or "")
            markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 شنیدن/تماشا", url=url[:2000])]]) if url.startswith("http") else None
            await bot.send_message(target_id, caption, reply_markup=markup)
        return True, caption
    except TelegramRetryAfter as exc:
        if not _retry:
            return False, caption
        await asyncio.sleep(exc.retry_after)
        return await send_daily_music_item(target_id, item, source, _retry=False)
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        log.warning("daily music send failed: %s", exc)
        return False, caption


@dp.callback_query(F.data == "music_daily_control")
async def music_daily_control_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    await callback.message.edit_text(_daily_music_control_text(), parse_mode="HTML", reply_markup=_daily_music_control_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "music_daily_toggle")
async def music_daily_toggle_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    if not runtime_settings.get("daily_music_target_id"):
        return await callback.answer("اول مقصد را وصل کن.", show_alert=True)
    new_value = not bool(runtime_settings.get("daily_music_enabled"))
    runtime_settings["daily_music_enabled"] = new_value
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"daily_music_enabled": new_value}}, upsert=True)
    await callback.message.edit_text(_daily_music_control_text(), parse_mode="HTML", reply_markup=_daily_music_control_keyboard())
    await callback.answer("موزیک امروز فعال شد ✅" if new_value else "موزیک امروز غیرفعال شد ⏸")


@dp.callback_query(F.data == "music_daily_connect")
async def music_daily_connect_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    music_daily_target_sessions.add(callback.from_user.id)
    await callback.message.answer("🔗 آیدی یا لینک عمومی مقصد موزیک را بفرست: @channel یا -100... یا https://t.me/... /cancel", parse_mode="HTML")
    await callback.answer("مقصد را بفرست 🔗")


@dp.callback_query(F.data == "music_daily_disconnect")
async def music_daily_disconnect_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    music_daily_target_sessions.discard(callback.from_user.id)
    runtime_settings.update({
        "daily_music_target_enabled": False,
        "daily_music_target_id": None,
        "daily_music_target_title": "",
        "daily_music_target_type": "",
        "daily_music_target_username": "",
        "daily_music_target_link": "",
    })
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"daily_music_target_enabled": False}, "$unset": {
        "daily_music_target_id": "", "daily_music_target_title": "", "daily_music_target_type": "",
        "daily_music_target_username": "", "daily_music_target_link": "",
    }}, upsert=True)
    await callback.message.edit_text(_daily_music_control_text(), parse_mode="HTML", reply_markup=_daily_music_control_keyboard())
    await callback.answer("اتصال قطع شد ✅")


@dp.callback_query(F.data == "music_daily_time")
async def music_daily_time_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    music_daily_time_sessions.add(callback.from_user.id)
    await callback.message.answer("🕒 زمان ارسال را به وقت تهران بفرست؛ مثال <code>12:30</code>. /cancel", parse_mode="HTML")
    await callback.answer("زمان را بفرست 🕒")


@dp.callback_query(F.data == "music_daily_test")
async def music_daily_test_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    target_id = runtime_settings.get("daily_music_target_id")
    if not target_id:
        return await callback.answer("اول مقصد را وصل کن.", show_alert=True)
    try:
        item, _core, source = await select_daily_music(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        sent, _caption = await send_daily_music_item(target_id, item, source)
    except Exception as exc:
        log.warning("daily music test failed: %s", exc)
        sent = False
    await callback.answer("موزیک تست ارسال شد ✅" if sent else "ارسال تست ناموفق بود.", show_alert=True)


@dp.callback_query(F.data == "music_playlist_public")
async def music_playlist_public_callback(callback: types.CallbackQuery):
    await show_public_music_playlist(callback.message, 0, edit=True, admin=is_admin(callback.from_user.id))
    await callback.answer()


@dp.callback_query(F.data.startswith("music_playlist_public:"))
async def music_playlist_public_page_callback(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        page = 0
    await show_public_music_playlist(callback.message, page, edit=True, admin=is_admin(callback.from_user.id))
    await callback.answer()


@dp.callback_query(F.data == "music_playlist_add")
async def music_playlist_add_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    await start_music_playlist_upload(callback.message, callback.from_user.id)
    await callback.answer("حالت آپلود گروهی فعال شد 🎵")


@dp.callback_query(F.data == "music_playlist_done")
async def music_playlist_done_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    count = music_playlist_upload_sessions.pop(callback.from_user.id, 0)
    await callback.message.answer(f"✅ آپلود گروهی پایان یافت؛ {count} آهنگ ثبت شد.", reply_markup=music_reply_menu())
    await callback.answer("تمام شد ✅")


@dp.callback_query(F.data.startswith("music_playlist_manage:"))
async def music_playlist_manage_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    try:
        page = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        page = 0
    await show_music_playlist_manage(callback.message, page, edit=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("music_playlist_delete:"))
async def music_playlist_delete_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ فقط مدیر ربات.", show_alert=True)
    item_id = callback.data.split(":", 1)[1]
    await public_music_playlist_col.update_one({"_id": item_id}, {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}})
    await show_music_playlist_manage(callback.message, 0, edit=True)
    await callback.answer("آهنگ از پلی‌لیست عمومی حذف شد ✅")


@dp.callback_query(F.data.startswith("musicplaylist:"))
async def music_playlist_item_callback(callback: types.CallbackQuery):
    item_id = callback.data.split(":", 1)[1]
    await callback.answer("در حال ارسال آهنگ…")
    try:
        await send_playlist_item(callback.from_user.id, item_id)
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        log.warning("playlist item send failed: %s", exc)
        await callback.message.answer("❌ ارسال آهنگ ناموفق بود.", reply_markup=music_reply_menu())


@dp.callback_query(F.data == "music_back")
async def music_back_callback(callback: types.CallbackQuery):
    await callback.message.answer("🎵 بخش موسیقی:", reply_markup=music_reply_menu())
    await callback.answer()


async def daily_music_worker():
    while True:
        try:
            target_id = runtime_settings.get("daily_music_target_id") if runtime_settings.get("daily_music_target_enabled") else None
            if target_id and runtime_settings.get("daily_music_enabled"):
                now = datetime.now(timezone(timedelta(hours=3, minutes=30)))
                target_time = runtime_settings.get("daily_music_time", "12:00")
                due, date_key = daily_music_due(now, target_time)
                if due and runtime_settings.get("daily_music_last_date") != date_key:
                    already = await scheduled_message_history_col.find_one({"kind": "daily_music", "date_key": date_key, "status": "sent"})
                    if already:
                        runtime_settings["daily_music_last_date"] = date_key
                        continue
                    item, core, source = await select_daily_music(date_key)
                    sent, caption = await send_daily_music_item(target_id, item, source)
                    if sent:
                        await record_scheduled_message_history("daily_music", caption, core, date_key, target_id)
                        runtime_settings["daily_music_last_date"] = date_key
                        await settings_col.update_one({"_id": "runtime"}, {"$set": {"daily_music_last_date": date_key}}, upsert=True)
                        log.info("daily music sent: target=%s,source=%s", target_id, source)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("daily music worker error: %s", exc)
        await asyncio.sleep(30)


@dp.callback_query(F.data.startswith("music_pick:"))
async def music_pick_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        index = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("گزینه نامعتبر است.", show_alert=True)
    await send_music_track_detail(user_id, index)
    await callback.answer()


@dp.callback_query(F.data.startswith("music_dl:"))
async def music_dl_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        _, index_raw, quality = callback.data.split(":")
        index = int(index_raw)
    except (IndexError, ValueError):
        return await callback.answer("گزینه نامعتبر است.", show_alert=True)
    items = music_search_cache.get(user_id) or []
    if index < 0 or index >= len(items):
        return await callback.answer("این نتیجه منقضی شده؛ دوباره جستجو کن.", show_alert=True)
    track = items[index]
    if quality not in QUALITY_PRESETS:
        quality = "original"
    await callback.answer("در صف قرار گرفت ✅")
    await enqueue_music_job(user_id, track, quality)


@dp.callback_query(F.data.startswith("music_preview:"))
async def music_preview_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        index = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("گزینه نامعتبر است.", show_alert=True)
    items = music_search_cache.get(user_id) or []
    if index < 0 or index >= len(items):
        return await callback.answer("این نتیجه منقضی شده؛ دوباره جستجو کن.", show_alert=True)
    track = items[index]
    preview_url = str(track.get("preview_url") or "")
    if not preview_url:
        return await callback.answer("پیش‌نمایشی برای این آهنگ نیست.", show_alert=True)
    await callback.answer("در حال دریافت پیش‌نمایش…")
    session = _music_session()
    try:
        with tempfile.TemporaryDirectory(prefix="ajor-preview-") as folder:
            item = await download_preview(session, preview_url, folder, f"{track.get('title') or 'پیش‌نمایش'} - {track.get('artist') or ''}")
            await send_downloaded_media(
                user_id, item,
                f"▶️ پیش‌نمایش ۳۰ ثانیه\n🎵 {str(track.get('title') or '')} · {str(track.get('artist') or '')}\nℹ️ نسخهٔ کامل از این منبع قابل دانلود نیست؛ با «جستجوی نسخهٔ دانلودی» تلاش کن.",
            )
    except MediaServiceError as exc:
        await bot.send_message(user_id, f"❌ {exc.message}", reply_markup=music_reply_menu())
    except Exception as exc:
        log.warning("preview failed: %s", exc)
        await bot.send_message(user_id, "❌ دریافت پیش‌نمایش ناموفق بود.", reply_markup=music_reply_menu())
    finally:
        if session is not http_session:
            await session.close()


@dp.callback_query(F.data.startswith("music_find:"))
async def music_find_callback(callback: types.CallbackQuery):
    """جستجوی خودکار نسخهٔ دانلودی از منبع دیگر (زنجیرهٔ fallback)."""
    user_id = callback.from_user.id
    try:
        index = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("گزینه نامعتبر است.", show_alert=True)
    items = music_search_cache.get(user_id) or []
    if index < 0 or index >= len(items):
        return await callback.answer("این نتیجه منقضی شده؛ دوباره جستجو کن.", show_alert=True)
    track = items[index]
    query = f"{track.get('title') or ''} {track.get('artist') or ''}".strip()[:100]
    if not query:
        return await callback.answer("نام آهنگ نامشخصه.", show_alert=True)
    await callback.answer("در حال جستجوی نسخهٔ دانلودی…")
    msg = await callback.message.answer(f"🔎 در حال جستجوی نسخهٔ دانلودی «{html.escape(query[:60])}»…", parse_mode="HTML")
    session = _music_session()
    try:
        found = await search_songs(session, query, 6)
    except Exception as exc:
        log.warning("music find failed: %s", exc)
        try:
            await msg.edit_text("❌ جستجوی نسخهٔ دانلودی ناموفق بود.")
        except TelegramBadRequest:
            pass
        return
    finally:
        if session is not http_session:
            await session.close()
    downloadable = next((t for t in found if t.get("downloadable")), None)
    if downloadable:
        music_search_cache[user_id] = [downloadable] + [t for t in found if t is not downloadable]
        try:
            await msg.edit_text(
                f"✅ نسخهٔ دانلودی پیدا شد!\n{format_music_item(music_search_cache[user_id][0])}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎧 دانلود کیفیت اصلی", callback_data="music_dl:0:original")],
                    [
                        InlineKeyboardButton(text="🔉 ۱۲۸k", callback_data="music_dl:0:high"),
                        InlineKeyboardButton(text="🔈 ۶۴k", callback_data="music_dl:0:low"),
                    ],
                ]),
            )
        except TelegramBadRequest:
            pass
    else:
        try:
            await msg.edit_text(
                "🤷 نسخهٔ کامل دانلودی پیدا نشد؛ ولی می‌تونی پیش‌نمایش رسمی یا لینک تماشا رو بگیری.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    ([InlineKeyboardButton(text="▶️ پیش‌نمایش", callback_data=f"music_preview:{index}")] if track.get("preview_url") else []) +
                    ([InlineKeyboardButton(text="🌐 تماشا", url=str(track["watch_url"])[:2000])] if track.get("watch_url") else []),
                ]),
            )
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "music_list")
async def music_list_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    items = music_search_cache.get(user_id) or []
    if not items:
        return await callback.answer("لیستی نیست؛ دوباره جستجو کن.", show_alert=True)
    lines = ["🎵 <b>نتایج</b>", ""]
    for index, item in enumerate(items):
        lines.append(f"{index + 1}. {format_music_item(item)}")
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"{index + 1}. {str(item.get('title') or '')[:34]}", callback_data=f"music_pick:{index}")]
        for index, item in enumerate(items)
    ]
    rows.append([InlineKeyboardButton(text="🔁 جستجوی دوباره", callback_data="music_search_again")])
    try:
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass
    await callback.answer()


@dp.callback_query(F.data == "music_trending")
async def music_trending_callback(callback: types.CallbackQuery):
    await callback.answer("در حال دریافت…")
    await present_music_trending(callback.from_user.id)


@dp.callback_query(F.data == "music_iranian_trending")
async def music_iranian_trending_callback(callback: types.CallbackQuery):
    await callback.answer("در حال دریافت ترند ایرانی…")
    await present_music_iranian_trending(callback.from_user.id)


@dp.callback_query(F.data == "music_iranian_search_again")
async def music_iranian_search_again_callback(callback: types.CallbackQuery):
    music_search_sessions.add(callback.from_user.id)
    await callback.message.answer("🇮🇷 نام آهنگ، خواننده یا «ریمیکس» را بفرست. /cancel", reply_markup=music_reply_menu())
    await callback.answer()


@dp.callback_query(F.data == "music_search_again")
async def music_search_again_callback(callback: types.CallbackQuery):
    music_search_sessions.add(callback.from_user.id)
    await callback.message.answer("🎵 اسم آهنگ یا خواننده رو بفرست. /cancel", reply_markup=music_reply_menu())
    await callback.answer()


async def requeue_media_job(callback: types.CallbackQuery, prefix: str, mode: str) -> None:
    job_id = callback.data[len(prefix):]
    job = await media_jobs_col.find_one({"_id": job_id, "user_id": callback.from_user.id})
    if not job:
        return await callback.answer("این درخواست دیگر موجود نیست.", show_alert=True)
    try:
        new_job = await enqueue_media_job(callback.from_user.id, job["url"], mode, "bot")
    except MediaServiceError as exc:
        return await callback.answer(f"❌ {exc.message}", show_alert=True)
    await callback.message.answer(
        f"✅ در صف قرار گرفت.\nشناسه: <code>{new_job['_id']}</code>\nنتیجه همین‌جا فرستاده می‌شه.",
        parse_mode="HTML", reply_markup=media_download_reply_menu(),
    )
    await callback.answer("در صف قرار گرفت ✅")


@dp.callback_query(F.data.startswith("media_caption:"))
async def media_caption_callback(callback: types.CallbackQuery):
    """ارسال دوباره کپشن پست به‌صورت قابل‌کپی."""
    job_id = callback.data.split(":", 1)[1]
    job = await media_jobs_col.find_one({"_id": job_id, "user_id": callback.from_user.id})
    if not job:
        return await callback.answer("درخواست پیدا نشد.", show_alert=True)
    caption = str(job.get("post_caption") or "").strip()
    if not caption:
        return await callback.answer("برای این پست متنی ذخیره نشده.", show_alert=True)
    await callback.message.answer(
        f"📝 <b>متن قابل‌کپی پست</b>\n\n<code>{html.escape(caption)}</code>",
        parse_mode="HTML",
    )
    await callback.answer("متن آماده شد ✅")


@dp.callback_query(F.data.startswith("media_retry:"))
async def media_retry_callback(callback: types.CallbackQuery):
    """تلاش دوباره برای همان job بدون مصرف سهمیهٔ روزانهٔ جدید."""
    job_id = callback.data.split(":", 1)[1]
    job = await media_jobs_col.find_one({"_id": job_id, "user_id": callback.from_user.id})
    if not job:
        return await callback.answer("درخواست پیدا نشد.", show_alert=True)
    if job.get("status") in {"queued", "processing"}:
        return await callback.answer("این درخواست همین حالا در حال پردازش است.", show_alert=True)
    await media_jobs_col.update_one(
        {"_id": job_id, "user_id": callback.from_user.id},
        {"$set": {"status": "queued", "requeued_at": datetime.now(timezone.utc)},
         "$unset": {"failure": "", "failure_message": "", "completed_at": "", "processing_started_at": ""}},
    )
    await callback.message.answer(
        f"✅ درخواست <code>{job_id}</code> دوباره وارد صف شد؛ نتیجه همین‌جا ارسال می‌شود.",
        parse_mode="HTML", reply_markup=media_download_reply_menu(),
    )
    await callback.answer("در صف قرار گرفت ✅")


@dp.callback_query(F.data.startswith("media_audio:"))
async def media_audio_callback(callback: types.CallbackQuery):
    await requeue_media_job(callback, "media_audio:", "audio")


@dp.callback_query(F.data.startswith("media_video:"))
async def media_video_callback(callback: types.CallbackQuery):
    await requeue_media_job(callback, "media_video:", "social")


@dp.callback_query(F.data.startswith("media_identify:"))
async def media_identify_callback(callback: types.CallbackQuery):
    """🎤 شناسایی آهنگ ویدئوی دانلودشده."""
    user_id = callback.from_user.id
    job_id = callback.data.split(":", 1)[1]
    await callback.answer("🎤 در حال شناسایی آهنگ...")
    job = await media_jobs_col.find_one({"_id": job_id})
    if not job or job.get("user_id") != user_id:
        return await callback.answer("❌ درخواست پیدا نشد.", show_alert=True)
    url = job.get("url", "")
    if not url:
        return await callback.answer("❌ لینک پیدا نشد.", show_show_alert=True)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # دانلود صوت از لینک
            await callback.message.answer("🎤 در حال استخراج صوت و شناسایی آهنگ...")
            item = await download_audio_track(url, tmpdir, 10 * 1024 * 1024)
            if item and item[1]:
                audio_path = item[1][0].path
                with open(audio_path, "rb") as f:
                    audio_data = f.read()
                result = await recognize_audio(audio_data)
                if result and result.get("title"):
                    song_info = f"🎵 <b>{html.escape(result['title'])}</b>"
                    if result.get("artist"):
                        song_info += f"\n👤 {html.escape(result['artist'])}"
                    if result.get("album"):
                        song_info += f"\n💿 {html.escape(result['album'])}"
                    await callback.message.answer(song_info, parse_mode="HTML")
                else:
                    await callback.message.answer("❌ آهنگ شناسایی نشد. ممکنه صدا کافی نباشه یا آهنگ توی دیتابیس نباشه.")
            else:
                await callback.message.answer("❌ استخراج صوت ناموفق بود.")
    except Exception as exc:
        log.warning("music identify failed: %s", exc)
        await callback.message.answer("❌ شناسایی آهنگ ناموفق بود.")


@dp.callback_query(F.data == "game")
async def game(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    await callback.message.answer("🎮 یک بازی انتخاب کن:", reply_markup=game_menu())
    await callback.answer()

@dp.callback_query(F.data == "hit_run_start")
async def hit_run_start(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("اول مراحل عضویت و دسترسی رو کامل کن!", show_alert=True)
    hit_run_sessions[callback.from_user.id] = {
        "hits": 0,
        "goal": 8,
        "started": time.monotonic(),
        "message_id": None,
    }
    sent = await callback.message.answer(
        "🏃 <b>بازی بزن در رو</b>\n\nهدف فراری را ۸ بار در کمتر از ۱۵ ثانیه بزن!\nامتیاز: ۰/۸",
        reply_markup=hit_run_keyboard(),
        parse_mode="HTML",
    )
    hit_run_sessions[callback.from_user.id]["message_id"] = sent.message_id
    await log_activity(callback.from_user.id, "hit_run_start", "شروع بزن در رو")
    await callback.answer("شروع شد؛ سریع باش! ⚡")


@dp.callback_query(F.data == "hit_run_hit")
async def hit_run_hit(callback: types.CallbackQuery):
    state = hit_run_sessions.get(callback.from_user.id)
    if not state or state.get("message_id") != callback.message.message_id:
        return await callback.answer("این بازی منقضی شده؛ دوباره شروعش کن.", show_alert=True)
    elapsed = time.monotonic() - state["started"]
    if elapsed > 15:
        hit_run_sessions.pop(callback.from_user.id, None)
        await callback.message.edit_text(
            f"⏰ وقت تموم شد!\n\nرکورد این دور: {state['hits']}/{state['goal']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 دوباره بازی کن", callback_data="hit_run_start")],
                [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
            ]),
        )
        await record_game(callback.from_user.id, "hit_run", False, state["hits"])
        return await callback.answer("وقت تموم شد!", show_alert=True)

    state["hits"] += 1
    if state["hits"] >= state["goal"]:
        hit_run_sessions.pop(callback.from_user.id, None)
        milliseconds = int(elapsed * 1000)
        xp = max(25, 90 - int(elapsed * 4))
        await record_game(callback.from_user.id, "hit_run", True, xp)
        await callback.message.edit_text(
            f"🏆 <b>گرفتمت!</b>\n\n۸ ضربه در <b>{elapsed:.2f} ثانیه</b>\n⚡ جایزه: +{xp} XP",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 رکورد جدید", callback_data="hit_run_start")],
                [InlineKeyboardButton(text="🏆 جدول رکوردها", callback_data="leaderboard")],
            ]),
            parse_mode="HTML",
        )
        await users_col.update_one(
            {"_id": callback.from_user.id},
            {"$min": {"hit_run_best_ms": milliseconds}},
        )
        return await callback.answer("عالی زدی! 🔥")

    await callback.message.edit_text(
        f"🏃 <b>بزن در رو</b>\n\nسریع‌تر! هدف داره فرار می‌کنه...\nامتیاز: {state['hits']}/{state['goal']}",
        reply_markup=hit_run_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer(f"ضربه {state['hits']} از {state['goal']}")


@dp.callback_query(F.data == "hit_run_miss")
async def hit_run_miss(callback: types.CallbackQuery):
    await callback.answer("اونجا نبود! 😜")


@dp.callback_query(F.data == "hit_run_cancel")
async def hit_run_cancel(callback: types.CallbackQuery):
    state = hit_run_sessions.pop(callback.from_user.id, None)
    if state:
        await record_game(callback.from_user.id, "hit_run", False, state.get("hits", 0))
    await callback.message.edit_text("بازی بزن در رو متوقف شد.", reply_markup=game_menu())
    await callback.answer()


@dp.callback_query(F.data == "dice")
async def dice(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    result = await callback.message.answer_dice(emoji="🎲")
    won = bool(result.dice and result.dice.value >= 5)
    await record_game(callback.from_user.id, "dice", won, 12 if won else 4)
    await callback.answer("۵ و ۶ جایزه بیشتری دارن! 🎲")

@dp.callback_query(F.data == "dart")
async def dart(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    result = await callback.message.answer_dice(emoji="🎯")
    won = bool(result.dice and result.dice.value >= 5)
    await record_game(callback.from_user.id, "dart", won, 12 if won else 4)
    await callback.answer("وسط هدف یعنی برد! 🎯")

@dp.callback_query(F.data == "rps")
async def rps(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    await callback.message.answer("🪨 یکی رو انتخاب کن:", reply_markup=rps_menu())
    await callback.answer()

@dp.callback_query(F.data.in_(["rps_stone", "rps_paper", "rps_scissors"]))
async def rps_play(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    choices = {
        "rps_stone": {"name": "🪨 سنگ", "beats": "rps_scissors"},
        "rps_paper": {"name": "📄 کاغذ", "beats": "rps_stone"},
        "rps_scissors": {"name": "✂️ قیچی", "beats": "rps_paper"},
    }
    user_choice = callback.data
    bot_choice = random.choice(list(choices.keys()))
    user_emoji = choices[user_choice]["name"]
    bot_emoji = choices[bot_choice]["name"]
    if user_choice == bot_choice:
        result = "🤝 مساوی!"
    elif choices[user_choice]["beats"] == bot_choice:
        result = "🎉 بردی!"
    else:
        result = "😢 باختی!"
    await callback.message.answer(f"تو: {user_emoji}\nربات: {bot_emoji}\n\n{result}")
    won = result.startswith("🎉")
    await record_game(callback.from_user.id, "rps", won, 15 if won else 5)
    await callback.answer()

MEMORY_EMOJIS = ["🍎", "🍌", "🍇", "🍉", "🍓", "🍒", "🥝", "🍍"]
MEMORY_BEST_MOVES = 12  # رکورد حافظه: پیدا کردن همه جفت‌ها در ۱۲ حرکت


def _memory_board_keyboard(token: str, game: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in range(4):
        buttons: list[InlineKeyboardButton] = []
        for col in range(4):
            idx = row * 4 + col
            state = game["state"][idx]
            if state == 2:
                text = MEMORY_EMOJIS[game["board"][idx]]
            elif state == 1:
                text = MEMORY_EMOJIS[game["board"][idx]]
            else:
                text = "❓"
            buttons.append(InlineKeyboardButton(text=text, callback_data=f"mem_card:{token}:{idx}"))
        rows.append(buttons)
    rows.append([InlineKeyboardButton(text="❌ پایان بازی", callback_data=f"mem_quit:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _memory_game_text(game: dict) -> str:
    if game["mode"] == "duo":
        return (
            f"🧠 <b>جورچین حافظه</b> — دونفره\n"
            f"👤 {html.escape(game['names'][1])}: {game['scores'][1]} جفت\n"
            f"👤 {html.escape(game['names'][2])}: {game['scores'][2]} جفت\n\n"
            f"نوبت: <b>{html.escape(game['names'][game['turn']])}</b>\n"
            "جفت‌ها رو پیدا کن؛ هر جفت = یک امتیاز"
        )
    return (
        f"🧠 <b>جورچین حافظه</b> — تکنفره\n"
        f"حرکت: {game['moves']} · رکورد: {MEMORY_BEST_MOVES}\n\n"
        "همه جفت‌ها رو با کمترین حرکت پیدا کن!"
    )


@dp.callback_query(F.data == "mem_start")
async def mem_start(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    await callback.message.answer(
        "🧠 <b>جورچین حافظه</b>\n\nحالت بازی رو انتخاب کن:\n"
        "• <b>تکنفره:</b> رکورد بزن — همه جفت‌ها در ۱۲ حرکت یا کمتر\n"
        "• <b>دونفره:</b> با رفیق/کاپلت نوبتی بازی کن — هرکی جفت بیشتری پیدا کنه برنده‌ست",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧍 تکنفره", callback_data="mem_solo"),
             InlineKeyboardButton(text="👥 دونفره", callback_data="mem_duo")],
            [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
        ]),
    )
    await callback.answer()


def _new_memory_game(chat_id: int, player1: int, name1: str, mode: str) -> tuple[str, dict]:
    token = uuid.uuid4().hex[:8]
    board = MEMORY_EMOJIS * 2
    random.shuffle(board)
    game: dict = {
        "chat_id": chat_id, "mode": mode, "token": token,
        "players": {1: player1, 2: None}, "names": {1: name1, 2: None},
        "board": board, "state": [0] * 16, "first": None,
        "turn": 1, "scores": {1: 0, 2: 0}, "moves": 0,
        "waiting": mode == "duo", "created_at": time.monotonic(),
    }
    return token, game


@dp.callback_query(F.data == "mem_solo")
async def mem_solo(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    token, game = _new_memory_game(callback.message.chat.id, callback.from_user.id, callback.from_user.full_name or "بازیکن", "solo")
    memory_games[token] = game
    sent = await callback.message.answer(
        _memory_game_text(game), parse_mode="HTML", reply_markup=_memory_board_keyboard(token, game),
    )
    game["message_id"] = sent.message_id
    await callback.answer("بازی شروع شد! 🧠")


@dp.callback_query(F.data == "mem_duo")
async def mem_duo(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    token, game = _new_memory_game(callback.message.chat.id, callback.from_user.id, callback.from_user.full_name or "بازیکن", "duo")
    memory_games[token] = game
    sent = await callback.message.answer(
        f"🧠 <b>جورچین حافظه — دونفره</b>\n\n"
        f"👤 {html.escape(game['names'][1])} دعوتت می‌کنه!\n"
        "نفر دوم دکمه «ورود به بازی» رو بزنه تا شروع بشه.\n"
        "🎮 اگه توی یک گروه هستید، نفر دوم از همون گروه وارد بشه.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 ورود به بازی", callback_data=f"mem_join:{token}")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data=f"mem_quit:{token}")],
        ]),
    )
    game["message_id"] = sent.message_id
    await callback.answer("در انتظار نفر دوم… 👥")


@dp.callback_query(F.data.startswith("mem_join:"))
async def mem_join(callback: types.CallbackQuery):
    token = callback.data.split(":", 1)[1]
    game = memory_games.get(token)
    if not game or not game.get("waiting"):
        return await callback.answer("این بازی موجود نیست یا شروع شده.", show_alert=True)
    if game["players"][1] == callback.from_user.id:
        return await callback.answer("تو خودتی! منتظر نفر دوم باش 😄", show_alert=True)
    game["players"][2] = callback.from_user.id
    game["names"][2] = callback.from_user.full_name or "بازیکن ۲"
    game["waiting"] = False
    game["turn"] = random.choice([1, 2])
    await callback.message.edit_text(
        _memory_game_text(game), parse_mode="HTML", reply_markup=_memory_board_keyboard(token, game),
    )
    await callback.answer("بازی شروع شد! 🧠")
    await log_activity(game["players"][1], "memory_duo", f"opponent={callback.from_user.id}")
    await log_activity(callback.from_user.id, "memory_duo", f"opponent={game['players'][1]}")


@dp.callback_query(F.data.startswith("mem_card:"))
async def mem_card(callback: types.CallbackQuery):
    _, token, idx_raw = callback.data.split(":", 2)
    game = memory_games.get(token)
    if not game:
        return await callback.answer("این بازی منقضی شده؛ دوباره شروعش کن.", show_alert=True)
    if game.get("waiting"):
        return await callback.answer("هنوز نفر دوم وارد نشده.", show_alert=True)
    if game["mode"] == "duo" and game["players"][game["turn"]] != callback.from_user.id:
        return await callback.answer(f"نوبت {game['names'][game['turn']]} هست!", show_alert=True)
    try:
        idx = int(idx_raw)
    except ValueError:
        return await callback.answer("کارت نامعتبر است.", show_alert=True)
    if not (0 <= idx < 16) or game["state"][idx] != 0:
        return await callback.answer("این کارت قبلاً باز شده.", show_alert=True)
    game["moves"] += 1
    if game["first"] is None:
        game["first"] = idx
        game["state"][idx] = 1
    else:
        first = game["first"]
        game["state"][idx] = 1
        game["first"] = None
        if game["board"][first] == game["board"][idx]:
            game["state"][first] = 2
            game["state"][idx] = 2
            game["scores"][game["turn"]] += 1
            finished = all(s == 2 for s in game["state"])
            try:
                await callback.message.edit_text(
                    _memory_game_text(game), parse_mode="HTML", reply_markup=_memory_board_keyboard(token, game),
                )
            except TelegramBadRequest:
                pass
            if finished:
                await _finish_memory_game(callback, token, game)
            return
        # جفت نبود — نمایش کوتاه و برگشت
        try:
            await callback.message.edit_text(
                _memory_game_text(game), parse_mode="HTML", reply_markup=_memory_board_keyboard(token, game),
            )
        except TelegramBadRequest:
            pass
        await asyncio.sleep(1.3)
        if memory_games.get(token) is not game:
            return
        game["state"][first] = 0
        game["state"][idx] = 0
        if game["mode"] == "duo":
            game["turn"] = 3 - game["turn"]
        try:
            await callback.message.edit_text(
                _memory_game_text(game), parse_mode="HTML", reply_markup=_memory_board_keyboard(token, game),
            )
        except TelegramBadRequest:
            pass
        return
    try:
        await callback.message.edit_text(
            _memory_game_text(game), parse_mode="HTML", reply_markup=_memory_board_keyboard(token, game),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


async def _finish_memory_game(callback: types.CallbackQuery, token: str, game: dict) -> None:
    if game["mode"] == "duo":
        s1, s2 = game["scores"][1], game["scores"][2]
        if s1 > s2:
            winner = game["players"][1]
            text = f"🏆 <b>{html.escape(game['names'][1])} برنده شد!</b>\n{s1} به {s2}"
        elif s2 > s1:
            winner = game["players"][2]
            text = f"🏆 <b>{html.escape(game['names'][2])} برنده شد!</b>\n{s2} به {s1}"
        else:
            winner = None
            text = f"🤝 مساوی شد! هر دو {s1} جفت"
        await record_game(game["players"][1], "memory", winner == game["players"][1], 25 if winner == game["players"][1] else 10)
        await record_game(game["players"][2], "memory", winner == game["players"][2], 25 if winner == game["players"][2] else 10)
    else:
        moves = game["moves"]
        if moves <= MEMORY_BEST_MOVES:
            rating, won, xp = "👑 افسانه‌ای!", True, 40
        elif moves <= 16:
            rating, won, xp = "🔥 خیلی خوب!", True, 25
        elif moves <= 24:
            rating, won, xp = "😊 خوب بود!", False, 10
        else:
            rating, won, xp = "🐢 تمرین بیشتر لازمه!", False, 5
        text = f"🎉 تموم شد! توی {moves} حرکت\nرتبه: {rating}"
        await record_game(game["players"][1], "memory", won, xp)
    memory_games.pop(token, None)
    try:
        await callback.message.edit_text(
            f"🧠 <b>جورچین حافظه</b>\n\n{text}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 دوباره بازی کن", callback_data="mem_start")],
                [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
            ]),
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("mem_quit:"))
async def mem_quit(callback: types.CallbackQuery):
    token = callback.data.split(":", 1)[1]
    game = memory_games.pop(token, None)
    if not game:
        return await callback.answer("بازی وجود نداره.", show_alert=True)
    await callback.message.edit_text(
        "❌ بازی حافظه تمام شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
        ]),
    )
    await callback.answer("بازی بسته شد.")


# ================= بیست و یک 🃏 =================

def _bj_text(game: dict) -> str:
    def hand_line(pid: int, hidden: bool = False) -> str:
        name = game["names"][pid]
        cards = game["hands"][pid]
        if hidden and cards:
            shown = f"🃏{cards[0]} + ❓"
            total = "؟"
        else:
            shown = " + ".join(f"🃏{c}" for c in cards) if cards else "—"
            total = str(sum(cards))
        return f"👤 {html.escape(name)}: {shown} = <b>{total}</b>"
    lines = ["🃏 <b>بیست و یک</b>"]
    if game["mode"] == "solo":
        lines.append(hand_line(1))
        lines.append(hand_line(2, hidden=game.get("bot_hidden", False)))
    else:
        lines.append(hand_line(1))
        lines.append(hand_line(2))
        lines.append(f"نوبت: <b>{html.escape(game['names'][game['turn']])}</b>")
    return "\n".join(lines)


def _bj_keyboard(token: str, game: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[
        InlineKeyboardButton(text="🃏 برداشت کارت", callback_data=f"bj_hit:{token}"),
        InlineKeyboardButton(text="✋ ایست", callback_data=f"bj_stand:{token}"),
    ]]
    if game["mode"] == "duo":
        rows.append([InlineKeyboardButton(text="❌ پایان بازی", callback_data=f"bj_quit:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "bj_start")
async def bj_start(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    await callback.message.answer(
        "🃏 <b>بیست و یک</b>\n\nبه ۲۱ نزدیک‌تر باش، ولی از ۲۱ بیشتر نشو!\n"
        "• <b>تکنفره:</b> با ربات\n"
        "• <b>دونفره:</b> با رفیق/کاپلت — هرکی نزدیک‌تر به ۲۱ برنده‌ست",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧍 تکنفره (با ربات)", callback_data="bj_solo"),
             InlineKeyboardButton(text="👥 دونفره", callback_data="bj_duo")],
            [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
        ]),
    )
    await callback.answer()


def _new_bj_game(chat_id: int, player1: int, name1: str, mode: str) -> tuple[str, dict]:
    token = uuid.uuid4().hex[:8]
    game: dict = {
        "chat_id": chat_id, "mode": mode, "token": token,
        "players": {1: player1, 2: None}, "names": {1: name1, 2: None},
        "hands": {1: [random.randint(1, 11), random.randint(1, 11)], 2: [random.randint(1, 11), random.randint(1, 11)]},
        "turn": 1, "stood": set(), "phase": "playing",
        "waiting": mode == "duo", "bot_hidden": True, "created_at": time.monotonic(),
    }
    return token, game


@dp.callback_query(F.data == "bj_solo")
async def bj_solo(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    token, game = _new_bj_game(callback.message.chat.id, callback.from_user.id, callback.from_user.full_name or "بازیکن", "solo")
    game["names"][2] = "🤖 ربات"
    game["players"][2] = None
    twenty_one_games[token] = game
    sent = await callback.message.answer(
        _bj_text(game), parse_mode="HTML", reply_markup=_bj_keyboard(token, game),
    )
    game["message_id"] = sent.message_id
    await callback.answer("بازی شروع شد! 🃏")


@dp.callback_query(F.data == "bj_duo")
async def bj_duo(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    token, game = _new_bj_game(callback.message.chat.id, callback.from_user.id, callback.from_user.full_name or "بازیکن", "duo")
    twenty_one_games[token] = game
    sent = await callback.message.answer(
        f"🃏 <b>بیست و یک — دونفره</b>\n\n👤 {html.escape(game['names'][1])} دعوتت می‌کنه!\n"
        "نفر دوم «ورود به بازی» رو بزنه.\n🎮 توی گروه، نفر دوم از همون گروه وارد بشه.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 ورود به بازی", callback_data=f"bj_join:{token}")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data=f"bj_quit:{token}")],
        ]),
    )
    game["message_id"] = sent.message_id
    await callback.answer("در انتظار نفر دوم… 👥")


@dp.callback_query(F.data.startswith("bj_join:"))
async def bj_join(callback: types.CallbackQuery):
    token = callback.data.split(":", 1)[1]
    game = twenty_one_games.get(token)
    if not game or not game.get("waiting"):
        return await callback.answer("این بازی موجود نیست یا شروع شده.", show_alert=True)
    if game["players"][1] == callback.from_user.id:
        return await callback.answer("تو خودتی! منتظر نفر دوم باش 😄", show_alert=True)
    game["players"][2] = callback.from_user.id
    game["names"][2] = callback.from_user.full_name or "بازیکن ۲"
    game["waiting"] = False
    game["turn"] = random.choice([1, 2])
    await callback.message.edit_text(_bj_text(game), parse_mode="HTML", reply_markup=_bj_keyboard(token, game))
    await callback.answer("بازی شروع شد! 🃏")
    await log_activity(game["players"][1], "bj_duo", f"opponent={callback.from_user.id}")
    await log_activity(callback.from_user.id, "bj_duo", f"opponent={game['players'][1]}")


@dp.callback_query(F.data.startswith("bj_hit:"))
async def bj_hit(callback: types.CallbackQuery):
    token = callback.data.split(":", 1)[1]
    game = twenty_one_games.get(token)
    if not game or game["phase"] != "playing":
        return await callback.answer("این بازی منقضی شده؛ دوباره شروعش کن.", show_alert=True)
    if game["mode"] == "duo" and game["players"][game["turn"]] != callback.from_user.id:
        return await callback.answer(f"نوبت {game['names'][game['turn']]} هست!", show_alert=True)
    pid = game["turn"]
    game["hands"][pid].append(random.randint(1, 11))
    total = sum(game["hands"][pid])
    if total > 21:
        await _bj_bust(callback, token, game, pid)
        return
    if total == 21:
        await _bj_twenty_one(callback, token, game, pid)
        return
    try:
        await callback.message.edit_text(_bj_text(game), parse_mode="HTML", reply_markup=_bj_keyboard(token, game))
    except TelegramBadRequest:
        pass
    await callback.answer()


async def _bj_bust(callback: types.CallbackQuery, token: str, game: dict, pid: int) -> None:
    game["phase"] = "done"
    name = game["names"][pid]
    if game["mode"] == "solo":
        result = f"💥 {html.escape(name)} از ۲۱ رد شد!\n🤖 ربات برنده شد!"
        await record_game(game["players"][1], "bj", False, 5)
    else:
        winner_pid = 3 - pid
        result = f"💥 {html.escape(name)} از ۲۱ رد شد!\n🏆 <b>{html.escape(game['names'][winner_pid])} برنده شد!</b>"
        await record_game(game["players"][1], "bj", winner_pid == 1, 25 if winner_pid == 1 else 10)
        await record_game(game["players"][2], "bj", winner_pid == 2, 25 if winner_pid == 2 else 10)
    twenty_one_games.pop(token, None)
    try:
        await callback.message.edit_text(
            f"{_bj_text(game)}\n\n{result}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 دوباره بازی کن", callback_data="bj_start")],
                [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
            ]),
        )
    except TelegramBadRequest:
        pass


async def _bj_twenty_one(callback: types.CallbackQuery, token: str, game: dict, pid: int) -> None:
    game["phase"] = "done"
    name = game["names"][pid]
    if game["mode"] == "solo":
        result = f"🎉 <b>{html.escape(name)} به ۲۱ رسید!</b>\n🤖 ربات باخت!"
        await record_game(game["players"][1], "bj", True, 30)
    else:
        result = f"🎉 <b>{html.escape(name)} به ۲۱ رسید!</b>\n🏆 برنده شد!"
        await record_game(game["players"][pid], "bj", True, 30)
        await record_game(game["players"][3 - pid], "bj", False, 5)
    twenty_one_games.pop(token, None)
    try:
        await callback.message.edit_text(
            f"{_bj_text(game)}\n\n{result}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 دوباره بازی کن", callback_data="bj_start")],
                [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
            ]),
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("bj_stand:"))
async def bj_stand(callback: types.CallbackQuery):
    token = callback.data.split(":", 1)[1]
    game = twenty_one_games.get(token)
    if not game or game["phase"] != "playing":
        return await callback.answer("این بازی منقضی شده؛ دوباره شروعش کن.", show_alert=True)
    if game["mode"] == "duo" and game["players"][game["turn"]] != callback.from_user.id:
        return await callback.answer(f"نوبت {game['names'][game['turn']]} هست!", show_alert=True)
    pid = game["turn"]
    game["stood"].add(pid)
    if game["mode"] == "duo":
        if len(game["stood"]) == 2:
            await _bj_compare(callback, token, game)
            return
        game["turn"] = 3 - game["turn"]
        try:
            await callback.message.edit_text(_bj_text(game), parse_mode="HTML", reply_markup=_bj_keyboard(token, game))
        except TelegramBadRequest:
            pass
        await callback.answer()
        return
    # تکنفره: ربات بازی می‌کند
    bot_pid = 2
    game["bot_hidden"] = False
    while sum(game["hands"][bot_pid]) < 17:
        game["hands"][bot_pid].append(random.randint(1, 11))
    await _bj_compare(callback, token, game)


async def _bj_compare(callback: types.CallbackQuery, token: str, game: dict) -> None:
    game["phase"] = "done"
    game["bot_hidden"] = False
    t1 = sum(game["hands"][1])
    t2 = sum(game["hands"][2])
    if game["mode"] == "solo":
        if t2 > 21 or t1 > t2:
            result = f"🎉 <b>{html.escape(game['names'][1])} برنده شد!</b>\n{t1} به {t2}"
            await record_game(game["players"][1], "bj", True, 25)
        elif t1 == t2:
            result = f"🤝 مساوی! {t1} به {t2}"
            await record_game(game["players"][1], "bj", False, 10)
        else:
            result = f"😢 ربات برنده شد!\n{t1} به {t2}"
            await record_game(game["players"][1], "bj", False, 5)
    else:
        if t1 > 21 and t2 > 21:
            result = "💥 هر دو از ۲۱ رد شدید! مساوی!"
            winner = None
        elif t1 > 21:
            result = f"🏆 <b>{html.escape(game['names'][2])} برنده شد!</b>\n{t2} به {t1}"
            winner = 2
        elif t2 > 21 or t1 > t2:
            result = f"🏆 <b>{html.escape(game['names'][1])} برنده شد!</b>\n{t1} به {t2}"
            winner = 1
        elif t1 == t2:
            result = f"🤝 مساوی! {t1} به {t2}"
            winner = None
        else:
            result = f"🏆 <b>{html.escape(game['names'][2])} برنده شد!</b>\n{t2} به {t1}"
            winner = 2
        await record_game(game["players"][1], "bj", winner == 1, 25 if winner == 1 else 10)
        await record_game(game["players"][2], "bj", winner == 2, 25 if winner == 2 else 10)
    twenty_one_games.pop(token, None)
    try:
        await callback.message.edit_text(
            f"{_bj_text(game)}\n\n{result}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 دوباره بازی کن", callback_data="bj_start")],
                [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
            ]),
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("bj_quit:"))
async def bj_quit(callback: types.CallbackQuery):
    token = callback.data.split(":", 1)[1]
    game = twenty_one_games.pop(token, None)
    if not game:
        return await callback.answer("بازی وجود نداره.", show_alert=True)
    await callback.message.edit_text(
        "❌ بازی بیست و یک تمام شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 منوی بازی", callback_data="back_game")],
        ]),
    )
    await callback.answer("بازی بسته شد.")


@dp.callback_query(F.data == "guess_game")
async def guess_game(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    number = random.randint(1, 20)
    guess_games[callback.from_user.id] = {"number": number, "attempts": 0}
    await callback.message.answer("🔢 من یک عدد بین ۱ تا ۲۰ انتخاب کردم!\nعدد مورد نظر را بفرستید.\nبرای انصراف، /cancel را بفرستید.")
    await log_activity(callback.from_user.id, "guess_game_start", "شروع بازی حدس عدد")
    await callback.answer()

@dp.message(Command("cancel"))
async def cancel_guess(message: types.Message):
    user_id = message.from_user.id
    if user_id in guess_games:
        del guess_games[user_id]
        await message.answer("❌ بازی حدس عدد لغو شد.")
    elif user_id in broadcast_sessions:
        broadcast_sessions.discard(user_id)
        broadcast_targets.pop(user_id, None)
        await message.answer("❌ ارسال پیام همگانی لغو شد.")
    elif user_id in withdrawal_sessions:
        withdrawal_sessions.discard(user_id)
        await message.answer("❌ فرآیند برداشت لغو شد.")
    elif user_id in config_upload_sessions:
        del config_upload_sessions[user_id]
        await message.answer("❌ حالت آپلود پروکسی/کانفیگ لغو شد.")
    elif user_id in hit_run_sessions:
        hit_run_sessions.pop(user_id, None)
        await message.answer("❌ بازی بزن در رو لغو شد.")
    elif user_id in qr_sessions:
        qr_sessions.discard(user_id)
        await message.answer("❌ ساخت QR لغو شد.")
    elif user_id in sticker_sessions:
        sticker_sessions.discard(user_id)
        await message.answer("❌ استیکرسازی لغو شد.")
    elif user_id in gif_sessions:
        gif_sessions.discard(user_id)
        await message.answer("❌ گیف‌سازی لغو شد.")
    elif user_id in video_round_sessions:
        video_round_sessions.discard(user_id)
        await message.answer("❌ تبدیل ویدئو به دایره‌ای لغو شد.", reply_markup=media_download_reply_menu())
    elif user_id in instagram_comment_sessions:
        instagram_comment_sessions.discard(user_id)
        await message.answer("❌ کپی متن کامنت لغو شد.", reply_markup=media_download_reply_menu())
    elif user_id in prompt_image_sessions:
        prompt_image_sessions.pop(user_id, None)
        await message.answer("❌ اجرای پرامپت روی عکس لغو شد.", reply_markup=ai_reply_menu())
    elif user_id in media_request_sessions:
        media_request_sessions.pop(user_id, None)
        await message.answer("❌ درخواست رسانه لغو شد.")
    elif user_id in group_rename_sessions:
        group_rename_sessions.pop(user_id, None)
        await message.answer("❌ تغییر نام لغو شد.", reply_markup=admin_files_reply_menu())
    elif user_id in admin_activity_search_sessions:
        admin_activity_search_sessions.discard(user_id)
        await message.answer("❌ رصد فعالیت لغو شد.", reply_markup=admin_reply_menu())
    elif user_id in music_playlist_upload_sessions:
        count = music_playlist_upload_sessions.pop(user_id, 0)
        await message.answer(f"✅ آپلود گروهی پلی‌لیست پایان یافت؛ {count} آهنگ ثبت شد.", reply_markup=music_reply_menu())
    elif user_id in music_daily_target_sessions:
        music_daily_target_sessions.discard(user_id)
        await message.answer("❌ اتصال مقصد موزیک امروز لغو شد.", reply_markup=music_reply_menu())
    elif user_id in music_daily_time_sessions:
        music_daily_time_sessions.discard(user_id)
        await message.answer("❌ تغییر زمان موزیک امروز لغو شد.", reply_markup=music_reply_menu())
    elif user_id in music_search_sessions or user_id in music_recognize_sessions:
        music_search_sessions.discard(user_id)
        music_recognize_sessions.discard(user_id)
        music_search_cache.pop(user_id, None)
        await message.answer("❌ حالت موزیک لغو شد.", reply_markup=music_reply_menu())
    elif user_id in reminder_sessions:
        reminder_sessions.discard(user_id)
        await message.answer("❌ ساخت یادآور لغو شد.")
    elif user_id in ai_sessions:
        ai_sessions.pop(user_id, None)
        await message.answer("✅ حالت هوش مصنوعی بسته شد.", reply_markup=chat_reply_menu(user_id))
    elif user_id in reschedule_sessions:
        reschedule_sessions.pop(user_id, None)
        await message.answer("❌ تغییر زمان لغو شد.")
    elif user_id in repost_edit_sessions:
        repost_edit_sessions.pop(user_id, None)
        cancel_album_buffers(user_id, "batch_edit")
        await message.answer("❌ ویرایش تک‌پست لغو شد؛ گروه قبلی حفظ شد.", reply_markup=repost_batch_keyboard(len(repost_batches.get(user_id, {}).get("items", []))))
    elif user_id in scheduled_add_sessions:
        scheduled_add_sessions.pop(user_id, None)
        cancel_album_buffers(user_id, "scheduled_add")
        await message.answer("❌ افزودن پست به زمان‌بندی لغو شد.")
    elif user_id in scheduled_edit_sessions:
        scheduled_edit_sessions.pop(user_id, None)
        cancel_album_buffers(user_id, "scheduled_edit")
        await message.answer("❌ ویرایش پست زمان‌بندی‌شده لغو شد.")
    elif user_id in raffle_create_sessions:
        raffle_create_sessions.discard(user_id)
        await message.answer("❌ ساخت قرعه‌کشی لغو شد.")
    elif user_id in prediction_create_sessions:
        prediction_create_sessions.discard(user_id)
        await message.answer("❌ ساخت پیش‌بینی لغو شد.")
    elif user_id in promo_create_sessions:
        promo_create_sessions.discard(user_id)
        await message.answer("❌ ساخت کد لغو شد.")
    elif user_id in promo_sticker_sessions:
        promo_sticker_sessions.pop(user_id, None)
        await message.answer("❌ ساخت کد استیکر لغو شد.")
    elif user_id in gift_redeem_sessions:
        gift_redeem_sessions.discard(user_id)
        await message.answer("❌ ورود کد هدیه لغو شد.")
    elif user_id in mission_create_sessions:
        mission_create_sessions.discard(user_id)
        await message.answer("❌ ساخت مأموریت لغو شد.")
    elif user_id in template_create_sessions:
        template_create_sessions.discard(user_id)
        await message.answer("❌ ساخت قالب لغو شد.")
    elif user_id in ticket_reply_sessions:
        ticket_reply_sessions.pop(user_id, None)
        await message.answer("❌ پاسخ تیکت لغو شد.")
    elif user_id in manual_balance_sessions:
        manual_balance_sessions.pop(user_id, None)
        await message.answer("❌ تغییر موجودی لغو شد.")
    elif user_id in service_shop_setting_sessions:
        service_shop_setting_sessions.pop(user_id, None)
        await message.answer("❌ تغییر تنظیم فروشگاه لغو شد.")
    elif user_id in service_delivery_sessions:
        service_delivery_sessions.pop(user_id, None)
        await message.answer("❌ تحویل سرویس لغو شد.")
    elif user_id in service_receipt_sessions:
        order_id = service_receipt_sessions.pop(user_id, None)
        await service_orders_col.update_one({"_id": order_id, "status": "awaiting_receipt"}, {"$set": {"status": "cancelled"}})
        await message.answer("❌ ارسال رسید و سفارش لغو شد.")
    elif user_id in admin_role_sessions:
        admin_role_sessions.pop(user_id, None)
        await message.answer("❌ افزودن مدیر لغو شد.")
    elif user_id in repost_cta_sessions:
        repost_cta_sessions.discard(user_id)
        await message.answer("❌ ویرایش متن دعوت لغو شد.")
    elif user_id in economy_setting_sessions:
        economy_setting_sessions.pop(user_id, None)
        await message.answer("❌ تغییر تنظیم اقتصادی لغو شد.")
    elif user_id in instant_repost_sessions:
        instant_repost_sessions.pop(user_id, None)
        cancel_album_buffers(user_id, "instant")
        await message.answer("⏹ انتشار فوری متوقف شد.")
    elif user_id in schedule_time_sessions:
        schedule_time_sessions.discard(user_id)
        repost_sessions.discard(user_id)
        repost_edit_sessions.pop(user_id, None)
        repost_batches.pop(user_id, None)
        cancel_album_buffers(user_id, "batch")
        cancel_album_buffers(user_id, "batch_edit")
        await message.answer("❌ ساخت پست زمان‌دار و گروه آن لغو شد.")
    elif user_id in repost_sessions or user_id in repost_batches:
        batch = repost_batches.get(user_id)
        if batch and batch.get("publishing"):
            await message.answer("⏳ انتشار گروه شروع شده و وسط کار قابل لغو نیست.")
        else:
            repost_sessions.discard(user_id)
            repost_edit_sessions.pop(user_id, None)
            repost_batches.pop(user_id, None)
            cancel_album_buffers(user_id, "batch")
            cancel_album_buffers(user_id, "batch_edit")
            await message.answer("❌ گروه بازنشر و همه پست‌های داخلش حذف شد.")
    elif user_id in daily_fal_channel_sessions:
        daily_fal_channel_sessions.discard(user_id)
        await message.answer("❌ اتصال مقصد فال صبحگاهی لغو شد.")
    elif user_id in greeting_target_sessions:
        greeting_target_sessions.discard(user_id)
        await message.answer("❌ اتصال مقصد جمله‌های خودکار لغو شد.")
    elif user_id in greeting_add_sessions:
        session = greeting_add_sessions.pop(user_id, {})
        kind = session.get("kind", "") if isinstance(session, dict) else session
        count = session.get("count", 0) if isinstance(session, dict) else 0
        await message.answer(
            f"❌ حالت افزودن لغو شد؛ {count} جملهٔ ثبت‌شده حفظ شد.",
            reply_markup=scheduled_greeting_keyboard(kind) if kind in GREETING_CONFIG else tools_reply_menu(),
        )
    elif user_id in greeting_edit_sessions:
        kind, _item_id = greeting_edit_sessions.pop(user_id)
        await message.answer("❌ ویرایش جمله لغو شد.", reply_markup=scheduled_greeting_keyboard(kind))
    elif user_id in channel_add_sessions:
        channel_add_sessions.discard(user_id)
        await message.answer("❌ افزودن کانال لغو شد.")
    elif user_id in engagement_post_sessions:
        engagement_post_sessions.discard(user_id)
        await message.answer("❌ تنظیم مرحله تعامل لغو شد.")
    elif user_id in caption_sessions:
        caption_sessions.discard(user_id)
        await message.answer("❌ کپشن‌سازی لغو شد.")
    elif user_id in support_sessions:
        support_sessions.discard(user_id)
        await message.answer("❌ ثبت پیام پشتیبانی لغو شد.")
    elif user_id in review_sessions:
        review_sessions.discard(user_id)
        await message.answer("❌ ثبت نظر لغو شد.")
    elif user_id in admin_search_sessions:
        admin_search_sessions.discard(user_id)
        await message.answer("❌ جستجوی کاربر لغو شد.")
    else:
        # پاکسازی سشن رسید ادمین اگر لغو شد
        cleared = False
        for s in list(receipt_sessions):
            if s[0] == user_id:
                receipt_sessions.remove(s)
                cleared = True
        if cleared:
            await message.answer("❌ ارسال رسید لغو شد.")
        else:
            await message.answer("⚠️ شما در حال حاضر هیچ عملیات فعالی ندارید.")

@dp.message(F.text.func(lambda t: t and t.isdigit()))
async def handle_numeric_input(message: types.Message):
    user_id = message.from_user.id
    if user_id in qr_sessions:
        qr_sessions.discard(user_id)
        await send_qr_result(message, message.text)
        return
    if user_id in gift_redeem_sessions:
        gift_redeem_sessions.discard(user_id)
        await ensure_user(user_id, message.from_user.full_name, username=message.from_user.username)
        return await send_promo_redemption_result(message, await redeem_promo_code(user_id, message.text))
    if user_id in manual_balance_sessions and is_admin(user_id):
        return await complete_manual_balance_change(message)
    if user_id in admin_role_sessions and is_owner(user_id):
        role = admin_role_sessions.pop(user_id); target = int(message.text)
        if target in ADMIN_IDS: return await message.answer("این آیدی از قبل مالک است.")
        await admins_col.update_one({"_id": target}, {"$addToSet": {"roles": role}, "$set": {"active": True, "added_by": user_id, "updated_at": datetime.now(timezone.utc)}, "$unset": {"role": ""}}, upsert=True)
        roles = set(delegated_admins_cache.get(target, set())); roles.add(role); delegated_admins_cache[target] = roles
        await audit_admin_action(user_id, "admin_role_added", f"role={role}", str(target))
        return await message.answer(f"✅ نقش {role} به مدیر {target} اضافه شد. نقش‌های فعلی: {', '.join(sorted(roles))}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👮 مدیریت نقش‌ها", callback_data="admin_roles")]]))
    if user_id in repost_cta_sessions and is_admin(user_id):
        repost_cta_sessions.discard(user_id)
        runtime_settings["repost_cta"] = message.text[:300]
        await settings_col.update_one({"_id": "runtime"}, {"$set": {"repost_cta": message.text[:300]}}, upsert=True)
        return await message.answer(f"✅ متن دعوت بازنشر ذخیره شد:\n\n{message.text[:300]}")
    if user_id in economy_setting_sessions and is_admin(user_id):
        key = economy_setting_sessions.pop(user_id)
        value = int(message.text)
        validation_error = validate_economy_setting_value(key, value)
        if validation_error:
            economy_setting_sessions[user_id] = key
            return await message.answer(validation_error)
        economy_settings[key] = value
        await settings_col.update_one({"_id": "runtime"}, {"$set": {f"economy.{key}": value}}, upsert=True)
        if key == "referral_ai_bonus_cap":
            await users_col.update_many(
                {"ai_referral_text_bonus": {"$gt": value}},
                {"$set": {"ai_referral_text_bonus": value}},
            )
        return await message.answer(f"✅ تنظیم جدید ذخیره شد: {value:,}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 تنظیمات اقتصاد", callback_data="economy_settings")]]))
    if user_id in instant_repost_sessions and is_admin(user_id):
        await publish_instant_repost(message)
        return
    if user_id in repost_sessions and is_admin(user_id):
        await stage_repost(message)
        return

    # رصد فعالیت کاربر
    if user_id in group_rename_sessions and is_admin(user_id):
        group_uuid = group_rename_sessions.pop(user_id, None)
        new_title = message.text.strip()[:60]
        if len(new_title) < 2:
            return await message.answer("❌ نام خیلی کوتاه است؛ دوباره بفرست یا /cancel.")
        await groups_col.update_one({"group_uuid": group_uuid}, {"$set": {"title": new_title}})
        return await message.answer(f"✅ نام گروه به «{html.escape(new_title)}» تغییر کرد.", parse_mode="HTML", reply_markup=admin_files_reply_menu())

    if user_id in admin_activity_search_sessions and is_admin(user_id):
        admin_activity_search_sessions.discard(user_id)
        query = message.text.strip()
        target_id = None
        if query.startswith("@"):
            user_doc = await users_col.find_one({"username": query[1:].strip().lower()})
            if user_doc:
                target_id = user_doc["_id"]
        else:
            try:
                target_id = int(normalize_digits(query).replace(",", "").strip())
            except ValueError:
                target_id = None
        if target_id is None:
            return await message.answer("❌ آیدی معتبر نیست؛ آیدی عددی یا @username بفرست.", reply_markup=admin_reply_menu())
        return await show_user_activity(message, target_id)

    # جستجوی عددی ادمین باید قبل از سایر سشن‌های عددی بررسی شود.
    if user_id in admin_search_sessions and is_admin(user_id):
        admin_search_sessions.discard(user_id)
        target_id = int(message.text)
        user = await users_col.find_one({"_id": target_id})
        if not user:
            return await message.answer("❌ کاربری با این آیدی پیدا نشد.")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"👤 {(user.get('name') or 'بدون نام')[:25]} · {target_id}",
                callback_data=f"admin_user_{target_id}",
            )]
        ])
        return await message.answer("🔎 کاربر پیدا شد:", reply_markup=keyboard)

    # ثبت امن درخواست برداشت
    if user_id in withdrawal_sessions:
        card_number = re.sub(r"\D", "", message.text)
        if not is_valid_card_number(card_number):
            return await message.answer("❌ شماره کارت معتبر نیست. یک شماره کارت ۱۶ رقمی صحیح بفرست یا /cancel")
        pending = await withdrawals_col.find_one({"user_id": user_id, "status": "pending"})
        if pending:
            withdrawal_sessions.discard(user_id)
            return await message.answer("⚠️ یک درخواست برداشت در حال بررسی داری.")
        user = await users_col.find_one({"_id": user_id})
        coins = int(user.get("coins", 0)) if user else 0
        if coins < 50:
            withdrawal_sessions.discard(user_id)
            return await message.answer("❌ موجودی برای برداشت کافی نیست؛ حداقل ۵۰ سکه لازم است.")
        deduct = await users_col.update_one({"_id": user_id, "coins": coins}, {"$inc": {"coins": -coins}})
        if deduct.modified_count == 0:
            return await message.answer("موجودی تغییر کرده؛ دوباره از منوی کیف پول تلاش کن.")
        withdrawal_sessions.discard(user_id)
        withdrawal_id = uuid.uuid4().hex[:8]
        toman = coins * 1000
        await withdrawals_col.insert_one({
            "withdrawal_id": withdrawal_id,
            "user_id": user_id,
            "name": message.from_user.full_name,
            "coins": coins,
            "amount_toman": toman,
            "card_number": card_number,
            "card_masked": mask_card(card_number),
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        })
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 مشاهده درخواست", callback_data=f"withdraw_view_{withdrawal_id}")]
        ])
        admin_text = (
            f"🔔 <b>درخواست برداشت جدید #{withdrawal_id}</b>\n"
            f"👤 {html.escape(message.from_user.full_name)} · <code>{user_id}</code>\n"
            f"🪙 {coins:,} سکه · 💵 <b>{toman:,} تومان</b>\n"
            f"💳 <code>{card_number}</code>"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, admin_text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as exc:
                log.warning("خطا در اعلان برداشت به ادمین %s: %s", admin_id, exc)
        await message.answer(f"✅ درخواست #{withdrawal_id} ثبت شد و در صف بررسی قرار گرفت.")
        await log_activity(user_id, "withdrawal_request", f"id={withdrawal_id}, coins={coins}, card={mask_card(card_number)}")
        return

    # بازی حدس عدد
    if user_id in guess_games:
        if not await is_member(user_id):
            await message.answer("❌ اول مراحل عضویت رو کامل کن!")
            guess_games.pop(user_id, None)
            return
        guess = int(message.text)
        game_state = guess_games[user_id]
        game_state["attempts"] += 1
        target = game_state["number"]
        if guess == target:
            xp = max(10, 45 - game_state["attempts"] * 3)
            await message.answer(
                f"🎉 <b>تبریک! درست حدس زدی!</b>\nعدد {target} بود.\n"
                f"تعداد تلاش: {game_state['attempts']}\n⚡ جایزه: +{xp} XP",
                parse_mode="HTML",
            )
            await record_game(user_id, "guess_number", True, xp)
            del guess_games[user_id]
        elif guess < target:
            await message.answer(f"📈 بیشتر از {guess} است. دوباره تلاش کن.")
        else:
            await message.answer(f"📉 کمتر از {guess} است. دوباره تلاش کن.")

@dp.callback_query(F.data == "admin_withdrawals")
async def admin_withdrawals_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    items = await withdrawals_col.find({"status": "pending"}).sort("created_at", 1).limit(20).to_list(length=20)
    if not items:
        await callback.message.answer("💸 درخواست برداشت در انتظاری وجود ندارد.")
        return await callback.answer()
    rows = [[InlineKeyboardButton(
        text=f"#{item['withdrawal_id']} · {item.get('amount_toman', 0):,} تومان",
        callback_data=f"withdraw_view_{item['withdrawal_id']}",
    )] for item in items]
    await callback.message.answer("💸 درخواست‌های در انتظار:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("withdraw_view_"))
async def admin_withdrawal_view(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    withdrawal_id = callback.data.rsplit("_", 1)[1]
    item = await withdrawals_col.find_one({"withdrawal_id": withdrawal_id})
    if not item:
        return await callback.answer("درخواست پیدا نشد.", show_alert=True)
    method = item.get("method", "legacy")
    if method == "usdt":
        destination = f"USDT-TRC20 · {item.get('amount_usdt')} USDT\nآدرس: <code>{html.escape(item.get('wallet_address', ''))}</code>"
    elif method == "card":
        destination = f"کارت‌به‌کارت · {html.escape(item.get('card_holder', ''))}\nکارت: <code>{item.get('card_number') or item.get('card_masked')}</code>"
    else:
        destination = f"درخواست قدیمی · <code>{item.get('card_number') or item.get('card_masked', '')}</code>"
    text = (
        f"💸 <b>برداشت #{withdrawal_id}</b>\n"
        f"وضعیت: <b>{item.get('status')}</b>\n"
        f"👤 {html.escape(item.get('name', ''))} · <code>{item['user_id']}</code>\n"
        f"💵 <b>{item.get('amount_toman', 0):,} تومان</b>\n{destination}"
    )
    rows = []
    if item.get("status") == "pending":
        rows.append([
            InlineKeyboardButton(text="✅ پرداخت شد", callback_data=f"withdraw_pay_{withdrawal_id}"),
            InlineKeyboardButton(text="↩️ رد و بازگشت", callback_data=f"withdraw_reject_{withdrawal_id}"),
        ])
    rows.append([InlineKeyboardButton(text="🔙 لیست برداشت‌ها", callback_data="admin_withdrawals")])
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("withdraw_pay_") | F.data.startswith("withdraw_reject_"))
async def admin_withdrawal_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    withdrawal_id = callback.data.rsplit("_", 1)[1]
    new_status = "paid" if callback.data.startswith("withdraw_pay_") else "rejected"
    current_item = await withdrawals_col.find_one({"withdrawal_id": withdrawal_id, "status": "pending"})
    if not current_item: return await callback.answer("این درخواست قبلاً بررسی شده است.", show_alert=True)
    if new_status == "paid" and current_item.get("requires_second_approval"):
        approvals = set(current_item.get("approvals", [])); approvals.add(callback.from_user.id)
        await withdrawals_col.update_one({"_id": current_item["_id"]}, {"$set": {"approvals": list(approvals)}})
        if len(approvals) < 2:
            return await callback.answer("تأیید اول ثبت شد؛ یک مدیر مالی دیگر باید تأیید کند.", show_alert=True)
    item = await withdrawals_col.find_one_and_update(
        {"withdrawal_id": withdrawal_id, "status": "pending"},
        {"$set": {
            "status": new_status,
            "processed_at": datetime.now(timezone.utc),
            "processed_by": callback.from_user.id,
        }},
    )
    if not item:
        return await callback.answer("این درخواست قبلاً بررسی شده است.", show_alert=True)
    if new_status == "rejected":
        if item.get("method") in {"card", "usdt"}:
            refund = int(item.get("amount_toman", 0))
            await users_col.update_one({"_id": item["user_id"]}, {"$inc": {"wallet_toman": refund}})
            user_text = f"↩️ درخواست برداشت #{withdrawal_id} رد شد و {refund:,} تومان به کیف پولت برگشت."
        else:
            coins = int(item.get("coins", 0))
            await users_col.update_one({"_id": item["user_id"]}, {"$inc": {"coins": coins}})
            user_text = f"↩️ درخواست برداشت #{withdrawal_id} رد شد و {coins} سکه برگشت."
    else:
        amount_label = f"{item.get('amount_usdt')} USDT" if item.get("method") == "usdt" else f"{int(item.get('amount_toman', 0)):,} تومان"
        user_text = f"✅ برداشت #{withdrawal_id} به مبلغ {amount_label} پرداخت شد. رسید تراکنش به‌زودی برایت ارسال می‌شود."
    await users_col.update_one({"_id": item["user_id"]}, {"$set": {"withdrawal_pending": False}})
    try:
        await bot.send_message(item["user_id"], user_text)
    except Exception:
        pass
    if new_status == "paid":
        receipt_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 ارسال رسید به کاربر", callback_data=f"send_receipt_{item['user_id']}")]])
        await callback.message.answer("✅ پرداخت ثبت شد. حالا رسید را برای کاربر ارسال کن:", reply_markup=receipt_keyboard)
    await log_activity(item["user_id"], f"withdrawal_{new_status}", f"id={withdrawal_id}")
    await callback.answer("وضعیت بروزرسانی شد.", show_alert=True)


@dp.callback_query(F.data.startswith("send_receipt_"))
async def admin_click_receipt(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    
    target_user_id = int(callback.data.split("_")[2])
    receipt_sessions.add((callback.from_user.id, target_user_id))
    
    await callback.message.answer(f"📸 لطفاً عکس رسید بانکی مربوط به کاربر `{target_user_id}` را ارسال کنید (یا /cancel برای انصراف):")
    await callback.answer()

@dp.callback_query(F.data == "coin_flip")
async def coin_flip(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    await callback.message.answer("🪙 شیر یا خط؟ انتخاب کن:", reply_markup=coin_menu())
    await callback.answer()

@dp.callback_query(F.data.in_(["coin_heads", "coin_tails"]))
async def coin_play(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
    user_choice = "شیر" if callback.data == "coin_heads" else "خط"
    bot_choice = random.choice(["شیر", "خط"])
    result = "🎉 بردی!" if user_choice == bot_choice else "😢 باختی!"
    await callback.message.answer(f"تو: {user_choice}\nربات: {bot_choice}\n\n{result}")
    won = user_choice == bot_choice
    await record_game(callback.from_user.id, "coin_flip", won, 12 if won else 4)
    await callback.answer()

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.answer("🏠 منوی اصلی پایین چت باز شد:", reply_markup=chat_reply_menu(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "back_game")
async def back_game(callback: types.CallbackQuery):
    await callback.message.answer("🔙 منوی بازی:", reply_markup=game_menu())
    await callback.answer()

@dp.message(Command("search"))
async def search_user_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    query = message.text.replace("/search ", "").strip()
    if not query or query == "/search":
        return await message.answer("❌ فرمت درست: `/search 12345` یا `/search ali`")

    if query.isdigit():
        user = await users_col.find_one({"_id": int(query)})
        if user:
            return await message.answer(
                f"✅ پیدا شد!\n🆔 آیدی: {user['_id']}\n📛 نام: {user.get('name', 'بدون نام')}\n"
                f"🪙 سکه: {user.get('coins', 0)}\nوضعیت: {'🚫 بن شده' if user.get('is_banned') else '✅ فعال'}"
            )

    safe_query = re.escape(query[:60])
    users = await users_col.find({"name": {"$regex": safe_query, "$options": "i"}}).limit(10).to_list(length=10)
    if users:
        text = "📋 **نتایج جستجو:**\n"
        for u in users:
            text += f"🆔 `{u['_id']}` - {u.get('name', 'بدون نام')}\n"
        await message.answer(text)
    else:
        await message.answer("❌ کسی رو پیدا نکردم.")

@dp.message(Command("ban"))
async def ban_cmd(message: types.Message):
    chat_type = getattr(message.chat.type, "value", str(message.chat.type))
    if chat_type in {"group", "supergroup"}:
        if not await is_chat_admin(message.chat.id, message.from_user.id):
            return await message.answer("⛔ فقط ادمین گروه می‌تواند بن کند.")
        target = await resolve_target(message)
        if not target:
            return await message.answer("روی پیام کاربر ریپلای کن و /ban بفرست؛ یا /ban ID")
        target_id, name = target
        allowed, error = await ensure_moderatable(message.chat.id, target_id)
        if not allowed:
            return await message.answer(error)
        try:
            await bot.ban_chat_member(message.chat.id, target_id)
            return await message.answer(f"🚫 {html.escape(name)} از گروه بن شد.", parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest):
            return await message.answer("❌ بن انجام نشد؛ دسترسی Ban Users ربات را بررسی کن.")
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ دسترسی ندارید!")
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.answer("❌ فرمت: /ban آیدی [دلیل]")
    target_id = int(parts[1]); reason = parts[2] if len(parts) > 2 else "بدون دلیل"
    await users_col.update_one({"_id": target_id}, {"$set": {"is_banned": True, "ban_reason": reason}})
    await message.answer(f"🚫 کاربر {target_id} از ربات بن شد.\nدلیل: {reason}")


@dp.message(Command("unban"))
async def unban_cmd(message: types.Message):
    chat_type = getattr(message.chat.type, "value", str(message.chat.type))
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        return await message.answer("❌ فرمت: /unban آیدی")
    target_id = int(parts[1])
    if chat_type in {"group", "supergroup"}:
        if not await is_chat_admin(message.chat.id, message.from_user.id):
            return await message.answer("⛔ فقط ادمین گروه می‌تواند رفع بن کند.")
        try:
            await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            return await message.answer(f"✅ کاربر {target_id} رفع بن شد.")
        except (TelegramForbiddenError, TelegramBadRequest):
            return await message.answer("❌ رفع بن انجام نشد؛ دسترسی ربات را بررسی کن.")
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ دسترسی ندارید!")
    await users_col.update_one(
        {"_id": target_id},
        {"$set": {"is_banned": False, "private_warning_count": 0}, "$unset": {"bot_banned_until": ""}},
    )
    await message.answer(f"✅ کاربر {target_id} در ربات آنبن شد و اخطارهای فعالش پاک شد.")


@dp.message(Command("mute"))
async def mute_group_user(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه می‌تواند کاربر را ساکت کند.")
    target = await resolve_target(message)
    if not target:
        return await message.answer("روی پیام کاربر ریپلای کن و مثلاً /mute 60 بفرست.")
    target_id, name = target
    parts = (message.text or "").split()
    try:
        minutes = max(1, min(43200, int(parts[1]))) if message.reply_to_message and len(parts) > 1 else 60
    except ValueError:
        return await message.answer("مدت سکوت باید عدد دقیقه باشد؛ مثلاً /mute 60")
    allowed, error = await ensure_moderatable(message.chat.id, target_id)
    if not allowed:
        return await message.answer(error)
    try:
        await bot.restrict_chat_member(message.chat.id, target_id, permissions=types.ChatPermissions(can_send_messages=False), until_date=datetime.now(timezone.utc) + timedelta(minutes=minutes))
        await message.answer(f"🔇 {html.escape(name)} برای {minutes} دقیقه ساکت شد.", parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer("❌ سکوت انجام نشد؛ دسترسی Restrict Members ربات را بررسی کن.")


@dp.message(Command("unmute"))
async def unmute_group_user(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    target = await resolve_target(message)
    if not target:
        return await message.answer("روی پیام کاربر ریپلای کن و /unmute بفرست؛ یا /unmute ID")
    try:
        await bot.restrict_chat_member(message.chat.id, target[0], permissions=full_chat_permissions())
        await message.answer(f"🔊 سکوت {html.escape(target[1])} برداشته شد.", parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer("❌ رفع سکوت انجام نشد؛ دسترسی ربات را بررسی کن.")


@dp.message(Command("kick"))
async def kick_group_user(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    target = await resolve_target(message)
    if not target:
        return await message.answer("روی پیام کاربر ریپلای کن و /kick بفرست؛ یا /kick ID")
    allowed, error = await ensure_moderatable(message.chat.id, target[0])
    if not allowed:
        return await message.answer(error)
    try:
        await bot.ban_chat_member(message.chat.id, target[0])
        await bot.unban_chat_member(message.chat.id, target[0], only_if_banned=True)
        await message.answer(f"👢 {html.escape(target[1])} از گروه حذف شد.", parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer("❌ حذف انجام نشد؛ دسترسی Ban Users ربات را بررسی کن.")


@dp.message(Command("warn"))
async def warn_group_user(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("روی پیام کاربر ریپلای کن و /warn [دلیل] بفرست.")
    reason = (message.text or "").partition(" ")[2].strip() or "اخطار توسط ادمین"
    await issue_group_warning(message, reason, target_user=message.reply_to_message.from_user)


@dp.message(Command("warnings"))
async def group_user_warnings(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    target = await resolve_target(message)
    if not target:
        return await message.answer("روی پیام کاربر ریپلای کن و /warnings بفرست؛ یا /warnings ID")
    data = await warnings_col.find_one({"_id": f"{message.chat.id}:{target[0]}"}) or {}
    await message.answer(f"⚠️ {html.escape(target[1])}\nاخطار فعال: {int(data.get('count', 0))}\nکل اخطارها: {int(data.get('total_warnings', 0))}\nمجازات‌ها: {int(data.get('punishments', 0))}", parse_mode="HTML")


@dp.message(Command("del"))
async def delete_replied_message(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    if not message.reply_to_message:
        return await message.answer("روی پیام موردنظر ریپلای کن و /del بفرست.")
    try:
        await bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer("❌ حذف انجام نشد؛ دسترسی Delete Messages ربات را بررسی کن.")


@dp.message(Command("modpanel"))
async def group_moderation_panel(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    try:
        await install_group_commands(message.chat.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    await message.answer("🛡 پنل مدیریت این گروه:\nمنوی اسلش همین گروه هم بروزرسانی شد؛ حالا / را بزن.", reply_markup=await group_panel_keyboard(message.chat.id))


@dp.message(Command("commands"))
async def group_commands_help(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    await message.answer(
        "📋 <b>دستورات مدیریت گروه</b>\n\n"
        "/modpanel — پنل تنظیمات\n/warn — اخطار با ریپلای\n/mute 60 — سکوت ۶۰ دقیقه\n"
        "/unmute — رفع سکوت\n/kick — حذف عضو\n/ban — بن عضو\n/unban ID — رفع بن\n"
        "/del — حذف پیام ریپلای‌شده\n/warnings — سابقه اخطار\n"
        "/setwelcome متن — تنظیم خوش‌آمد\n/filter add کلمه — افزودن فیلتر\n/filter del کلمه — حذف فیلتر\n/filter list — فهرست فیلترها\n"
        "/trust و /untrust — لیست سفید کاربران\n/allowdomain — دامنه‌های مجاز\n\n"
        "نکته: برای اکثر دستورات روی پیام کاربر ریپلای کن.",
        reply_markup=await group_panel_keyboard(message.chat.id), parse_mode="HTML",
    )


@dp.message(Command("setwelcome"))
async def set_group_welcome(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        return await message.answer("متن خوش‌آمد را بعد از دستور بنویس. متغیرها: {name} و {group}")
    await group_settings_col.update_one({"_id": message.chat.id}, {"$set": {"welcome_text": text[:1000], "welcome_enabled": True}}, upsert=True)
    await message.answer("✅ پیام خوش‌آمد سفارشی ذخیره شد.")


@dp.message(Command("filter"))
async def manage_group_filter(message: types.Message):
    if not await is_chat_admin(message.chat.id, message.from_user.id):
        return await message.answer("⛔ فقط ادمین گروه دسترسی دارد.")
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2 or parts[1] == "list":
        settings = await get_group_settings(message.chat.id)
        words = settings.get("blocked_words", [])
        return await message.answer("🧹 کلمات فیلتر سفارشی:\n" + ("، ".join(words) if words else "هنوز کلمه‌ای ثبت نشده."))
    if len(parts) < 3 or parts[1] not in {"add", "del", "remove"}:
        return await message.answer("فرمت: /filter add کلمه یا /filter del کلمه یا /filter list")
    word = normalize_chat_text(parts[2])[:50]
    if not word:
        return await message.answer("کلمه معتبر نیست.")
    operation = {"$addToSet": {"blocked_words": word}} if parts[1] == "add" else {"$pull": {"blocked_words": word}}
    await group_settings_col.update_one({"_id": message.chat.id}, operation, upsert=True)
    await message.answer("✅ فیلتر سفارشی بروزرسانی شد.")


@dp.message(Command("trust"))
async def trust_group_user(message:types.Message):
    if not await is_chat_admin(message.chat.id,message.from_user.id):return await message.answer("⛔ فقط ادمین.")
    target=await resolve_target(message)
    if not target:return await message.answer("روی پیام کاربر ریپلای کن و /trust بفرست.")
    await group_settings_col.update_one({"_id":message.chat.id},{"$addToSet":{"trusted_users":target[0]}},upsert=True);await message.answer(f"✅ {html.escape(target[1])} به لیست سفید اضافه شد.",parse_mode="HTML")


@dp.message(Command("untrust"))
async def untrust_group_user(message:types.Message):
    if not await is_chat_admin(message.chat.id,message.from_user.id):return await message.answer("⛔ فقط ادمین.")
    target=await resolve_target(message)
    if not target:return await message.answer("روی پیام کاربر ریپلای کن و /untrust بفرست.")
    await group_settings_col.update_one({"_id":message.chat.id},{"$pull":{"trusted_users":target[0]}});await message.answer("✅ از لیست سفید حذف شد.")


def normalized_hostname(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").strip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    return host if re.fullmatch(r"[a-z0-9.-]{1,253}", host) and ".." not in host else ""


def is_allowed_url(url: str, allowed_domains: list[str]) -> bool:
    host = normalized_hostname(url)
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in map(normalized_hostname, allowed_domains) if domain)


@dp.message(Command("allowdomain"))
async def allow_domain_command(message:types.Message):
    if not await is_chat_admin(message.chat.id,message.from_user.id):return await message.answer("⛔ فقط ادمین.")
    parts=(message.text or "").split(maxsplit=2);settings=await get_group_settings(message.chat.id)
    if len(parts)<2 or parts[1]=="list":return await message.answer("🌐 دامنه‌های مجاز:\n"+("\n".join(settings['allowed_domains']) if settings['allowed_domains'] else "خالی"))
    if len(parts)<3 or parts[1] not in {"add","del"}:return await message.answer("/allowdomain add example.com یا /allowdomain del example.com")
    domain=normalized_hostname(parts[2])
    if not domain:return await message.answer("دامنه معتبر نیست؛ نمونه: example.com")
    op={"$addToSet":{"allowed_domains":domain}} if parts[1]=="add" else {"$pull":{"allowed_domains":domain}}
    await group_settings_col.update_one({"_id":message.chat.id},op,upsert=True);await message.answer("✅ فهرست دامنه‌های مجاز بروزرسانی شد.")


@dp.callback_query(F.data == "broadcast_menu")
async def broadcast_menu_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    await callback.message.answer("📢 مخاطب پیام را انتخاب کن:", reply_markup=broadcast_menu())
    await callback.answer()


@dp.callback_query(F.data.in_({"broadcast_start", "broadcast_all", "broadcast_active", "broadcast_inactive", "broadcast_highpoints", "broadcast_noreferral", "broadcast_pending"}))
async def broadcast_start_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    target = {
        "broadcast_active": "active", "broadcast_inactive": "inactive",
        "broadcast_highpoints": "highpoints", "broadcast_noreferral": "noreferral", "broadcast_pending": "pending",
    }.get(callback.data, "all")
    broadcast_sessions.add(callback.from_user.id)
    broadcast_targets[callback.from_user.id] = target
    labels = {"all": "همه کاربران", "active": "فعال‌های ۷ روز اخیر", "inactive": "غیرفعال‌ها", "highpoints": "بالای ۱۰۰۰ امتیاز", "noreferral": "بدون رفرال", "pending": "برداشت در انتظار"}
    await callback.message.answer(
        f"📢 پیام برای <b>{labels[target]}</b> را بفرست. متن، عکس، ویدیو و فایل پشتیبانی می‌شود.\nبرای انصراف /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


async def do_broadcast(admin_id: int, content_message: types.Message):
    target = broadcast_targets.pop(admin_id, "all")
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    query: dict = {"is_banned": {"$ne": True}}
    if target == "active":
        query["last_activity"] = {"$gte": seven_days_ago}
    elif target == "inactive":
        query["$or"] = [{"last_activity": {"$lt": seven_days_ago}}, {"last_activity": {"$exists": False}}]
    elif target == "highpoints": query["xp"] = {"$gte": 1000}
    elif target == "noreferral": query["referral_count"] = {"$in": [0, None]}
    elif target == "pending":
        pending_ids = await withdrawals_col.distinct("user_id", {"status": "pending"}); query["_id"] = {"$in": pending_ids}
    all_users = await users_col.find(query, {"_id": 1}).to_list(length=None)
    total = len(all_users)
    sent, failed = 0, 0
    started = datetime.now(timezone.utc)
    status_msg = await bot.send_message(admin_id, f"📢 شروع ارسال به {total:,} کاربر...")
    for index, user in enumerate(all_users, 1):
        try:
            await content_message.copy_to(user["_id"])
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await content_message.copy_to(user["_id"])
                sent += 1
            except Exception:
                failed += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
            await users_col.update_one({"_id": user["_id"]}, {"$set": {"bot_blocked": True}})
        except Exception as exc:
            failed += 1
            log.warning("خطا در ارسال به %s: %s", user["_id"], exc)
        if index % 100 == 0:
            try:
                await status_msg.edit_text(f"📤 در حال ارسال... {index:,}/{total:,}\n✅ {sent:,} · ❌ {failed:,}")
            except TelegramBadRequest:
                pass
        await asyncio.sleep(0.045)
    await broadcasts_col.insert_one({
        "admin_id": admin_id,
        "target": target,
        "total": total,
        "sent": sent,
        "failed": failed,
        "created_at": started,
        "finished_at": datetime.now(timezone.utc),
    })
    await status_msg.edit_text(f"✅ ارسال تمام شد.\n\nموفق: {sent:,}\nناموفق: {failed:,}\nکل: {total:,}")

def active_service_offer() -> dict | None:
    if not service_shop_settings.get("offer_active"):
        return None
    expires = service_shop_settings.get("offer_expires_at")
    if isinstance(expires, datetime):
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return None
    percent = max(0, min(90, int(service_shop_settings.get("offer_percent", 0) or 0)))
    if percent <= 0:
        return None
    return {
        "percent": percent,
        "title": clean_profile_value(service_shop_settings.get("offer_title"), 100) or "آفر ویژه",
        "expires_at": expires,
    }


def service_plan_price(months: int) -> tuple[int, int, dict | None]:
    plan = SERVICE_PLANS.get(months)
    if not plan:
        raise ValueError("پلن نامعتبر است")
    original = int(plan["price"])
    offer = active_service_offer()
    final = original
    if offer:
        final = max(1_000, original * (100 - offer["percent"]) // 100)
        final = (final // 1_000) * 1_000
    return original, final, offer


def service_type_keyboard(action: str = "buy") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"{item['emoji']} {item['title']} · {item['app']}",
        callback_data=f"svctype:{action}:{key}",
    )] for key, item in SERVICE_CATALOG.items()]
    rows.append([InlineKeyboardButton(text="🏠 منوی سرویس", callback_data="svc:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_plan_keyboard(service_type: str, action: str = "buy", service_id: str = "") -> InlineKeyboardMarkup:
    rows = []
    for months, plan in SERVICE_PLANS.items():
        _, final, offer = service_plan_price(months)
        price = f"{final:,} تومان"
        if offer:
            price += f" · {offer['percent']}٪ تخفیف"
        data = f"svcplan:{action}:{service_type}:{months}"
        if service_id:
            data += f":{service_id}"
        rows.append([InlineKeyboardButton(text=f"{plan['title']} · {price}", callback_data=data)])
    rows.append([InlineKeyboardButton(text="🔙 انتخاب نوع سرویس", callback_data="svc:buy")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def service_payment_keyboard(service_type: str, months: int, service_id: str = "") -> InlineKeyboardMarkup:
    suffix = f":{service_id}" if service_id else ""
    _, final_price, _ = service_plan_price(months)
    rate = await stars_toman_rate()
    stars = max(1, final_price // rate)
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="💰 پرداخت از کیف پول", callback_data=f"svcpay:wallet:{service_type}:{months}{suffix}")],
        [InlineKeyboardButton(text="💳 کارت‌به‌کارت و ارسال رسید", callback_data=f"svcpay:card:{service_type}:{months}{suffix}")],
    ]
    if economy_settings.get("stars_enabled", True):
        rows.insert(1, [InlineKeyboardButton(text=f"⭐ پرداخت با ستاره ({stars:,} ⭐)", callback_data=f"svcpay:stars:{service_type}:{months}{suffix}")])
    rows.append([InlineKeyboardButton(text="🔙 پلن‌ها", callback_data=f"svctype:buy:{service_type}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def notify_service_order_admins(order: dict, title: str) -> None:
    service = SERVICE_CATALOG.get(order.get("service_type"), {})
    text = (
        f"{title}\n\n"
        f"سفارش: <code>{order['_id']}</code>\n"
        f"کاربر: <code>{order['user_id']}</code>\n"
        f"سرویس: {service.get('title', order.get('service_type'))}\n"
        f"مدت: {order.get('months')} ماه\n"
        f"مبلغ: <b>{int(order.get('final_price', 0)):,} تومان</b>\n"
        f"روش: {html.escape(order.get('payment_method', '-'))}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 تحویل کانفیگ", callback_data=f"svcdeliver:{order['_id']}")],
        [InlineKeyboardButton(text="❌ لغو و بازپرداخت", callback_data=f"svccancel:{order['_id']}")],
    ])
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=keyboard)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


async def create_service_order(
    user_id: int,
    service_type: str,
    months: int,
    payment_method: str,
    renewal_service_id: str | None = None,
) -> dict:
    if service_type not in SERVICE_CATALOG or months not in SERVICE_PLANS:
        raise ValueError("سرویس یا پلن نامعتبر است")
    original, final, offer = service_plan_price(months)
    order = {
        "_id": uuid.uuid4().hex[:10].upper(),
        "user_id": user_id,
        "service_type": service_type,
        "months": months,
        "original_price": original,
        "final_price": final,
        "discount_percent": offer["percent"] if offer else 0,
        "offer_title": offer["title"] if offer else None,
        "payment_method": payment_method,
        "renewal_service_id": renewal_service_id,
        "status": "created",
        "created_at": datetime.now(timezone.utc),
    }
    await service_orders_col.insert_one(order)
    return order


async def renew_existing_service(order: dict) -> dict | None:
    service_id = order.get("renewal_service_id")
    if not service_id:
        return None
    service = await user_services_col.find_one({"_id": service_id, "user_id": order["user_id"]})
    if not service:
        return None
    expires = service.get("expires_at")
    if not isinstance(expires, datetime):
        expires = datetime.now(timezone.utc)
    elif expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    start = max(expires, datetime.now(timezone.utc))
    new_expires = start + timedelta(days=30 * int(order["months"]))
    await user_services_col.update_one(
        {"_id": service_id},
        {"$set": {"expires_at": new_expires, "status": "active", "last_renewed_at": datetime.now(timezone.utc)},
         "$push": {"renewal_orders": order["_id"]}},
    )
    await service_orders_col.update_one(
        {"_id": order["_id"]},
        {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc), "service_id": service_id}},
    )
    try:
        await bot.send_message(
            order["user_id"],
            f"✅ سرویس <code>{service_id}</code> تمدید شد.\nاعتبار جدید تا: <b>{format_tehran_datetime(new_expires)}</b>",
            parse_mode="HTML",
            reply_markup=service_reply_menu(),
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    return {**service, "expires_at": new_expires}


async def mark_service_order_paid(order_id: str, approved_by: int | None = None) -> dict | None:
    order = await service_orders_col.find_one({"_id": order_id})
    if not order:
        return None
    await service_orders_col.update_one(
        {"_id": order_id},
        {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc), "approved_by": approved_by}},
    )
    order["status"] = "paid"
    if order.get("renewal_service_id"):
        await renew_existing_service(order)
    else:
        await service_orders_col.update_one({"_id": order_id}, {"$set": {"status": "awaiting_delivery"}})
        order["status"] = "awaiting_delivery"
        await notify_service_order_admins(order, "🛒 <b>سفارش پرداخت‌شده آماده تحویل</b>")
        try:
            await bot.send_message(
                order["user_id"],
                f"✅ پرداخت سفارش <code>{order_id}</code> تأیید شد.\nکانفیگ اختصاصی توسط مدیر آماده و از همین ربات تحویل می‌شود.",
                parse_mode="HTML",
                reply_markup=service_reply_menu(),
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    return order


async def show_user_services(message: types.Message) -> None:
    items = await user_services_col.find({"user_id": message.from_user.id}).sort("created_at", -1).limit(30).to_list(length=30)
    if not items:
        return await message.answer("📱 هنوز سرویس تحویل‌شده‌ای نداری.", reply_markup=service_reply_menu())
    now = datetime.now(timezone.utc)
    lines = ["📱 <b>سرویس‌های من</b>", ""]
    rows = []
    for item in items:
        expires = item.get("expires_at")
        if isinstance(expires, datetime) and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        active = isinstance(expires, datetime) and expires > now and item.get("status") == "active"
        lines.append(
            f"{'🟢' if active else '🔴'} <code>{item['_id']}</code> · {SERVICE_CATALOG.get(item.get('service_type'), {}).get('title', item.get('service_type'))}\n"
            f"   اعتبار تا: {format_tehran_datetime(expires) if isinstance(expires, datetime) else 'نامشخص'}"
        )
        rows.append([InlineKeyboardButton(text=f"♻️ تمدید {item['_id']}", callback_data=f"svcrenew:{item['_id']}")])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def show_service_orders(message: types.Message) -> None:
    items = await service_orders_col.find({"user_id": message.from_user.id}).sort("created_at", -1).limit(10).to_list(length=10)
    if not items:
        return await message.answer("📊 هنوز سفارشی ثبت نکردی.", reply_markup=service_reply_menu())
    labels = {
        "awaiting_receipt": "منتظر رسید", "payment_review": "در بررسی پرداخت",
        "awaiting_delivery": "آماده‌سازی کانفیگ", "paid": "پرداخت‌شده",
        "completed": "تکمیل‌شده", "cancelled": "لغوشده", "payment_rejected": "رسید رد شد",
    }
    lines = ["📊 <b>وضعیت سفارش‌ها</b>", ""]
    for item in items:
        lines.append(
            f"• <code>{item['_id']}</code> · {labels.get(item.get('status'), item.get('status'))}\n"
            f"  {SERVICE_CATALOG.get(item.get('service_type'), {}).get('title', '')} · {int(item.get('final_price',0)):,} تومان"
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=service_reply_menu())


@dp.callback_query(F.data == "svc:home")
async def service_home_callback(callback: types.CallbackQuery):
    await callback.message.answer("🛍 مرکز سرویس اختصاصی:", reply_markup=service_reply_menu())
    await callback.answer()


@dp.callback_query(F.data == "svc:buy")
async def service_buy_callback(callback: types.CallbackQuery):
    await callback.message.answer("🚀 نوع سرویس اختصاصی رو انتخاب کن:", reply_markup=service_type_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("svctype:"))
async def service_type_callback(callback: types.CallbackQuery):
    _, action, service_type = callback.data.split(":", 2)
    if service_type not in SERVICE_CATALOG:
        return await callback.answer("نوع سرویس نامعتبر است.", show_alert=True)
    await callback.message.answer(
        f"{SERVICE_CATALOG[service_type]['emoji']} <b>{SERVICE_CATALOG[service_type]['title']}</b>\nاپ پیشنهادی: {SERVICE_CATALOG[service_type]['app']}\n\nمدت سرویس رو انتخاب کن:",
        parse_mode="HTML",
        reply_markup=service_plan_keyboard(service_type, action),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("svcplan:"))
async def service_plan_callback(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) not in {4, 5}:
        return await callback.answer("پلن نامعتبر است.", show_alert=True)
    _, _action, service_type, months_text, *rest = parts
    try:
        months = int(months_text)
        original, final, offer = service_plan_price(months)
    except (ValueError, TypeError):
        return await callback.answer("پلن نامعتبر است.", show_alert=True)
    service_id = rest[0] if rest else ""
    discount_line = f"\n🎁 {offer['title']} · {offer['percent']}٪ تخفیف\nقیمت قبل: <s>{original:,}</s> تومان" if offer else ""
    await callback.message.answer(
        f"🧾 <b>پیش‌فاکتور سرویس</b>\n\n"
        f"نوع: {SERVICE_CATALOG[service_type]['title']}\n"
        f"مدت: {SERVICE_PLANS[months]['title']}"
        f"{discount_line}\n"
        f"مبلغ نهایی: <b>{final:,} تومان</b>\n\nروش پرداخت رو انتخاب کن:",
        parse_mode="HTML",
        reply_markup=await service_payment_keyboard(service_type, months, service_id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("svcpay:"))
async def service_payment_callback(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) not in {4, 5}:
        return await callback.answer("درخواست نامعتبر است.", show_alert=True)
    _, method, service_type, months_text, *rest = parts
    try:
        months = int(months_text)
        renewal_id = rest[0] if rest else None
        if renewal_id:
            service = await user_services_col.find_one({"_id": renewal_id, "user_id": callback.from_user.id})
            if not service:
                return await callback.answer("سرویس برای تمدید پیدا نشد.", show_alert=True)
            service_type = service["service_type"]
        order = await create_service_order(callback.from_user.id, service_type, months, method, renewal_id)
    except ValueError as exc:
        return await callback.answer(str(exc), show_alert=True)
    if method == "stars":
        try:
            rate = await stars_toman_rate()
            stars = max(1, order["final_price"] // rate)
            title = f"{SERVICE_CATALOG.get(service_type, {}).get('title', 'سرویس')} — {months} ماهه"
            invoice = await bot.create_invoice_link(
                title=title,
                description=f"پرداخت سرویس {title} با ستاره‌های تلگرام",
                payload=f"svc:{order['_id']}",
                currency="XTR",
                prices=[types.LabeledPrice(label=title, amount=stars)],
            )
            await service_orders_col.update_one({"_id": order["_id"]}, {"$set": {"stars": stars}})
            await callback.message.answer(
                f"⭐ <b>پرداخت با ستاره</b>\n\n"
                f"🛒 {html.escape(title)}\n"
                f"💰 مبلغ: <b>{stars:,} ⭐ ستاره</b>\n\n"
                f"🔗 روی دکمه زیر بزن و پرداخت را انجام بده:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"⭐ پرداخت {stars:,} ستاره", url=invoice)],
                    [InlineKeyboardButton(text="🏠 منوی سرویس", callback_data="svc:home")],
                ]),
            )
        except Exception as exc:
            log.warning("stars invoice failed: %s", exc)
            await service_orders_col.update_one({"_id": order["_id"]}, {"$set": {"status": "payment_failed"}})
            return await callback.message.answer(
                "❌ ساخت فاکتور ستاره ناموفق بود. لطفاً بعداً دوباره تلاش کن یا از کیف پول استفاده کن.",
                reply_markup=service_reply_menu(),
            )
        await callback.answer("فاکتور ساخته شد ✅")
        return
    if method == "wallet":
        debit = await users_col.update_one(
            {"_id": callback.from_user.id, "wallet_toman": {"$gte": order["final_price"]}, "wallet_frozen": {"$ne": True}},
            {"$inc": {"wallet_toman": -order["final_price"]}},
        )
        if not debit.modified_count:
            await service_orders_col.update_one({"_id": order["_id"]}, {"$set": {"status": "payment_failed"}})
            return await callback.message.answer(
                f"❌ موجودی کیف پول کافی نیست. مبلغ لازم: {order['final_price']:,} تومان\nاز بخش کیف پول می‌تونی موجودی رو افزایش بدی.",
                reply_markup=service_reply_menu(),
            )
        await wallet_transactions_col.insert_one({
            "user_id": callback.from_user.id, "type": "service_purchase",
            "amount_toman": -order["final_price"], "order_id": order["_id"],
            "created_at": datetime.now(timezone.utc),
        })
        await mark_service_order_paid(order["_id"])
        await callback.answer("پرداخت موفق ✅", show_alert=True)
        return
    card = re.sub(r"\D", "", str(service_shop_settings.get("card_number", "")))
    holder = clean_profile_value(service_shop_settings.get("card_holder"), 80)
    if len(card) != 16 or not holder:
        await service_orders_col.update_one({"_id": order["_id"]}, {"$set": {"status": "card_unavailable"}})
        return await callback.message.answer(
            "⚠️ پرداخت کارت‌به‌کارت فعلاً توسط مدیر تنظیم نشده؛ از کیف پول استفاده کن.",
            reply_markup=service_reply_menu(),
        )
    await service_orders_col.update_one({"_id": order["_id"]}, {"$set": {"status": "awaiting_receipt"}})
    service_receipt_sessions[callback.from_user.id] = order["_id"]
    await callback.message.answer(
        f"💳 <b>کارت‌به‌کارت</b>\n\nمبلغ: <b>{order['final_price']:,} تومان</b>\n"
        f"کارت: <code>{card}</code>\nبه نام: <b>{html.escape(holder)}</b>\n\n"
        f"{html.escape(service_shop_settings.get('payment_note') or '')}\n"
        "حالا عکس رسید رو بفرست. /cancel برای لغو",
        parse_mode="HTML",
        reply_markup=service_reply_menu(),
    )
    await callback.answer("منتظر رسید هستم 📸")


@dp.callback_query(F.data.startswith("svcrenew:"))
async def service_renew_callback(callback: types.CallbackQuery):
    service_id = callback.data.split(":", 1)[1]
    service = await user_services_col.find_one({"_id": service_id, "user_id": callback.from_user.id})
    if not service:
        return await callback.answer("سرویس پیدا نشد.", show_alert=True)
    await callback.message.answer(
        f"♻️ تمدید <code>{service_id}</code>\nمدت جدید رو انتخاب کن:",
        parse_mode="HTML",
        reply_markup=service_plan_keyboard(service["service_type"], "renew", service_id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("svcapprove:") | F.data.startswith("svcreject:"))
async def service_receipt_review_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "finance"):
        return await callback.answer("⛔ دسترسی مالی نداری.", show_alert=True)
    action, order_id = callback.data.split(":", 1)
    order = await service_orders_col.find_one({"_id": order_id, "status": "payment_review"})
    if not order:
        return await callback.answer("سفارش قبلاً بررسی شده.", show_alert=True)
    if action == "svcreject":
        await service_orders_col.update_one(
            {"_id": order_id}, {"$set": {"status": "payment_rejected", "reviewed_by": callback.from_user.id, "reviewed_at": datetime.now(timezone.utc)}}
        )
        try:
            await bot.send_message(order["user_id"], f"❌ رسید سفارش {order_id} تأیید نشد. برای پیگیری با پشتیبانی تماس بگیر.")
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        await callback.answer("رسید رد شد.", show_alert=True)
    else:
        await mark_service_order_paid(order_id, callback.from_user.id)
        await callback.answer("پرداخت تأیید شد ✅", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("svcdeliver:"))
async def service_delivery_start(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی نداری.", show_alert=True)
    order_id = callback.data.split(":", 1)[1]
    order = await service_orders_col.find_one({"_id": order_id, "status": "awaiting_delivery"})
    if not order:
        return await callback.answer("سفارش آماده تحویل پیدا نشد.", show_alert=True)
    service_delivery_sessions[callback.from_user.id] = order_id
    await callback.message.answer(
        f"📦 کانفیگ اختصاصی سفارش <code>{order_id}</code> را به‌صورت متن یا فایل بفرست.\n/cancel برای لغو",
        parse_mode="HTML",
    )
    await callback.answer("منتظر کانفیگ هستم")


@dp.callback_query(F.data.startswith("svccancel:"))
async def service_order_cancel_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "finance"):
        return await callback.answer("⛔ دسترسی مالی نداری.", show_alert=True)
    order_id = callback.data.split(":", 1)[1]
    order = await service_orders_col.find_one({"_id": order_id, "status": {"$in": ["paid", "awaiting_delivery"]}})
    if not order:
        return await callback.answer("سفارش قابل لغو نیست.", show_alert=True)
    if order.get("payment_method") == "wallet":
        await users_col.update_one({"_id": order["user_id"]}, {"$inc": {"wallet_toman": int(order["final_price"])}})
        await wallet_transactions_col.insert_one({
            "user_id": order["user_id"], "type": "service_refund", "amount_toman": int(order["final_price"]),
            "order_id": order_id, "created_at": datetime.now(timezone.utc),
        })
    await service_orders_col.update_one(
        {"_id": order_id}, {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc), "cancelled_by": callback.from_user.id}}
    )
    try: await bot.send_message(order["user_id"], f"ℹ️ سفارش {order_id} لغو شد." + (" مبلغ به کیف پولت برگشت." if order.get("payment_method") == "wallet" else " برای بازپرداخت کارت با پشتیبانی تماس بگیر."))
    except (TelegramForbiddenError, TelegramBadRequest): pass
    await callback.answer("سفارش لغو شد.", show_alert=True)


async def complete_service_delivery(admin_id: int, order_id: str, delivery_type: str, content: str) -> dict | None:
    order = await service_orders_col.find_one({"_id": order_id, "status": "awaiting_delivery"})
    if not order:
        return None
    service_id = uuid.uuid4().hex[:8].upper()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30 * int(order["months"]))
    service = {
        "_id": service_id, "order_id": order_id, "user_id": order["user_id"],
        "service_type": order["service_type"], "months": order["months"],
        "status": "active", "started_at": datetime.now(timezone.utc), "expires_at": expires_at,
        "delivery_type": delivery_type, "created_at": datetime.now(timezone.utc), "delivered_by": admin_id,
    }
    if delivery_type == "text": service["config_text"] = content
    else: service["file_id"] = content
    await user_services_col.insert_one(service)
    await service_orders_col.update_one(
        {"_id": order_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc), "service_id": service_id, "delivered_by": admin_id}}
    )
    intro = (
        f"✅ <b>سرویس اختصاصی شما آماده شد</b>\n\nشناسه: <code>{service_id}</code>\n"
        f"نوع: {SERVICE_CATALOG[order['service_type']]['title']}\n"
        f"اعتبار تا: <b>{format_tehran_datetime(expires_at)}</b>\n\n"
    )
    try:
        if delivery_type == "text":
            await bot.send_message(order["user_id"], intro + f"<code>{html.escape(content)}</code>", parse_mode="HTML", reply_markup=service_reply_menu())
        else:
            await bot.send_document(order["user_id"], content, caption=intro, parse_mode="HTML")
        await bot.send_message(order["user_id"], "💡 اطلاعات کانفیگ را عمومی منتشر نکن. برای آموزش یا تعویض با پشتیبانی تماس بگیر.", reply_markup=service_reply_menu())
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    return service


@dp.callback_query(F.data == "admin_service_shop")
async def admin_service_shop_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی نداری.", show_alert=True)
    pending = await service_orders_col.count_documents({"status": {"$in": ["payment_review", "awaiting_delivery"]}})
    offer = active_service_offer()
    card = re.sub(r"\D", "", str(service_shop_settings.get("card_number", "")))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📦 سفارش‌های در انتظار ({pending})", callback_data="admin_service_orders")],
        [InlineKeyboardButton(text="🎁 تنظیم آفر", callback_data="svcadmin:offer"), InlineKeyboardButton(text="🧹 حذف آفر", callback_data="svcadmin:offer_clear")],
        [InlineKeyboardButton(text="💳 تنظیم کارت پرداخت", callback_data="svcadmin:card")],
        [InlineKeyboardButton(text="📝 متن راهنمای پرداخت", callback_data="svcadmin:note")],
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await callback.message.answer(
        "🛒 <b>فروشگاه سرویس اختصاصی</b>\n\n"
        f"سفارش معطل: <b>{pending}</b>\n"
        f"کارت پرداخت: {'✅ تنظیم شده' if len(card)==16 else '❌ تنظیم نشده'}\n"
        f"آفر: {html.escape(offer['title']) + ' · ' + str(offer['percent']) + '٪' if offer else 'فعلاً تخفیفی موجود نیست'}",
        parse_mode="HTML", reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_service_orders")
async def admin_service_orders_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ دسترسی نداری.", show_alert=True)
    items = await service_orders_col.find({"status": {"$in": ["payment_review", "awaiting_delivery"]}}).sort("created_at", 1).limit(50).to_list(length=50)
    rows = []
    for item in items:
        if item["status"] == "payment_review":
            rows.append([InlineKeyboardButton(text=f"🧾 {item['_id']} · بررسی رسید", callback_data=f"svcapprove:{item['_id']}"), InlineKeyboardButton(text="❌", callback_data=f"svcreject:{item['_id']}")])
        else:
            rows.append([InlineKeyboardButton(text=f"📦 {item['_id']} · تحویل", callback_data=f"svcdeliver:{item['_id']}")])
    rows.append([InlineKeyboardButton(text="🔙 فروشگاه", callback_data="admin_service_shop")])
    await callback.message.answer("📦 سفارش‌های در انتظار:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("svcadmin:"))
async def service_shop_setting_start(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id): return await callback.answer("⛔ فقط مالک.", show_alert=True)
    action = callback.data.split(":", 1)[1]
    if action == "offer_clear":
        service_shop_settings.update({"offer_active": False, "offer_percent": 0, "offer_title": "", "offer_expires_at": None})
        await settings_col.update_one({"_id": "service_shop"}, {"$set": dict(service_shop_settings)}, upsert=True)
        return await callback.answer("آفر حذف شد.", show_alert=True)
    service_shop_setting_sessions[callback.from_user.id] = action
    prompts = {
        "offer": "فرمت آفر: <code>50 | تخفیف آخرشب | 6</code>\nدرصد | عنوان | مدت ساعت",
        "card": "فرمت کارت: <code>621986... | نام صاحب کارت</code>",
        "note": "متن راهنمای پرداخت و ارسال رسید را بفرست.",
    }
    await callback.message.answer(prompts.get(action, "مقدار جدید را بفرست."), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    await callback.message.answer("⚙️ پنل مدیریت پایین چت باز شد:", reply_markup=admin_reply_menu())
    await callback.answer()

DEFAULT_REPOST_CTA = "📣 اخبار و ترندهای روز را از @Ajor_pareh دنبال کنید."


def current_repost_cta() -> str:
    return str(runtime_settings.get("repost_cta", DEFAULT_REPOST_CTA) or "").strip()[:300]


FUNCTIONAL_TELEGRAM_LINKS = {"proxy", "socks", "share", "addstickers", "addemoji", "joinchat", "iv"}


def truncate_entity_html(text: str, entities, max_visible: int) -> str:
    if len(text) <= max_visible:
        return html_decoration.unparse(text=text, entities=entities or [])
    data = add_surrogates(text)
    cut_units = max(0, max_visible - 1)
    cut_bytes = data[: cut_units * 2]
    while cut_bytes:
        try:
            cut_text = remove_surrogates(cut_bytes)
            break
        except UnicodeDecodeError:
            cut_bytes = cut_bytes[:-2]
    else:
        cut_text = ""
    actual_units = len(cut_bytes) // 2
    kept_entities = [
        entity for entity in (entities or [])
        if entity.offset >= 0 and entity.offset + entity.length <= actual_units
    ]
    return html_decoration.unparse(text=cut_text, entities=kept_entities) + "…"


def message_entity_html(message: types.Message, limit: int) -> str:
    raw = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    cta = current_repost_cta()
    reserve = len(cta) + len("\n\n📣 @Ajor_pareh") + 4
    return truncate_entity_html(raw, entities, max(0, limit - reserve))


def replace_telegram_brand_link(match: re.Match) -> str:
    raw = match.group(0)
    path = (match.group("path") or "").lower()
    if path in FUNCTIONAL_TELEGRAM_LINKS:
        return raw
    return "https://t.me/Ajor_pareh"


def build_branded_caption(text: str | None, limit: int) -> str:
    branded = (text or "").strip()
    branded = re.sub(
        r"https?://(?:t\.me|telegram\.me)/(?:s/)?(?P<path>[A-Za-z0-9_]+)(?:/\d+)?(?:\?[^\s\"'<>]*)?",
        replace_telegram_brand_link,
        branded,
        flags=re.I,
    )
    branded = re.sub(r"(?<![\w@])@[A-Za-z0-9_]{5,}", "@Ajor_pareh", branded)
    branded = re.sub(r"(?:@Ajor_pareh\s*){2,}", "@Ajor_pareh ", branded).strip()
    cta = current_repost_cta()
    suffix_parts = []
    if cta:
        suffix_parts.append(cta)
    if "@Ajor_pareh" not in branded and "@Ajor_pareh" not in cta:
        suffix_parts.append("📣 @Ajor_pareh")
    suffix = "\n\n".join(suffix_parts)
    separator = "\n\n" if branded and suffix else ""
    available = max(0, limit - len(separator) - len(suffix))
    if len(branded) > available:
        branded = branded[: max(0, available - 1)].rstrip() + "…"
    return f"{branded}{separator}{suffix}"[:limit]


def build_branded_html(source_html: str) -> str:
    branded = re.sub(
        r"https?://(?:t\.me|telegram\.me)/(?:s/)?(?P<path>[A-Za-z0-9_]+)(?:/\d+)?(?:\?[^\s\"'<>]*)?",
        replace_telegram_brand_link,
        source_html,
        flags=re.I,
    )
    branded = re.sub(r"(?<![\w@])@[A-Za-z0-9_]{5,}", "@Ajor_pareh", branded)
    visible = html.unescape(re.sub(r"<[^>]+>", "", branded))
    cta = current_repost_cta()
    suffix_parts = []
    if cta:
        suffix_parts.append(html.escape(cta))
    if "@Ajor_pareh" not in visible and "@Ajor_pareh" not in cta:
        suffix_parts.append("📣 @Ajor_pareh")
    suffix = "\n\n".join(suffix_parts)
    separator = "\n\n" if branded.strip() and suffix else ""
    return f"{branded.strip()}{separator}{suffix}"


def extract_repost_payload(message: types.Message) -> dict | None:
    if message.photo or message.video or message.animation or message.document or message.audio or message.voice:
        source_html = message_entity_html(message, 1024)
        caption = build_branded_html(source_html)
        if message.photo:
            return {"type": "photo", "file_id": message.photo[-1].file_id, "caption": caption, "parse_mode": "HTML"}
        if message.video:
            return {"type": "video", "file_id": message.video.file_id, "caption": caption, "parse_mode": "HTML"}
        if message.animation:
            return {"type": "animation", "file_id": message.animation.file_id, "caption": caption, "parse_mode": "HTML"}
        if message.audio:
            return {
                "type": "audio", "file_id": message.audio.file_id,
                "caption": caption, "parse_mode": "HTML",
                "title": str(message.audio.title or "")[:64],
                "performer": str(message.audio.performer or "")[:64],
            }
        if message.voice:
            return {"type": "voice", "file_id": message.voice.file_id, "caption": caption, "parse_mode": "HTML"}
        return {"type": "document", "file_id": message.document.file_id, "caption": caption, "parse_mode": "HTML"}
    if message.text:
        source_html = message_entity_html(message, 4096)
        return {"type": "text", "text": build_branded_html(source_html), "parse_mode": "HTML"}
    return None


def build_album_payload(messages: list[types.Message]) -> dict | None:
    ordered = sorted(messages, key=lambda item: item.message_id)
    caption_message = next((item for item in ordered if item.caption), None)
    if caption_message:
        caption_html = message_entity_html(caption_message, 1024)
        caption_source = build_branded_html(caption_html)
    else:
        caption_source = build_branded_caption(None, 1024)
    media_items = []
    for message in ordered[:10]:
        if message.photo:
            media_items.append({"type": "photo", "file_id": message.photo[-1].file_id})
        elif message.video:
            media_items.append({"type": "video", "file_id": message.video.file_id})
        elif message.document:
            media_items.append({"type": "document", "file_id": message.document.file_id})
    if not media_items:
        return None
    return {"type": "album", "items": media_items, "caption": caption_source, "parse_mode": "HTML"}


async def send_repost_payload(chat_id: int, payload: dict, reply_markup=None):
    kind = payload["type"]
    parse_mode = payload.get("parse_mode")
    if kind == "album":
        media = []
        caption = payload.get("caption") or None
        for index, item in enumerate(payload.get("items", [])[:10]):
            item_caption = caption if index == 0 else None
            if item["type"] == "photo":
                media.append(InputMediaPhoto(media=item["file_id"], caption=item_caption, parse_mode=parse_mode if item_caption else None))
            elif item["type"] == "video":
                media.append(InputMediaVideo(media=item["file_id"], caption=item_caption, parse_mode=parse_mode if item_caption else None))
            elif item["type"] == "document":
                media.append(InputMediaDocument(media=item["file_id"], caption=item_caption, parse_mode=parse_mode if item_caption else None))
        if not media:
            raise ValueError("آلبوم خالی است")
        return await bot.send_media_group(chat_id, media=media)
    if kind == "photo":
        return await bot.send_photo(chat_id, payload["file_id"], caption=payload["caption"], parse_mode=parse_mode, reply_markup=reply_markup)
    if kind == "video":
        return await bot.send_video(chat_id, payload["file_id"], caption=payload["caption"], parse_mode=parse_mode, reply_markup=reply_markup)
    if kind == "animation":
        return await bot.send_animation(chat_id, payload["file_id"], caption=payload["caption"], parse_mode=parse_mode, reply_markup=reply_markup)
    if kind == "audio":
        return await bot.send_audio(
            chat_id, payload["file_id"], caption=payload.get("caption"),
            parse_mode=parse_mode, title=payload.get("title") or None,
            performer=payload.get("performer") or None, reply_markup=reply_markup,
        )
    if kind == "voice":
        return await bot.send_voice(chat_id, payload["file_id"], caption=payload.get("caption"), parse_mode=parse_mode, reply_markup=reply_markup)
    if kind == "sticker":
        return await bot.send_sticker(chat_id, payload["file_id"], reply_markup=reply_markup)
    if kind == "document":
        return await bot.send_document(chat_id, payload["file_id"], caption=payload["caption"], parse_mode=parse_mode, reply_markup=reply_markup)
    return await bot.send_message(chat_id, payload["text"], parse_mode=parse_mode, reply_markup=reply_markup)


def published_message_id(result) -> int | None:
    if isinstance(result, list):
        return result[0].message_id if result else None
    return getattr(result, "message_id", None)


async def finalize_repost_album(key: tuple[int, str, str]):
    try:
        await asyncio.sleep(1.35)
        entry = album_buffers.pop(key, None)
        if not entry:
            return
        payload = build_album_payload(entry["messages"])
        if not payload:
            return await entry["last_message"].answer("❌ آلبوم قابل پردازش نبود.")
        if entry["mode"] == "instant":
            await publish_instant_repost(entry["last_message"], payload=payload)
        elif entry["mode"] == "batch_edit":
            await replace_repost_item(entry["last_message"], payload=payload)
        elif entry["mode"] == "scheduled_add":
            await append_scheduled_payload(entry["last_message"], payload=payload)
        elif entry["mode"] == "scheduled_edit":
            await replace_scheduled_payload(entry["last_message"], payload=payload)
        else:
            await stage_repost(entry["last_message"], payload=payload)
    except asyncio.CancelledError:
        return
    except Exception as exc:
        log.exception("پردازش آلبوم بازنشر ناموفق بود: %s", exc)
        entry = album_buffers.pop(key, None)
        if entry:
            await entry["last_message"].answer("❌ پردازش آلبوم ناموفق بود؛ دوباره ارسال کن.")


async def buffer_repost_album(message: types.Message, mode: str):
    key = (message.from_user.id, str(message.media_group_id), mode)
    entry = album_buffers.get(key)
    if not entry:
        entry = {"messages": [], "last_message": message, "mode": mode, "task": None}
        album_buffers[key] = entry
    if all(existing.message_id != message.message_id for existing in entry["messages"]):
        entry["messages"].append(message)
    entry["last_message"] = message
    old_task = entry.get("task")
    if old_task and not old_task.done():
        old_task.cancel()
    entry["task"] = asyncio.create_task(finalize_repost_album(key))


def cancel_album_buffers(user_id: int, mode: str | None = None):
    for key, entry in list(album_buffers.items()):
        if key[0] == user_id and (mode is None or key[2] == mode):
            task = entry.get("task")
            if task and not task.done():
                task.cancel()
            album_buffers.pop(key, None)


def instant_repost_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹ پایان انتشار فوری", callback_data="instant_repost_cancel")],
    ])


async def _auto_delete_button_msg(message: types.Message, delay: float = 0.3) -> None:
    """پیام دکمه ReplyKeyboard رو بعد از تأخیر کوتاه پاک می‌کنه — چت تمیز بمونه."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


async def _auto_delete_instant_confirm(msg: types.Message, delay: int = 5) -> None:
    """پیام تأیید انتشار فوری رو بعد از چند ثانیه پاک می‌کنه."""
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


async def publish_instant_repost(message: types.Message, payload: dict | None = None):
    payload = payload or extract_repost_payload(message)
    if not payload:
        return await message.answer("❌ فقط متن، عکس، ویدئو، گیف یا فایل پشتیبانی می‌شود.", reply_markup=instant_repost_keyboard())
    user_id = message.from_user.id
    # ذخیره message_id پیام اصلی کاربر برای پاک‌سازی بعدی
    if user_id in instant_repost_sessions:
        instant_repost_sessions[user_id].append(message.message_id)
    try:
        published = await send_repost_payload(CHANNEL_ID, payload)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            published = await send_repost_payload(CHANNEL_ID, payload)
        except Exception as retry_exc:
            log.warning("انتشار فوری بعد از retry ناموفق بود: %s", retry_exc)
            return await message.answer("❌ انتشار فوری ناموفق بود؛ دوباره بفرست.", reply_markup=instant_repost_keyboard())
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        log.warning("انتشار فوری ناموفق بود: %s", exc)
        return await message.answer("❌ انتشار نشد؛ دسترسی ارسال پست ربات در کانال را بررسی کن.", reply_markup=instant_repost_keyboard())
    message_id = published_message_id(published)
    await log_activity(user_id, "instant_repost", f"channel={CHANNEL_ID},message={message_id}")
    # پاک‌سازی فوری پیام اصلی کاربر (چت شلوغ نشه)
    try:
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    # تأیید با دکمه پایان — پاک نمیشه تا کاربر دکمه رو بزنه
    try:
        confirm = await message.answer(
            f"✅ <a href=\"https://t.me/Ajor_pareh/{message_id}\">لینک پست</a>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏹ پایان انتشار فوری", callback_data="instant_repost_cancel")],
            ]),
        )
        # تأیید ذخیره بشه تا با پایان انتشار پاک بشه
        if user_id in instant_repost_sessions:
            instant_repost_sessions[user_id].append(confirm.message_id)
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


@dp.callback_query(F.data == "repost_cta_settings")
async def repost_cta_settings_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    repost_cta_sessions.add(callback.from_user.id)
    current = current_repost_cta() or "— غیرفعال —"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♻️ بازگشت به متن پیش‌فرض", callback_data="repost_cta_reset")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    await callback.message.answer(
        "✍️ <b>ویرایش متن دعوت بازنشر</b>\n\n"
        f"متن فعلی:\n<blockquote>{html.escape(current)}</blockquote>\n"
        "متن جدید را در یک پیام بفرست. می‌توانی از ایموجی و @Ajor_pareh استفاده کنی.\n"
        "حداکثر ۳۰۰ کاراکتر. برای حذف کامل متن بنویس <code>خاموش</code> و برای انصراف /cancel.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer("متن جدید رو بفرست ✍️")


@dp.callback_query(F.data == "repost_cta_reset")
async def repost_cta_reset_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    repost_cta_sessions.discard(callback.from_user.id)
    runtime_settings["repost_cta"] = DEFAULT_REPOST_CTA
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"repost_cta": DEFAULT_REPOST_CTA}}, upsert=True)
    await callback.message.answer(f"✅ متن پیش‌فرض برگشت:\n\n{DEFAULT_REPOST_CTA}")
    await callback.answer("بازنشانی شد.", show_alert=True)


@dp.callback_query(F.data == "instant_repost_start")
async def instant_repost_start_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if batch and batch.get("items"):
        return await callback.answer("اول گروه بازنشر باز رو منتشر یا کنسل کن.", show_alert=True)
    repost_sessions.discard(callback.from_user.id)
    cancel_album_buffers(callback.from_user.id)
    # پاک‌سازی session های هوش مصنوعی تا عکس بعدی به‌جای کانال به ساخت تصویر نرود
    prompt_image_sessions.pop(callback.from_user.id, None)
    ai_sessions.pop(callback.from_user.id, None)
    gif_sessions.discard(callback.from_user.id)
    sticker_sessions.discard(callback.from_user.id)
    instant_repost_sessions[callback.from_user.id] = []
    await callback.message.answer(
        "⚡ <b>انتشار فوری فعال شد</b>\n\n"
        "از الان هر پستی بفرستی، مستقیماً با برند @Ajor_pareh در کانال منتشر می‌شه.\n"
        "✅ تأیید کوچیک بعد از ۵ ثانیه خودکار پاک می‌شه — چت شلوغ نمی‌شه.\n"
        "برای توقف از دکمه زیر یا /cancel استفاده کن.",
        reply_markup=instant_repost_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("حالت فوری روشن شد ⚡")


@dp.callback_query(F.data == "instant_repost_cancel")
async def instant_repost_cancel_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    # پاک‌سازی همه پیام‌های ذخیره‌شده
    msg_ids = instant_repost_sessions.pop(callback.from_user.id, [])
    for mid in msg_ids:
        try:
            await bot.delete_message(callback.from_user.id, mid)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    cancel_album_buffers(callback.from_user.id, "instant")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.message.answer("⏹ انتشار فوری متوقف شد.")
    await callback.answer("متوقف شد.", show_alert=True)


def repost_payload_preview(payload: dict) -> str:
    """یک خلاصهٔ کوتاه برای مدیریت تک‌پست، بدون نمایش کامل محتوای پست."""
    if not isinstance(payload, dict):
        return "رسانهٔ نامعتبر"
    labels = {
        "text": "متن",
        "photo": "عکس",
        "video": "ویدئو",
        "animation": "گیف",
        "audio": "آهنگ",
        "voice": "ویس",
        "sticker": "استیکر",
        "document": "فایل",
        "album": "آلبوم",
    }
    kind = labels.get(payload.get("type"), "رسانه")
    raw = payload.get("text") or payload.get("caption") or ""
    raw = html.unescape(re.sub(r"<[^>]+>", "", str(raw)))
    raw = re.sub(r"\s+", " ", raw).strip()
    if payload.get("type") == "album":
        raw = f"{len(payload.get('items') or [])} فایل" + (f" · {raw}" if raw else "")
    return f"{kind} · {raw[:42]}" if raw else kind


def repost_batch_manage_keyboard(batch: dict) -> InlineKeyboardMarkup:
    rows = []
    for index, item in enumerate(batch.get("items", [])):
        preview = repost_payload_preview(item.get("payload") or "")
        rows.append([
            InlineKeyboardButton(text=f"✏️ {index + 1} · {preview[:28]}", callback_data=f"repost_edit:{index}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"repost_delete:{index}"),
        ])
    rows.append([InlineKeyboardButton(text="🔙 برگشت به گروه", callback_data="repost_batch_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_repost_batch_manage(message: types.Message, admin_id: int, *, edit: bool = False) -> None:
    batch = repost_batches.get(admin_id)
    if not batch:
        text = "❌ گروه بازنشر پیدا نشد یا منقضی شده."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return
    items = batch.get("items", [])
    if not items:
        text = "🛠 گروه خالی است. برای اضافه‌کردن پست، روی «پست بعدی را بفرست» بزن."
        markup = repost_batch_keyboard(0)
    else:
        text = (
            f"🛠 <b>مدیریت پست‌های گروه</b> · {len(items)} پست\n\n"
            "برای اصلاح، نسخهٔ جدید همان پست را بفرست؛ برای حذف، دکمهٔ 🗑 را بزن."
        )
        markup = repost_batch_manage_keyboard(batch)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def replace_repost_item(message: types.Message, payload: dict | None = None) -> None:
    """جایگزینی اتمیک یک پست در گروه پیش‌نویس."""
    user_id = message.from_user.id
    index = repost_edit_sessions.get(user_id)
    batch = repost_batches.get(user_id)
    if index is None or not batch:
        repost_edit_sessions.pop(user_id, None)
        return await message.answer("❌ گروه ویرایش پیدا نشد؛ دوباره گروه را باز کن.")
    if batch.get("publishing"):
        repost_edit_sessions.pop(user_id, None)
        return await message.answer("⏳ انتشار گروه شروع شده و دیگر قابل ویرایش نیست.")
    payload = payload or extract_repost_payload(message)
    if not payload:
        return await message.answer("❌ نسخهٔ جدید باید متن، عکس، ویدئو، گیف یا فایل باشد. دوباره بفرست یا /cancel بزن.")
    items = batch.get("items", [])
    if not 0 <= index < len(items):
        repost_edit_sessions.pop(user_id, None)
        return await message.answer("❌ شمارهٔ پست دیگر معتبر نیست؛ گروه را دوباره باز کن.")
    items[index] = {"payload": payload, "published": False}
    batch["created_at"] = time.monotonic()
    repost_edit_sessions.pop(user_id, None)
    repost_sessions.discard(user_id)
    await message.answer(
        f"✅ پست شمارهٔ {index + 1} با نسخهٔ جدید جایگزین شد.\n"
        "برای مدیریت تک‌پست‌ها دکمهٔ زیر را بزن:",
        reply_markup=repost_batch_keyboard(len(items)),
    )


async def append_scheduled_payload(message: types.Message, payload: dict | None = None) -> None:
    """افزودن یک پست به زمان‌بندی pending با شرط وضعیت و مقایسهٔ نسخه."""
    user_id = message.from_user.id
    job_id = scheduled_add_sessions.get(user_id)
    payload = payload or extract_repost_payload(message)
    if not job_id:
        return await message.answer("❌ جلسهٔ افزودن پست پیدا نشد؛ از فهرست زمان‌بندی دوباره انتخاب کن.")
    if not payload:
        return await message.answer("❌ پست باید متن، عکس، ویدئو، گیف یا فایل باشد. دوباره بفرست یا /cancel بزن.")
    job = await scheduled_posts_col.find_one({"_id": job_id})
    if not job or job.get("status") != "pending":
        scheduled_add_sessions.pop(user_id, None)
        return await message.answer("⛔ این زمان‌بندی دیگر باز نیست؛ اگر انتشار شروع شده، تغییرش ممکن نیست.")
    items = list(job.get("items") or [])
    if len(items) >= 20:
        scheduled_add_sessions.pop(user_id, None)
        return await message.answer("⚠️ سقف هر گروه ۲۰ پست است؛ اول یکی از پست‌ها را حذف کن.")
    updated_items = [*items, payload]
    result = await scheduled_posts_col.update_one(
        {"_id": job_id, "status": "pending", "items": items},
        {"$set": {"items": updated_items, "updated_at": datetime.now(timezone.utc)}},
    )
    if not result.modified_count:
        scheduled_add_sessions.pop(user_id, None)
        return await message.answer("⚠️ گروه هم‌زمان تغییر کرد؛ فهرست زمان‌بندی را دوباره باز کن.")
    scheduled_add_sessions.pop(user_id, None)
    await message.answer(
        f"✅ پست جدید به زمان‌بندی <code>{job_id}</code> اضافه شد.\n"
        f"تعداد فعلی: <b>{len(updated_items)}</b> پست",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛠 مدیریت همین گروه", callback_data=f"schedmanage:{job_id}"),
            InlineKeyboardButton(text="🔙 جزئیات", callback_data=f"schedinfo:{job_id}"),
        ]]),
    )


async def replace_scheduled_payload(message: types.Message, payload: dict | None = None) -> None:
    """جایگزینی اتمیک یک آیتم در زمان‌بندی pending."""
    user_id = message.from_user.id
    session = scheduled_edit_sessions.get(user_id)
    payload = payload or extract_repost_payload(message)
    if not session:
        return await message.answer("❌ جلسهٔ ویرایش زمان‌بندی پیدا نشد؛ دوباره از مدیریت گروه انتخاب کن.")
    job_id, index = session
    if not payload:
        return await message.answer("❌ نسخهٔ جدید باید متن، عکس، ویدئو، گیف یا فایل باشد. دوباره بفرست یا /cancel بزن.")
    job = await scheduled_posts_col.find_one({"_id": job_id})
    if not job or job.get("status") != "pending":
        scheduled_edit_sessions.pop(user_id, None)
        return await message.answer("⛔ انتشار این زمان‌بندی شروع شده یا بسته شده است؛ ویرایش ممکن نیست.")
    items = list(job.get("items") or [])
    if not 0 <= index < len(items):
        scheduled_edit_sessions.pop(user_id, None)
        return await message.answer("❌ شمارهٔ پست دیگر معتبر نیست؛ مدیریت گروه را دوباره باز کن.")
    updated_items = list(items)
    updated_items[index] = payload
    result = await scheduled_posts_col.update_one(
        {"_id": job_id, "status": "pending", "items": items},
        {"$set": {"items": updated_items, "updated_at": datetime.now(timezone.utc)}},
    )
    if not result.modified_count:
        scheduled_edit_sessions.pop(user_id, None)
        return await message.answer("⚠️ گروه هم‌زمان تغییر کرد؛ فهرست را دوباره باز کن.")
    scheduled_edit_sessions.pop(user_id, None)
    await message.answer(
        f"✅ پست شمارهٔ {index + 1} در زمان‌بندی <code>{job_id}</code> ویرایش شد.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛠 مدیریت گروه", callback_data=f"schedmanage:{job_id}"),
        ]]),
    )


def repost_batch_keyboard(count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ پست بعدی را بفرست", callback_data="repost_batch_continue")],
    ]
    if count:
        rows.append([InlineKeyboardButton(text=f"👁 پیش‌نمایش {count} پست", callback_data="repost_batch_preview")])
        rows.append([
            InlineKeyboardButton(text=f"🚀 انتشار همه {count} پست", callback_data="repost_batch_publish"),
            InlineKeyboardButton(text="⏰ زمان‌بندی", callback_data="repost_batch_schedule"),
        ])
        rows.append([InlineKeyboardButton(text="🛠 ویرایش یا حذف یک پست", callback_data="repost_batch_manage")])
    rows.append([InlineKeyboardButton(text="🗑 کنسل و حذف کل گروه", callback_data="repost_batch_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_repost_batch(admin_id: int) -> dict:
    batch = {
        "admin_id": admin_id,
        "items": [],
        "created_at": time.monotonic(),
        "publishing": False,
    }
    repost_batches[admin_id] = batch
    repost_sessions.add(admin_id)
    return batch


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + jd
    days += (jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for length in month_days:
        if gd <= length:
            break
        gd -= length
        gm += 1
    return gy, gm, gd


def normalize_digits(value: str) -> str:
    return value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def parse_schedule_time(value: str) -> datetime:
    value = normalize_digits(value.strip().lower())
    tehran_tz = timezone(timedelta(hours=3, minutes=30))
    now = datetime.now(tehran_tz)
    relative = re.match(r"^(امروز|فردا)\s+(\d{1,2}):(\d{2})$", value)
    if relative:
        target_date = now.date() + timedelta(days=1 if relative.group(1) == "فردا" else 0)
        hour, minute = int(relative.group(2)), int(relative.group(3))
        local = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=tehran_tz)
    else:
        match = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})$", value)
        if not match:
            raise ValueError("فرمت زمان نامعتبر است")
        year, month, day, hour, minute = map(int, match.groups())
        if year < 1700:
            year, month, day = jalali_to_gregorian(year, month, day)
        local = datetime(year, month, day, hour, minute, tzinfo=tehran_tz)
    if local <= now + timedelta(seconds=30):
        raise ValueError("زمان باید در آینده باشد")
    if local > now + timedelta(days=365):
        raise ValueError("حداکثر تا یک سال آینده قابل زمان‌بندی است")
    return local.astimezone(timezone.utc)


def format_tehran_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(timezone(timedelta(hours=3, minutes=30)))
    return local.strftime("%Y-%m-%d %H:%M")


REPEAT_PATTERN = re.compile(
    r"^(?:(هر\s+)?(روزانه|روز|هفتگی|هفته|ماهانه|ماه|شنبه|یکشنبه|دوشنبه|سه‌شنبه|چهارشنبه|پنجشنبه|جمعه))\s+(\d{1,2}):(\d{2})$"
)
REPEAT_WEEKDAY = {
    "شنبه": 5, "یکشنبه": 6, "دوشنبه": 0, "سه‌شنبه": 1,
    "چهارشنبه": 2, "پنجشنبه": 3, "جمعه": 4,
}


def parse_recurring_input(value: str) -> tuple[str | None, datetime, str]:
    """پشتیبانی از یادآورهای تکراری: «هر روز 09:00 | متن»، «هفتگی 08:30 | متن»، «شنبه 10:00 | متن»."""
    parts = [part.strip() for part in normalize_digits(value).split("|", 1)]
    if len(parts) != 2 or not parts[1]:
        raise ValueError("فرمت: فردا 09:00 | متن یادآوری")
    head = parts[0].strip().lower()
    repeat = None
    scheduled_at: datetime | None = None
    match = REPEAT_PATTERN.match(head)
    tehran_tz = timezone(timedelta(hours=3, minutes=30))
    now = datetime.now(tehran_tz)
    if match:
        keyword = match.group(2)
        hour, minute = int(match.group(3)), int(match.group(4))
        if keyword in ("روزانه", "روز"):
            repeat = "daily"
        elif keyword in ("هفتگی", "هفته"):
            repeat = "weekly"
        elif keyword in ("ماهانه", "ماه"):
            repeat = "monthly"
        elif keyword in REPEAT_WEEKDAY:
            repeat = "weekly"
        # اولین اجرا: نزدیک‌ترین زمان آینده
        base = datetime(now.year, now.month, now.day, hour, minute, tzinfo=tehran_tz)
        if repeat == "daily":
            if base <= now:
                base += timedelta(days=1)
        elif repeat == "weekly":
            target_weekday = REPEAT_WEEKDAY.get(keyword, now.weekday())
            delta = (target_weekday - now.weekday()) % 7
            base = datetime(now.year, now.month, now.day, hour, minute, tzinfo=tehran_tz) + timedelta(days=delta)
            if base <= now:
                base += timedelta(days=7)
        elif repeat == "monthly":
            month = now.month + (1 if now.day > 28 else 0)
            year = now.year + (1 if month > 12 else 0)
            month = ((month - 1) % 12) + 1
            base = datetime(year, month, min(hour if False else now.day, 28), hour, minute, tzinfo=tehran_tz)
            if base <= now:
                base = datetime(now.year, now.month, 28, hour, minute, tzinfo=tehran_tz) + timedelta(days=1)
        scheduled_at = base.astimezone(timezone.utc)
    if scheduled_at is None:
        scheduled_at = parse_schedule_time(parts[0])
    reminder_text = clean_profile_value(parts[1], 500)
    if len(reminder_text) < 2:
        raise ValueError("متن یادآوری خیلی کوتاه است")
    return repeat, scheduled_at, reminder_text


def parse_miniapp_datetime(value: str) -> datetime:
    try:
        local = datetime.fromisoformat(normalize_digits(str(value).strip()))
    except ValueError as exc:
        raise ValueError("زمان نامعتبر است") from exc
    tehran_tz = timezone(timedelta(hours=3, minutes=30))
    if local.tzinfo is None:
        local = local.replace(tzinfo=tehran_tz)
    now = datetime.now(tehran_tz)
    local = local.astimezone(tehran_tz)
    if local <= now + timedelta(seconds=30):
        raise ValueError("زمان باید در آینده باشد")
    if local > now + timedelta(days=365):
        raise ValueError("حداکثر تا یک سال آینده")
    return local.astimezone(timezone.utc)


async def create_user_reminder(user_id: int, reminder_text: str, scheduled_at: datetime, source: str, repeat: str | None = None) -> dict:
    pending_count = await reminders_col.count_documents({"user_id": user_id, "status": "pending"})
    if pending_count >= 30:
        raise ValueError("حداکثر ۳۰ یادآور فعال مجاز است")
    reminder = {
        "_id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "text": clean_profile_value(reminder_text, 500),
        "scheduled_at": scheduled_at,
        "status": "pending",
        "source": source,
        "repeat": repeat or None,
        "created_at": datetime.now(timezone.utc),
    }
    await reminders_col.insert_one(reminder)
    return reminder


async def send_user_reminders_list(message: types.Message) -> None:
    items = await reminders_col.find(
        {"user_id": message.from_user.id, "status": "pending"}
    ).sort("scheduled_at", 1).limit(20).to_list(length=20)
    if not items:
        return await message.answer(
            "⏰ یادآور فعالی نداری.\nنمونه ساخت: <code>فردا 09:00 | تماس با علی</code>",
            parse_mode="HTML",
            reply_markup=tools_reply_menu(),
        )
    lines = ["⏰ <b>یادآورهای فعال</b>", ""]
    rows = []
    repeat_labels = {"daily": "🔁 هر روز", "weekly": "🔁 هر هفته", "monthly": "🔁 هر ماه"}
    for index, item in enumerate(items, 1):
        rep = repeat_labels.get(item.get("repeat"))
        rep_text = f" · {rep}" if rep else ""
        lines.append(
            f"{index}. {html.escape(item['text'][:80])}{rep_text}\n   🕒 {format_tehran_datetime(item['scheduled_at'])}"
        )
        rows.append([InlineKeyboardButton(
            text=f"🗑 حذف {index}", callback_data=f"remcancel:{item['_id']}"
        )])
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def parse_review_input(value: str) -> tuple[int, str]:
    value = str(value or "").strip()
    match = re.match(r"^([1-5])\s*\|\s*(.+)$", value, flags=re.S)
    rating = int(match.group(1)) if match else 5
    review_text = clean_profile_value(match.group(2) if match else value, 500)
    if len(review_text) < 5:
        raise ValueError("نظر باید حداقل ۵ کاراکتر باشد")
    return rating, review_text


async def create_user_review(
    user_id: int,
    name: str,
    username: str | None,
    raw_text: str,
    source: str,
) -> dict:
    rating, review_text = parse_review_input(raw_text)
    profanity = detect_profanity(review_text)
    if profanity:
        raise ValueError("لطفاً نظر را بدون عبارت نامناسب ثبت کن")
    if await reviews_col.find_one({"user_id": user_id, "day": today_str()}):
        raise ValueError("امروز یک نظر ثبت کرده‌ای؛ فردا می‌توانی نظر تازه بفرستی")
    document = {
        "_id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "name": clean_profile_value(name, 80) or "کاربر تلگرام",
        "username": username,
        "rating": rating,
        "text": review_text,
        "day": today_str(),
        "source": source,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    await reviews_col.insert_one(document)
    await users_col.update_one(
        {"_id": user_id},
        {"$inc": {"reviews_submitted_count": 1}, "$set": {"last_review_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ انتشار", callback_data=f"review:approve:{document['_id']}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"review:reject:{document['_id']}"),
    ]])
    alert = (
        "💬 <b>نظر جدید برای بررسی</b>\n\n"
        f"کاربر: {html.escape(document['name'])} · <code>{user_id}</code>\n"
        f"امتیاز: {'⭐' * rating}\n"
        f"نظر: {html.escape(review_text)}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, alert, parse_mode="HTML", reply_markup=keyboard)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    return document


async def send_reviews_to_bot(message: types.Message) -> None:
    items = await reviews_col.find({"status": "published"}).sort("published_at", -1).limit(10).to_list(length=10)
    lines = ["💬 <b>نظرهای تأییدشده کاربران</b>", ""]
    if items:
        for item in items:
            lines.append(
                f"{'⭐' * max(1, min(5, int(item.get('rating', 5))))} <b>{html.escape(item.get('name') or 'کاربر')}</b>\n"
                f"{html.escape(item.get('text') or '')}\n"
            )
    else:
        lines.append("هنوز نظر واقعی تأییدشده‌ای ثبت نشده.\n")
    lines.extend(["", "🧪 <b>چند نمونه نمایشی رابط</b>"])
    for item in DEMO_REVIEWS[:5]:
        lines.append(f"{'⭐' * item['rating']} <b>{html.escape(item['name'])}</b> — {html.escape(item['text'])}")
    lines.append("\nنمونه‌های بالا با برچسب نمایشی هستند؛ نظرهای واقعی بعد از بررسی منتشر می‌شوند.")
    await message.answer("\n".join(lines)[:4000], parse_mode="HTML", reply_markup=reviews_reply_menu())


async def stage_repost(message: types.Message, payload: dict | None = None):
    admin_id = message.from_user.id
    batch = repost_batches.get(admin_id)
    if not batch or time.monotonic() - batch["created_at"] > 2 * 60 * 60:
        batch = create_repost_batch(admin_id)
    if batch.get("publishing"):
        return await message.answer("⏳ انتشار گروه قبلی در حال انجامه؛ چند لحظه صبر کن.")
    if len(batch["items"]) >= 20:
        return await message.answer(
            "⚠️ سقف هر گروه ۲۰ پسته. الان انتشار رو بزن یا گروه رو کنسل کن.",
            reply_markup=repost_batch_keyboard(len(batch["items"])),
        )
    payload = payload or extract_repost_payload(message)
    if not payload:
        return await message.answer("❌ فقط متن، عکس، ویدئو، گیف یا فایل دارای کپشن پشتیبانی می‌شود.")
    batch["items"].append({"payload": payload, "published": False})
    count = len(batch["items"])
    await message.answer(
        f"✅ پست شماره <b>{count}</b> به گروه بازنشر اضافه و با @Ajor_pareh آماده شد.\n\n"
        "پست بعدی رو بفرست یا یکی از گزینه‌های زیر رو بزن:",
        reply_markup=repost_batch_keyboard(count),
        parse_mode="HTML",
    )


async def show_repost_start(message: types.Message, admin_id: int):
    instant_repost_sessions.pop(admin_id, None)
    cancel_album_buffers(admin_id, "instant")
    batch = repost_batches.get(admin_id)
    if batch and batch["items"] and not batch.get("publishing"):
        repost_sessions.add(admin_id)
        return await message.answer(
            f"♻️ یک گروه بازنشر با <b>{len(batch['items'])} پست</b> بازه.\n"
            "می‌تونی پست‌های بیشتری بفرستی یا همین گروه رو منتشر کنی:",
            reply_markup=repost_batch_keyboard(len(batch["items"])),
            parse_mode="HTML",
        )
    create_repost_batch(admin_id)
    await message.answer(
        "♻️ <b>گروه بازنشر جدید ساخته شد</b>\n\n"
        "پست‌های متنی، عکس، ویدئو، گیف یا فایل را یکی‌یکی برای ربات فوروارد کن. "
        "همه داخل همین گروه جمع می‌شوند؛ شناسه‌ها با @Ajor_pareh جایگزین و متن دعوت اضافه می‌شود.\n\n"
        "بعد از هر پست، دکمه‌های <b>انتشار همه</b> و <b>کنسل کل گروه</b> را می‌بینی. "
        "حداکثر ۲۰ پست در هر گروه. فقط محتوایی را بازنشر کن که اجازه استفاده از آن را داری.\n"
        "برای لغو سریع /cancel",
        reply_markup=repost_batch_keyboard(0),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "repost_start")
async def repost_start_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    await show_repost_start(callback.message, callback.from_user.id)
    await callback.answer()


@dp.callback_query(F.data == "repost_batch_continue")
async def repost_batch_continue_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if not batch:
        create_repost_batch(callback.from_user.id)
    repost_sessions.add(callback.from_user.id)
    await callback.answer("پست بعدی رو فوروارد کن ➕", show_alert=True)


@dp.callback_query(F.data == "repost_batch_manage")
async def repost_batch_manage_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if not batch or not batch.get("items"):
        return await callback.answer("گروه خالیه؛ اول چند پست بفرست.", show_alert=True)
    if batch.get("publishing"):
        return await callback.answer("انتشار شروع شده و دیگر قابل ویرایش نیست.", show_alert=True)
    await show_repost_batch_manage(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("repost_edit:"))
async def repost_edit_item_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        index = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("شمارهٔ پست نامعتبر است.", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if not batch or batch.get("publishing"):
        return await callback.answer("گروه پیدا نشد یا انتشارش شروع شده.", show_alert=True)
    if not 0 <= index < len(batch.get("items", [])):
        return await callback.answer("این پست دیگر وجود ندارد.", show_alert=True)
    repost_edit_sessions[callback.from_user.id] = index
    scheduled_add_sessions.pop(callback.from_user.id, None)
    scheduled_edit_sessions.pop(callback.from_user.id, None)
    repost_sessions.discard(callback.from_user.id)
    cancel_album_buffers(callback.from_user.id, "batch_edit")
    await callback.message.answer(
        f"✏️ نسخهٔ جدید پست شمارهٔ {index + 1} را بفرست.\n"
        "می‌توانی متن، عکس، ویدئو، گیف یا فایل بفرستی؛ نسخهٔ قبلی فقط همین پست جایگزین می‌شود.\n"
        "برای لغو /cancel",
    )
    await callback.answer("منتظر نسخهٔ جدید هستم ✏️")


@dp.callback_query(F.data.startswith("repost_delete:"))
async def repost_delete_item_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        index = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("شمارهٔ پست نامعتبر است.", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if not batch or batch.get("publishing"):
        return await callback.answer("گروه پیدا نشد یا انتشارش شروع شده.", show_alert=True)
    items = batch.get("items", [])
    if not 0 <= index < len(items):
        return await callback.answer("این پست دیگر وجود ندارد.", show_alert=True)
    items.pop(index)
    batch["created_at"] = time.monotonic()
    repost_edit_sessions.pop(callback.from_user.id, None)
    await show_repost_batch_manage(callback.message, callback.from_user.id, edit=True)
    await callback.answer("پست از گروه حذف شد ✅")


@dp.callback_query(F.data == "repost_batch_back")
async def repost_batch_back_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if not batch:
        return await callback.answer("گروه پیدا نشد.", show_alert=True)
    await callback.message.edit_text(
        f"♻️ گروه بازنشر · {len(batch.get('items', []))} پست\n\n"
        "پست بعدی را بفرست یا یکی از گزینه‌ها را انتخاب کن:",
        reply_markup=repost_batch_keyboard(len(batch.get("items", []))),
    )
    await callback.answer()


@dp.callback_query(F.data == "repost_batch_cancel")
async def repost_batch_cancel_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if batch and batch.get("publishing"):
        return await callback.answer("انتشار شروع شده و وسط کار قابل لغو نیست.", show_alert=True)
    batch = repost_batches.pop(callback.from_user.id, None)
    repost_sessions.discard(callback.from_user.id)
    repost_edit_sessions.pop(callback.from_user.id, None)
    cancel_album_buffers(callback.from_user.id, "batch")
    cancel_album_buffers(callback.from_user.id, "batch_edit")
    count = len(batch["items"]) if batch else 0
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.message.answer(f"🗑 گروه بازنشر کنسل شد و {count} پست از صف حذف شد.")
    await callback.answer("گروه حذف شد.", show_alert=True)


@dp.callback_query(F.data == "repost_batch_preview")
async def repost_batch_preview_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if not batch or not batch["items"]:
        return await callback.answer("گروه خالیه؛ اول چند پست بفرست.", show_alert=True)
    await callback.answer("پیش‌نمایش در حال ارساله...")
    await callback.message.answer(f"👁 <b>پیش‌نمایش گروه · {len(batch['items'])} پست</b>", parse_mode="HTML")
    for index, item in enumerate(batch["items"], 1):
        await callback.message.answer(f"— پست {index} از {len(batch['items'])} —")
        await send_repost_payload(callback.from_user.id, item["payload"])
        await asyncio.sleep(0.25)
    await callback.message.answer("پایان پیش‌نمایش؛ انتشار یا کنسل؟", reply_markup=repost_batch_keyboard(len(batch["items"])))


@dp.callback_query(F.data == "repost_batch_schedule")
async def repost_batch_schedule_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    batch = repost_batches.get(callback.from_user.id)
    if not batch or not batch["items"]:
        return await callback.answer("گروه خالیه؛ اول چند پست بفرست.", show_alert=True)
    repost_sessions.discard(callback.from_user.id)
    schedule_time_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "⏰ <b>زمان انتشار گروه را به وقت تهران بفرست</b>\n\n"
        "فرمت‌های قابل قبول:\n"
        "<code>امروز 21:30</code>\n<code>فردا 09:00</code>\n"
        "<code>1405/05/08 18:30</code> (شمسی)\n"
        "<code>2026-07-30 18:30</code> (میلادی)\n\n"
        "برای انصراف /cancel",
        parse_mode="HTML",
    )
    await callback.answer("زمان رو بفرست ⏰")


@dp.callback_query(F.data == "scheduled_posts")
async def scheduled_posts_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    items = await scheduled_posts_col.find({"status": {"$in": ["pending", "publishing", "failed"]}}).sort("scheduled_at", 1).limit(20).to_list(length=20)
    rows = [[InlineKeyboardButton(
        text=f"⏰ {format_tehran_datetime(item['scheduled_at'])} · {len(item.get('items', []))} پست · {item.get('status')}",
        callback_data=f"schedinfo:{item['_id']}",
    )] for item in items]
    if not rows:
        rows.append([InlineKeyboardButton(text="— پست زمان‌داری وجود ندارد —", callback_data="schednoop")])
    rows.extend([
        [InlineKeyboardButton(text="▶️ ادامه صف" if runtime_settings.get("scheduler_paused") else "⏸ توقف کل صف", callback_data="scheduler_toggle")],
        [InlineKeyboardButton(text="➕ ساخت گروه زمان‌دار", callback_data="scheduled_create")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    await callback.message.answer("⏰ <b>پست‌های زمان‌دار</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "scheduled_create")
async def scheduled_create_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    repost_batches.pop(callback.from_user.id, None)
    repost_edit_sessions.pop(callback.from_user.id, None)
    scheduled_add_sessions.pop(callback.from_user.id, None)
    scheduled_edit_sessions.pop(callback.from_user.id, None)
    create_repost_batch(callback.from_user.id)
    await callback.message.answer("⏰ گروه زمان‌دار ساخته شد. پست‌ها را یکی‌یکی بفرست؛ بعد دکمه «زمان‌بندی» را بزن.", reply_markup=repost_batch_keyboard(0))
    await callback.answer()


@dp.callback_query(F.data == "schednoop")
async def scheduled_noop_callback(callback: types.CallbackQuery):
    await callback.answer("هنوز پست زمان‌داری ثبت نشده.")


@dp.callback_query(F.data.startswith("schedinfo:"))
async def scheduled_info_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    job_id = callback.data.split(":", 1)[1]
    item = await scheduled_posts_col.find_one({"_id": job_id})
    if not item:
        return await callback.answer("این زمان‌بندی پیدا نشد.", show_alert=True)
    items = list(item.get("items") or [])
    rows = [
        [InlineKeyboardButton(text="🚀 انتشار همین الان", callback_data=f"schednow:{job_id}"), InlineKeyboardButton(text="🕒 تغییر زمان", callback_data=f"schedreschedule:{job_id}")],
        [InlineKeyboardButton(text="🔁 روزانه", callback_data=f"schedrepeat:{job_id}:daily"), InlineKeyboardButton(text="🔁 هفتگی", callback_data=f"schedrepeat:{job_id}:weekly")],
    ]
    if item.get("status") == "pending":
        rows.append([
            InlineKeyboardButton(text="➕ افزودن پست", callback_data=f"schedadd:{job_id}"),
            InlineKeyboardButton(text="🛠 ویرایش/حذف پست‌ها", callback_data=f"schedmanage:{job_id}"),
        ])
    rows.extend([
        [InlineKeyboardButton(text="🗑 لغو زمان‌بندی", callback_data=f"schedcancel:{job_id}")],
        [InlineKeyboardButton(text="🔙 فهرست", callback_data="scheduled_posts")],
    ])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    await callback.message.answer(
        f"⏰ <b>زمان‌بندی #{job_id}</b>\n"
        f"زمان تهران: <b>{format_tehran_datetime(item['scheduled_at'])}</b>\n"
        f"تعداد پست: <b>{len(items)}</b>\nوضعیت: <b>{item.get('status')}</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


async def show_scheduled_manage(message: types.Message, job: dict, *, edit: bool = False) -> None:
    job_id = str(job["_id"])
    items = list(job.get("items") or [])
    rows = []
    for index, payload in enumerate(items):
        preview = repost_payload_preview(payload)
        rows.append([
            InlineKeyboardButton(text=f"✏️ {index + 1} · {preview[:28]}", callback_data=f"schededit:{job_id}:{index}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"scheddelete:{job_id}:{index}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ افزودن پست", callback_data=f"schedadd:{job_id}")])
    rows.append([InlineKeyboardButton(text="🔙 جزئیات زمان‌بندی", callback_data=f"schedinfo:{job_id}")])
    text = (
        f"🛠 <b>مدیریت پست‌های زمان‌بندی #{job_id}</b>\n"
        f"تعداد: <b>{len(items)}</b> از ۲۰\n\n"
        "ویرایش یعنی نسخهٔ جدید همان پست را بفرستی؛ حذف فقط همان پست را از گروه خارج می‌کند."
    )
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


@dp.callback_query(F.data.startswith("schedadd:"))
async def scheduled_add_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "schedule"):
        return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    job_id = callback.data.split(":", 1)[1]
    job = await scheduled_posts_col.find_one({"_id": job_id})
    if not job:
        return await callback.answer("این زمان‌بندی پیدا نشد.", show_alert=True)
    if job.get("status") != "pending":
        return await callback.answer("⛔ انتشار شروع شده یا زمان‌بندی بسته شده است.", show_alert=True)
    if len(job.get("items") or []) >= 20:
        return await callback.answer("سقف گروه ۲۰ پست است؛ اول یکی را حذف کن.", show_alert=True)
    scheduled_add_sessions[callback.from_user.id] = job_id
    scheduled_edit_sessions.pop(callback.from_user.id, None)
    repost_edit_sessions.pop(callback.from_user.id, None)
    cancel_album_buffers(callback.from_user.id, "scheduled_add")
    await callback.message.answer(
        f"➕ یک پست جدید برای زمان‌بندی <code>{job_id}</code> بفرست.\n"
        "متن، عکس، ویدئو، گیف یا فایل قابل قبول است؛ برای لغو /cancel",
        parse_mode="HTML",
    )
    await callback.answer("منتظر پست جدید هستم ➕")


@dp.callback_query(F.data.startswith("schedmanage:"))
async def scheduled_manage_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "schedule"):
        return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    job_id = callback.data.split(":", 1)[1]
    job = await scheduled_posts_col.find_one({"_id": job_id})
    if not job:
        return await callback.answer("این زمان‌بندی پیدا نشد.", show_alert=True)
    if job.get("status") != "pending":
        return await callback.answer("⛔ این گروه دیگر قابل تغییر نیست.", show_alert=True)
    await show_scheduled_manage(callback.message, job, edit=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("schededit:"))
async def scheduled_edit_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "schedule"):
        return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer("درخواست ویرایش نامعتبر است.", show_alert=True)
    job_id = parts[1]
    try:
        index = int(parts[2])
    except ValueError:
        return await callback.answer("شمارهٔ پست نامعتبر است.", show_alert=True)
    job = await scheduled_posts_col.find_one({"_id": job_id, "status": "pending"})
    if not job or not 0 <= index < len(job.get("items") or []):
        return await callback.answer("این پست دیگر قابل ویرایش نیست.", show_alert=True)
    scheduled_edit_sessions[callback.from_user.id] = (job_id, index)
    scheduled_add_sessions.pop(callback.from_user.id, None)
    repost_edit_sessions.pop(callback.from_user.id, None)
    cancel_album_buffers(callback.from_user.id, "scheduled_edit")
    await callback.message.answer(
        f"✏️ نسخهٔ جدید پست شمارهٔ {index + 1} از زمان‌بندی <code>{job_id}</code> را بفرست.\n"
        "فقط همان پست جایگزین می‌شود؛ برای لغو /cancel",
        parse_mode="HTML",
    )
    await callback.answer("منتظر نسخهٔ جدید هستم ✏️")


@dp.callback_query(F.data.startswith("scheddelete:"))
async def scheduled_delete_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "schedule"):
        return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer("درخواست حذف نامعتبر است.", show_alert=True)
    job_id = parts[1]
    try:
        index = int(parts[2])
    except ValueError:
        return await callback.answer("شمارهٔ پست نامعتبر است.", show_alert=True)
    job = await scheduled_posts_col.find_one({"_id": job_id, "status": "pending"})
    if not job:
        return await callback.answer("این زمان‌بندی دیگر باز نیست.", show_alert=True)
    items = list(job.get("items") or [])
    if not 0 <= index < len(items):
        return await callback.answer("این پست دیگر وجود ندارد.", show_alert=True)
    updated_items = items[:index] + items[index + 1:]
    update = {"items": updated_items, "updated_at": datetime.now(timezone.utc)}
    if not updated_items:
        update.update({
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc),
            "cancelled_by": callback.from_user.id,
            "cancelled_reason": "all_items_removed",
        })
    result = await scheduled_posts_col.update_one(
        {"_id": job_id, "status": "pending", "items": items},
        {"$set": update},
    )
    if not result.modified_count:
        return await callback.answer("⚠️ گروه هم‌زمان تغییر کرد؛ دوباره بازش کن.", show_alert=True)
    scheduled_add_sessions.pop(callback.from_user.id, None)
    scheduled_edit_sessions.pop(callback.from_user.id, None)
    if not updated_items:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await callback.message.answer("🗑 آخرین پست حذف شد و زمان‌بندی هم لغو شد.")
    else:
        updated_job = dict(job)
        updated_job.update(update)
        await show_scheduled_manage(callback.message, updated_job, edit=True)
    await callback.answer("پست حذف شد ✅")


@dp.callback_query(F.data == "scheduler_toggle")
async def scheduler_toggle_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "schedule"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    runtime_settings["scheduler_paused"] = not runtime_settings.get("scheduler_paused"); await settings_col.update_one({"_id":"runtime"},{"$set":{"scheduler_paused":runtime_settings["scheduler_paused"]}},upsert=True)
    await audit_admin_action(callback.from_user.id,"scheduler_toggle",str(runtime_settings["scheduler_paused"]));await callback.answer("صف متوقف شد." if runtime_settings["scheduler_paused"] else "صف ادامه پیدا کرد.",show_alert=True)


@dp.callback_query(F.data.startswith("schednow:") | F.data.startswith("schedreschedule:") | F.data.startswith("schedrepeat:"))
async def scheduled_advanced_action(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "schedule"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    parts=callback.data.split(":");action=parts[0];job_id=parts[1]
    if action=="schednow": await scheduled_posts_col.update_one({"_id":job_id,"status":"pending"},{"$set":{"scheduled_at":datetime.now(timezone.utc)}});return await callback.answer("برای انتشار فوری به صف رفت.",show_alert=True)
    if action=="schedreschedule": reschedule_sessions[callback.from_user.id]=job_id;await callback.message.answer("زمان جدید را بفرست؛ مثال فردا 09:00 یا 1405/05/10 18:30. /cancel");return await callback.answer()
    repeat=parts[2];await scheduled_posts_col.update_one({"_id":job_id},{"$set":{"repeat":repeat}});await callback.answer("تکرار روزانه تنظیم شد." if repeat=="daily" else "تکرار هفتگی تنظیم شد.",show_alert=True)


@dp.callback_query(F.data.startswith("schedcancel:"))
async def scheduled_cancel_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    job_id = callback.data.split(":", 1)[1]
    result = await scheduled_posts_col.update_one(
        {"_id": job_id, "status": {"$in": ["pending", "failed"]}},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc), "cancelled_by": callback.from_user.id}},
    )
    if not result.modified_count:
        return await callback.answer("این پست در حال انتشار یا قبلاً لغو شده.", show_alert=True)
    if scheduled_add_sessions.get(callback.from_user.id) == job_id:
        scheduled_add_sessions.pop(callback.from_user.id, None)
    if scheduled_edit_sessions.get(callback.from_user.id, (None, None))[0] == job_id:
        scheduled_edit_sessions.pop(callback.from_user.id, None)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer("زمان‌بندی لغو شد.", show_alert=True)


@dp.callback_query(F.data == "repost_batch_publish")
async def repost_batch_publish_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    admin_id = callback.from_user.id
    batch = repost_batches.get(admin_id)
    if not batch or not batch["items"]:
        return await callback.answer("گروه خالیه؛ اول چند پست بفرست.", show_alert=True)
    if batch.get("publishing"):
        return await callback.answer("انتشار همین الان در حال انجامه.", show_alert=True)
    batch["publishing"] = True
    repost_sessions.discard(admin_id)
    total = len(batch["items"])
    status_message = await callback.message.answer(f"🚀 شروع انتشار {total} پست در @Ajor_pareh ...")
    await callback.answer("انتشار گروه شروع شد 🚀")
    sent = 0
    failed = 0
    for index, item in enumerate(batch["items"], 1):
        if item.get("published"):
            continue
        try:
            published = await send_repost_payload(CHANNEL_ID, item["payload"])
            item["published"] = True
            item["published_message_id"] = published_message_id(published)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                published = await send_repost_payload(CHANNEL_ID, item["payload"])
                item["published"] = True
                item["published_message_id"] = published_message_id(published)
                sent += 1
            except Exception as retry_exc:
                failed += 1
                log.warning("بازنشر پست %s بعد از retry ناموفق بود: %s", index, retry_exc)
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            failed += 1
            log.warning("بازنشر پست %s ناموفق بود: %s", index, exc)
        except Exception as exc:
            failed += 1
            log.exception("خطای بازنشر پست %s: %s", index, exc)
        try:
            await status_message.edit_text(f"📤 انتشار گروه: {index}/{total}\n✅ موفق: {sent} · ❌ ناموفق: {failed}")
        except TelegramBadRequest:
            pass
        await asyncio.sleep(0.7)
    remaining = [item for item in batch["items"] if not item.get("published")]
    if remaining:
        batch["items"] = remaining
        batch["publishing"] = False
        repost_sessions.add(admin_id)
        await status_message.edit_text(
            f"⚠️ انتشار ناقص بود.\n✅ {sent} پست منتشر شد · ❌ {len(remaining)} پست باقی موند.\n"
            "می‌تونی دوباره انتشار رو بزنی یا گروه باقی‌مانده رو کنسل کنی.",
            reply_markup=repost_batch_keyboard(len(remaining)),
        )
    else:
        repost_batches.pop(admin_id, None)
        await status_message.edit_text(f"✅ هر {sent} پست با برند @Ajor_pareh منتشر شدند.")
    await log_activity(admin_id, "smart_repost_batch", f"total={total},sent={sent},failed={failed}")


@dp.channel_post()
@dp.edited_channel_post()
async def track_channel_post(message: types.Message):
    if message.chat.id != CHANNEL_ID:
        return
    content = (message.text or message.caption or "").strip()
    if not content:
        content = "پست رسانه‌ای جدید از Ajorpareh"
    media_type = "text"
    if message.photo:
        media_type = "photo"
    elif message.video:
        media_type = "video"
    elif message.animation:
        media_type = "animation"
    username = message.chat.username or "Ajor_pareh"
    await channel_posts_col.update_one(
        {"_id": message.message_id},
        {"$set": {
            "text": content[:3000],
            "media_type": media_type,
            "url": f"https://t.me/{username}/{message.message_id}",
            "published_at": message.date,
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )


@dp.my_chat_member()
async def track_managed_chat(event: types.ChatMemberUpdated):
    chat_type = getattr(event.chat.type, "value", str(event.chat.type))
    if chat_type not in {"group", "supergroup", "channel"}:
        return
    status = getattr(event.new_chat_member.status, "value", str(event.new_chat_member.status))
    old_status = getattr(event.old_chat_member.status, "value", str(event.old_chat_member.status))
    await managed_chats_col.update_one(
        {"_id": event.chat.id},
        {"$set": {
            "title": event.chat.title,
            "username": event.chat.username,
            "type": chat_type,
            "status": status,
            "updated_at": datetime.now(timezone.utc),
            "added_by": event.from_user.id if event.from_user else None,
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    if status in {"administrator", "creator"} and chat_type in {"group", "supergroup"}:
        try:
            await install_group_commands(event.chat.id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            log.warning("ثبت منوی اسلش گروه %s ممکن نشد: %s", event.chat.id, exc)
    if status in {"administrator", "creator"} and old_status not in {"administrator", "creator"}:
        adder = event.from_user.full_name if event.from_user else "مدیر"
        intro = (
            f"سلام <b>{html.escape(adder)}</b> عزیز 🌹\n\n"
            "🔰 با دستیار قدرتمند مدیریت گروه Ajorpareh آشنا شوید\n"
            "🔰 برای نظم، امنیت و کنترل ساده‌تر گروه‌ها\n\n"
            "<b>ویژگی‌های کلیدی:</b>\n"
            "✅ پاسخ سریع به دستورات و طراحی‌شده برای گروه‌های بزرگ\n"
            "✅ ضد اسپم، فیلتر پیشرفته کلمات و کنترل لینک/فوروارد\n"
            "✅ اخطار هوشمند و مجازات خودکار پس از ۳ هشدار\n"
            "✅ بن، آنبن، حذف، سکوت زمان‌دار و پاک‌کردن پیام\n"
            "✅ پیام خوش‌آمد شخصی‌سازی‌شده برای اعضای جدید\n"
            "✅ تنظیم جداگانه قفل‌ها و مجازات برای هر گروه\n"
            "✅ پنل مدیریتی، آمار اخطارها و بروزرسانی‌های منظم\n\n"
            "برای شروع دستور /modpanel را بفرستید."
        )
        try:
            keyboard = await group_panel_keyboard(event.chat.id) if chat_type in {"group", "supergroup"} else None
            await bot.send_message(event.chat.id, intro, reply_markup=keyboard, parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            log.warning("پیام معرفی مدیریت ارسال نشد: %s", exc)


@dp.message(F.new_chat_members)
async def welcome_new_group_members(message: types.Message):
    settings = await get_group_settings(message.chat.id)
    if not settings["welcome_enabled"]:
        return
    group_name = message.chat.title or "گروه"
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        mention = f'<a href="tg://user?id={member.id}">{html.escape(member.full_name)}</a>'
        template = settings.get("welcome_text")
        if template:
            text = template.replace("{name}", mention).replace("{group}", html.escape(group_name))
        else:
            text = f"🌹 خوش اومدی {mention}!\nبه جمع <b>{html.escape(group_name)}</b> اضافه شدی؛ امیدواریم کنار هم لحظه‌های خوبی بسازیم ✨\nلطفاً قوانین گروه رو رعایت کن و با بقیه محترمانه رفتار کن."
        await message.answer(text, parse_mode="HTML")


async def group_panel_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    settings = await get_group_settings(chat_id)
    filter_label = "🟢 ضد فحش" if settings["anti_profanity"] else "⚪ ضد فحش"
    spam_label = "🟢 ضد اسپم" if settings["anti_spam"] else "⚪ ضد اسپم"
    links_label = "🔒 لینک" if settings["block_links"] else "🔓 لینک"
    forwards_label = "🔒 فوروارد" if settings["block_forwards"] else "🔓 فوروارد"
    welcome_label = "👋 خوش‌آمد روشن" if settings["welcome_enabled"] else "👋 خوش‌آمد خاموش"
    punishments = {"mute": "سکوت", "kick": "حذف", "ban": "بن"}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=filter_label, callback_data=f"gfilter:{chat_id}"), InlineKeyboardButton(text=spam_label, callback_data=f"gspam:{chat_id}")],
        [InlineKeyboardButton(text=links_label, callback_data=f"glinks:{chat_id}"), InlineKeyboardButton(text=forwards_label, callback_data=f"gforwards:{chat_id}")],
        [InlineKeyboardButton(text=welcome_label, callback_data=f"gwelcome:{chat_id}")],
        [InlineKeyboardButton(text=f"⚖️ مجازات ۳ اخطار: {punishments[settings['punishment']]}", callback_data=f"gpunish:{chat_id}")],
        [InlineKeyboardButton(text="📊 آمار اخطارها", callback_data=f"gstats:{chat_id}")],
        [InlineKeyboardButton(text="📖 راهنمای دستورات", callback_data=f"ghelp:{chat_id}")],
    ])


@dp.callback_query(F.data == "managed_chats")
async def managed_chats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    chats = await managed_chats_col.find({"status": {"$in": ["administrator", "creator", "member", "active"]}}).sort("updated_at", -1).limit(30).to_list(length=30)
    rows = [[InlineKeyboardButton(
        text=f"{'📣' if chat.get('type') == 'channel' else '👥'} {(chat.get('title') or chat['_id'])}",
        callback_data=f"mchat:{chat['_id']}",
    )] for chat in chats]
    if not rows:
        rows.append([InlineKeyboardButton(text="— هنوز گروهی ثبت نشده —", callback_data="mchatnoop")])
    rows.append([InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")])
    await callback.message.answer("🛡 <b>گروه‌ها و کانال‌های تحت مدیریت</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "mchatnoop")
async def managed_chat_noop(callback: types.CallbackQuery):
    await callback.answer("ربات را در یک گروه یا کانال ادمین کن تا اینجا نمایش داده شود.")


@dp.callback_query(F.data.startswith("mchat:"))
async def managed_chat_info_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    chat_id = int(callback.data.split(":", 1)[1])
    chat = await managed_chats_col.find_one({"_id": chat_id})
    if not chat:
        return await callback.answer("چت پیدا نشد.", show_alert=True)
    keyboard = await group_panel_keyboard(chat_id) if chat.get("type") in {"group", "supergroup"} else InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 فهرست", callback_data="managed_chats")]])
    await callback.message.answer(
        f"🛡 <b>{html.escape(str(chat.get('title') or chat_id))}</b>\n"
        f"شناسه: <code>{chat_id}</code>\nنوع: {chat.get('type')}\nوضعیت ربات: {chat.get('status')}",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("gfilter:") | F.data.startswith("gspam:") | F.data.startswith("glinks:") | F.data.startswith("gforwards:") | F.data.startswith("gwelcome:") | F.data.startswith("gpunish:") | F.data.startswith("gstats:") | F.data.startswith("ghelp:"))
async def group_panel_action_callback(callback: types.CallbackQuery):
    action, chat_text = callback.data.split(":", 1)
    chat_id = int(chat_text)
    if not is_admin(callback.from_user.id) and not await is_chat_admin(chat_id, callback.from_user.id):
        return await callback.answer("فقط ادمین‌های این گروه دسترسی دارند.", show_alert=True)
    settings = await get_group_settings(chat_id)
    if action in {"gfilter", "gspam", "glinks", "gforwards", "gwelcome"}:
        field_map = {"gfilter": "anti_profanity", "gspam": "anti_spam", "glinks": "block_links", "gforwards": "block_forwards", "gwelcome": "welcome_enabled"}
        field = field_map[action]; new_value = not settings[field]
        await group_settings_col.update_one({"_id": chat_id}, {"$set": {field: new_value}}, upsert=True)
        await callback.message.answer("✅ تنظیمات گروه بروزرسانی شد.", reply_markup=await group_panel_keyboard(chat_id))
    elif action == "gpunish":
        cycle = {"mute": "kick", "kick": "ban", "ban": "mute"}
        new_value = cycle[settings["punishment"]]
        await group_settings_col.update_one({"_id": chat_id}, {"$set": {"punishment": new_value}}, upsert=True)
        await callback.message.answer("✅ نوع مجازات عوض شد.", reply_markup=await group_panel_keyboard(chat_id))
    elif action == "gstats":
        active = await warnings_col.count_documents({"chat_id": chat_id, "count": {"$gt": 0}})
        agg = await warnings_col.aggregate([{"$match": {"chat_id": chat_id}}, {"$group": {"_id": None, "warnings": {"$sum": "$total_warnings"}, "punishments": {"$sum": "$punishments"}}}]).to_list(length=1)
        data = agg[0] if agg else {}
        await callback.message.answer(f"📊 اخطارهای کل: {int(data.get('warnings', 0))}\nمجازات‌ها: {int(data.get('punishments', 0))}\nکاربران دارای اخطار فعال: {active}")
    else:
        await callback.message.answer(
            "📖 <b>دستورات مدیریت گروه</b>\n\n"
            "/warn — اخطار به پیام ریپلای‌شده\n/mute 60 — سکوت ۶۰ دقیقه\n/unmute — رفع سکوت\n/kick — حذف کاربر\n/ban — بن کاربر\n/unban ID — رفع بن\n/del — حذف پیام ریپلای‌شده\n/warnings — تعداد اخطارها\n/modpanel — پنل گروه\n/setwelcome متن — پیام خوش‌آمد سفارشی\n/filter add واژه — افزودن کلمه ممنوع",
            parse_mode="HTML",
        )
    await callback.answer()


PROMO_REWARD_ALIASES = {
    "xp": "xp", "point": "xp", "points": "xp", "امتیاز": "xp",
    "coin": "coins", "coins": "coins", "سکه": "coins",
    "ai": "ai_text", "ai_text": "ai_text", "پیام": "ai_text", "هوش": "ai_text",
    "ai_image": "ai_image", "image": "ai_image", "تصویر": "ai_image",
    "badge": "badge", "نشان": "badge", "مدال": "badge",
    "sticker": "sticker", "استیکر": "sticker",
    "gif": "gif", "گیف": "gif",
}


def parse_promo_rewards(spec: str) -> dict:
    spec = normalize_digits(str(spec or "").strip())
    if spec.isdigit():
        return {"xp": max(1, min(1_000_000, int(spec)))}
    rewards: dict = {}
    for raw_part in re.split(r"[,;،]", spec):
        part = raw_part.strip()
        if not part:
            continue
        if "=" in part:
            raw_key, raw_value = [piece.strip() for piece in part.split("=", 1)]
        else:
            raw_key, raw_value = part, "1"
        key = PROMO_REWARD_ALIASES.get(raw_key.lower())
        if not key:
            raise ValueError(f"نوع پاداش ناشناخته: {raw_key}")
        if key in {"sticker", "gif"}:
            rewards[key] = True
            continue
        if key == "badge":
            if raw_value not in SHOP_CATALOG or SHOP_CATALOG[raw_value].get("kind") != "badge":
                raise ValueError("نشان نامعتبر است؛ مثل badge_neon")
            rewards[key] = raw_value
            continue
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"مقدار {raw_key} باید عدد باشد") from exc
        limits = {"xp": 1_000_000, "coins": 100_000, "ai_text": 50, "ai_image": 5}
        total_value = rewards.get(key, 0) + value
        if value <= 0 or total_value > limits[key]:
            raise ValueError(f"مقدار {raw_key} باید بین ۱ تا {limits[key]} باشد")
        rewards[key] = total_value
    if not rewards:
        raise ValueError("حداقل یک پاداش لازم است")
    if rewards.get("sticker") and rewards.get("gif"):
        raise ValueError("در هر کد فقط یکی از استیکر یا گیف مجاز است")
    return rewards


def promo_rewards_from_document(item: dict) -> dict:
    rewards = dict(item.get("rewards") or {})
    if not rewards and int(item.get("points", 0) or 0) > 0:
        rewards["xp"] = int(item["points"])
    if item.get("sticker_file_id"):
        rewards["sticker"] = True
    if item.get("animation_file_id"):
        rewards["gif"] = True
    return rewards


def promo_reward_summary(item_or_rewards: dict) -> str:
    rewards = promo_rewards_from_document(item_or_rewards) if "rewards" in item_or_rewards or "points" in item_or_rewards else item_or_rewards
    parts = []
    if rewards.get("xp"): parts.append(f"{int(rewards['xp'])} XP")
    if rewards.get("coins"): parts.append(f"{int(rewards['coins'])} سکه")
    if rewards.get("ai_text"): parts.append(f"{int(rewards['ai_text'])} پیام AI روزانه")
    if rewards.get("ai_image"): parts.append(f"{int(rewards['ai_image'])} تصویر AI روزانه")
    if rewards.get("badge"): parts.append(f"نشان {SHOP_CATALOG.get(rewards['badge'], {}).get('title', rewards['badge'])}")
    if rewards.get("sticker"): parts.append("استیکر تلگرام")
    if rewards.get("gif"): parts.append("گیف تلگرام")
    return " + ".join(parts) or "بدون پاداش"


async def save_promo_code(config: dict, media_file_id: str | None = None) -> dict:
    document = {
        "rewards": config["rewards"],
        "max_uses": config["max_uses"],
        "uses": 0,
        "active": True,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=config["days"]),
        "created_by": config["created_by"],
        "created_at": datetime.now(timezone.utc),
    }
    if config["rewards"].get("sticker") and media_file_id:
        document["sticker_file_id"] = media_file_id
    if config["rewards"].get("gif") and media_file_id:
        document["animation_file_id"] = media_file_id
    unset_fields = {"points": ""}
    if not config["rewards"].get("sticker"):
        unset_fields["sticker_file_id"] = ""
    if not config["rewards"].get("gif"):
        unset_fields["animation_file_id"] = ""
    await promo_codes_col.update_one(
        {"_id": config["code"]},
        {"$set": document, "$unset": unset_fields},
        upsert=True,
    )
    return {"_id": config["code"], **document}


async def redeem_promo_code(user_id: int, code: str) -> dict:
    code = re.sub(r"[^A-Z0-9_]", "", str(code or "").upper())[:20]
    if not re.fullmatch(r"[A-Z0-9_]{4,20}", code):
        return {"ok": False, "reason": "invalid"}
    item = await promo_codes_col.find_one({"_id": code, "active": {"$ne": False}, "expires_at": {"$gt": datetime.now(timezone.utc)}})
    if not item:
        return {"ok": False, "reason": "invalid"}
    redemption_id = f"{code}:{user_id}"
    redemption = await promo_redemptions_col.find_one({"_id": redemption_id})
    if redemption and (redemption.get("status") == "completed" or "status" not in redemption):
        return {
            "ok": True, "duplicate": True, "code": code,
            "rewards": redemption.get("rewards") or promo_rewards_from_document(item),
            "sticker_file_id": item.get("sticker_file_id"),
            "animation_file_id": item.get("animation_file_id"),
            "coin_balance": await coin_balance(user_id),
        }
    is_new = redemption is None
    if is_new:
        try:
            await promo_redemptions_col.insert_one({
                "_id": redemption_id, "code": code, "user_id": user_id,
                "status": "reserving", "created_at": datetime.now(timezone.utc),
            })
        except DuplicateKeyError:
            return {"ok": False, "reason": "processing"}
        capacity = await promo_codes_col.update_one(
            {"_id": code, "active": {"$ne": False}, "uses": {"$lt": int(item.get("max_uses", 0))}},
            {"$inc": {"uses": 1}},
        )
        if not capacity.modified_count:
            await promo_redemptions_col.delete_one({"_id": redemption_id})
            return {"ok": False, "reason": "capacity"}
        await promo_redemptions_col.update_one(
            {"_id": redemption_id}, {"$set": {"status": "processing", "capacity_reserved": True}}
        )
    elif not redemption.get("capacity_reserved"):
        return {"ok": False, "reason": "processing"}

    rewards = promo_rewards_from_document(item)
    claimed_key = f"promo:{code}"
    xp = max(0, int(rewards.get("xp", 0) or 0))
    ai_text = max(0, int(rewards.get("ai_text", 0) or 0))
    ai_image = max(0, int(rewards.get("ai_image", 0) or 0))
    badge = rewards.get("badge")
    set_stage = {
        "xp": {"$add": [{"$ifNull": ["$xp", 0]}, xp]},
        "ai_gift_text_bonus": {"$min": [ai_service.config.max_user_text_bonus, {"$add": [{"$ifNull": ["$ai_gift_text_bonus", 0]}, ai_text]}]},
        "ai_gift_image_bonus": {"$min": [ai_service.config.max_user_image_bonus, {"$add": [{"$ifNull": ["$ai_gift_image_bonus", 0]}, ai_image]}]},
        "claimed_promo_rewards": {"$setUnion": [{"$ifNull": ["$claimed_promo_rewards", []]}, [claimed_key]]},
        "last_promo_code": code,
        "last_promo_at": datetime.now(timezone.utc),
    }
    if badge:
        set_stage["badges"] = {"$setUnion": [{"$ifNull": ["$badges", []]}, [badge]]}
    await users_col.update_one(
        {"_id": user_id, "claimed_promo_rewards": {"$ne": claimed_key}},
        [{"$set": set_stage}],
        upsert=False,
    )
    coins = max(0, int(rewards.get("coins", 0) or 0))
    coin_result = {"amount": 0, "balance": await coin_balance(user_id)}
    if coins:
        coin_result = await apply_coin_transaction(
            user_id, coins, "promo_code", f"coin:promo:{redemption_id}", {"code": code}
        )
    await promo_redemptions_col.update_one(
        {"_id": redemption_id},
        {"$set": {
            "status": "completed", "rewards": rewards,
            "awarded_coins": int(coin_result.get("amount", 0)),
            "completed_at": datetime.now(timezone.utc),
        }},
    )
    balance_value = coin_result.get("balance")
    if balance_value is None:
        balance_value = await coin_balance(user_id)
    return {
        "ok": True, "duplicate": False, "code": code, "rewards": rewards,
        "awarded_coins": int(coin_result.get("amount", 0)),
        "coin_balance": int(balance_value),
        "sticker_file_id": item.get("sticker_file_id"),
        "animation_file_id": item.get("animation_file_id"),
    }


async def send_promo_redemption_result(message: types.Message, result: dict):
    if not result.get("ok"):
        texts = {
            "invalid": "❌ کد نامعتبر یا منقضی است.",
            "capacity": "❌ ظرفیت استفاده از این کد تمام شده.",
            "processing": "⏳ این کد در حال پردازش است؛ چند ثانیه دیگه دوباره امتحان کن.",
        }
        return await message.answer(texts.get(result.get("reason"), "❌ دریافت هدیه ممکن نشد."), reply_markup=rewards_reply_menu())
    summary = promo_reward_summary(result.get("rewards") or {})
    await message.answer(
        ("✅ این کد قبلاً برایت فعال شده بود.\n" if result.get("duplicate") else "🎉 <b>کد هدیه فعال شد!</b>\n")
        + f"\n🎁 {html.escape(summary)}",
        parse_mode="HTML",
        reply_markup=rewards_reply_menu(),
    )
    if result.get("sticker_file_id"):
        try: await message.answer_sticker(result["sticker_file_id"])
        except TelegramBadRequest: pass
    if result.get("animation_file_id"):
        try: await message.answer_animation(result["animation_file_id"], caption="🎁 گیف هدیه شما")
        except TelegramBadRequest: pass


@dp.callback_query(F.data == "promo_manage")
async def promo_manage_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "content"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    items = await promo_codes_col.find({"active": {"$ne": False}}).sort("created_at", -1).limit(20).to_list(length=20)
    rows = [[InlineKeyboardButton(text=f"🎟 {item['_id']} · {promo_reward_summary(item)[:35]} · {item.get('uses',0)}/{item.get('max_uses')}", callback_data=f"promoinfo:{item['_id']}"), InlineKeyboardButton(text="🗑", callback_data=f"promodel:{item['_id']}")] for item in items]
    rows.extend([[InlineKeyboardButton(text="➕ کد جدید", callback_data="promo_add")], [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")]])
    await callback.message.answer("🎟 <b>کدهای جایزه</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"); await callback.answer()


@dp.callback_query(F.data == "promo_add")
async def promo_add_start(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "content"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    promo_create_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "🎟 <b>ساخت کد هدیه چندمنظوره</b>\n\n"
        "فرمت: <code>CODE | پاداش‌ها | سقف استفاده | اعتبار روز</code>\n\n"
        "نمونه‌ها:\n"
        "<code>AJOR100 | xp=100 | 50 | 7</code>\n"
        "<code>COIN20 | coins=20 | 100 | 3</code>\n"
        "<code>VIPAI | xp=50,coins=10,ai_text=5,ai_image=1 | 20 | 7</code>\n"
        "<code>NEON | badge=badge_neon | 10 | 30</code>\n"
        "<code>FUNSTICKER | sticker,coins=5 | 50 | 7</code>\n"
        "<code>FUNGIF | gif,xp=20 | 50 | 7</code>\n\n"
        "نوع‌ها: xp، coins، ai_text، ai_image، badge، sticker، gif\n/cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("promodel:"))
async def promo_delete_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "content"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    code = callback.data.split(":",1)[1]; await promo_codes_col.update_one({"_id": code}, {"$set": {"active": False}}); await callback.answer("غیرفعال شد.", show_alert=True)


@dp.callback_query(F.data.startswith("promoinfo:"))
async def promo_info_callback(callback: types.CallbackQuery):
    code = callback.data.split(":", 1)[1]
    item = await promo_codes_col.find_one({"_id": code})
    if not item: return await callback.answer("کد پیدا نشد.", show_alert=True)
    expires = item.get("expires_at"); expires_text = format_tehran_datetime(expires) if isinstance(expires, datetime) else "نامشخص"
    await callback.answer(
        f"{code}\nپاداش: {promo_reward_summary(item)}\nاستفاده: {item.get('uses',0)}/{item.get('max_uses')}\nانقضا: {expires_text}",
        show_alert=True,
    )


@dp.callback_query(F.data == "gift_help")
async def gift_help_callback(callback: types.CallbackQuery):
    gift_redeem_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "🎟 کد هدیه‌ات رو بفرست؛ می‌تونه شامل سکه، XP، سهمیه AI، نشان، استیکر یا گیف باشه.\n"
        "مثال: <code>AJOR100</code>\n/cancel برای لغو",
        parse_mode="HTML",
        reply_markup=rewards_reply_menu(),
    )
    await callback.answer()


@dp.message(Command("gift"))
async def redeem_gift_command(message: types.Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        gift_redeem_sessions.add(message.from_user.id)
        return await message.answer("🎟 کد رو بفرست؛ مثال <code>AJOR100</code>", parse_mode="HTML", reply_markup=rewards_reply_menu())
    await ensure_user(message.from_user.id, message.from_user.full_name, username=message.from_user.username)
    result = await redeem_promo_code(message.from_user.id, parts[1])
    await send_promo_redemption_result(message, result)


def mission_progress(user: dict, mission: dict) -> int:
    field = MISSION_FIELD_MAP.get(str(mission.get("type")), "xp")
    return max(0, int(user.get(field, 0) or 0))


async def mission_snapshots(user_id: int) -> list[dict]:
    user = await users_col.find_one({"_id": user_id}) or {}
    items = await missions_col.find({"active": {"$ne": False}}).sort([("builtin", -1), ("created_at", 1)]).limit(30).to_list(length=30)
    claims = await mission_claims_col.find({"user_id": user_id}, {"mission_id": 1}).to_list(length=100)
    claimed_ids = {str(item.get("mission_id")) for item in claims}
    result = []
    for item in items:
        target = max(1, int(item.get("target", 1)))
        progress = mission_progress(user, item)
        result.append({
            "id": str(item["_id"]),
            "title": item.get("title") or "مأموریت",
            "description": item.get("description") or "",
            "type": item.get("type") or "points",
            "target": target,
            "progress": min(progress, target),
            "completed": progress >= target,
            "claimed": str(item["_id"]) in claimed_ids,
            "points": max(0, int(item.get("points", 0))),
            "coins": max(0, int(item.get("coins", 0))),
        })
    return result


async def claim_mission_reward(user_id: int, mission_id: ObjectId) -> dict:
    item = await missions_col.find_one({"_id": mission_id, "active": {"$ne": False}})
    user = await users_col.find_one({"_id": user_id}) or {}
    if not item:
        return {"ok": False, "reason": "not_found"}
    if mission_progress(user, item) < int(item.get("target", 1)):
        return {"ok": False, "reason": "incomplete"}
    claim_id = f"{mission_id}:{user_id}"
    try:
        await mission_claims_col.insert_one({
            "_id": claim_id,
            "mission_id": mission_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        return {"ok": False, "reason": "claimed"}
    points = max(0, int(item.get("points", 0)))
    coins = max(0, int(item.get("coins", 0)))
    if points:
        await users_col.update_one({"_id": user_id}, {"$inc": {"xp": points}})
        await record_score_event(user_id, points, "mission", f"score:mission:{claim_id}")
    coin_result = {"amount": 0, "balance": await coin_balance(user_id)}
    if coins:
        coin_result = await apply_coin_transaction(
            user_id,
            coins,
            "mission_reward",
            f"coin:mission:{claim_id}",
            {"mission_id": str(mission_id)},
            apply_multiplier=True,
        )
    balance_value = coin_result.get("balance")
    if balance_value is None:
        balance_value = await coin_balance(user_id)
    return {
        "ok": True,
        "mission_id": str(mission_id),
        "points": points,
        "coins": int(coin_result.get("amount", 0)),
        "coin_balance": int(balance_value),
    }


@dp.callback_query(F.data == "mission_manage")
async def mission_manage_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id,"content"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    items=await missions_col.find({"active":{"$ne":False}}).sort("created_at",-1).limit(20).to_list(length=20)
    rows=[[InlineKeyboardButton(text=f"🎯 {item['title']} · {item['points']} XP · {int(item.get('coins',0))} سکه",callback_data=f"missioninfo:{item['_id']}"),InlineKeyboardButton(text="🗑",callback_data=f"missiondel:{item['_id']}")] for item in items]
    rows.extend([[InlineKeyboardButton(text="➕ مأموریت جدید",callback_data="mission_add")],[InlineKeyboardButton(text="🔙 پنل",callback_data="admin_panel")]])
    await callback.message.answer("🎯 <b>مدیریت مأموریت‌ها</b>",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),parse_mode="HTML");await callback.answer()


@dp.callback_query(F.data == "mission_add")
async def mission_add_start(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id,"content"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    mission_create_sessions.add(callback.from_user.id);await callback.message.answer("فرمت: <code>دعوت ۵ دوست | referrals | 5 | 500 | 20</code>\nعنوان | نوع | هدف | XP | سکه\nنوع‌ها: referrals, games, streak, points, reactions, reviews, ai_requests, voice_transcriptions\n/cancel",parse_mode="HTML");await callback.answer()


@dp.callback_query(F.data.startswith("missioninfo:"))
async def mission_info_callback(callback:types.CallbackQuery):
    try:oid=ObjectId(callback.data.split(":",1)[1])
    except InvalidId:return await callback.answer("نامعتبر.",show_alert=True)
    item=await missions_col.find_one({"_id":oid})
    if not item:return await callback.answer("مأموریت پیدا نشد.",show_alert=True)
    await callback.answer(f"{item.get('title')}\n{item.get('description','')}\nنوع: {item.get('type')}\nهدف: {item.get('target')}\nجایزه: {item.get('points')} XP + {int(item.get('coins',0))} سکه",show_alert=True)


@dp.callback_query(F.data.startswith("missiondel:"))
async def mission_delete_callback(callback:types.CallbackQuery):
    try:oid=ObjectId(callback.data.split(":",1)[1])
    except InvalidId:return await callback.answer("نامعتبر.",show_alert=True)
    await missions_col.update_one({"_id":oid},{"$set":{"active":False}});await callback.answer("غیرفعال شد.",show_alert=True)


@dp.callback_query(F.data == "user_missions")
@dp.message(Command("missions"))
async def user_missions_handler(event):
    user = event.from_user
    message = event.message if isinstance(event, types.CallbackQuery) else event
    missions = await mission_snapshots(user.id)
    rows = []
    for item in missions:
        if item["claimed"]:
            icon, suffix = "☑️", "گرفته شد"
        elif item["completed"]:
            icon, suffix = "✅", "دریافت جایزه"
        else:
            icon, suffix = "⏳", f"{item['progress']}/{item['target']}"
        reward = f"{item['points']} XP"
        if item["coins"]:
            reward += f" + {item['coins']} سکه"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {item['title']} · {suffix} · {reward}",
            callback_data=f"missionclaim:{item['id']}",
        )])
    await message.answer(
        "🎯 <b>مأموریت‌های جایزه</b>\n\nکار واقعی انجام بده، پیشرفتت خودکار ثبت می‌شه و بعد جایزه رو بگیر.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="فعلاً مأموریتی نیست",callback_data="missionnoop")]]),
        parse_mode="HTML",
    )
    if isinstance(event, types.CallbackQuery):
        await event.answer()


@dp.callback_query(F.data.startswith("missionclaim:"))
async def mission_claim_callback(callback:types.CallbackQuery):
    try:
        oid = ObjectId(callback.data.split(":", 1)[1])
    except InvalidId:
        return await callback.answer("نامعتبر.", show_alert=True)
    result = await claim_mission_reward(callback.from_user.id, oid)
    if not result.get("ok"):
        messages = {
            "not_found": "مأموریت پیدا نشد.",
            "incomplete": "مأموریت هنوز کامل نشده.",
            "claimed": "جایزه قبلاً گرفته شده.",
        }
        return await callback.answer(messages.get(result.get("reason"), "جایزه قابل دریافت نیست."), show_alert=True)
    await callback.answer(
        f"🎉 {result['points']} XP و {result['coins']} سکه گرفتی!",
        show_alert=True,
    )


@dp.callback_query(F.data == "missionnoop")
async def mission_noop(callback:types.CallbackQuery):await callback.answer("فعلاً مأموریتی ثبت نشده.")


@dp.callback_query(F.data == "raffle_manage")
async def raffle_manage_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "content"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    items = await raffles_col.find({"status": "active"}).sort("ends_at", 1).limit(20).to_list(length=20)
    rows = [[InlineKeyboardButton(text=f"🎡 {item['title']} · {item.get('entries',0)} ورودی", callback_data=f"raffleinfo:{item['_id']}"), InlineKeyboardButton(text="🎯 قرعه", callback_data=f"raffledraw:{item['_id']}")] for item in items]
    rows.extend([[InlineKeyboardButton(text="➕ قرعه‌کشی جدید", callback_data="raffle_add")], [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")]])
    await callback.message.answer("🎡 <b>مدیریت قرعه‌کشی‌ها</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"); await callback.answer()


@dp.callback_query(F.data == "raffle_add")
async def raffle_add_start(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "content"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    raffle_create_sessions.add(callback.from_user.id); await callback.message.answer("فرمت: <code>قرعه‌کشی هفتگی | 50 | 24 | 5</code>\nعنوان | هزینه سکه | مدت ساعت | سقف ورودی هر کاربر\n/cancel", parse_mode="HTML"); await callback.answer()


@dp.callback_query(F.data.startswith("raffleinfo:"))
async def raffle_info_callback(callback: types.CallbackQuery):
    try: oid = ObjectId(callback.data.split(":",1)[1])
    except InvalidId: return await callback.answer("نامعتبر.", show_alert=True)
    item=await raffles_col.find_one({"_id":oid}); await callback.answer(f"{item.get('title')}\nهزینه: {item.get('cost')} سکه\nورودی: {item.get('entries',0)}\nاستخر: {item.get('pool',0)}", show_alert=True)


@dp.callback_query(F.data.startswith("raffledraw:"))
async def raffle_draw_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id,"content"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    try:oid=ObjectId(callback.data.split(":",1)[1])
    except InvalidId:return await callback.answer("نامعتبر.",show_alert=True)
    raffle=await raffles_col.find_one_and_update({"_id":oid,"status":"active"},{"$set":{"status":"drawing"}},return_document=ReturnDocument.BEFORE)
    if not raffle:return await callback.answer("قبلاً قرعه‌کشی شده.",show_alert=True)
    entries=await raffle_entries_col.find({"raffle_id":oid}).to_list(length=100000)
    if not entries:await raffles_col.update_one({"_id":oid},{"$set":{"status":"cancelled"}});return await callback.answer("هیچ شرکت‌کننده‌ای نبود.",show_alert=True)
    winner=random.choice(entries);prize=max(1,math.floor(int(raffle.get("pool",0))*.7));await apply_coin_transaction(winner["user_id"],prize,"raffle_prize",f"coin:raffle:{oid}:winner",{"raffle_id":str(oid)})
    await raffles_col.update_one({"_id":oid},{"$set":{"status":"completed","winner_id":winner["user_id"],"prize":prize,"drawn_at":datetime.now(timezone.utc)}})
    try:await bot.send_message(winner["user_id"],f"🏆 برنده «{raffle['title']}» شدی و {prize} سکه گرفتی!")
    except Exception:pass
    await audit_admin_action(callback.from_user.id,"raffle_draw",f"winner={winner['user_id']},prize={prize}",str(oid));await callback.answer(f"برنده: {winner['user_id']} · {prize} سکه",show_alert=True)


@dp.callback_query(F.data == "prediction_manage")
async def prediction_manage_callback(callback:types.CallbackQuery):
    if not has_permission(callback.from_user.id,"content"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    items=await predictions_col.find({"status":"active"}).sort("ends_at",1).limit(20).to_list(length=20);rows=[]
    for item in items:
        rows.append([InlineKeyboardButton(text=f"📈 {item['question'][:28]}",callback_data=f"predinfo:{item['_id']}")])
        rows.append([InlineKeyboardButton(text=f"✅ {option[:18]}",callback_data=f"predsettle:{item['_id']}:{index}") for index,option in enumerate(item['options'][:3])])
    rows.extend([[InlineKeyboardButton(text="➕ پیش‌بینی جدید",callback_data="prediction_add")],[InlineKeyboardButton(text="🔙 پنل",callback_data="admin_panel")]])
    await callback.message.answer("📈 <b>پیش‌بینی ترندها</b>\nبرای تسویه روی گزینه برنده بزن.",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),parse_mode="HTML");await callback.answer()


@dp.callback_query(F.data == "prediction_add")
async def prediction_add_start(callback:types.CallbackQuery):
    if not has_permission(callback.from_user.id,"content"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    prediction_create_sessions.add(callback.from_user.id);await callback.message.answer("فرمت: <code>کدام ترند می‌شود؟ | گزینه یک,گزینه دو | 24</code>\nسؤال | گزینه‌ها | مدت ساعت\n/cancel",parse_mode="HTML");await callback.answer()


@dp.callback_query(F.data.startswith("predinfo:"))
async def prediction_info_callback(callback:types.CallbackQuery):
    try:oid=ObjectId(callback.data.split(":",1)[1])
    except InvalidId:return await callback.answer("نامعتبر.",show_alert=True)
    item=await predictions_col.find_one({"_id":oid});await callback.answer(f"{item.get('question')}\nاستخر: {item.get('pool',0)} سکه",show_alert=True)


@dp.callback_query(F.data.startswith("predsettle:"))
async def prediction_settle_callback(callback:types.CallbackQuery):
    if not has_permission(callback.from_user.id,"content"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    _,oid_text,option_text=callback.data.split(":",2)
    try:oid=ObjectId(oid_text);winning=int(option_text)
    except (InvalidId,ValueError):return await callback.answer("نامعتبر.",show_alert=True)
    prediction=await predictions_col.find_one_and_update({"_id":oid,"status":"active"},{"$set":{"status":"settling","winning_option":winning}},return_document=ReturnDocument.BEFORE)
    if not prediction:return await callback.answer("قبلاً تسویه شده.",show_alert=True)
    bets=await prediction_bets_col.find({"prediction_id":oid,"status":"open"}).to_list(length=100000);winner_stake=sum(b['stake'] for b in bets if b['option']==winning);pool=sum(b['stake'] for b in bets);paid=0
    for bet in bets:
        if bet['option']==winning and winner_stake:
            payout=bet['stake']+math.floor(max(0,pool-winner_stake)*.85*bet['stake']/winner_stake);await apply_coin_transaction(bet['user_id'],payout,"prediction_prize",f"coin:{bet['_id']}:prize",{"prediction_id":str(oid)});paid+=payout;status="won"
        else:payout=0;status="lost"
        await prediction_bets_col.update_one({"_id":bet['_id']},{"$set":{"status":status,"payout":payout}})
    await predictions_col.update_one({"_id":oid},{"$set":{"status":"completed","winning_option":winning,"paid":paid,"settled_at":datetime.now(timezone.utc)}});await callback.answer(f"تسویه شد؛ {paid} سکه پرداخت شد.",show_alert=True)


@dp.callback_query(F.data == "template_manage")
async def template_manage_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "templates"): return await callback.answer("⛔ دسترسی قالب‌ها ندارید.", show_alert=True)
    items = await content_templates_col.find().sort("updated_at", -1).limit(30).to_list(length=30)
    rows = [[InlineKeyboardButton(text=f"📝 {item.get('name')}", callback_data=f"template_use:{item['_id']}"), InlineKeyboardButton(text="🗑", callback_data=f"template_del:{item['_id']}")] for item in items]
    rows.extend([[InlineKeyboardButton(text="➕ قالب جدید", callback_data="template_add")], [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")]])
    await callback.message.answer("📝 <b>قالب‌های آماده محتوا</b>\nبا انتخاب قالب، متن آن به گروه بازنشر اضافه می‌شود.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"); await callback.answer()


@dp.callback_query(F.data == "template_add")
async def template_add_start(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "templates"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    template_create_sessions.add(callback.from_user.id); await callback.message.answer("قالب را بفرست: <code>نام قالب | متن قالب</code>\n/cancel", parse_mode="HTML"); await callback.answer()


@dp.callback_query(F.data.startswith("template_use:"))
async def template_use_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "templates"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    try: oid = ObjectId(callback.data.split(":",1)[1])
    except InvalidId: return await callback.answer("شناسه نامعتبر.", show_alert=True)
    item = await content_templates_col.find_one({"_id": oid})
    if not item: return await callback.answer("قالب پیدا نشد.", show_alert=True)
    batch = repost_batches.get(callback.from_user.id) or create_repost_batch(callback.from_user.id); batch["items"].append({"payload": {"type": "text", "text": build_branded_caption(item["content"], 4096)}, "published": False})
    await callback.message.answer(f"✅ قالب «{html.escape(item['name'])}» به گروه بازنشر اضافه شد.", reply_markup=repost_batch_keyboard(len(batch["items"])), parse_mode="HTML"); await callback.answer()


@dp.callback_query(F.data.startswith("template_del:"))
async def template_delete_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "templates"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    try: oid = ObjectId(callback.data.split(":",1)[1])
    except InvalidId: return await callback.answer("شناسه نامعتبر.", show_alert=True)
    await content_templates_col.delete_one({"_id": oid}); await audit_admin_action(callback.from_user.id, "template_delete", target=str(oid)); await callback.answer("حذف شد.", show_alert=True)


@dp.callback_query(F.data == "admin_roles")
async def admin_roles_callback(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id): return await callback.answer("⛔ فقط مالک ربات.", show_alert=True)
    rows = []
    for admin_id, roles in delegated_admins_cache.items():
        role_text = "+".join(sorted(roles)) or "بدون نقش"
        rows.append([InlineKeyboardButton(text=f"{admin_id} · {role_text}", callback_data=f"roleinfo:{admin_id}"), InlineKeyboardButton(text="🗑", callback_data=f"roledel:{admin_id}")])
    rows.extend([
        [InlineKeyboardButton(text="➕ مدیر محتوا", callback_data="roleadd:content"), InlineKeyboardButton(text="➕ پشتیبانی", callback_data="roleadd:support")],
        [InlineKeyboardButton(text="➕ مالی", callback_data="roleadd:finance"), InlineKeyboardButton(text="➕ ناظر گروه", callback_data="roleadd:moderator")],
        [InlineKeyboardButton(text="➕ تحلیلگر", callback_data="roleadd:analyst")],
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await callback.message.answer("👮 <b>نقش مدیران</b>\nمدیر جدید را با نقش محدود اضافه کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("roleadd:"))
async def role_add_start(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id): return await callback.answer("⛔ فقط مالک ربات.", show_alert=True)
    role = callback.data.split(":", 1)[1]
    if role not in ROLE_PERMISSIONS or role == "owner": return await callback.answer("نقش نامعتبر.", show_alert=True)
    admin_role_sessions[callback.from_user.id] = role
    await callback.message.answer(f"آیدی عددی مدیر جدید برای نقش <b>{role}</b> را بفرست. /cancel برای لغو", parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("roledel:"))
async def role_delete_callback(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id): return await callback.answer("⛔ فقط مالک ربات.", show_alert=True)
    target = int(callback.data.split(":", 1)[1]); await admins_col.delete_one({"_id": target}); delegated_admins_cache.pop(target, None)
    await audit_admin_action(callback.from_user.id, "admin_role_deleted", target=str(target))
    await callback.answer("مدیر حذف شد.", show_alert=True)


@dp.callback_query(F.data.startswith("roleinfo:"))
async def role_info_callback(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id): return await callback.answer("⛔ فقط مالک ربات.", show_alert=True)
    target = int(callback.data.split(":", 1)[1]); roles = delegated_admins_cache.get(target, set())
    labels = {"content": "محتوا", "support": "پشتیبانی", "finance": "مالی", "moderator": "ناظر گروه", "analyst": "تحلیلگر"}
    rows = [[InlineKeyboardButton(text=f"{'✅' if role in roles else '➕'} {label}", callback_data=f"roletoggle:{target}:{role}")] for role, label in labels.items()]
    rows.extend([[InlineKeyboardButton(text="🗑 حذف کامل مدیر", callback_data=f"roledel:{target}")], [InlineKeyboardButton(text="🔙 مدیران", callback_data="admin_roles")]])
    await callback.message.answer(
        f"👮 <b>مدیر {target}</b>\nنقش‌های فعال: <code>{html.escape(', '.join(sorted(roles)) or 'ندارد')}</code>\n\nهر مدیر می‌تواند هم‌زمان چند نقش داشته باشد:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("roletoggle:"))
async def role_toggle_callback(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id): return await callback.answer("⛔ فقط مالک ربات.", show_alert=True)
    _, target_text, role = callback.data.split(":", 2); target = int(target_text)
    if role not in ROLE_PERMISSIONS or role == "owner": return await callback.answer("نقش نامعتبر.", show_alert=True)
    roles = set(delegated_admins_cache.get(target, set()))
    if role in roles: roles.remove(role)
    else: roles.add(role)
    if roles:
        await admins_col.update_one({"_id": target}, {"$set": {"roles": sorted(roles), "active": True, "updated_at": datetime.now(timezone.utc)}, "$unset": {"role": ""}}, upsert=True)
        delegated_admins_cache[target] = roles
    else:
        await admins_col.delete_one({"_id": target}); delegated_admins_cache.pop(target, None)
    await audit_admin_action(callback.from_user.id, "admin_roles_changed", ",".join(sorted(roles)), str(target))
    await callback.answer("نقش‌ها بروزرسانی شدند.", show_alert=True)


@dp.callback_query(F.data == "admin_audit")
async def admin_audit_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "stats"): return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    items = await admin_audit_col.find().sort("created_at", -1).limit(25).to_list(length=25)
    lines = ["📜 <b>آخرین فعالیت مدیران</b>", ""]
    for item in items:
        at = item.get("created_at"); when = at.strftime("%m-%d %H:%M") if isinstance(at, datetime) else "-"
        lines.append(f"• {when} · <code>{item.get('admin_id')}</code> · {html.escape(str(item.get('action')))}")
    await callback.message.answer("\n".join(lines)[:4000], parse_mode="HTML"); await callback.answer()


@dp.callback_query(F.data == "admin_health")
async def admin_health_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id,"stats"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    started=time.monotonic();mongo_ok=True
    try:await mongo_client.admin.command("ping")
    except Exception:mongo_ok=False
    info=await bot.get_webhook_info();errors=await health_events_col.count_documents({"created_at":{"$gte":datetime.now(timezone.utc)-timedelta(hours=24)}});pending=await scheduled_posts_col.count_documents({"status":"pending"})
    await callback.message.answer("🩺 <b>مرکز سلامت ربات</b>\n\n"f"Telegram API: ✅\nMongoDB: {'✅' if mongo_ok else '❌'}\nWebhook: {'✅' if info.url else '❌'}\nPending updates: {info.pending_update_count}\nپست زمان‌دار: {pending}\nخطاهای ۲۴ ساعت: {errors}\nUptime: {int(time.monotonic()-BOT_STARTED_AT)} ثانیه\nزمان بررسی: {int((time.monotonic()-started)*1000)}ms",parse_mode="HTML");await callback.answer()


@dp.callback_query(F.data == "admin_ai_status")
async def admin_ai_status_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "stats"):
        return await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
    day = today_str()
    status = ai_service.public_status()
    metrics, usage = await asyncio.gather(
        ai_provider_metrics_col.find({"day": day}).sort("calls", -1).to_list(length=20),
        ai_usage_col.aggregate([
            {"$match": {"day": day}},
            {"$group": {
                "_id": None,
                "users": {"$sum": 1},
                "text": {"$sum": "$text_requests"},
                "images": {"$sum": "$image_requests"},
            }},
        ]).to_list(length=1),
    )
    provider_labels = {
        "gemini": "Gemini متن",
        "gemini_vision": "Gemini تصویرخوان",
        "gemini_image": "Gemini تصویرساز",
        "gemini_audio": "Gemini ویس‌خوان",
        "groq_audio": "Groq Whisper",
        "pollinations_image": "Pollinations تصویر رایگان",
        "groq": "Groq",
        "cerebras": "Cerebras",
        "openrouter": "OpenRouter",
    }
    lines = [
        "🤖 <b>وضعیت هوش مصنوعی</b>",
        "",
        f"متن: {'✅' if status['configured'] else '❌'} · تصویر: {'✅' if status['image_generation'] else '❌'}",
        "زنجیره فعال: " + (" ← ".join(status["text_providers"]) or "هیچ‌کدام"),
    ]
    totals = usage[0] if usage else {}
    lines.extend([
        f"کاربران امروز: <b>{int(totals.get('users', 0)):,}</b>",
        f"درخواست متن امروز: <b>{int(totals.get('text', 0)):,}</b>",
        f"درخواست تصویر امروز: <b>{int(totals.get('images', 0)):,}</b>",
        "",
        "<b>ارائه‌دهنده‌ها</b>",
    ])
    if not metrics:
        lines.append("هنوز درخواستی ثبت نشده.")
    for item in metrics:
        calls = max(0, int(item.get("calls", 0)))
        successes = max(0, int(item.get("successes", 0)))
        failures = max(0, int(item.get("failures", 0)))
        avg = int(item.get("latency_ms_total", 0)) // max(1, calls)
        label = provider_labels.get(str(item.get("provider")), str(item.get("provider")))
        lines.append(
            f"• {html.escape(label)}: {successes}/{calls} موفق · {failures} خطا · میانگین {avg}ms"
        )
    await callback.message.answer("\n".join(lines)[:4000], parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_backup")
async def admin_backup_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id,"backup"):return await callback.answer("⛔ دسترسی پشتیبان ندارید.",show_alert=True)
    await callback.answer("در حال ساخت پشتیبان...")
    collections={"users":users_col,"settings":settings_col,"configs":configs_col,"withdrawals":withdrawals_col,"tickets":tickets_col,"required_channels":required_channels_col,"missions":missions_col,"promo_codes":promo_codes_col,"templates":content_templates_col,"service_orders":service_orders_col,"user_services":user_services_col}
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        for name,col in collections.items():
            docs=await col.find().limit(10000).to_list(length=10000);archive.writestr(f"{name}.json",json.dumps(docs,ensure_ascii=False,default=str,indent=2))
    output.seek(0);await callback.message.answer_document(BufferedInputFile(output.read(),filename=f"ajorpareh-backup-{today_str()}.zip"),caption="💾 پشتیبان تنظیمات و داده‌های اصلی")
    await audit_admin_action(callback.from_user.id,"backup_export")


@dp.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    now = datetime.now(timezone.utc)
    total_users, banned_users, active_24h, active_7d, new_24h = await asyncio.gather(
        users_col.count_documents({}),
        users_col.count_documents({"is_banned": True}),
        users_col.count_documents({"last_activity": {"$gte": now - timedelta(days=1)}}),
        users_col.count_documents({"last_activity": {"$gte": now - timedelta(days=7)}}),
        users_col.count_documents({"joined_at": {"$gte": now - timedelta(days=1)}}),
    )
    games = await users_col.aggregate([{"$group": {"_id": None, "count": {"$sum": "$games_played"}, "xp": {"$sum": "$xp"}}}]).to_list(length=1)
    game_count = int(games[0].get("count", 0)) if games else 0
    total_xp = int(games[0].get("xp", 0)) if games else 0
    open_tickets = await tickets_col.count_documents({"status": "open"})
    pending_withdrawals = await withdrawals_col.count_documents({"status": "pending"})
    await callback.message.answer(
        "📊 <b>داشبورد زنده Ajorpareh</b>\n\n"
        f"👥 کل کاربران: <b>{total_users:,}</b>\n"
        f"🆕 عضو جدید ۲۴ ساعت: <b>{new_24h:,}</b>\n"
        f"🟢 فعال ۲۴ ساعت: <b>{active_24h:,}</b>\n"
        f"📅 فعال ۷ روز: <b>{active_7d:,}</b>\n"
        f"🚫 مسدود: {banned_users:,}\n\n"
        f"🎮 مجموع بازی‌ها: <b>{game_count:,}</b>\n"
        f"⚡ XP توزیع‌شده: {total_xp:,}\n"
        f"🎫 تیکت باز: {open_tickets:,}\n"
        f"💸 برداشت در انتظار: {pending_withdrawals:,}\n\n"
        f"🖥 حالت اجرا: <code>{'WEBHOOK' if USE_WEBHOOK else 'POLLING'}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_analytics")
async def admin_analytics_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    since = datetime.now(timezone.utc) - timedelta(days=7)
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 12},
    ]
    rows = await activities_col.aggregate(pipeline).to_list(length=12)
    labels = {
        "start": "شروع ربات", "menu": "بازکردن منو", "daily_reward": "جایزه روزانه",
        "game_hit_run": "بزن در رو", "game_quiz": "کوئیز", "ai_chat": "گفتگو با AI",
        "get_proxy": "دریافت پروکسی", "youtube_download": "دانلود یوتیوب",
    }
    lines = ["📈 <b>فعالیت‌های ۷ روز اخیر</b>", ""]
    if rows:
        for row in rows:
            name = labels.get(row["_id"], str(row["_id"]))
            lines.append(f"• {html.escape(name)}: <b>{row['count']:,}</b>")
    else:
        lines.append("هنوز داده‌ای ثبت نشده است.")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

# ======== پنل رصد و نظارت مدیران ========

ACTIVITY_LABELS = {
    "start": "🚀 شروع ربات", "menu": "📋 بازکردن منو", "daily_reward": "🎁 جایزه روزانه",
    "game_hit_run": "🏃 بزن در رو", "game_quiz": "🧠 کوئیز", "game_memory": "🧠 جورچین حافظه",
    "game_bj": "🃏 بیست و یک", "game_rps": "🪨 سنگ‌کاغذقیچی", "game_guess": "🔢 حدس عدد",
    "game_dice": "🎲 تاس", "game_dart": "🎯 دارت", "game_coin": "🪙 شیر یا خط",
    "ai_chat": "🤖 گفتگو با AI", "ai_image": "🎨 ساخت تصویر", "ai_voice_transcription": "🎙 ویس به متن",
    "get_proxy": "🌐 دریافت پروکسی", "get_config": "🔐 دریافت کانفیگ",
    "media_social": "📥 دانلود شبکه", "media_direct": "🔗 آپلود URL", "media_audio": "🎵 استخراج صوت",
    "media_music": "🎵 دانلود آهنگ", "media_preview": "▶️ پیش‌نمایش", "media_music_preview": "🎵 پیش‌نمایش آهنگ",
    "youtube_download": "▶️ دانلود یوتیوب", "sticker_create": "🪄 ساخت استیکر",
    "gif_create": "🎞 ساخت گیف", "qr_create": "📱 ساخت QR", "reminder_add": "⏰ یادآور",
    "truth_dare": "🎭 جرأت یا حقیقت", "review_add": "⭐ ثبت نظر", "referral": "👥 دعوت دوست",
    "withdraw_request": "💸 درخواست برداشت", "service_order": "🛒 سفارش سرویس",
    "gift_redeem": "🎟 کد هدیه", "mission_claim": "🎯 مأموریت", "raffle_join": "🎡 قرعه‌کشی",
    "prediction_bet": "📈 پیش‌بینی", "spin": "🔄 گردونه", "hokm_create": "🎴 ساخت اتاق حکم",
    "hokm_join": "🎴 ورود به حکم", "casual_chat": "💬 گفتگو",
}


def _activity_label(action: str) -> str:
    return ACTIVITY_LABELS.get(str(action), str(action))


@dp.callback_query(F.data == "admin_live_activity")
async def admin_live_activity_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        rows = await activities_col.find().sort("timestamp", -1).limit(25).to_list(length=25)
    except Exception as exc:
        log.warning("live activity failed: %s", exc)
        return await callback.answer("خطا در خواندن فعالیت‌ها.", show_alert=True)
    lines = ["📡 <b>رصد زنده فعالیت‌ها</b>", "(۲۵ رویداد آخر)", ""]
    # بهینه: یک کوئری $in به‌جای ۲۵ کوئری جدا (N+1)
    name_cache: dict[int, str] = {}
    user_ids = [r.get("user_id") for r in rows if r.get("user_id")]
    if user_ids:
        try:
            found = await users_col.find({"_id": {"$in": user_ids}}, {"name": 1}).to_list(length=50)
            name_cache = {u["_id"]: (u.get("name") or "") for u in found}
        except Exception:
            pass
    for row in rows:
        user_id = row.get("user_id")
        name = name_cache.get(user_id) or (str(user_id) if user_id else "?")
        ts = row.get("timestamp")
        time_str = ""
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            time_str = ts.astimezone(timezone(timedelta(hours=3, minutes=30))).strftime("%H:%M")
        details = str(row.get("details") or "")[:60]
        lines.append(
            f"• <code>{user_id}</code> {html.escape(name[:20])} — {_activity_label(row.get('action'))} ({time_str})"
            + (f"\n  {html.escape(details)}" if details else "")
        )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="admin_live_activity")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


admin_activity_search_sessions: set[int] = set()


@dp.callback_query(F.data == "admin_activity_user")
async def admin_activity_user_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    admin_activity_search_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "🕵️ <b>رصد فعالیت یک کاربر</b>\n\nآیدی عددی یا @username کاربر را بفرست. /cancel",
        parse_mode="HTML", reply_markup=admin_reply_menu(),
    )
    await callback.answer()


async def show_user_activity(message: types.Message, target_id: int) -> None:
    user = await users_col.find_one({"_id": target_id}, {"name": 1, "username": 1, "joined_at": 1, "last_activity": 1})
    if not user:
        return await message.answer("❌ کاربری با این آیدی پیدا نشد.", reply_markup=admin_reply_menu())
    rows = await activities_col.find({"user_id": target_id}).sort("timestamp", -1).limit(25).to_list(length=25)
    name = (user.get("name") or "بدون نام")[:60]
    username = user.get("username")
    lines = [
        f"🕵️ <b>فعالیت‌های {html.escape(name)}</b>",
        f"آیدی: <code>{target_id}</code>" + (f" · @{html.escape(str(username))}" if username else ""),
        f"تعداد رویدادهای ثبت‌شده: <b>{await activities_col.count_documents({'user_id': target_id}):,}</b>",
        "",
    ]
    if not rows:
        lines.append("📭 هنوز فعالیتی ثبت نشده.")
    for row in rows:
        ts = row.get("timestamp")
        time_str = ""
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            time_str = ts.astimezone(timezone(timedelta(hours=3, minutes=30))).strftime("%m-%d %H:%M")
        details = str(row.get("details") or "")[:70]
        lines.append(f"• ({time_str}) {_activity_label(row.get('action'))}" + (f"\n  <code>{html.escape(details)}</code>" if details else ""))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 پروفایل کاربر", callback_data=f"admin_user_{target_id}")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "admin_active_users")
async def admin_active_users_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    today_start = datetime.now(timezone.utc) - timedelta(hours=24)
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    today_count = await users_col.count_documents({"last_activity": {"$gte": today_start}})
    week_count = await users_col.count_documents({"last_activity": {"$gte": week_start}})
    total = await users_col.count_documents({})
    active = await users_col.find({"last_activity": {"$gte": today_start}}).sort("last_activity", -1).limit(20).to_list(length=20)
    lines = [
        "🔥 <b>کاربران فعال</b>", "",
        f"👥 کل کاربران: <b>{total:,}</b>",
        f"📅 فعال در ۲۴ ساعت: <b>{today_count:,}</b>",
        f"📆 فعال در ۷ روز: <b>{week_count:,}</b>",
        "",
        "<b>۲۰ کاربر فعال اخیر:</b>",
    ]
    for u in active:
        name = (u.get("name") or "بدون نام")[:24]
        ts = u.get("last_activity")
        time_str = ""
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            time_str = ts.astimezone(timezone(timedelta(hours=3, minutes=30))).strftime("%H:%M")
        banned = "🚫" if u.get("is_banned") else ""
        lines.append(f"• {banned} {html.escape(name)} · <code>{u['_id']}</code> · {time_str}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="admin_active_users")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "admin_media_stats")
async def admin_media_stats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        queued = await media_jobs_col.count_documents({"status": "queued"})
        processing = await media_jobs_col.count_documents({"status": "processing"})
        completed = await media_jobs_col.count_documents({"status": "completed"})
        failed = await media_jobs_col.count_documents({"status": "failed"})
        preview = await media_jobs_col.count_documents({"status": "preview"})
        total = queued + processing + completed + failed + preview
        failed_24 = await media_jobs_col.count_documents({
            "status": "failed", "failed_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=24)},
        })
        lines = [
            "📊 <b>آمار مرکز رسانه</b>", "",
            f"📋 کل درخواست‌ها: <b>{total:,}</b>",
            f"⏳ در صف: <b>{queued}</b>",
            f"⚙️ در حال پردازش: <b>{processing}</b>",
            f"✅ کامل‌شده: <b>{completed:,}</b>",
            f"▶️ پیش‌نمایش: <b>{preview}</b>",
            f"❌ ناموفق: <b>{failed}</b> (۲۴ ساعت اخیر: {failed_24})",
            "",
            "💡 برای پاک‌سازی درخواست‌های قدیمی از «🧹 پاکسازی صف رسانه» استفاده کن.",
        ]
    except Exception as exc:
        log.warning("media stats failed: %s", exc)
        return await callback.answer("خطا در دریافت آمار رسانه.", show_alert=True)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 پاکسازی صف", callback_data="admin_media_cleanup")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "admin_media_cleanup")
async def admin_media_cleanup_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        # حذف درخواست‌های ناموفق/پیش‌نمایش قدیمی‌تر از ۳ روز و کامل‌شده‌های قدیمی‌تر از ۷ روز
        cutoff_failed = datetime.now(timezone.utc) - timedelta(days=3)
        cutoff_done = datetime.now(timezone.utc) - timedelta(days=7)
        removed = await media_jobs_col.delete_many({
            "$or": [
                {"status": "failed", "failed_at": {"$lt": cutoff_failed}},
                {"status": "preview", "completed_at": {"$lt": cutoff_done}},
                {"status": "completed", "completed_at": {"$lt": cutoff_done}},
            ]
        })
        await log_activity(callback.from_user.id, "admin_media_cleanup", f"removed={removed.deleted_count}")
        await callback.message.answer(
            f"🧹 <b>پاکسازی صف رسانه</b>\n\n{removed.deleted_count:,} درخواست قدیمی حذف شد. ✅",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 آمار رسانه", callback_data="admin_media_stats")],
                [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
            ]),
        )
    except Exception as exc:
        log.warning("media cleanup failed: %s", exc)
        return await callback.answer("خطا در پاکسازی صف.", show_alert=True)
    await callback.answer()


@dp.callback_query(F.data == "admin_ai_stats")
async def admin_ai_stats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    today = today_str()
    try:
        today_usage = await ai_usage_col.find_one({"_id": today})
        today_text = int((today_usage or {}).get("text_count", 0) or 0)
        today_image = int((today_usage or {}).get("image_count", 0) or 0)
        week_text = 0
        week_image = 0
        days_list = [(datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(7)]
        week_rows = await ai_usage_col.find({"_id": {"$in": days_list}}).to_list(length=10)
        for u in week_rows:
            week_text += int(u.get("text_count", 0) or 0)
            week_image += int(u.get("image_count", 0) or 0)
        provider_rows = await ai_provider_metrics_col.find({"day": today}).sort("calls", -1).limit(5).to_list(length=5)
        lines = [
            "📈 <b>آمار هوش مصنوعی</b>", "",
            f"📅 امروز: {today_text:,} پیام · {today_image:,} تصویر",
            f"📆 ۷ روز: {week_text:,} پیام · {week_image:,} تصویر",
            "",
            "<b>سرویس‌های امروز:</b>",
        ]
        if provider_rows:
            for row in provider_rows:
                calls = int(row.get("calls", 0) or 0)
                errors = int(row.get("errors", 0) or 0)
                lines.append(f"• {html.escape(str(row.get('provider', '')))}: {calls:,} درخواست ({errors} خطا)")
        else:
            lines.append("• داده‌ای ثبت نشده.")
    except Exception as exc:
        log.warning("ai stats failed: %s", exc)
        return await callback.answer("خطا در دریافت آمار هوش مصنوعی.", show_alert=True)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ])
    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


async def build_users_page(page: int = 0):
    per_page = 8
    page = max(0, page)
    users = await users_col.find().sort("last_activity", -1).skip(page * per_page).limit(per_page).to_list(length=per_page)
    total = await users_col.count_documents({})
    rows = []
    for user in users:
        status = "🚫" if user.get("is_banned") else ("⛔" if user.get("bot_blocked") else "✅")
        name = (user.get("name") or "بدون نام")[:24]
        rows.append([InlineKeyboardButton(text=f"{status} {name} · {user['_id']}", callback_data=f"admin_user_{user['_id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="➡️ قبلی", callback_data=f"users_page_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton(text="بعدی ⬅️", callback_data=f"users_page_{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔎 جستجو", callback_data="admin_search_user"), InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")])
    return f"👥 <b>کاربران</b> · صفحه {page + 1} · مجموع {total:,}", InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "list_users")
@dp.callback_query(F.data.startswith("users_page_"))
async def list_users_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    page = int(callback.data.rsplit("_", 1)[1]) if callback.data.startswith("users_page_") else 0
    text, keyboard = await build_users_page(page)
    await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_user_"))
async def admin_user_detail(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    target_id = int(callback.data.rsplit("_", 1)[1])
    user = await users_col.find_one({"_id": target_id})
    if not user:
        return await callback.answer("کاربر پیدا نشد.", show_alert=True)
    joined = user.get("joined_at")
    joined_text = joined.strftime("%Y-%m-%d") if isinstance(joined, datetime) else "نامشخص"
    ai_admin_text_bonus = max(0, min(ai_service.config.max_user_text_bonus, int(user.get("ai_admin_text_bonus", 0) or 0)))
    ai_admin_image_bonus = max(0, min(ai_service.config.max_user_image_bonus, int(user.get("ai_admin_image_bonus", 0) or 0)))
    ai_referral_text_bonus = max(0, min(ai_service.config.max_referral_text_bonus, int(user.get("ai_referral_text_bonus", 0) or 0)))
    ai_gift_text_bonus = max(0, min(ai_service.config.max_user_text_bonus, int(user.get("ai_gift_text_bonus", 0) or 0)))
    ai_gift_image_bonus = max(0, min(ai_service.config.max_user_image_bonus, int(user.get("ai_gift_image_bonus", 0) or 0)))
    text = (
        f"👤 <b>{html.escape(user.get('name') or 'بدون نام')}</b>\n"
        f"🆔 <code>{target_id}</code>\n"
        f"🔗 @{html.escape(user.get('username') or 'ندارد')}\n"
        f"📅 عضویت: {joined_text}\n\n"
        f"⚡ امتیاز: {int(user.get('xp', 0)):,}\n"
        f"🪙 سکه: {int(user.get('coins', 0)):,}\n"
        f"💵 کیف پول: {int(user.get('wallet_toman', 0)):,} تومان\n"
        f"🎮 بازی: {int(user.get('games_played', 0)):,} · برد: {int(user.get('games_won', 0)):,}\n"
        f"🎁 دعوت: {int(user.get('referral_count', 0)):,}\n"
        f"🤖 سهمیه متن: +{ai_admin_text_bonus} مدیر · +{ai_referral_text_bonus} رفرال · +{ai_gift_text_bonus} هدیه\n"
        f"🎨 سهمیه تصویر: +{ai_admin_image_bonus} مدیر · +{ai_gift_image_bonus} هدیه\n"
        f"وضعیت: {'🚫 مسدود' if user.get('is_banned') else '✅ فعال'} · کیف پول: {'🧊 فریز' if user.get('wallet_frozen') else '🟢 باز'}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 بن/آنبن", callback_data=f"admin_toggleban_{target_id}"),
         InlineKeyboardButton(text="📋 فعالیت", callback_data=f"admin_activity_{target_id}")],
        [InlineKeyboardButton(text="➕ ۱۰۰ امتیاز", callback_data=f"admin_addxp_{target_id}"),
         InlineKeyboardButton(text="➕ ۱۰ سکه", callback_data=f"admin_addcoin_{target_id}")],
        [InlineKeyboardButton(text="⚡ افزایش/کاهش امتیاز", callback_data=f"admin_adjust:{target_id}:xp"),
         InlineKeyboardButton(text="🪙 افزایش/کاهش سکه", callback_data=f"admin_adjust:{target_id}:coins")],
        [InlineKeyboardButton(text="💵 افزایش/کاهش تومان", callback_data=f"admin_adjust:{target_id}:wallet_toman")],
        [InlineKeyboardButton(text="🧊 فریز/بازکردن کیف پول", callback_data=f"admin_freeze_{target_id}")],
        [InlineKeyboardButton(text="🤖 مدیریت سهمیه هوش مصنوعی", callback_data=f"aiquota:{target_id}:show")],
        [InlineKeyboardButton(text="✉️ پیام مستقیم", url=f"tg://user?id={target_id}")],
        [InlineKeyboardButton(text="🔙 کاربران", callback_data="list_users")],
    ])
    await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


async def show_admin_ai_quota(callback: types.CallbackQuery, target_id: int):
    user = await users_col.find_one(
        {"_id": target_id},
        {"name": 1, "ai_admin_text_bonus": 1, "ai_admin_image_bonus": 1, "ai_referral_text_bonus": 1, "ai_gift_text_bonus": 1, "ai_gift_image_bonus": 1},
    ) or {}
    admin_text = max(0, min(ai_service.config.max_user_text_bonus, int(user.get("ai_admin_text_bonus", 0) or 0)))
    admin_image = max(0, min(ai_service.config.max_user_image_bonus, int(user.get("ai_admin_image_bonus", 0) or 0)))
    referral_text = max(0, min(ai_service.config.max_referral_text_bonus, int(user.get("ai_referral_text_bonus", 0) or 0)))
    gift_text = max(0, min(ai_service.config.max_user_text_bonus, int(user.get("ai_gift_text_bonus", 0) or 0)))
    gift_image = max(0, min(ai_service.config.max_user_image_bonus, int(user.get("ai_gift_image_bonus", 0) or 0)))
    text_limit = ai_service.config.daily_text_limit + admin_text + referral_text + gift_text
    image_limit = ai_service.config.daily_image_limit + admin_image + gift_image
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ ۵ پیام", callback_data=f"aiquota:{target_id}:text+5"),
         InlineKeyboardButton(text="➖ ۵ پیام", callback_data=f"aiquota:{target_id}:text-5")],
        [InlineKeyboardButton(text="➕ ۱ تصویر", callback_data=f"aiquota:{target_id}:image+1"),
         InlineKeyboardButton(text="➖ ۱ تصویر", callback_data=f"aiquota:{target_id}:image-1")],
        [InlineKeyboardButton(text="🧹 حذف سهمیه ویژه مدیر", callback_data=f"aiquota:{target_id}:reset")],
        [InlineKeyboardButton(text="🔙 اطلاعات کاربر", callback_data=f"admin_user_{target_id}")],
    ])
    await callback.message.answer(
        "🤖 <b>سهمیه ویژه هوش مصنوعی</b>\n\n"
        f"کاربر: {html.escape(user.get('name') or str(target_id))}\n"
        f"سهمیه پایه متن: {ai_service.config.daily_text_limit}\n"
        f"هدیه مدیر: +{admin_text}\n"
        f"هدیه رفرال: +{referral_text}\n"
        f"هدیه کدها: +{gift_text}\n"
        f"مجموع متن روزانه: <b>{text_limit}</b>\n\n"
        f"سهمیه پایه تصویر: {ai_service.config.daily_image_limit}\n"
        f"هدیه مدیر: +{admin_image}\n"
        f"هدیه کدها: +{gift_image}\n"
        f"مجموع تصویر روزانه: <b>{image_limit}</b>\n\n"
        "این افزایش هر روز همراه سهمیه پایه تازه می‌شود.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("aiquota:"))
async def admin_ai_quota_callback(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id):
        return await callback.answer("⛔ فقط مالک ربات می‌تواند سهمیه AI را تغییر دهد.", show_alert=True)
    try:
        _, target_text, action = callback.data.split(":", 2)
        target_id = int(target_text)
    except (ValueError, AttributeError):
        return await callback.answer("درخواست نامعتبر است.", show_alert=True)
    if action == "show":
        await show_admin_ai_quota(callback, target_id)
        return await callback.answer()
    user = await users_col.find_one(
        {"_id": target_id}, {"ai_admin_text_bonus": 1, "ai_admin_image_bonus": 1}
    )
    if not user:
        return await callback.answer("کاربر پیدا نشد.", show_alert=True)
    if action == "reset":
        new_text = new_image = 0
    else:
        current_text = max(0, int(user.get("ai_admin_text_bonus", 0) or 0))
        current_image = max(0, int(user.get("ai_admin_image_bonus", 0) or 0))
        if action == "text+5":
            new_text, new_image = min(ai_service.config.max_user_text_bonus, current_text + 5), current_image
        elif action == "text-5":
            new_text, new_image = max(0, current_text - 5), current_image
        elif action == "image+1":
            new_text, new_image = current_text, min(ai_service.config.max_user_image_bonus, current_image + 1)
        elif action == "image-1":
            new_text, new_image = current_text, max(0, current_image - 1)
        else:
            return await callback.answer("عملیات نامعتبر است.", show_alert=True)
    await users_col.update_one(
        {"_id": target_id},
        {"$set": {
            "ai_admin_text_bonus": new_text,
            "ai_admin_image_bonus": new_image,
            "ai_quota_updated_at": datetime.now(timezone.utc),
            "ai_quota_updated_by": callback.from_user.id,
        }},
    )
    await audit_admin_action(
        callback.from_user.id,
        "ai_quota_update",
        f"text={new_text},image={new_image}",
        str(target_id),
    )
    await callback.answer("سهمیه ویژه بروزرسانی شد ✅", show_alert=True)
    await show_admin_ai_quota(callback, target_id)


@dp.callback_query(F.data.startswith("admin_toggleban_"))
async def admin_toggle_ban(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    target_id = int(callback.data.rsplit("_", 1)[1])
    user = await users_col.find_one({"_id": target_id}, {"is_banned": 1}) or {}
    new_state = not bool(user.get("is_banned"))
    await users_col.update_one({"_id": target_id}, {"$set": {"is_banned": new_state, "ban_reason": "پنل مدیریت"}})
    await callback.answer("کاربر بن شد." if new_state else "کاربر آنبن شد.", show_alert=True)


@dp.callback_query(F.data.startswith("admin_addxp_") | F.data.startswith("admin_addcoin_"))
async def admin_add_balance(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "finance"):
        return await callback.answer("⛔ دسترسی مالی ندارید.", show_alert=True)
    target_id = int(callback.data.rsplit("_", 1)[1])
    field, amount = ("xp", 100) if callback.data.startswith("admin_addxp_") else ("coins", 10)
    result = await apply_admin_balance_adjustment(callback.from_user.id, target_id, field, amount)
    if not result.get("ok"):
        return await callback.answer("کاربر پیدا نشد یا تغییر انجام نشد.", show_alert=True)
    _, label = ADMIN_BALANCE_FIELDS[field]
    await callback.answer(f"{amount:,} {label} اضافه شد.", show_alert=True)


@dp.callback_query(F.data.startswith("admin_freeze_"))
async def admin_freeze_wallet(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "finance"): return await callback.answer("⛔ دسترسی مالی ندارید.", show_alert=True)
    target = int(callback.data.rsplit("_", 1)[1]); user = await users_col.find_one({"_id": target}, {"wallet_frozen": 1}) or {}
    frozen = not bool(user.get("wallet_frozen")); await users_col.update_one({"_id": target}, {"$set": {"wallet_frozen": frozen}})
    await audit_admin_action(callback.from_user.id, "wallet_freeze", str(frozen), str(target)); await callback.answer("کیف پول فریز شد." if frozen else "کیف پول باز شد.", show_alert=True)


ADMIN_BALANCE_FIELDS = {
    "xp": ("⚡", "امتیاز"),
    "coins": ("🪙", "سکه"),
    "wallet_toman": ("💵", "تومان"),
}
MAX_ADMIN_BALANCE_ADJUSTMENT = 1_000_000_000_000


async def apply_admin_balance_adjustment(admin_id: int, target_id: int, field: str, amount: int) -> dict:
    if field not in ADMIN_BALANCE_FIELDS or amount == 0 or abs(amount) > MAX_ADMIN_BALANCE_ADJUSTMENT:
        return {"ok": False, "reason": "invalid"}
    user = await users_col.find_one({"_id": target_id}, {field: 1, "name": 1})
    if not user:
        return {"ok": False, "reason": "not_found"}
    before = int(user.get(field, 0) or 0)
    if field == "coins":
        coin_result = await apply_coin_transaction(
            target_id,
            amount,
            "admin_manual_balance",
            f"coin:admin:{admin_id}:{target_id}:{uuid.uuid4().hex}",
            {"admin_id": admin_id},
        )
        if not coin_result.get("ok"):
            return {"ok": False, "reason": "insufficient"}
        applied = int(coin_result.get("amount", amount))
        after = int(coin_result.get("balance", before + applied))
    else:
        query: dict = {"_id": target_id}
        if amount < 0:
            query[field] = {"$gte": -amount}
        updated = await users_col.find_one_and_update(
            query,
            {"$inc": {field: amount}, "$set": {"last_admin_balance_at": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            return {"ok": False, "reason": "insufficient"}
        applied = amount
        after = int(updated.get(field, 0) or 0)
    transaction_id = f"admin-balance:{uuid.uuid4().hex}"
    transaction = {
        "_id": transaction_id,
        "user_id": target_id,
        "type": "admin_balance_adjustment",
        "field": field,
        "amount": applied,
        "balance_before": before,
        "balance_after": after,
        "admin_id": admin_id,
        "created_at": datetime.now(timezone.utc),
    }
    if field == "wallet_toman":
        transaction["amount_toman"] = applied
    try:
        await wallet_transactions_col.insert_one(transaction)
    except Exception as exc:
        log.warning("ثبت تراکنش تغییر موجودی %s ناموفق بود: %s", transaction_id, exc)
    await audit_admin_action(
        admin_id,
        "manual_balance",
        f"field={field},amount={applied:+},before={before},after={after},tx={transaction_id}",
        str(target_id),
    )
    icon, label = ADMIN_BALANCE_FIELDS[field]
    try:
        await bot.send_message(
            target_id,
            f"🎁 موجودی شما توسط مدیریت بروزرسانی شد.\n{icon} {label}: {applied:+,}\nموجودی جدید: {after:,}",
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    return {"ok": True, "field": field, "amount": applied, "before": before, "after": after, "name": user.get("name")}


async def complete_manual_balance_change(message: types.Message):
    admin_id = message.from_user.id
    if admin_id not in manual_balance_sessions or not has_permission(admin_id, "finance"):
        manual_balance_sessions.pop(admin_id, None)
        return await message.answer("⛔ دسترسی مالی ندارید.")
    target_id, field = manual_balance_sessions[admin_id]
    try:
        amount = int(normalize_digits(message.text or "").replace(",", "").replace("٬", "").strip())
    except ValueError:
        return await message.answer("عدد معتبر بفرست؛ مثلاً <code>500000</code> یا <code>-200</code>.", parse_mode="HTML")
    if amount == 0 or abs(amount) > MAX_ADMIN_BALANCE_ADJUSTMENT:
        return await message.answer("مقدار باید غیرصفر و حداکثر یک تریلیون باشد؛ دوباره بفرست یا /cancel.")
    result = await apply_admin_balance_adjustment(admin_id, target_id, field, amount)
    if not result.get("ok"):
        if result.get("reason") == "not_found":
            manual_balance_sessions.pop(admin_id, None)
            return await message.answer("❌ کاربر پیدا نشد.")
        if result.get("reason") == "insufficient":
            return await message.answer("❌ این کاهش موجودی را منفی می‌کند؛ مقدار کمتری بفرست.")
        return await message.answer("❌ مقدار یا درخواست نامعتبر است.")
    manual_balance_sessions.pop(admin_id, None)
    icon, label = ADMIN_BALANCE_FIELDS[result["field"]]
    sign = "+" if result["amount"] > 0 else ""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 بازگشت به کاربر", callback_data=f"admin_user_{target_id}")],
        [InlineKeyboardButton(text="💰 کاربر دیگر", callback_data="admin_balance_user")],
    ])
    return await message.answer(
        "✅ <b>موجودی بروزرسانی شد</b>\n\n"
        f"کاربر: {html.escape(result.get('name') or str(target_id))}\n"
        f"{icon} نوع: {label}\n"
        f"تغییر: <b>{sign}{result['amount']:,}</b>\n"
        f"قبل: {result['before']:,}\n"
        f"بعد: <b>{result['after']:,}</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("admin_adjust:"))
async def admin_adjust_start(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "finance"):
        return await callback.answer("⛔ دسترسی مالی ندارید.", show_alert=True)
    try:
        _, target, field = callback.data.split(":", 2)
        target_id = int(target)
    except (ValueError, AttributeError):
        return await callback.answer("درخواست نامعتبر است.", show_alert=True)
    if field not in ADMIN_BALANCE_FIELDS:
        return await callback.answer("فیلد نامعتبر است.", show_alert=True)
    user = await users_col.find_one({"_id": target_id}, {field: 1, "name": 1})
    if not user:
        return await callback.answer("کاربر پیدا نشد.", show_alert=True)
    manual_balance_sessions[callback.from_user.id] = (target_id, field)
    icon, label = ADMIN_BALANCE_FIELDS[field]
    current = int(user.get(field, 0) or 0)
    await callback.message.answer(
        f"{icon} <b>تغییر {label}</b>\n\n"
        f"کاربر: {html.escape(user.get('name') or str(target_id))}\n"
        f"موجودی فعلی: <b>{current:,}</b>\n\n"
        "عدد مثبت برای افزایش یا منفی برای کاهش بفرست.\n"
        "مثال: <code>1000000</code> یا <code>-500</code>\n"
        "حداکثر هر تغییر: یک تریلیون · لغو: /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_activity_"))
async def admin_activity_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    target_id = int(callback.data.rsplit("_", 1)[1])
    activities = await activities_col.find({"user_id": target_id}).sort("timestamp", -1).limit(12).to_list(length=12)
    lines = [f"📋 <b>آخرین فعالیت‌های {target_id}</b>", ""]
    for item in activities:
        lines.append(f"• <code>{html.escape(item.get('action', '-'))}</code> — {html.escape(str(item.get('details', ''))[:80])}")
    if not activities:
        lines.append("فعالیتی ثبت نشده است.")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_balance_user")
async def admin_balance_user_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "finance"):
        return await callback.answer("⛔ دسترسی مالی ندارید.", show_alert=True)
    admin_search_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "💰 <b>افزایش موجودی کاربر</b>\n\n"
        "آیدی عددی، نام یا <code>@username</code> کاربر رو بفرست.\n"
        "بعد از انتخاب کاربر می‌تونی تومان، سکه یا امتیازش رو تغییر بدی.\n\n"
        "برای انصراف /cancel",
        parse_mode="HTML",
        reply_markup=admin_finance_reply_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_search_user")
async def admin_search_user_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    admin_search_sessions.add(callback.from_user.id)
    await callback.message.answer("🔎 آیدی عددی، نام یا یوزرنیم کاربر را بفرست. برای انصراف /cancel")
    await callback.answer()


@dp.callback_query(F.data == "admin_export_users")
async def admin_export_users_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    rows = await users_col.find({}, {
        "_id": 1, "name": 1, "username": 1, "joined_at": 1, "last_activity": 1,
        "xp": 1, "coins": 1, "games_played": 1, "games_won": 1, "is_banned": 1,
    }).to_list(length=None)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["user_id", "name", "username", "joined_at", "last_activity", "xp", "coins", "games", "wins", "banned"])
    for user in rows:
        writer.writerow([
            user["_id"], user.get("name", ""), user.get("username", ""), user.get("joined_at", ""),
            user.get("last_activity", ""), user.get("xp", 0), user.get("coins", 0),
            user.get("games_played", 0), user.get("games_won", 0), user.get("is_banned", False),
        ])
    data = stream.getvalue().encode("utf-8-sig")
    await callback.message.answer_document(
        BufferedInputFile(data, filename=f"ajorpareh-users-{today_str()}.csv"),
        caption=f"📥 خروجی {len(rows):,} کاربر",
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_stars_settings")
async def admin_stars_settings_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    rate = await stars_toman_rate()
    enabled = bool(economy_settings.get("stars_enabled", True))
    auto = bool(economy_settings.get("stars_auto_rate", True))
    status = "✅ فعال" if enabled else "⛔ غیرفعال"
    rate_mode = "⚡ خودکار (قیمت رسمی)" if auto else "✍️ دستی"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"💱 نرخ هر ستاره: {rate:,} تومان", callback_data="econset:stars_rate_toman")],
        [InlineKeyboardButton(text="🔄 فعال/غیرفعال", callback_data="toggle_stars_enabled")],
        [InlineKeyboardButton(text="⚡ نرخ خودکار/دستی", callback_data="toggle_stars_auto")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
    ]
    await callback.message.answer(
        "⭐ <b>تنظیمات پرداخت با ستاره</b>\n\n"
        f"وضعیت: {status}\n"
        f"نرخ: {rate_mode}\n"
        f"هر <b>{rate:,} تومان</b> = ۱ ستاره\n\n"
        "📌 <b>نرخ خودکار:</b> ستاره یک ارز رسمیه (مثل تتر) و قیمتش از طرف تلگرام تعیین میشه.\n"
        "ربات هر بار قیمت رسمی (۱ ستاره ≈ ۲ سنت) رو × نرخ لحظهای دلار میکنه — نیازی به تعیین دستی نیست!\n\n"
        "1️⃣ @BotFather ← /mybots ← Ajorparehbot ← Payments ← Telegram Stars\n"
        "2️⃣ بعد از فعالسازی، کاربران با ستاره سرویس میخرن و ستارهها مستقیم به حساب تو میاد.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@dp.callback_query(F.data == "toggle_stars_auto")
async def toggle_stars_auto_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    economy_settings["stars_auto_rate"] = not bool(economy_settings.get("stars_auto_rate", True))
    await settings_col.update_one(
        {"_id": "runtime"},
        {"$set": {"economy.stars_auto_rate": bool(economy_settings.get("stars_auto_rate", True))}},
        upsert=True,
    )
    mode = "⚡ خودکار (قیمت رسمی)" if economy_settings.get("stars_auto_rate") else "✍️ دستی"
    await callback.answer(mode)
    await admin_stars_settings_callback(callback)


@dp.callback_query(F.data == "toggle_stars_enabled")
async def toggle_stars_enabled_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    economy_settings["stars_enabled"] = not bool(economy_settings.get("stars_enabled", True))
    await settings_col.update_one(
        {"_id": "runtime"},
        {"$set": {"economy.stars_enabled": bool(economy_settings.get("stars_enabled", True))}},
        upsert=True,
    )
    await callback.answer("✅" if economy_settings.get("stars_enabled") else "⛔")
    await admin_stars_settings_callback(callback)


FAL_MORNING_MESSAGES = (
    "امروز را با نیت روشن و یک قدم کوچک اما واقعی شروع کن؛ همین قدم‌های کوچک مسیرهای بزرگ می‌سازند.",
    "صبح امروز فرصت تازه‌ای است برای اینکه از نگرانی‌های دیروز فاصله بگیری و روی چیزی که در اختیار توست تمرکز کنی.",
    "نشانهٔ امروز بیشتر از جنس آرامش و روشن‌شدن تدریجی مسیر است؛ عجله نکن و تصمیم‌ها را با دل آرام بگیر.",
    "امروز یک گفت‌وگوی صادقانه یا یک خبر خوب می‌تواند نگاهت را به موضوعی قدیمی تغییر دهد.",
    "اگر راهت کمی کند پیش رفت، آن را نشانهٔ شکست ندان؛ بعضی نتیجه‌ها به زمان و مراقبت بیشتری نیاز دارند.",
    "امروز برای شروع دوباره، عذرخواهی، تشکر یا برداشتن یک قدم عقب‌افتاده روز مناسبی است.",
    "حافظ امروز تو را به دیدن فرصت‌هایی دعوت می‌کند که در شلوغی و عجله از کنارشان رد می‌شوی.",
    "به جای اینکه همهٔ مسیر را یک‌جا حل کنی، فقط کار مهم امروز را مشخص کن و با حوصله انجامش بده.",
)
FAL_FOCUSES = (
    "تمرکز امروزت را روی نظم، گفت‌وگوی روشن و تمام‌کردن یک کار نیمه‌تمام بگذار.",
    "امروز مرز میان خواستهٔ خودت و انتظار دیگران را با مهربانی اما شفاف نگه دار.",
    "به نشانه‌های کوچک پیشرفت توجه کن؛ لازم نیست نتیجهٔ بزرگ فوراً دیده شود.",
    "در تصمیم مهم امروز، احساس را بشنو اما اطلاعات و واقعیت را هم کنار آن بگذار.",
    "یک زمان کوتاه برای سکوت، نوشتن یا قدم‌زدن می‌تواند ذهن شلوغت را مرتب کند.",
    "امروز چیزی را که قابل کنترل نیست رها کن و انرژی‌ات را روی انتخاب بعدی خودت بگذار.",
    "با آدمی که برایت مهم است ارتباط بگیر؛ یک پیام ساده می‌تواند فاصله‌ای قدیمی را کمتر کند.",
    "در کار و رابطه، کیفیت حضور تو از سرعت واکنش‌دادنت مهم‌تر است.",
)
FAL_ACTIONS = (
    "پیشنهاد عملی: سه کار مهمت را بنویس و فقط اولی را تا پایان انجام بده.",
    "پیشنهاد عملی: قبل از پاسخ‌دادن به یک پیام حساس، چند دقیقه مکث و متن را دوباره مرور کن.",
    "پیشنهاد عملی: امروز یک هزینه یا تصمیم عجولانه را ۲۴ ساعت عقب بینداز و دوباره بررسی کن.",
    "پیشنهاد عملی: از یک نفر تشکر کن یا خبر خوبی را که مدت‌ها عقب انداخته‌ای با او در میان بگذار.",
    "پیشنهاد عملی: ده دقیقه برای مرتب‌کردن میز، فایل‌ها یا برنامهٔ فردایت کنار بگذار.",
    "پیشنهاد عملی: یک کار کوچک برای سلامت بدنت انجام بده؛ آب، خواب، حرکت یا غذای بهتر.",
    "پیشنهاد عملی: اگر هدفی داری، کوچک‌ترین اقدام قابل انجامش را همین امروز شروع کن.",
    "پیشنهاد عملی: چیزی را که از آن می‌ترسی روی کاغذ بنویس و فقط اولین راه امن مواجهه با آن را مشخص کن.",
)
FAL_CAUTIONS = (
    "یادآوری: از قول‌های عجولانه و تصمیم‌گیری در اوج خستگی یا عصبانیت دوری کن.",
    "یادآوری: هر خبری که می‌شنوی واقعیت نهایی نیست؛ قبل از قضاوت، منبع و جزئیات را بررسی کن.",
    "یادآوری: مهربانی با دیگران نباید به معنی نادیده‌گرفتن مرزها و نیازهای خودت باشد.",
    "یادآوری: امروز مقایسه‌کردن پشت‌صحنهٔ زندگی خودت با ظاهر زندگی دیگران کمکت نمی‌کند.",
    "یادآوری: اگر موضوعی مهم است، آن را فقط به فال نسپار و از مشورت و اطلاعات معتبر هم استفاده کن.",
    "یادآوری: تأخیر کوتاه گاهی برای کامل‌شدن تصمیم لازم است، اما ترس را بهانهٔ همیشگی نکن.",
    "یادآوری: در گفت‌وگوها به لحن خودت و برداشت طرف مقابل هم توجه کن؛ سوءتفاهم را زود روشن کن.",
    "یادآوری: امروز مراقب خرج‌های هیجانی و وعده‌های بیش از حد خوش‌بینانه باش.",
)
FAL_AFFIRMATIONS = (
    "جملهٔ امروز: من حق دارم آرام پیش بروم و در عین حال هر روز یک قدم جلوتر باشم.",
    "جملهٔ امروز: من میان امید و واقع‌بینی تعادل می‌سازم.",
    "جملهٔ امروز: پاسخ همه‌چیز را همین حالا نمی‌دانم، اما قدم بعدی‌ام را می‌توانم انتخاب کنم.",
    "جملهٔ امروز: ارزش من به سرعت رسیدنم یا نظر دیگران وابسته نیست.",
    "جملهٔ امروز: با ذهنی باز، قلبی مهربان و مرزهایی روشن روزم را می‌سازم.",
    "جملهٔ امروز: فرصت‌های تازه را می‌بینم و برای استفاده از آن‌ها آماده‌ام.",
    "جملهٔ امروز: از تجربهٔ گذشته یاد می‌گیرم، اما آینده‌ام را فقط با گذشته تعریف نمی‌کنم.",
    "جملهٔ امروز: آرامش من یک انتخاب روزانه است، نه پاداشی که باید از دیگران بگیرم.",
)
FAL_REFLECTIONS = (
    "برای تأمل: امروز کدام نگرانی را می‌توانی به یک اقدام کوچک تبدیل کنی؟",
    "برای تأمل: اگر از قضاوت دیگران نمی‌ترسیدی، امروز چه کاری را شروع می‌کردی؟",
    "برای تأمل: کدام رابطه یا هدف به توجه آرام و پیوستهٔ تو نیاز دارد؟",
    "برای تأمل: چه چیزی در زندگی‌ات همین حالا ارزش شکرگزاری دارد؟",
    "برای تأمل: کدام تصمیم را باید با اطلاعات بیشتر بگیری، نه با عجله؟",
    "برای تأمل: امروز چطور می‌توانی برای خودت همان‌قدر مهربان باشی که برای دوستت هستی؟",
    "برای تأمل: یک نشانهٔ واقعی پیشرفت در زندگی‌ات چیست که کمتر به آن توجه کرده‌ای؟",
    "برای تأمل: امروز چه چیزی را می‌توانی ساده‌تر، کوتاه‌تر یا روشن‌تر انجام بدهی؟",
)


def _daily_fal_pick(items: tuple[str, ...], seed: str, offset: int) -> str:
    digest = hashlib.sha256(f"{seed}:{offset}".encode()).digest()
    index = int.from_bytes(digest[:4], "big") % len(items)
    return items[index]


def build_fal_message(data: dict, *, morning: bool = False, for_channel: bool = False) -> str:
    """فال را با شعر، تفسیر و چند بخش کاربردی و متنوع برای صبح آماده می‌کند."""
    poem = [str(line).strip() for line in (data.get("poem") or []) if str(line).strip()][:14]
    interpretation = str(data.get("interpretation") or "").strip()
    if not poem and not interpretation:
        raise ValueError("فال خالی است")
    now_tehran = datetime.now(timezone(timedelta(hours=3, minutes=30)))
    date_text = now_tehran.strftime("%Y/%m/%d")
    seed = f"{date_text}|{'|'.join(poem[:3])}|{interpretation[:120]}"
    title = "🍷 فال صبحگاهی حافظ" if morning else "🍷 فال حافظ"
    lines = [title, f"📅 {date_text}", "", "🪞 <i>ای حافظ شیرازی…</i>", ""]
    lines.extend(f"<i>{html.escape(line)}</i>" for line in poem)
    if interpretation:
        lines.extend(["", "💬 <b>تفسیر فال:</b>", html.escape(interpretation[:1200])])
    if morning:
        lines.extend([
            "",
            "🌤 <b>پیام صبحگاهی:</b>",
            html.escape(_daily_fal_pick(FAL_MORNING_MESSAGES, seed, 1)),
            "",
            "🧭 <b>تمرکز امروز:</b>",
            html.escape(_daily_fal_pick(FAL_FOCUSES, seed, 2)),
            "",
            "🎯 <b>پیشنهاد عملی:</b>",
            html.escape(_daily_fal_pick(FAL_ACTIONS, seed, 3)),
            "",
            "⚠️ <b>یادآوری:</b>",
            html.escape(_daily_fal_pick(FAL_CAUTIONS, seed, 4)),
            "",
            "✨ <b>جملهٔ انرژی‌بخش:</b>",
            html.escape(_daily_fal_pick(FAL_AFFIRMATIONS, seed, 5)),
            "",
            "📝 <b>پرسش امروز:</b>",
            html.escape(_daily_fal_pick(FAL_REFLECTIONS, seed, 6)),
            "",
            (
                "🔔 برای حال خوب و تأمل است؛ تصمیم‌های مهمت را با عقل، اطلاعات و مشورت بگیر."
                if not for_channel
                else "🔔 برای فال شخصی و دریافت صبحگاهی، دکمهٔ پایین را بزن."
            ),
        ])
    else:
        lines.extend([
            "",
            "✨ <b>پیام امروز:</b>",
            html.escape(_daily_fal_pick(FAL_MORNING_MESSAGES, seed, 7)),
            "",
            "🧭 <b>یک پیشنهاد برای نیتت:</b>",
            html.escape(_daily_fal_pick(FAL_ACTIONS, seed, 8)),
        ])
    return "\n".join(lines)[:4000]


async def fetch_non_repeating_fal_message(date_key: str) -> tuple[dict, str]:
    """فال جدید را با مقایسهٔ ۳۰ روز اخیر انتخاب می‌کند."""
    history = await _recent_scheduled_history("daily_fal")
    previous = [item.get("core_text") or item.get("text") or "" for item in history]
    best: tuple[dict, str, float] | None = None
    for _attempt in range(5):
        data = await hafez_fal()
        candidate = build_fal_message(data, morning=True)
        score = sum(1.0 if scheduled_messages_similar(candidate, old) else 0.0 for old in previous)
        if best is None or score < best[2]:
            best = (data, candidate, score)
        if score == 0:
            return data, candidate
    if best is None:
        raise ValueError("فال جدیدی برای ارسال پیدا نشد")
    return best[0], best[1]


def daily_fal_target_status() -> str:
    target_id = runtime_settings.get("daily_fal_channel_id")
    if not target_id or not runtime_settings.get("daily_fal_channel_enabled"):
        return "❌ متصل نیست"
    title = str(runtime_settings.get("daily_fal_channel_title") or target_id)
    chat_type = str(runtime_settings.get("daily_fal_channel_type") or "مقصد")
    return f"✅ {html.escape(title[:70])} · {html.escape(chat_type)} · <code>{target_id}</code>"


def daily_fal_admin_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔄 فعال/غیرفعال فال خصوصی", callback_data="toggle_daily_fal")],
        [InlineKeyboardButton(text="🔗 اتصال یا تغییر کانال/گروه", callback_data="daily_fal_connect")],
    ]
    if runtime_settings.get("daily_fal_channel_id"):
        rows.append([
            InlineKeyboardButton(text="📤 ارسال آزمایشی", callback_data="daily_fal_test"),
            InlineKeyboardButton(text="🔌 قطع اتصال", callback_data="daily_fal_disconnect"),
        ])
    rows.append([InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def daily_fal_admin_text() -> str:
    private_status = "✅ فعال" if runtime_settings.get("daily_fal_enabled") else "⏸ غیرفعال"
    return (
        "🍷 <b>مدیریت فال روزانه صبحگاهی</b>\n\n"
        f"👤 ارسال برای مشترکین خصوصی: <b>{private_status}</b>\n"
        f"📣 مقصد کانال/گروه: {daily_fal_target_status()}\n\n"
        "فال متصل‌شده هر روز صبح به‌صورت خودکار ارسال می‌شود. "
        "برای اتصال، آیدی عددی، @username یا لینک عمومی کانال/گروه را بفرست."
    )


def parse_daily_fal_target(value: str) -> int | str:
    """آیدی عددی یا لینک عمومی t.me را به مقصد قابل استفادهٔ Bot API تبدیل می‌کند."""
    raw = normalize_digits(str(value or "").strip())
    if not raw:
        raise ValueError("آیدی یا لینک مقصد خالی است")
    if raw.lstrip("-").isdigit():
        chat_id = int(raw)
        if chat_id >= 0:
            raise ValueError("آیدی گروه/کانال باید معمولاً با -100 یا - شروع شود")
        return chat_id
    if raw.startswith("@") and re.fullmatch(r"@[A-Za-z0-9_]{5,32}", raw):
        return raw
    candidate = raw
    if not re.match(r"^https?://", candidate, flags=re.I):
        candidate = "https://" + candidate.lstrip("/")
    parsed = urlparse(candidate)
    if parsed.netloc.lower() not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        raise ValueError("فقط لینک عمومی t.me یا telegram.me قابل اتصال است")
    path = parsed.path.strip("/")
    if path.startswith("+") or path.startswith("joinchat/"):
        raise ValueError("لینک دعوت خصوصی به‌تنهایی قابل شناسایی نیست؛ آیدی عددی را بفرست و ربات را اول عضو/ادمین کن")
    if path.startswith("c/"):
        internal_id = path.split("/", 2)[1]
        if internal_id.isdigit():
            return int(f"-100{internal_id}")
    first = path.split("/", 1)[0]
    if first.lstrip("-").isdigit():
        return int(first)
    if re.fullmatch(r"[A-Za-z0-9_]{5,32}", first):
        return f"@{first}"
    raise ValueError("لینک عمومی کانال یا گروه پیدا نشد")


async def connect_daily_fal_target(message: types.Message, value: str) -> None:
    user_id = message.from_user.id
    try:
        identifier = parse_daily_fal_target(value)
        chat = await bot.get_chat(identifier)
        chat_type = getattr(chat.type, "value", str(chat.type))
        if chat_type not in {"channel", "group", "supergroup"}:
            raise ValueError("این مقصد کانال، گروه یا سوپرگروه نیست")
        bot_info = await bot.get_me()
        member = await bot.get_chat_member(chat.id, bot_info.id)
        member_status = getattr(member.status, "value", str(member.status))
        if chat_type == "channel" and member_status not in {"administrator", "creator"}:
            raise ValueError("برای ارسال در کانال، ربات باید ادمین یا سازنده باشد")
        if chat_type in {"group", "supergroup"} and member_status not in {"administrator", "creator", "member", "restricted"}:
            raise ValueError("ربات در این گروه عضو نیست یا اجازهٔ ارسال ندارد")
        if member_status == "restricted" and getattr(member, "can_send_messages", True) is False:
            raise ValueError("ربات در این گروه اجازهٔ ارسال پیام ندارد")
    except ValueError as exc:
        return await message.answer(f"❌ {exc}\nدوباره بفرست یا /cancel بزن.")
    except Exception as exc:
        log.warning("daily fal target connection failed: %s", exc)
        return await message.answer(
            "❌ مقصد پیدا نشد یا ربات داخلش دسترسی ارسال ندارد. آیدی/لینک را بررسی کن و دوباره بفرست."
        )

    username = getattr(chat, "username", None)
    public_link = f"https://t.me/{username}" if username else ""
    runtime_settings.update({
        "daily_fal_channel_enabled": True,
        "daily_fal_channel_id": int(chat.id),
        "daily_fal_channel_title": str(getattr(chat, "title", None) or username or chat.id),
        "daily_fal_channel_type": chat_type,
        "daily_fal_channel_username": str(username or ""),
        "daily_fal_channel_link": public_link,
    })
    await settings_col.update_one(
        {"_id": "runtime"},
        {
            "$set": {
                "daily_fal_channel_enabled": True,
                "daily_fal_channel_id": int(chat.id),
                "daily_fal_channel_title": runtime_settings["daily_fal_channel_title"],
                "daily_fal_channel_type": chat_type,
                "daily_fal_channel_username": str(username or ""),
                "daily_fal_channel_link": public_link,
            }
        },
        upsert=True,
    )
    daily_fal_channel_sessions.discard(user_id)
    await log_activity(user_id, "daily_fal_target_connected", f"chat_id={chat.id},type={chat_type}")
    await message.answer(
        f"✅ فال صبحگاهی به <b>{html.escape(runtime_settings['daily_fal_channel_title'])}</b> متصل شد.\n"
        "از این به بعد هر روز صبح خودکار ارسال می‌شود. برای اطمینان می‌توانی «📤 ارسال آزمایشی» را بزن.",
        parse_mode="HTML",
        reply_markup=daily_fal_admin_keyboard(),
    )


async def send_daily_fal_to_target(target_id: int | str, text: str) -> bool:
    try:
        await bot.send_message(
            int(target_id) if str(target_id).lstrip("-").isdigit() else target_id,
            text[:4000],
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🍷 فال شخصی در ربات", url="https://t.me/Ajorparehbot?start=daily_fal"),
            ]]),
        )
        return True
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            await bot.send_message(
                int(target_id) if str(target_id).lstrip("-").isdigit() else target_id,
                text[:4000],
                parse_mode="HTML",
            )
            return True
        except (TelegramForbiddenError, TelegramBadRequest) as retry_exc:
            log.warning("daily fal target retry failed: %s", retry_exc)
            return False
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        log.warning("daily fal target send failed: %s", exc)
        return False


@dp.callback_query(F.data == "toggle_daily_fal")
async def toggle_daily_fal_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    current = bool(runtime_settings.get("daily_fal_enabled"))
    runtime_settings["daily_fal_enabled"] = not current
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"daily_fal_enabled": not current}}, upsert=True)
    await callback.answer("فال خصوصی فعال شد ✅" if not current else "فال خصوصی غیرفعال شد ⏸")
    await callback.message.answer(daily_fal_admin_text(), reply_markup=daily_fal_admin_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "daily_fal_connect")
async def daily_fal_connect_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    daily_fal_channel_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "🔗 <b>اتصال مقصد فال صبحگاهی</b>\n\n"
        "یکی از این فرمت‌ها را بفرست:\n"
        "<code>@public_channel</code>\n"
        "<code>https://t.me/public_channel</code>\n"
        "<code>-1001234567890</code>\n"
        "<code>https://t.me/c/1234567890/15</code>\n\n"
        "ربات باید در کانال/گروه عضو باشد و برای ارسال پیام دسترسی داشته باشد. "
        "لینک دعوت خصوصی مثل <code>t.me/+...</code> به‌تنهایی قابل شناسایی نیست؛ در آن حالت آیدی عددی را بفرست. /cancel",
        parse_mode="HTML",
    )
    await callback.answer("آیدی یا لینک مقصد را بفرست 🔗")


@dp.callback_query(F.data == "daily_fal_disconnect")
async def daily_fal_disconnect_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    daily_fal_channel_sessions.discard(callback.from_user.id)
    runtime_settings.update({
        "daily_fal_channel_enabled": False,
        "daily_fal_channel_id": None,
        "daily_fal_channel_title": "",
        "daily_fal_channel_type": "",
        "daily_fal_channel_username": "",
        "daily_fal_channel_link": "",
    })
    await settings_col.update_one(
        {"_id": "runtime"},
        {
            "$set": {"daily_fal_channel_enabled": False},
            "$unset": {
                "daily_fal_channel_id": "",
                "daily_fal_channel_title": "",
                "daily_fal_channel_type": "",
                "daily_fal_channel_username": "",
                "daily_fal_channel_link": "",
            },
        },
        upsert=True,
    )
    await callback.message.answer("🔌 اتصال مقصد فال صبحگاهی قطع شد.", reply_markup=daily_fal_admin_keyboard())
    await callback.answer("اتصال قطع شد ✅")


@dp.callback_query(F.data == "daily_fal_test")
async def daily_fal_test_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    target_id = runtime_settings.get("daily_fal_channel_id")
    if not target_id:
        return await callback.answer("اول یک کانال یا گروه وصل کن.", show_alert=True)
    await callback.answer("در حال ارسال تست…")
    try:
        data = await hafez_fal()
        sent = await send_daily_fal_to_target(target_id, build_fal_message(data, morning=True, for_channel=True))
    except Exception as exc:
        log.warning("daily fal test failed: %s", exc)
        sent = False
    await callback.message.answer("✅ فال تست به مقصد ارسال شد." if sent else "❌ ارسال تست ناموفق بود؛ ادمین‌بودن ربات و آیدی مقصد را بررسی کن.", reply_markup=daily_fal_admin_keyboard())


GREETING_PAGE_SIZE = 8
GREETING_ADD_SESSION_LIMIT = 50
GREETING_BATCH_MAX_PER_MESSAGE = 20
SCHEDULED_NO_REPEAT_DAYS = 30
DAILY_MUSIC_NO_REPEAT_DAYS = 183  # حداقل شش ماه
SCHEDULED_MESSAGE_HISTORY_LIMIT = 500
SCHEDULED_GREETING_TEMPLATES = {
    "midnight": "🌙 ۰۰:۰۰\n\n{sentence}\n\nشبت آرام و دلت روشن.",
    "morning": "🌅 صبح بخیر\n\n{sentence}\n\nروزت پر از آرامش و اتفاق‌های خوب.",
}
GREETING_CONFIG = {
    "midnight": {
        "label": "🕛 00:00",
        "time": "00:00",
        "enabled_key": "midnight_greeting_enabled",
        "last_key": "midnight_greeting_last_date",
        "defaults": MIDNIGHT_DEFAULT_SENTENCES,
    },
    "morning": {
        "label": "🌅 صبح بخیر",
        "time": "08:00",
        "enabled_key": "morning_greeting_enabled",
        "last_key": "morning_greeting_last_date",
        "defaults": MORNING_DEFAULT_SENTENCES,
    },
}


def _greeting_config(kind: str) -> dict:
    if kind not in GREETING_CONFIG:
        raise ValueError("نوع جمله نامعتبر است")
    return GREETING_CONFIG[kind]


def greeting_target_status() -> str:
    target_id = runtime_settings.get("greeting_target_id")
    if not target_id or not runtime_settings.get("greeting_target_enabled"):
        return "❌ مقصدی وصل نیست"
    title = str(runtime_settings.get("greeting_target_title") or target_id)
    chat_type = str(runtime_settings.get("greeting_target_type") or "مقصد")
    return f"✅ {html.escape(title[:70])} · {html.escape(chat_type)} · <code>{target_id}</code>"


def scheduled_greeting_text(kind: str) -> str:
    config = _greeting_config(kind)
    enabled = bool(runtime_settings.get(config["enabled_key"]))
    status = "✅ فعال" if enabled else "⏸ غیرفعال"
    return (
        f"{config['label']} <b>جملهٔ خودکار</b>\n\n"
        f"وضعیت: <b>{status}</b>\n"
        f"زمان ارسال: <b>{config['time']}</b> به وقت تهران\n"
        f"مقصد: {greeting_target_status()}\n\n"
        "برای هر دو زمان‌بندی یک مقصد مشترک استفاده می‌شود. "
        "جمله‌های پیش‌فرض قابل حذف، ویرایش و تکمیل هستند."
    )


def scheduled_greeting_keyboard(kind: str) -> InlineKeyboardMarkup:
    config = _greeting_config(kind)
    enabled = bool(runtime_settings.get(config["enabled_key"]))
    rows = [[
        InlineKeyboardButton(
            text="⏸ غیرفعال‌کردن" if enabled else "✅ فعال‌کردن",
            callback_data=f"greettoggle:{kind}",
        )
    ]]
    rows.append([
        InlineKeyboardButton(text="🔗 اتصال یا تغییر مقصد", callback_data="greetconnect"),
        InlineKeyboardButton(text="🔌 قطع اتصال", callback_data="greetdisconnect"),
    ])
    if runtime_settings.get("greeting_target_id"):
        rows.append([InlineKeyboardButton(text="📤 ارسال آزمایشی", callback_data=f"greetsendtest:{kind}")])
    rows.extend([
        [
            InlineKeyboardButton(text="➕ افزودن جمله", callback_data=f"greetadd:{kind}"),
            InlineKeyboardButton(text="🛠 مدیریت جمله‌ها", callback_data=f"greetmanage:{kind}:0"),
        ],
        [InlineKeyboardButton(text="🔙 ابزارهای ربات", callback_data="greetback")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_scheduled_greeting_control(message: types.Message, kind: str) -> None:
    try:
        _greeting_config(kind)
    except ValueError:
        return await message.answer("❌ گزینهٔ جمله نامعتبر است.")
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ این ابزار فقط برای مدیر ربات فعال است.")
    await message.answer(
        scheduled_greeting_text(kind),
        parse_mode="HTML",
        reply_markup=scheduled_greeting_keyboard(kind),
    )


def sanitize_greeting_text(value: str) -> str:
    """لینک، یوزرنیم و آیدی‌های تلگرامی را از جملهٔ مدیر حذف می‌کند."""
    text = str(value or "").replace("\u200b", " ").strip()
    text = re.sub(
        r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/|tg://)\S+",
        " ",
        text,
    )
    text = re.sub(r"(?<![\w])@[A-Za-z0-9_]{5,32}", " ", text)
    text = re.sub(r"(?<!\d)-100\d{5,}(?!\d)", " ", text)
    text = re.sub(r"(?<!\d)\d{8,}(?!\d)", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n-–—|،,؛:")
    if len(text) < 3:
        raise ValueError("بعد از حذف لینک و آیدی، متن قابل استفاده‌ای باقی نماند")
    if len(text) > 500:
        raise ValueError("جمله نباید بیشتر از ۵۰۰ کاراکتر باشد")
    return text


async def seed_scheduled_greetings() -> None:
    """۱۰۰ جملهٔ هر دسته را فقط در اولین راه‌اندازی وارد MongoDB می‌کند."""
    marker_id = "scheduled_greeting_defaults_seeded"
    marker = await settings_col.find_one({"_id": marker_id}) or {}
    for kind, config in GREETING_CONFIG.items():
        if marker.get(kind):
            continue
        if await scheduled_greetings_col.count_documents({"kind": kind}) == 0:
            now = datetime.now(timezone.utc)
            await scheduled_greetings_col.insert_many([
                {
                    "_id": f"{kind}_default_{index:03d}",
                    "kind": kind,
                    "text": text,
                    "active": True,
                    "source": "default",
                    "order": index,
                    "created_at": now,
                    "updated_at": now,
                }
                for index, text in enumerate(config["defaults"], 1)
            ])
        await settings_col.update_one(
            {"_id": marker_id},
            {"$set": {kind: True}},
            upsert=True,
        )
        marker[kind] = True


async def _greeting_entries(kind: str) -> list[dict]:
    _greeting_config(kind)
    return await scheduled_greetings_col.find({"kind": kind}).sort(
        [("order", 1), ("created_at", 1)]
    ).to_list(length=500)


def _similarity_normal_form(text: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")).lower())
    value = re.sub(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", " ", value)
    value = re.sub(r"\d+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def scheduled_messages_similar(left: str, right: str) -> bool:
    """تشخیص تکرار واقعی و شباهت زیاد، نه فقط برابری دقیق متن."""
    a = _similarity_normal_form(left)
    b = _similarity_normal_form(right)
    if not a or not b:
        return False
    if a == b:
        return True
    left_tokens = set(a.split())
    right_tokens = set(b.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return jaccard >= 0.68 or SequenceMatcher(None, a, b).ratio() >= 0.80


async def _recent_scheduled_history(kind: str) -> list[dict]:
    retention_days = DAILY_MUSIC_NO_REPEAT_DAYS if kind == "daily_music" else SCHEDULED_NO_REPEAT_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    return await scheduled_message_history_col.find(
        {"kind": kind, "sent_at": {"$gte": cutoff}}
    ).sort("sent_at", -1).to_list(length=SCHEDULED_MESSAGE_HISTORY_LIMIT)


async def record_scheduled_message_history(
    kind: str,
    text: str,
    core_text: str,
    date_key: str,
    target_id: int | str,
) -> None:
    history_id = hashlib.sha256(f"{kind}:{target_id}:{date_key}".encode()).hexdigest()[:32]
    await scheduled_message_history_col.update_one(
        {"_id": history_id},
        {"$set": {
            "kind": kind,
            "text": text[:4000],
            "core_text": core_text[:1000],
            "date_key": date_key,
            "target_id": target_id,
            "status": "sent",
            "sent_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )


def render_scheduled_greeting(kind: str, sentence: str) -> str:
    template = SCHEDULED_GREETING_TEMPLATES[kind]
    return template.format(sentence=sentence)


async def _active_greeting(kind: str, date_key: str) -> tuple[dict | None, str | None]:
    entries = await scheduled_greetings_col.find(
        {"kind": kind, "active": {"$ne": False}}
    ).sort([("order", 1), ("created_at", 1)]).to_list(length=500)
    if not entries:
        return None, None
    history = await _recent_scheduled_history(kind)
    previous = [item.get("core_text") or item.get("text") or "" for item in history]
    candidates: list[tuple[dict, str]] = []
    for entry in entries:
        try:
            text = sanitize_greeting_text(entry.get("text", ""))
        except ValueError:
            continue
        if not any(scheduled_messages_similar(text, old) for old in previous):
            candidates.append((entry, text))
    if not candidates:
        # اگر مدیر کمتر از ۳۰ جملهٔ متفاوت نگه دارد، کم‌شباهت‌ترین مورد انتخاب می‌شود
        # تا زمان‌بندی متوقف نشود؛ با ۱۰۰ جملهٔ پیش‌فرض این شاخه معمولاً اجرا نمی‌شود.
        scored: list[tuple[float, dict, str]] = []
        for entry in entries:
            try:
                text = sanitize_greeting_text(entry.get("text", ""))
            except ValueError:
                continue
            score = sum(
                1.0 if scheduled_messages_similar(text, old) else 0.0
                for old in previous
            )
            scored.append((score, entry, text))
        if not scored:
            return None, None
        best_score = min(item[0] for item in scored)
        candidates = [(entry, text) for score, entry, text in scored if score == best_score]
    digest = hashlib.sha256(f"{kind}:{date_key}".encode()).digest()
    entry, text = candidates[int.from_bytes(digest[:4], "big") % len(candidates)]
    return entry, text


async def connect_scheduled_greeting_target(message: types.Message, value: str) -> None:
    user_id = message.from_user.id
    try:
        identifier = parse_daily_fal_target(value)
        chat = await bot.get_chat(identifier)
        chat_type = getattr(chat.type, "value", str(chat.type))
        if chat_type not in {"channel", "group", "supergroup"}:
            raise ValueError("این مقصد کانال، گروه یا سوپرگروه نیست")
        bot_info = await bot.get_me()
        member = await bot.get_chat_member(chat.id, bot_info.id)
        member_status = getattr(member.status, "value", str(member.status))
        if chat_type == "channel" and member_status not in {"administrator", "creator"}:
            raise ValueError("برای ارسال در کانال، ربات باید ادمین یا سازنده باشد")
        if chat_type in {"group", "supergroup"} and member_status not in {"administrator", "creator", "member", "restricted"}:
            raise ValueError("ربات در این گروه عضو نیست یا اجازهٔ ارسال ندارد")
        if member_status == "restricted" and getattr(member, "can_send_messages", True) is False:
            raise ValueError("ربات در این گروه اجازهٔ ارسال پیام ندارد")
    except ValueError as exc:
        return await message.answer(f"❌ {exc}\nدوباره بفرست یا /cancel بزن.")
    except Exception as exc:
        log.warning("scheduled greeting target connection failed: %s", exc)
        return await message.answer("❌ مقصد پیدا نشد یا ربات دسترسی ارسال ندارد؛ آیدی/لینک را بررسی کن.")

    username = getattr(chat, "username", None)
    public_link = f"https://t.me/{username}" if username else ""
    runtime_settings.update({
        "greeting_target_enabled": True,
        "greeting_target_id": int(chat.id),
        "greeting_target_title": str(getattr(chat, "title", None) or username or chat.id),
        "greeting_target_type": chat_type,
        "greeting_target_username": str(username or ""),
        "greeting_target_link": public_link,
    })
    await settings_col.update_one(
        {"_id": "runtime"},
        {"$set": {
            "greeting_target_enabled": True,
            "greeting_target_id": int(chat.id),
            "greeting_target_title": runtime_settings["greeting_target_title"],
            "greeting_target_type": chat_type,
            "greeting_target_username": str(username or ""),
            "greeting_target_link": public_link,
        }},
        upsert=True,
    )
    greeting_target_sessions.discard(user_id)
    await message.answer(
        f"✅ مقصد جمله‌های خودکار به <b>{html.escape(runtime_settings['greeting_target_title'])}</b> وصل شد.\n"
        "حالا از گزینهٔ فعال‌کردن یا ارسال آزمایشی استفاده کن.",
        parse_mode="HTML",
        reply_markup=tools_reply_menu(),
    )


def greeting_add_keyboard(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ پایان افزودن", callback_data=f"greetadd_done:{kind}"),
            InlineKeyboardButton(text="❌ لغو حالت افزودن", callback_data=f"greetadd_cancel:{kind}"),
        ],
        [InlineKeyboardButton(text="🛠 مدیریت جمله‌ها", callback_data=f"greetmanage:{kind}:0")],
    ])


async def save_greeting_sentence(message: types.Message, kind: str, raw_text: str) -> None:
    session = greeting_add_sessions.get(message.from_user.id)
    if isinstance(session, str):
        session = {"kind": session, "count": 0}
        greeting_add_sessions[message.from_user.id] = session
    if not isinstance(session, dict) or session.get("kind") != kind:
        return await message.answer("❌ جلسهٔ افزودن جمله پیدا نشد؛ دوباره از گزینهٔ افزودن جمله شروع کن.")
    current_count = int(session.get("count", 0))
    remaining = GREETING_ADD_SESSION_LIMIT - current_count
    if remaining <= 0:
        greeting_add_sessions.pop(message.from_user.id, None)
        return await message.answer("✅ سقف این نوبت تکمیل شد؛ جمله‌های ثبت‌شده حفظ شدند.")
    raw_items = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    if not raw_items:
        return await message.answer("❌ جملهٔ خالی قابل ذخیره نیست؛ جملهٔ بعدی را بفرست یا پایان را بزن.")
    if len(raw_items) > GREETING_BATCH_MAX_PER_MESSAGE:
        return await message.answer(
            f"❌ در هر پیام حداکثر {GREETING_BATCH_MAX_PER_MESSAGE} جمله بفرست؛ "
            "می‌توانی چند پیام پشت‌سرهم هم ارسال کنی."
        )
    if len(raw_items) > remaining:
        raw_items = raw_items[:remaining]
    documents = []
    rejected = 0
    now = datetime.now(timezone.utc)
    for raw_item in raw_items:
        try:
            cleaned = sanitize_greeting_text(raw_item)
        except ValueError:
            rejected += 1
            continue
        documents.append({
            "_id": f"{kind}_{uuid.uuid4().hex[:12]}",
            "kind": kind,
            "text": cleaned,
            "active": True,
            "source": "admin",
            "order": 10000,
            "created_at": now,
            "updated_at": now,
        })
    if documents:
        await scheduled_greetings_col.insert_many(documents)
        session["count"] = current_count + len(documents)
    saved_count = len(documents)
    if session.get("count", current_count) >= GREETING_ADD_SESSION_LIMIT:
        greeting_add_sessions.pop(message.from_user.id, None)
        ending = " سقف این نوبت تکمیل شد."
    else:
        ending = " جملهٔ بعدی را بفرست یا «پایان افزودن» را بزن."
    rejected_text = f" · {rejected} مورد به‌خاطر لینک/آیدی رد شد" if rejected else ""
    if saved_count == 0:
        return await message.answer(
            "❌ هیچ جملهٔ قابل ذخیره‌ای پیدا نشد؛ لینک و آیدی از متن حذف می‌شوند. دوباره بفرست.",
            reply_markup=greeting_add_keyboard(kind),
        )
    await message.answer(
        f"✅ {saved_count} جمله ثبت شد{rejected_text}. مجموع این نوبت: "
        f"{session.get('count', current_count + saved_count)} جمله.{ending}",
        reply_markup=greeting_add_keyboard(kind) if message.from_user.id in greeting_add_sessions else scheduled_greeting_keyboard(kind),
    )


async def edit_greeting_sentence(message: types.Message, kind: str, item_id: str, raw_text: str) -> None:
    try:
        text = sanitize_greeting_text(raw_text)
    except ValueError as exc:
        return await message.answer(f"❌ {exc}\nدوباره بفرست یا /cancel بزن.")
    result = await scheduled_greetings_col.update_one(
        {"_id": item_id, "kind": kind},
        {"$set": {"text": text, "updated_at": datetime.now(timezone.utc)}},
    )
    greeting_edit_sessions.pop(message.from_user.id, None)
    if not result.modified_count:
        return await message.answer("❌ جمله پیدا نشد؛ فهرست جمله‌ها را دوباره باز کن.")
    await message.answer(
        "✅ جمله ویرایش شد؛ لینک‌ها و آیدی‌های احتمالی از متن حذف شدند.",
        reply_markup=scheduled_greeting_keyboard(kind),
    )


async def show_greeting_manage(message: types.Message, kind: str, page: int, *, edit: bool = False) -> None:
    entries = await _greeting_entries(kind)
    total_pages = max(1, (len(entries) + GREETING_PAGE_SIZE - 1) // GREETING_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * GREETING_PAGE_SIZE
    visible = entries[start:start + GREETING_PAGE_SIZE]
    lines = [
        f"🛠 <b>مدیریت جمله‌های {html.escape(GREETING_CONFIG[kind]['label'])}</b>",
        f"تعداد جمله‌ها: <b>{len(entries)}</b> · صفحهٔ {page + 1} از {total_pages}",
        "",
    ]
    rows = []
    for index, entry in enumerate(visible, start + 1):
        sentence = html.escape(str(entry.get("text") or "")[:100])
        lines.append(f"<b>{index}.</b> {sentence}")
        rows.append([
            InlineKeyboardButton(text=f"✏️ ویرایش {index}", callback_data=f"greetedit:{kind}:{entry['_id']}"),
            InlineKeyboardButton(text=f"🗑 حذف {index}", callback_data=f"greetdelete:{kind}:{entry['_id']}"),
        ])
    if not visible:
        lines.append("هنوز جمله‌ای باقی نمانده؛ یک جملهٔ تازه اضافه کن.")
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"greetpage:{kind}:{page - 1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton(text="⏭ بعدی", callback_data=f"greetpage:{kind}:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.extend([
        [InlineKeyboardButton(text="➕ افزودن جمله", callback_data=f"greetadd:{kind}")],
        [InlineKeyboardButton(text="🔙 تنظیمات جمله", callback_data=f"greetcontrol:{kind}")],
    ])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


@dp.callback_query(F.data.startswith("greetcontrol:"))
async def greeting_control_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    kind = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        scheduled_greeting_text(kind),
        parse_mode="HTML",
        reply_markup=scheduled_greeting_keyboard(kind),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("greettoggle:"))
async def greeting_toggle_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    kind = callback.data.split(":", 1)[1]
    config = _greeting_config(kind)
    if not runtime_settings.get("greeting_target_id"):
        return await callback.answer("اول یک کانال یا گروه را وصل کن.", show_alert=True)
    new_value = not bool(runtime_settings.get(config["enabled_key"]))
    runtime_settings[config["enabled_key"]] = new_value
    await settings_col.update_one(
        {"_id": "runtime"},
        {"$set": {config["enabled_key"]: new_value}},
        upsert=True,
    )
    await callback.message.edit_text(
        scheduled_greeting_text(kind),
        parse_mode="HTML",
        reply_markup=scheduled_greeting_keyboard(kind),
    )
    await callback.answer("فعال شد ✅" if new_value else "غیرفعال شد ⏸")


@dp.callback_query(F.data == "greetconnect")
async def greeting_connect_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    greeting_target_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "🔗 آیدی یا لینک عمومی کانال/گروه را بفرست:\n"
        "<code>@public_channel</code> یا <code>-1001234567890</code> یا <code>https://t.me/public_channel</code>\n\n"
        "ربات باید داخل مقصد امکان ارسال داشته باشد. لینک دعوت خصوصی به‌تنهایی قابل شناسایی نیست؛ آیدی عددی را بفرست. /cancel",
        parse_mode="HTML",
    )
    await callback.answer("مقصد را بفرست 🔗")


@dp.callback_query(F.data == "greetdisconnect")
async def greeting_disconnect_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    greeting_target_sessions.discard(callback.from_user.id)
    runtime_settings.update({
        "greeting_target_enabled": False,
        "greeting_target_id": None,
        "greeting_target_title": "",
        "greeting_target_type": "",
        "greeting_target_username": "",
        "greeting_target_link": "",
    })
    await settings_col.update_one(
        {"_id": "runtime"},
        {
            "$set": {"greeting_target_enabled": False},
            "$unset": {
                "greeting_target_id": "",
                "greeting_target_title": "",
                "greeting_target_type": "",
                "greeting_target_username": "",
                "greeting_target_link": "",
            },
        },
        upsert=True,
    )
    await callback.message.answer("🔌 مقصد جمله‌های خودکار قطع شد.", reply_markup=tools_reply_menu())
    await callback.answer("اتصال قطع شد ✅")


@dp.callback_query(F.data.startswith("greetsendtest:"))
async def greeting_test_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    kind = callback.data.split(":", 1)[1]
    target_id = runtime_settings.get("greeting_target_id")
    if not target_id:
        return await callback.answer("اول مقصد را وصل کن.", show_alert=True)
    entry, text = await _active_greeting(kind, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if not entry or not text:
        return await callback.answer("برای این دسته جملهٔ فعالی وجود ندارد.", show_alert=True)
    sent = await send_scheduled_greeting_text(target_id, render_scheduled_greeting(kind, text))
    await callback.answer("تست ارسال شد ✅" if sent else "ارسال تست ناموفق بود.", show_alert=True)


@dp.callback_query(F.data.startswith("greetadd:"))
async def greeting_add_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    kind = callback.data.split(":", 1)[1]
    _greeting_config(kind)
    greeting_add_sessions[callback.from_user.id] = {"kind": kind, "count": 0}
    greeting_edit_sessions.pop(callback.from_user.id, None)
    await callback.message.answer(
        f"➕ حالت افزودن گروهی برای {GREETING_CONFIG[kind]['label']} فعال شد.\n"
        "حالا یک جمله در هر پیام یا چند جمله در چند خط بفرست؛ می‌توانی تا ۵۰ جمله پشت‌سرهم اضافه کنی.\n"
        "هر لینک، @username و آیدی عددی خودکار حذف می‌شود. برای پایان از دکمهٔ زیر یا /cancel استفاده کن.",
        reply_markup=greeting_add_keyboard(kind),
    )
    await callback.answer("حالت افزودن گروهی فعال شد ✍️")


@dp.callback_query(F.data.startswith("greetadd_done:") | F.data.startswith("greetadd_cancel:"))
async def greeting_add_finish_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    parts = callback.data.split(":", 1)
    kind = parts[1] if len(parts) > 1 else ""
    _greeting_config(kind)
    session = greeting_add_sessions.pop(callback.from_user.id, None)
    count = session.get("count", 0) if isinstance(session, dict) else 0
    await callback.message.answer(
        f"✅ حالت افزودن پایان یافت؛ {count} جمله در این نوبت ثبت شد.",
        reply_markup=scheduled_greeting_keyboard(kind),
    )
    await callback.answer("حالت افزودن بسته شد ✅")


@dp.callback_query(F.data.startswith("greetmanage:"))
async def greeting_manage_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    parts = callback.data.split(":")
    kind = parts[1] if len(parts) > 1 else ""
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    _greeting_config(kind)
    await show_greeting_manage(callback.message, kind, page, edit=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("greetpage:"))
async def greeting_page_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    parts = callback.data.split(":")
    kind = parts[1] if len(parts) > 1 else ""
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    _greeting_config(kind)
    await show_greeting_manage(callback.message, kind, page, edit=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("greetedit:"))
async def greeting_edit_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return await callback.answer("جمله نامعتبر است.", show_alert=True)
    kind, item_id = parts[1], parts[2]
    _greeting_config(kind)
    if not await scheduled_greetings_col.find_one({"_id": item_id, "kind": kind}):
        return await callback.answer("این جمله پیدا نشد.", show_alert=True)
    greeting_edit_sessions[callback.from_user.id] = (kind, item_id)
    greeting_add_sessions.pop(callback.from_user.id, None)
    await callback.message.answer(
        f"✏️ متن جدید جملهٔ {GREETING_CONFIG[kind]['label']} را بفرست.\n"
        "لینک‌ها و آیدی‌ها قبل از ذخیره حذف می‌شوند. /cancel",
    )
    await callback.answer("متن جدید را بفرست ✏️")


@dp.callback_query(F.data.startswith("greetdelete:"))
async def greeting_delete_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ این ابزار فقط برای مدیر است.", show_alert=True)
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return await callback.answer("جمله نامعتبر است.", show_alert=True)
    kind, item_id = parts[1], parts[2]
    _greeting_config(kind)
    await scheduled_greetings_col.delete_one({"_id": item_id, "kind": kind})
    await show_greeting_manage(callback.message, kind, 0, edit=True)
    await callback.answer("جمله حذف شد ✅")


@dp.callback_query(F.data == "greetback")
async def greeting_back_callback(callback: types.CallbackQuery):
    await callback.message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
    await callback.answer()


async def send_scheduled_greeting_text(target_id: int | str, text: str) -> bool:
    try:
        await bot.send_message(
            int(target_id) if str(target_id).lstrip("-").isdigit() else target_id,
            sanitize_greeting_text(text),
        )
        return True
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            await bot.send_message(
                int(target_id) if str(target_id).lstrip("-").isdigit() else target_id,
                sanitize_greeting_text(text),
            )
            return True
        except (TelegramForbiddenError, TelegramBadRequest) as retry_exc:
            log.warning("scheduled greeting retry failed: %s", retry_exc)
            return False
    except (TelegramForbiddenError, TelegramBadRequest, ValueError) as exc:
        log.warning("scheduled greeting send failed: %s", exc)
        return False


async def scheduled_greetings_worker():
    """ارسال جمل فعال در نیمه‌شب و صبح، با جلوگیری از ارسال تکراری روزانه."""
    while True:
        try:
            target_id = (
                runtime_settings.get("greeting_target_id")
                if runtime_settings.get("greeting_target_enabled")
                else None
            )
            if target_id:
                now_tehran = datetime.now(timezone(timedelta(hours=3, minutes=30)))
                date_key = now_tehran.strftime("%Y-%m-%d")
                for kind, config in GREETING_CONFIG.items():
                    if not runtime_settings.get(config["enabled_key"]):
                        continue
                    last_date = runtime_settings.get(config["last_key"])
                    if last_date == date_key:
                        continue
                    already_sent = await scheduled_message_history_col.find_one({
                        "kind": kind,
                        "date_key": date_key,
                        "status": "sent",
                    })
                    if already_sent:
                        runtime_settings[config["last_key"]] = date_key
                        continue
                    if kind == "midnight":
                        due = 0 <= now_tehran.hour < 2
                    else:
                        due = 8 <= now_tehran.hour < 12
                    if not due:
                        continue
                    entry, text = await _active_greeting(kind, date_key)
                    if not entry or not text:
                        log.warning("no active scheduled greeting for %s", kind)
                        continue
                    rendered = render_scheduled_greeting(kind, text)
                    if await send_scheduled_greeting_text(target_id, rendered):
                        await record_scheduled_message_history(
                            kind,
                            rendered,
                            text,
                            date_key,
                            target_id,
                        )
                        runtime_settings[config["last_key"]] = date_key
                        await settings_col.update_one(
                            {"_id": "runtime"},
                            {"$set": {config["last_key"]: date_key}},
                            upsert=True,
                        )
                        log.info("scheduled greeting sent: kind=%s,target=%s", kind, target_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("scheduled greetings worker error: %s", exc)
        await asyncio.sleep(30)


@dp.callback_query(F.data == "toggle_auto_rates")
async def toggle_auto_rates_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    current = bool(runtime_settings.get("auto_rates_channel"))
    runtime_settings["auto_rates_channel"] = not current
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"auto_rates_channel": not current}}, upsert=True)
    await callback.answer("فعال شد ✅" if not current else "غیرفعال شد ⏸")
    await callback.message.answer(
        f"📈 پست خودکار نرخ ارز: {'✅ فعال' if not current else '⏸ غیرفعال'}\n"
        "هر ۶ ساعت، نرخ ارز + قیمت کریپتو به کانال فرستاده می‌شود.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
        ]),
    )


@dp.callback_query(F.data == "toggle_daily_prayer")
async def toggle_daily_prayer_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    current = bool(runtime_settings.get("daily_prayer_channel"))
    runtime_settings["daily_prayer_channel"] = not current
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"daily_prayer_channel": not current}}, upsert=True)
    await callback.answer("فعال شد ✅" if not current else "غیرفعال شد ⏸")
    city = str(runtime_settings.get("daily_prayer_city") or "تهران")
    await callback.message.answer(
        f"🕌 پست اذان روزانه در کانال: {'✅ فعال' if not current else '⏸ غیرفعال'}\n"
        f"🏙 شهر: {city}\n"
        "هر روز ساعت ۵:۳۰ صبح به وقت تهران، اوقات شرعی امروز به کانال فرستاده می‌شود.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏙 تغییر شهر اذان", callback_data="set_prayer_city")],
            [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
        ]),
    )


@dp.callback_query(F.data == "set_prayer_city")
async def set_prayer_city_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    awaiting_prayer_city.add(callback.from_user.id)
    await callback.message.answer("🏙 نام شهر رو بفرست (مثلاً: مشهد، اصفهان، شیراز، تبریز...)")
    await callback.answer()


async def auto_rates_worker():
    """هر ۶ ساعت نرخ ارز و کریپتو را در کانال منتشر می‌کند (اگر فعال باشد)."""
    while True:
        try:
            if runtime_settings.get("auto_rates_channel") and CHANNEL_ID:
                last = runtime_settings.get("auto_rates_last")
                now = datetime.now(timezone.utc)
                if not last or (now - last) >= timedelta(hours=6):
                    usd_irr = eur_irr = gbp_irr = None
                    try:
                        usd = await exchange_rate("usd", "irr")
                        usd_irr = int(usd["rate"])
                    except Exception:
                        pass
                    try:
                        eur = await exchange_rate("eur", "irr")
                        eur_irr = int(eur["rate"])
                    except Exception:
                        pass
                    try:
                        gbp = await exchange_rate("gbp", "irr")
                        gbp_irr = int(gbp["rate"])
                    except Exception:
                        pass
                    crypto_lines = []
                    try:
                        coins = await crypto_price(["btc", "eth", "تتر"])
                        for coin in coins:
                            crypto_lines.append(f"{coin['symbol']}: ${coin['price_usd']:,.2f}")
                    except Exception:
                        pass
                    gold_toman = None
                    try:
                        gold_toman = await gold_price_toman()
                    except Exception:
                        pass
                    lines = ["📈 <b>گزارش بازار</b>", ""]
                    if usd_irr:
                        lines.append(f"🇺🇸 دلار: <b>{usd_irr:,} ریال</b> ({usd_irr // 1000:,} تومان)")
                    if eur_irr:
                        lines.append(f"🇪🇺 یورو: <b>{eur_irr:,} ریال</b>")
                    if gbp_irr:
                        lines.append(f"🇬🇧 پوند: <b>{gbp_irr:,} ریال</b>")
                    if gold_toman:
                        lines.append(f"🥇 طلای ۱۸ عیار: <b>{gold_toman:,} تومان</b>/گرم")
                    if crypto_lines:
                        lines.append("")
                        lines.append("🪙 <b>کریپتو:</b>")
                        lines.append(" · ".join(crypto_lines))
                    if len(lines) > 2:
                        try:
                            await bot.send_message(CHANNEL_ID, "\n".join(lines), parse_mode="HTML")
                            runtime_settings["auto_rates_last"] = now
                            await settings_col.update_one({"_id": "runtime"}, {"$set": {"auto_rates_last": now}}, upsert=True)
                            log.info("auto rates posted to channel")
                        except (TelegramForbiddenError, TelegramBadRequest) as exc:
                            log.warning("auto rates post failed: %s", exc)
        except Exception as exc:
            log.warning("auto rates worker error: %s", exc)
        await asyncio.sleep(600)  # هر ۱۰ دقیقه چک


async def daily_fal_worker():
    """فال صبحگاهی را برای مشترکین و مقصد متصل‌شده ارسال می‌کند."""
    while True:
        try:
            send_to_users = bool(runtime_settings.get("daily_fal_enabled"))
            target_id = (
                runtime_settings.get("daily_fal_channel_id")
                if runtime_settings.get("daily_fal_channel_enabled")
                else None
            )
            if send_to_users or target_id:
                now_tehran = datetime.now(timezone(timedelta(hours=3, minutes=30)))
                last_date = runtime_settings.get("daily_fal_last_date")
                # پنجرهٔ ۷ تا ۱۲ باعث می‌شود Restart یا قطعی کوتاه، فال همان صبح را از بین نبرد.
                in_morning_window = 7 <= now_tehran.hour < 12
                today_key = now_tehran.strftime("%Y-%m-%d")
                if in_morning_window and last_date != today_key:
                    already_sent = await scheduled_message_history_col.find_one({
                        "kind": "daily_fal",
                        "date_key": today_key,
                        "status": "sent",
                    })
                    if already_sent:
                        runtime_settings["daily_fal_last_date"] = today_key
                        continue
                    subscribed = []
                    if send_to_users:
                        subscribed = await users_col.find(
                            {"fal_subscribed": True, "is_banned": {"$ne": True}}
                        ).to_list(length=500)
                    try:
                        _fal_data, text = await fetch_non_repeating_fal_message(today_key)
                    except Exception as exc:
                        log.warning("daily fal fetch failed: %s", exc)
                        text = None
                    if text:
                        channel_sent = False
                        if target_id:
                            channel_sent = await send_daily_fal_to_target(target_id, text)
                            if not channel_sent:
                                log.warning("daily fal was not delivered to target %s", target_id)
                        sent = 0
                        for user in subscribed:
                            try:
                                await bot.send_message(
                                    int(user["_id"]), text[:4000], parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                        [InlineKeyboardButton(text="🍷 فال دوباره", callback_data="daily_fal_again")],
                                        [InlineKeyboardButton(text="🔕 لغو اشتراک", callback_data="daily_fal_off")],
                                    ]),
                                )
                                sent += 1
                                await asyncio.sleep(0.08)
                            except (TelegramForbiddenError, TelegramBadRequest):
                                continue
                        if channel_sent or sent:
                            await record_scheduled_message_history(
                                "daily_fal",
                                text,
                                text,
                                today_key,
                                target_id or "private_subscriptions",
                            )
                        # فال تولید شده؛ حتی اگر امروز مشترکی نداشته باشیم، دوباره در همان صبح تکرار نشود.
                        runtime_settings["daily_fal_last_date"] = today_key
                        await settings_col.update_one(
                            {"_id": "runtime"},
                            {"$set": {"daily_fal_last_date": today_key}},
                            upsert=True,
                        )
                        log.info(
                            "daily fal delivered: users=%d,target=%s",
                            sent,
                            bool(channel_sent),
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("daily fal worker error: %s", exc)
        await asyncio.sleep(60)


async def daily_prayer_worker():
    """هر روز ساعت ۵:۳۰ صبح به وقت تهران، اوقات شرعی امروز در کانال منتشر می‌شود."""
    while True:
        try:
            if runtime_settings.get("daily_prayer_channel") and CHANNEL_ID:
                now_tehran = datetime.now(timezone(timedelta(hours=3, minutes=30)))
                last_date = runtime_settings.get("daily_prayer_last_date")
                if now_tehran.hour == 5 and now_tehran.minute >= 30 and last_date != now_tehran.strftime("%Y-%m-%d"):
                    text = None
                    try:
                        city = str(runtime_settings.get("daily_prayer_city") or "تهران")
                        data = await prayer_times(city)
                        text = format_prayer_text(data)
                    except Exception as exc:
                        log.warning("daily prayer fetch failed: %s", exc)
                    if text:
                        await bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
                        runtime_settings["daily_prayer_last_date"] = now_tehran.strftime("%Y-%m-%d")
                        await settings_col.update_one(
                            {"_id": "runtime"},
                            {"$set": {"daily_prayer_last_date": now_tehran.strftime("%Y-%m-%d")}},
                            upsert=True,
                        )
                        log.info("daily prayer times posted to channel")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("daily prayer worker error: %s", exc)
        await asyncio.sleep(60)


# ============ اذان‌گوی شخصی ============
AZAN_LABELS = {"Fajr": "اذان صبح", "Dhuhr": "اذان ظهر", "Asr": "اذان عصر", "Maghrib": "اذان مغرب", "Isha": "اذان عشاء"}
_azan_cache: dict = {"date": "", "timings": {}, "city": ""}
_azan_cache_attempt = 0.0
_azan_sent_date = ""
_azan_sent_today: set[str] = set()


async def _azan_today_timings() -> dict:
    global _azan_cache, _azan_cache_attempt
    tz = timezone(timedelta(hours=3, minutes=30))
    today = datetime.now(tz).strftime("%d-%m-%Y")
    now_mono = time.monotonic()
    if _azan_cache.get("date") == today and _azan_cache.get("timings"):
        return _azan_cache
    if now_mono - _azan_cache_attempt < 600:
        return _azan_cache  # تلاش مجدد بعد از ۱۰ دقیقه
    _azan_cache_attempt = now_mono
    city = str(runtime_settings.get("daily_prayer_city") or "تهران")
    data = await prayer_times(city)
    _azan_cache = {"date": today, "timings": data.get("timings") or {}, "city": data.get("city") or city}
    return _azan_cache


async def prayer_azan_worker():
    """اذان‌گوی شخصی: در هر وقت نماز، به مشترکین پیام اذان می‌دهد."""
    global _azan_sent_date, _azan_sent_today
    tz = timezone(timedelta(hours=3, minutes=30))
    while True:
        try:
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")
            if _azan_sent_date != today:
                _azan_sent_date = today
                _azan_sent_today = set()
            cache = await _azan_today_timings()
            timings = cache.get("timings") or {}
            if timings:
                now_min = now.hour * 60 + now.minute
                for key, label in AZAN_LABELS.items():
                    t_str = str(timings.get(key) or "")
                    if ":" not in t_str or key in _azan_sent_today:
                        continue
                    try:
                        hh, mm = t_str.split(":")[:2]
                        t_min = int(hh) * 60 + int(mm)
                    except ValueError:
                        continue
                    if 0 <= now_min - t_min < 2:
                        _azan_sent_today.add(key)
                        city = cache.get("city") or "تهران"
                        text = f"🕌 <b>{label}</b> — {html.escape(city)}\n⏰ {t_str}"
                        subs = await users_col.find(
                            {"prayer_subscribed": True, "is_banned": {"$ne": True}}
                        ).to_list(length=1000)
                        sent = 0
                        for u in subs:
                            try:
                                await bot.send_message(
                                    int(u["_id"]), text, parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                        [InlineKeyboardButton(text="🔕 لغو اذان‌گوی", callback_data="azan_off")],
                                    ]),
                                )
                                sent += 1
                                await asyncio.sleep(0.08)
                            except (TelegramForbiddenError, TelegramBadRequest):
                                continue
                        log.info("azan %s sent to %d users", key, sent)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("azan worker error: %s", exc)
        await asyncio.sleep(30)


@dp.callback_query(F.data == "azan_off")
async def azan_off_callback(callback: types.CallbackQuery):
    await users_col.update_one({"_id": callback.from_user.id}, {"$set": {"prayer_subscribed": False}}, upsert=True)
    try:
        await callback.message.edit_text("🔕 اذان‌گوی شخصی لغو شد. اگه خواستی با /praysub دوباره فعالش کن.")
    except TelegramBadRequest:
        pass
    await callback.answer()


async def build_weekly_finance_report() -> str:
    """گزارش مالی ۷ روز اخیر: فروش، کیف پول، سکه، امتیاز و کاربران."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    sales_orders = 0
    sales_toman = 0
    wallet_in = 0
    wallet_out = 0
    coins_minted = 0
    coins_burned = 0
    points_given = 0
    new_users = 0
    active_users = 0
    try:
        orders = await service_orders_col.find(
            {"created_at": {"$gte": since}, "status": {"$in": ["paid", "awaiting_delivery", "completed"]}},
            {"final_price": 1, "payment_method": 1},
        ).to_list(length=10000)
        sales_orders = len(orders)
        sales_toman = sum(int(o.get("final_price") or 0) for o in orders)
        payment_breakdown: dict[str, int] = {}
        for o in orders:
            pm = o.get("payment_method") or "unknown"
            payment_breakdown[pm] = payment_breakdown.get(pm, 0) + int(o.get("final_price") or 0)
    except Exception as exc:
        log.warning("weekly report: orders %s", exc)
        payment_breakdown = {}
    try:
        rows = await wallet_transactions_col.find(
            {"created_at": {"$gte": since}, "type": {"$ne": "service_refund"}}, {"amount_toman": 1}
        ).to_list(length=100000)
        for r in rows:
            amt = int(r.get("amount_toman") or 0)
            if amt > 0:
                wallet_in += amt
            else:
                wallet_out += -amt
    except Exception as exc:
        log.warning("weekly report: wallet %s", exc)
    try:
        rows = await coin_transactions_col.find(
            {"created_at": {"$gte": since}, "status": "completed"}, {"amount": 1, "direction": 1}
        ).to_list(length=100000)
        for r in rows:
            amt = int(r.get("amount") or 0)
            if r.get("direction") == "burn":
                coins_burned += -amt
            else:
                coins_minted += amt
    except Exception as exc:
        log.warning("weekly report: coins %s", exc)
    try:
        agg = await score_events_col.aggregate([
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {"_id": None, "total": {"$sum": "$points"}}},
        ]).to_list(length=1)
        points_given = int(agg[0]["total"]) if agg else 0
    except Exception as exc:
        log.warning("weekly report: scores %s", exc)
    try:
        new_users = await users_col.count_documents({"created_at": {"$gte": since}})
        active_users = await users_col.count_documents({"last_activity": {"$gte": since}})
    except Exception as exc:
        log.warning("weekly report: users %s", exc)
    lines = [
        "📊 <b>گزارش مالی هفتگی آجُرپاره</b>",
        "",
        f"🛒 فروش سرویس‌ها: <b>{sales_orders:,} سفارش</b> — <b>{sales_toman:,} تومان</b>",
    ]
    if payment_breakdown:
        method_labels = {"wallet": "کیف پول", "card": "کارت‌به‌کارت", "stars": "ستاره", "unknown": "سایر"}
        parts = []
        for pm, total in sorted(payment_breakdown.items(), key=lambda kv: -kv[1]):
            parts.append(f"{method_labels.get(pm, pm)}: {total:,}")
        lines.append("🧾 روش پرداخت: " + " · ".join(parts))
    lines.extend([
        f"📥 ورودی کیف پول: {wallet_in:,} تومان",
        f"📤 خروجی کیف پول: {wallet_out:,} تومان",
        f"🪙 سکه ضرب‌شده: {coins_minted:,}",
        f"🔥 سکه سوزانده‌شده: {coins_burned:,}",
        f"⭐ امتیاز داده‌شده: {points_given:,}",
        "",
        f"👥 کاربران جدید: {new_users:,} نفر",
        f"🗓 کاربران فعال (۷ روز): {active_users:,} نفر",
        "",
        "📅 آمار ۷ روز اخیر",
    ])
    return "\n".join(lines)


async def weekly_finance_worker():
    """هر جمعه ساعت ۲۱ به وقت تهران، گزارش مالی هفتگی به کانال ارسال می‌شود."""
    while True:
        try:
            if runtime_settings.get("weekly_finance_channel") and CHANNEL_ID:
                now_tehran = datetime.now(timezone(timedelta(hours=3, minutes=30)))
                iso = now_tehran.isocalendar()
                week_key = f"{iso[0]}-{iso[1]}"
                last_week = runtime_settings.get("weekly_finance_last_week")
                if now_tehran.weekday() == 4 and now_tehran.hour >= 21 and last_week != week_key:
                    report = await build_weekly_finance_report()
                    if report:
                        await bot.send_message(CHANNEL_ID, report, parse_mode="HTML")
                        runtime_settings["weekly_finance_last_week"] = week_key
                        await settings_col.update_one(
                            {"_id": "runtime"},
                            {"$set": {"weekly_finance_last_week": week_key}},
                            upsert=True,
                        )
                        log.info("weekly finance report posted to channel")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("weekly finance worker error: %s", exc)
        await asyncio.sleep(60)


@dp.callback_query(F.data == "toggle_weekly_finance")
async def toggle_weekly_finance_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    current = bool(runtime_settings.get("weekly_finance_channel"))
    runtime_settings["weekly_finance_channel"] = not current
    await settings_col.update_one({"_id": "runtime"}, {"$set": {"weekly_finance_channel": not current}}, upsert=True)
    await callback.answer("فعال شد ✅" if not current else "غیرفعال شد ⏸")
    await callback.message.answer(
        f"📊 آمار مالی هفتگی در کانال: {'✅ فعال' if not current else '⏸ غیرفعال'}\n"
        "هر جمعه ساعت ۲۱ به وقت تهران، گزارش مالی هفتگی (فروش، کیف پول، سکه، امتیاز، کاربران) به کانال ارسال می‌شود.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")],
        ]),
    )


@dp.callback_query(F.data == "weekly_finance_send_now")
async def weekly_finance_send_now_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    await callback.answer("در حال ساخت گزارش...")
    report = await build_weekly_finance_report()
    if CHANNEL_ID:
        await bot.send_message(CHANNEL_ID, report, parse_mode="HTML")
        await callback.message.answer("✅ گزارش مالی هفتگی به کانال ارسال شد.")
    else:
        await callback.message.answer("❌ کانال تنظیم نشده است (CHANNEL_ID).")


@dp.callback_query(F.data == "daily_fal_again")
async def daily_fal_again_callback(callback: types.CallbackQuery):
    await fal_command(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "daily_fal_off")
async def daily_fal_off_callback(callback: types.CallbackQuery):
    await users_col.update_one({"_id": callback.from_user.id}, {"$set": {"fal_subscribed": False}}, upsert=True)
    await callback.message.edit_text("🔕 اشتراک فال روزانه لغو شد. اگه خواستی با /falsub دوباره فعالش کن.")
    await callback.answer()


@dp.callback_query(F.data.in_({"toggle_maintenance", "toggle_force_join"}))
async def admin_toggle_setting(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    key = "maintenance" if callback.data == "toggle_maintenance" else "force_join"
    runtime_settings[key] = not runtime_settings.get(key, False)
    await settings_col.update_one({"_id": "runtime"}, {"$set": {key: runtime_settings[key]}}, upsert=True)
    if key == "maintenance" and not runtime_settings[key]:
        asyncio.create_task(notify_maintenance_waiters(), name="maintenance-notify-now")
    await callback.message.answer(
        "⚙️ تنظیمات بروزرسانی شد."
        + (" اعلان آنلاین‌شدن برای کاربران منتظر ارسال می‌شود." if key == "maintenance" and not runtime_settings[key] else ""),
        reply_markup=admin_menu(),
    )
    await callback.answer("روشن شد" if runtime_settings[key] else "خاموش شد", show_alert=True)


@dp.callback_query(F.data == "admin_finance")
async def admin_finance_callback(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "finance"): return await callback.answer("⛔ دسترسی مالی ندارید.", show_alert=True)
    aggregate = await users_col.aggregate([{"$group": {"_id": None, "wallets": {"$sum": "$wallet_toman"}, "points": {"$sum": "$xp"}, "frozen": {"$sum": {"$cond": ["$wallet_frozen", 1, 0]}}}}]).to_list(length=1)
    totals = aggregate[0] if aggregate else {}
    pending = await withdrawals_col.aggregate([{"$match": {"status": "pending"}}, {"$group": {"_id": None, "count": {"$sum": 1}, "amount": {"$sum": "$amount_toman"}}}]).to_list(length=1); pend = pending[0] if pending else {}
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    suspicious = await referral_events_col.aggregate([{"$match": {"created_at": {"$gte": since}}}, {"$group": {"_id": "$referrer_id", "count": {"$sum": 1}}}, {"$match": {"count": {"$gte": 5}}}, {"$sort": {"count": -1}}, {"$limit": 10}]).to_list(length=10)
    suspect_text = "، ".join(f"{item['_id']} ({item['count']})" for item in suspicious) or "موردی نیست"
    await callback.message.answer(
        "📊 <b>گزارش مالی و ضدتقلب</b>\n\n"
        f"موجودی کل کیف پول‌ها: <b>{int(totals.get('wallets', 0)):,} تومان</b>\n"
        f"امتیاز کل کاربران: <b>{int(totals.get('points', 0)):,}</b>\nکیف پول فریز: <b>{int(totals.get('frozen', 0))}</b>\n"
        f"برداشت در انتظار: <b>{int(pend.get('count', 0))}</b> به مبلغ <b>{int(pend.get('amount', 0)):,}</b> تومان\n\n"
        f"رفرال مشکوک ۲۴ ساعت اخیر: <code>{html.escape(suspect_text)}</code>",
        parse_mode="HTML",
    ); await callback.answer()


def validate_economy_setting_value(key: str, value: int) -> str | None:
    if key == "referral_ai_text_bonus":
        return None if 0 <= value <= 5 else "سهمیه هر رفرال باید بین ۰ تا ۵ پیام باشد."
    if key == "referral_ai_bonus_cap":
        return None if 0 <= value <= 50 else "سقف هدیه رفرال باید بین ۰ تا ۵۰ پیام باشد."
    if value <= 0 or value > 1_000_000_000:
        return "عدد باید بیشتر از صفر و در محدوده منطقی باشد."
    return None


@dp.callback_query(F.data == "economy_settings")
async def economy_settings_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💱 نرخ هر امتیاز", callback_data="econset:point_toman_rate")],
        [InlineKeyboardButton(text="₮ نرخ هر تتر", callback_data="econset:usdt_toman_rate")],
        [InlineKeyboardButton(text="📉 حداقل برداشت", callback_data="econset:min_withdraw_toman")],
        [InlineKeyboardButton(text="📅 سقف برداشت روزانه", callback_data="econset:daily_withdraw_limit")],
        [InlineKeyboardButton(text="✌️ حد تأیید دومرحله‌ای", callback_data="econset:large_withdraw_threshold")],
        [InlineKeyboardButton(text="🤖 سهمیه AI هر رفرال", callback_data="econset:referral_ai_text_bonus")],
        [InlineKeyboardButton(text="🧯 سقف سهمیه AI رفرال", callback_data="econset:referral_ai_bonus_cap")],
        [InlineKeyboardButton(text="⭐ تنظیمات پرداخت ستاره", callback_data="admin_stars_settings")],
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await callback.message.answer(
        "💰 <b>تنظیمات اقتصاد</b>\n\n"
        f"پاداش هر رفرال: <b>{economy_settings['referral_points']} امتیاز</b>\n"
        f"سهمیه AI هر رفرال: <b>+{int(economy_settings['referral_ai_text_bonus'])} پیام روزانه</b>\n"
        f"سقف هدیه رفرال AI: <b>+{int(economy_settings['referral_ai_bonus_cap'])} پیام</b>\n"
        f"هر امتیاز: <b>{int(economy_settings['point_toman_rate']):,} تومان</b>\n"
        f"حداقل تبدیل: <b>{int(economy_settings['min_convert_points']):,} امتیاز</b>\n"
        f"حداقل برداشت: <b>{int(economy_settings['min_withdraw_toman']):,} تومان</b>\n"
        f"سقف روزانه: <b>{int(economy_settings['daily_withdraw_limit']):,} تومان</b>\n"
        f"تأیید دومرحله‌ای از: <b>{int(economy_settings['large_withdraw_threshold']):,} تومان</b>\n"
        f"نرخ تتر: <b>{int(economy_settings['usdt_toman_rate']):,} تومان</b> · TRC20",
        reply_markup=keyboard, parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("econset:"))
async def economy_setting_start(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    key = callback.data.split(":", 1)[1]
    if key not in {"point_toman_rate", "usdt_toman_rate", "min_withdraw_toman", "daily_withdraw_limit", "large_withdraw_threshold", "referral_ai_text_bonus", "referral_ai_bonus_cap", "stars_rate_toman"}:
        return await callback.answer("تنظیم نامعتبر است.", show_alert=True)
    economy_setting_sessions[callback.from_user.id] = key
    labels = {
        "point_toman_rate": "ارزش هر امتیاز به تومان",
        "usdt_toman_rate": "قیمت هر USDT به تومان",
        "min_withdraw_toman": "حداقل برداشت تومان",
        "daily_withdraw_limit": "سقف برداشت روزانه",
        "large_withdraw_threshold": "حد تأیید دومرحله‌ای",
        "referral_ai_text_bonus": "پیام روزانه AI برای هر رفرال واقعی (۰ تا ۵)",
        "referral_ai_bonus_cap": "سقف کل هدیه AI رفرال (۰ تا ۵۰)",
        "stars_rate_toman": "ارزش هر ستاره به تومان (مثلاً 10000)",
    }
    await callback.message.answer(f"عدد جدید برای «{labels[key]}» را بفرست. مثال: <code>100000</code>\nبرای انصراف /cancel", parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_required_channels")
async def admin_required_channels_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    gate_status = "فعال" if engagement_gate_cache.get("enabled") else "خاموش"
    await callback.message.answer(
        "📣 <b>مدیریت عضویت اجباری</b>\n\n"
        f"کانال‌های فعال: <b>{len(required_channels_cache)}</b>\n"
        f"مرحله مشاهده/تعامل: <b>{gate_status}</b>\n\n"
        "ربات باید در تمام کانال‌های ثبت‌شده ادمین باشد تا بتواند عضویت کاربران را بررسی کند.",
        reply_markup=required_channels_admin_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "reqch_noop")
async def required_channel_noop(callback: types.CallbackQuery):
    await callback.answer("هنوز کانالی اضافه نشده.")


@dp.callback_query(F.data == "reqch_add")
async def required_channel_add_start(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    channel_add_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "➕ <b>افزودن کانال اجباری</b>\n\n"
        "برای کانال عمومی:\n<code>@channel_username | عنوان دلخواه</code>\n\n"
        "برای کانال خصوصی:\n<code>-1001234567890 | https://t.me/+InviteLink | عنوان دلخواه</code>\n\n"
        "⚠️ قبل از ارسال، ربات را در آن کانال ادمین کن. برای انصراف /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("reqch_info:"))
async def required_channel_info(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    chat_id = int(callback.data.split(":", 1)[1])
    channel = next((item for item in required_channels_cache if item["_id"] == chat_id), None)
    if not channel:
        return await callback.answer("کانال پیدا نشد.", show_alert=True)
    await callback.answer(f"{channel.get('title')}\n{channel.get('join_url')}", show_alert=True)


@dp.callback_query(F.data.startswith("reqch_delete:"))
async def required_channel_delete(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    chat_id = int(callback.data.split(":", 1)[1])
    result = await required_channels_col.delete_one({"_id": chat_id})
    await refresh_required_channels()
    await callback.message.answer(
        "🗑 کانال حذف شد." if result.deleted_count else "کانال قبلاً حذف شده بود.",
        reply_markup=required_channels_admin_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "engagement_config")
async def engagement_config_start(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    engagement_post_sessions.add(callback.from_user.id)
    await callback.message.answer(
        "👀 <b>تنظیم مرحله مشاهده پست‌ها</b>\n\n"
        "لینک کانال یا یک پست، متن مأموریت و زمان انتظار را بفرست:\n"
        "<code>https://t.me/channel | ۱۰ پست آخر را ببین و روی یکی واکنش بزن | 15</code>\n\n"
        "نکته: تلگرام بازدید واقعی پست را به ربات گزارش نمی‌دهد؛ این مرحله با زمان انتظار و تأیید کاربر اجرا می‌شود. برای انصراف /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "engagement_remove")
async def engagement_remove_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    engagement_gate_cache.update({"enabled": False, "version": None, "url": None})
    await settings_col.update_one(
        {"_id": "runtime"},
        {"$set": {"engagement_gate": dict(engagement_gate_cache)}},
        upsert=True,
    )
    await callback.message.answer("🗑 مرحله تعامل حذف و غیرفعال شد.", reply_markup=required_channels_admin_menu())
    await callback.answer()


@dp.callback_query(F.data == "broadcast_history")
async def broadcast_history_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    items = await broadcasts_col.find().sort("created_at", -1).limit(10).to_list(length=10)
    lines = ["📬 <b>آخرین ارسال‌های همگانی</b>", ""]
    labels = {"all": "همه", "active": "فعال‌ها", "inactive": "غیرفعال‌ها"}
    for item in items:
        lines.append(
            f"• {labels.get(item.get('target'), item.get('target'))}: ✅ {item.get('sent', 0):,} · ❌ {item.get('failed', 0):,}"
        )
    if not items:
        lines.append("هنوز ارسالی ثبت نشده است.")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_tickets")
async def admin_tickets_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    tickets = await tickets_col.find({"status": "open"}).sort("created_at", 1).limit(15).to_list(length=15)
    if not tickets:
        await callback.message.answer("🎫 هیچ تیکت در حال بررسی وجود ندارد.")
        return await callback.answer()
    rows = []
    for ticket in tickets:
        preview = str(ticket.get("text", ""))[:30]
        rows.append([InlineKeyboardButton(text=f"#{ticket['ticket_id']} · {preview}", callback_data=f"ticket_view_{ticket['ticket_id']}")])
    await callback.message.answer("🎫 تیکت‌های باز:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("ticket_view_"))
async def admin_ticket_view(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    ticket_id = callback.data.rsplit("_", 1)[1]
    ticket = await tickets_col.find_one({"ticket_id": ticket_id})
    if not ticket:
        return await callback.answer("تیکت پیدا نشد.", show_alert=True)
    text = (
        f"🎫 <b>تیکت #{ticket_id}</b>\n"
        f"وضعیت: <b>{ticket.get('status', 'open')}</b> · اولویت: <b>{ticket.get('priority', 'normal')}</b>\n"
        f"مسئول: <code>{ticket.get('assigned_to') or 'تعیین نشده'}</code>\n"
        f"👤 {html.escape(ticket.get('name', ''))} · <code>{ticket['user_id']}</code>\n\n"
        f"{html.escape(ticket.get('text', ''))}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ پاسخ", callback_data=f"ticket_reply_{ticket_id}"), InlineKeyboardButton(text="👤 برداشتن تیکت", callback_data=f"ticket_assign_{ticket_id}")],
        [InlineKeyboardButton(text="🟡 در حال بررسی", callback_data=f"ticket_progress_{ticket_id}"), InlineKeyboardButton(text="🔴 فوری", callback_data=f"ticket_priority_{ticket_id}")],
        [InlineKeyboardButton(text="✅ بستن تیکت", callback_data=f"ticket_close_{ticket_id}")],
        [InlineKeyboardButton(text="✉️ گفتگو با کاربر", url=f"tg://user?id={ticket['user_id']}")],
    ])
    await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("ticket_reply_") | F.data.startswith("ticket_assign_") | F.data.startswith("ticket_progress_") | F.data.startswith("ticket_priority_"))
async def ticket_workflow_action(callback: types.CallbackQuery):
    if not has_permission(callback.from_user.id, "support"): return await callback.answer("⛔ دسترسی پشتیبانی ندارید.", show_alert=True)
    action, ticket_id = callback.data.split("_", 2)[1:]
    ticket = await tickets_col.find_one({"ticket_id": ticket_id})
    if not ticket: return await callback.answer("تیکت پیدا نشد.", show_alert=True)
    if action == "reply":
        ticket_reply_sessions[callback.from_user.id] = ticket_id; await callback.message.answer(f"پاسخ تیکت #{ticket_id} را بفرست. /cancel"); return await callback.answer()
    update = {"assigned_to": callback.from_user.id} if action == "assign" else {"status": "in_progress", "assigned_to": callback.from_user.id} if action == "progress" else {"priority": "urgent"}
    await tickets_col.update_one({"_id": ticket["_id"]}, {"$set": update}); await audit_admin_action(callback.from_user.id, f"ticket_{action}", target=ticket_id); await callback.answer("تیکت بروزرسانی شد.", show_alert=True)


@dp.callback_query(F.data.startswith("ticket_close_"))
async def admin_ticket_close(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    ticket_id = callback.data.rsplit("_", 1)[1]
    ticket = await tickets_col.find_one_and_update(
        {"ticket_id": ticket_id, "status": "open"},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc), "closed_by": callback.from_user.id}},
    )
    if ticket:
        try:
            await bot.send_message(ticket["user_id"], f"✅ تیکت #{ticket_id} توسط پشتیبانی بررسی و بسته شد.")
        except Exception:
            pass
    await callback.answer("تیکت بسته شد.", show_alert=True)


@dp.callback_query(F.data == "user_activities")
async def user_activities_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    await callback.message.answer("📋 برای مشاهده فعالیت‌ها از دستور `/activity آیدی_کاربر` استفاده کنید.\nمثال: `/activity 123456789`")
    await callback.answer()

@dp.message(Command("activity"))
async def activity_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ فقط ادمین!")
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("❌ فرمت: `/activity 123456789`")
    try:
        target_user_id = int(parts[1])
    except ValueError:
        return await message.answer("❌ آیدی نامعتبر است.")
    target_user = await users_col.find_one({"_id": target_user_id})
    if not target_user:
        return await message.answer("❌ کاربری با این آیدی پیدا نشد.")
    activities = await activities_col.find({"user_id": target_user_id}).sort("timestamp", -1).limit(20).to_list(length=20)
    if not activities:
        return await message.answer(f"📋 کاربر {target_user_id} هیچ فعالیتی نداشته است.")
    result = f"📋 **فعالیت‌های کاربر {target_user_id}**\n\n"
    for act in activities:
        result += f"🕐 {act['timestamp']}\n➡️ {act['action']} - {act.get('details', '')}\n\n"
    await message.answer(result[:4000])

@dp.callback_query(F.data == "upload_file")
async def upload_file_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    await groups_col.update_many({"admin_id": callback.from_user.id, "is_active": True}, {"$set": {"is_active": False}})
    group_uuid = str(uuid.uuid4())[:8]
    await groups_col.insert_one({
        "group_uuid": group_uuid,
        "admin_id": callback.from_user.id,
        "created_at": datetime.now(timezone.utc),
        "date_str": today_str(),
        "is_active": True,
        "file_count": 0,
    })
    await callback.message.answer(f"📤 **گروه جدید ساخته شد!**\nشناسه گروه: `{group_uuid}`\n\nفایل‌ها را ارسال کنید.", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "publish_group")
async def publish_group_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    group = await groups_col.find_one({"admin_id": callback.from_user.id, "is_active": True})
    if not group:
        return await callback.answer("❌ شما هیچ گروه فعالی ندارید.", show_alert=True)
    group_uuid = group["group_uuid"]
    file_count = group.get("file_count", 0)
    if file_count == 0:
        return await callback.answer("❌ این گروه هیچ فایلی ندارد.", show_alert=True)
    await groups_col.update_one({"group_uuid": group_uuid}, {"$set": {"is_active": False}})
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=group_{group_uuid}"
    text = f"✅ **گروه منتشر شد!**\n\n🔗 لینک: <code>{link}</code>\n📂 تعداد فایل: {file_count}"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.message(F.sticker)
async def handle_promo_sticker(message: types.Message):
    user_id = message.from_user.id
    config = promo_sticker_sessions.get(user_id)
    if not config or not is_admin(user_id):
        if is_admin(user_id):
            if user_id in repost_edit_sessions:
                return await replace_repost_item(message, {"type": "sticker", "file_id": message.sticker.file_id})
            if user_id in scheduled_add_sessions:
                return await append_scheduled_payload(message, {"type": "sticker", "file_id": message.sticker.file_id})
            if user_id in scheduled_edit_sessions:
                return await replace_scheduled_payload(message, {"type": "sticker", "file_id": message.sticker.file_id})
            if user_id in instant_repost_sessions:
                return await publish_instant_repost(message, payload={"type": "sticker", "file_id": message.sticker.file_id})
            if user_id in repost_sessions:
                return await stage_repost(message, payload={"type": "sticker", "file_id": message.sticker.file_id})
        return
    if not config["rewards"].get("sticker"):
        return await message.answer("این کد منتظر گیف است؛ یک فایل GIF/Animation بفرست یا /cancel بزن.")
    promo_sticker_sessions.pop(message.from_user.id, None)
    item = await save_promo_code(config, message.sticker.file_id)
    await message.answer(
        f"✅ کد استیکری <code>{config['code']}</code> ساخته شد.\n🎁 {html.escape(promo_reward_summary(item))}",
        parse_mode="HTML",
    )


@dp.message(F.chat.type == "private", F.voice | F.audio)
async def handle_private_audio(message: types.Message):
    user_id = message.from_user.id
    if user_id in music_playlist_upload_sessions and is_admin(user_id):
        return await save_playlist_upload(message)
    if is_admin(user_id):
        if user_id in repost_edit_sessions:
            return await replace_repost_item(message)
        if user_id in scheduled_add_sessions:
            return await append_scheduled_payload(message)
        if user_id in scheduled_edit_sessions:
            return await replace_scheduled_payload(message)
        if user_id in instant_repost_sessions:
            return await publish_instant_repost(message)
        if user_id in repost_sessions:
            return await stage_repost(message)
    if user_id in music_recognize_sessions:
        return await handle_music_recognize_request(message)
    ai_mode = ai_sessions.get(message.from_user.id, {}).get("mode")
    if ai_mode == "voice":
        await handle_ai_audio_request(message)
        return
    await message.answer(
        "🎙 برای تبدیل صدا به متن، اول از منوی «🤖 هوش مصنوعی» گزینه «🎙 ویس به متن» رو انتخاب کن.",
        reply_markup=ai_reply_menu(),
    )


async def handle_music_recognize_request(message: types.Message) -> None:
    user_id = message.from_user.id
    media = message.voice or message.audio or message.video or message.video_note
    if not media:
        return await message.answer("فایل صوتی یا ویدئو ارسال کن. /cancel", reply_markup=music_reply_menu())
    try:
        file = await bot.get_file(media.file_id)
        if not file.file_path:
            return await message.answer("❌ دریافت فایل ناموفق بود؛ دوباره تلاش کن.", reply_markup=music_reply_menu())
        progress = await message.answer("🎤 در حال بررسی تکهٔ صدا… (تشخیص مثل Shazam)")
        with tempfile.TemporaryDirectory(prefix="ajor-songrec-") as folder:
            local_path = Path(folder) / "snippet"
            await bot.download_file(file.file_path, destination=local_path)
            if not local_path.is_file() or local_path.stat().st_size <= 0:
                return await progress.edit_text("❌ فایل صوتی معتبر نیست؛ دوباره تلاش کن.")
            rec_session = _music_session()
            try:
                result = await recognize_audio(rec_session, str(local_path))
            finally:
                if rec_session is not http_session:
                    await rec_session.close()
            if not result:
                return await progress.edit_text(
                    "🔍 آهنگی تشخیص داده نشد (یا سرویس تشخیص هنوز فعال نشده).\n"
                    "میتونی اسم آهنگ رو بفرستی تا جستجو کنم. /cancel",
                )
            music_recognize_sessions.discard(user_id)
            await progress.edit_text(
                f"✅ <b>آهنگ تشخیص داده شد</b>\n\n"
                f"🎵 عنوان: <b>{html.escape(result['title'])}</b>\n"
                f"👤 خواننده: {html.escape(result.get('artist') or 'ناشناس')}\n"
                + (f"💿 آلبوم: {html.escape(result['album'])}\n" if result.get("album") else "")
                + "\nهمین حالا جستجو و دانلودش می‌کنم…",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎵 ادامه برای این آهنگ", callback_data="music_pick:0")],
                    [InlineKeyboardButton(text="🎤 تشخیص آهنگ دیگر", callback_data="music_recognize_again")],
                ]),
            )
            music_search_cache[user_id] = [{
                "source": "query",
                "provider": "🎵 تشخیص",
                "id": f"{result['title']} {result.get('artist') or ''}",
                "title": result["title"],
                "artist": result.get("artist") or "",
                "album": result.get("album") or "",
                "duration": 0,
                "artwork": None,
                "preview_url": None,
                "downloadable": False,
                "watch_url": None,
                "permalink": result.get("song_link") or "",
            }]
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        log.warning("music recognize failed: %s", exc)
        try:
            await message.answer("❌ دریافت تکهٔ صدا ناموفق بود؛ دوباره تلاش کن.", reply_markup=music_reply_menu())
        except TelegramBadRequest:
            pass
    except MediaServiceError as exc:
        try:
            await message.answer(f"❌ {exc.message}", reply_markup=music_reply_menu())
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "music_recognize_again")
async def music_recognize_again_callback(callback: types.CallbackQuery):
    music_recognize_sessions.add(callback.from_user.id)
    await callback.message.answer("🎤 یه تکهٔ ۱۰ تا ۳۰ ثانیه‌ای بفرست. /cancel", reply_markup=music_reply_menu())
    await callback.answer()


@dp.message(F.chat.type == "private", F.video | F.video_note)
async def handle_private_video_for_music(message: types.Message):
    if message.from_user.id in music_recognize_sessions:
        return await handle_music_recognize_request(message)
    if message.from_user.id in video_round_sessions:
        return await handle_video_round_request(message)
    # این handler قبلاً ویدئو را مصرف می‌کرد و نمی‌گذاشت مسیر بازنشر/زمان‌بندی
    # به handle_file_upload برسد؛ همهٔ مسیرهای ویدئو را به همان router می‌سپاریم.
    return await handle_file_upload(message)


async def handle_video_round_request(message: types.Message) -> None:
    """تبدیل ویدئو به ویدئو مسیج دایره‌ای با انیمیشن پیشرفت ۰ تا ۱۰۰٪."""
    user_id = message.from_user.id
    video_round_sessions.discard(user_id)
    media = message.video or message.video_note
    if not media:
        return await message.answer("❌ یک ویدئو بفرست. /cancel", reply_markup=media_download_reply_menu())
    if int(media.file_size or 0) > 200 * 1024 * 1024:
        return await message.answer("❌ حجم ویدئو خیلی زیاد است؛ حداکثر ۲۰۰ مگابایت.", reply_markup=media_download_reply_menu())

    progress_message = None
    last_percent = -1

    async def on_progress(percent: int, stage: str) -> None:
        nonlocal progress_message, last_percent
        percent = max(0, min(100, int(percent)))
        if percent == last_percent:
            return
        last_percent = percent
        bar = "▓" * round(percent / 10) + "░" * (10 - round(percent / 10))
        text = (
            f"🔄 <b>در حال تبدیل ویدئو به دایره‌ای…</b>\n"
            f"<code>{bar} {percent}%</code>\n"
            f"{stage}"
        )
        try:
            if progress_message is None:
                progress_message = await message.answer(text, parse_mode="HTML")
            else:
                await progress_message.edit_text(text, parse_mode="HTML")
        except (TelegramBadRequest, TelegramForbiddenError):
            pass

    temp_folder = None
    try:
        suffix = ".mp4"
        if media.file_name and Path(str(media.file_name)).suffix:
            suffix = Path(str(media.file_name)).suffix.lower()[:5]
        # دانلود استریمی مستقیم به دیسک (بدون کپی در RAM) — حیاتی برای فایل‌های بزرگ
        temp_folder = tempfile.TemporaryDirectory(prefix=f"ajor-round-in-{user_id}-")
        input_path = Path(temp_folder.name) / f"input{suffix}"
        if progress_message is None:
            await on_progress(1, "در حال دانلود ویدئو")
        await download_telegram_media_to_path(media.file_id, str(input_path))
        output_path = Path(temp_folder.name) / "round.mp4"
        await convert_video_to_round(str(input_path), str(output_path), progress_callback=on_progress)
        filename = f"ajorpareh-round-{user_id}-{int(time.time())}.mp4"
        # ارسال مستقیم از دیسک (FSInputFile) — بدون کپی در حافظه
        upload = FSInputFile(str(output_path), filename=filename)
        try:
            await message.answer_video_note(upload, length=640, request_timeout=600)
        except TelegramBadRequest:
            # اگر video_note قبول نشد، به‌صورت ویدئو معمولی بفرست
            await message.answer_video(upload, caption="🔵 ویدئو دایره‌ای (با فرمت ویدئو)", request_timeout=600)
        if progress_message:
            try:
                await progress_message.delete()
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
        await message.answer(
            "✅ <b>ویدئو مسیج دایره‌ای آماده شد!</b>\n"
            "🔵 این پیام مثل ویدئو مسیج تلگرام دایره‌ای پخش می‌شه.",
            parse_mode="HTML", reply_markup=media_download_reply_menu(),
        )
        await users_col.update_one(
            {"_id": user_id},
            {"$inc": {"round_videos_created": 1}, "$set": {"last_round_video_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        size_bytes = Path(output_path).stat().st_size if output_path and Path(output_path).exists() else 0
        await log_activity(user_id, "video_round", f"size={size_bytes}")
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.warning("ارسال ویدئو دایره‌ای ناموفق بود: %s", exc)
        if progress_message:
            try: await progress_message.delete()
            except (TelegramBadRequest, TelegramForbiddenError): pass
        await message.answer(
            "❌ ارسال ویدئو دایره‌ای ناموفق بود. ویدئو باید کمتر از ۶۰ ثانیه و حداکثر ۲۰۰ مگابایت باشد.",
            reply_markup=media_download_reply_menu(),
        )
    except Exception as exc:
        log.warning("تبدیل ویدئو دایره‌ای ناموفق بود: %s", exc)
        if progress_message:
            try: await progress_message.delete()
            except (TelegramBadRequest, TelegramForbiddenError): pass
        await message.answer(
            f"❌ {getattr(exc, 'message', 'تبدیل ویدئو ناموفق بود؛ فرمت یا طول ویدئو را بررسی کن')}",
            reply_markup=media_download_reply_menu(),
        )
    finally:
        if temp_folder is not None:
            try:
                temp_folder.cleanup()
            except Exception:
                pass


@dp.message(F.photo)
async def handle_admin_receipt_photo(message: types.Message):
    service_order_id = service_receipt_sessions.get(message.from_user.id)
    if service_order_id:
        order = await service_orders_col.find_one({"_id": service_order_id, "user_id": message.from_user.id, "status": "awaiting_receipt"})
        if not order:
            service_receipt_sessions.pop(message.from_user.id, None)
            return await message.answer("❌ سفارش منتظر رسید پیدا نشد.", reply_markup=service_reply_menu())
        service_receipt_sessions.pop(message.from_user.id, None)
        photo_id = message.photo[-1].file_id
        await service_orders_col.update_one(
            {"_id": service_order_id},
            {"$set": {"status": "payment_review", "receipt_file_id": photo_id, "receipt_sent_at": datetime.now(timezone.utc)}},
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ تأیید پرداخت", callback_data=f"svcapprove:{service_order_id}"),
            InlineKeyboardButton(text="❌ رد رسید", callback_data=f"svcreject:{service_order_id}"),
        ]])
        caption = (
            f"🧾 <b>رسید خرید سرویس</b>\nسفارش: <code>{service_order_id}</code>\n"
            f"کاربر: <code>{message.from_user.id}</code>\nمبلغ: <b>{int(order['final_price']):,} تومان</b>"
        )
        for admin_id in ADMIN_IDS:
            try: await bot.send_photo(admin_id, photo_id, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            except (TelegramForbiddenError, TelegramBadRequest): pass
        return await message.answer("✅ رسید ثبت شد و برای بررسی مدیر ارسال شد.", reply_markup=service_reply_menu())
    if message.from_user.id in prompt_image_sessions and message.from_user.id not in instant_repost_sessions and message.from_user.id not in repost_sessions:
        await handle_prompt_reference_image(message)
        return
    ai_mode = ai_sessions.get(message.from_user.id, {}).get("mode")
    if ai_mode in {"vision", "edit_image"} and message.from_user.id not in instant_repost_sessions:
        await handle_ai_photo_request(message, ai_mode)
        return
    if ai_mode == "image":
        # اگر کاربر در حالت ساخت تصویر، عکس را با کپشن/پرامپت فرستاد،
        # آن را به‌عنوان عکس مرجع اجرا کن تا جنسیت و هویت عوض نشود.
        if (message.caption or "").strip() and message.from_user.id not in instant_repost_sessions:
            prompt_image_sessions[message.from_user.id] = message.caption.strip()
            await handle_prompt_reference_image(message)
            return
        await message.answer("🎨 برای ساخت تصویر، توضیحت رو به‌صورت متن بفرست؛ یا عکس را همراه کپشن پرامپت بفرست.", reply_markup=ai_reply_menu())
        return
    if ai_mode and message.from_user.id not in instant_repost_sessions:
        await message.answer("📝 این ابزار ورودی متنی می‌خواد؛ نوشته‌ات رو به‌صورت پیام بفرست یا «👁 تحلیل تصویر» رو انتخاب کن.", reply_markup=ai_reply_menu())
        return
    if message.from_user.id in gif_sessions:
        gif_sessions.discard(message.from_user.id)
        await send_gif_result(message, message.photo[-1], ".jpg", from_photo=True)
        return
    if message.from_user.id in sticker_sessions:
        sticker_sessions.discard(message.from_user.id)
        await send_sticker_result(message)
        return
    if not is_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    if user_id in repost_edit_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "batch_edit")
        else:
            await replace_repost_item(message)
        return
    if user_id in scheduled_add_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "scheduled_add")
        else:
            await append_scheduled_payload(message)
        return
    if user_id in scheduled_edit_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "scheduled_edit")
        else:
            await replace_scheduled_payload(message)
        return
    if user_id in instant_repost_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "instant")
        else:
            await publish_instant_repost(message)
        return
    if user_id in repost_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "batch")
        else:
            await stage_repost(message)
        return

    # بررسی اینکه آیا ادمین در حال ارسال رسید برای کاربری است یا خیر
    active_session = None
    for session in receipt_sessions:
        if session[0] == message.from_user.id:
            active_session = session
            break
            
    if active_session:
        receipt_sessions.remove(active_session)
        target_user_id = active_session[1]
        photo_id = message.photo[-1].file_id
        caption = message.caption or "رسید واریز وجه برای شما ارسال شد. مبارکتون باشه! 🌸"

        try:
            await bot.send_photo(
                target_user_id, 
                photo_id, 
                caption=f"🎁 **مبلغ درخواست شما واریز شد!**\n\n{caption}"
            )
            await message.answer("✅ رسید با موفقیت به کاربر ارسال شد و فرآیند تسویه به پایان رسید.")
            await log_activity(target_user_id, "withdrawal_completed", "رسید واریز وجه برای کاربر ارسال شد")
        except Exception as e:
            await message.answer(f"❌ خطا در ارسال رسید به کاربر: {e}")
        return

    # آپلود فایل عکس معمولی توسط ادمین در گروه بارگذاری فایل
    if message.from_user.id in broadcast_sessions:
        broadcast_sessions.discard(message.from_user.id)
        await do_broadcast(message.from_user.id, message)
        return
        
    group = await groups_col.find_one({"admin_id": message.from_user.id, "is_active": True})
    if not group:
        return
        
    group_uuid = group["group_uuid"]
    file_id = message.photo[-1].file_id
    file_uuid = str(uuid.uuid4())[:8]
    caption = message.caption if message.caption else DEFAULT_CAPTION
    
    await files_col.insert_one({
        "uuid": file_uuid,
        "group_uuid": group_uuid,
        "file_id": file_id,
        "type": "photo",
        "name": "عکس",
        "caption": caption,
        "uploaded_at": datetime.now(timezone.utc),
    })
    await groups_col.update_one({"group_uuid": group_uuid}, {"$inc": {"file_count": 1}})
    updated = await groups_col.find_one({"group_uuid": group_uuid})
    await message.answer(f"✅ عکس اضافه شد.\nتعداد فایل‌ها: {updated['file_count']}")

@dp.message(F.document | F.video)
async def handle_file_upload(message: types.Message):
    delivery_order_id = service_delivery_sessions.get(message.from_user.id)
    if delivery_order_id and is_admin(message.from_user.id):
        if not message.document:
            return await message.answer("برای تحویل فایل کانفیگ، آن را به‌صورت Document بفرست.")
        service_delivery_sessions.pop(message.from_user.id, None)
        service = await complete_service_delivery(message.from_user.id, delivery_order_id, "document", message.document.file_id)
        return await message.answer("✅ فایل سرویس برای کاربر تحویل شد." if service else "❌ سفارش آماده تحویل نیست.", reply_markup=admin_finance_reply_menu())
    if message.from_user.id in music_playlist_upload_sessions and is_admin(message.from_user.id):
        return await save_playlist_upload(message)
    if message.from_user.id in gif_sessions:
        media = message.video or message.document
        mime_type = (getattr(media, "mime_type", None) or "").lower()
        file_name = (getattr(media, "file_name", None) or "").lower()
        if message.document and not (mime_type.startswith("video/") or "gif" in mime_type or file_name.endswith((".gif", ".mp4", ".webm", ".mov"))):
            return await message.answer("❌ برای ساخت گیف، فایل GIF یا ویدئویی بفرست. /cancel برای لغو")
        if int(getattr(media, "file_size", 0) or 0) > 19 * 1024 * 1024:
            return await message.answer("❌ حجم فایل بیشتر از ۱۹ مگابایته؛ فایل کوچیک‌تری بفرست یا /cancel بزن.")
        gif_sessions.discard(message.from_user.id)
        suffix = Path(file_name).suffix if file_name else (".mp4" if message.video else ".bin")
        await send_gif_result(message, media, suffix)
        return
    if not is_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    if user_id in repost_edit_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "batch_edit")
        else:
            await replace_repost_item(message)
        return
    if user_id in scheduled_add_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "scheduled_add")
        else:
            await append_scheduled_payload(message)
        return
    if user_id in scheduled_edit_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "scheduled_edit")
        else:
            await replace_scheduled_payload(message)
        return
    if user_id in instant_repost_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "instant")
        else:
            await publish_instant_repost(message)
        return
    if user_id in repost_sessions:
        if message.media_group_id:
            await buffer_repost_album(message, "batch")
        else:
            await stage_repost(message)
        return

    if message.from_user.id in config_upload_sessions:
        category = config_upload_sessions[message.from_user.id]
        if message.document:
            file_id = message.document.file_id
        elif message.video:
            file_id = message.video.file_id
        else:
            return
        unique_id=(message.document.file_unique_id if message.document else message.video.file_unique_id);content_hash=hashlib.sha256(f"{category}:{unique_id}".encode()).hexdigest()
        if await configs_col.find_one({"category":category,"content_hash":content_hash,"active":{"$ne":False}}):return await message.answer("⚠️ این فایل تکراریه و قبلاً ذخیره شده.")
        await configs_col.insert_one({
            "category": category, "content_type": "document", "file_id": file_id, "content_hash":content_hash,
            "file_name": re.sub(r"@[A-Za-z0-9_]{5,}", "@Ajor_pareh", message.document.file_name if message.document else "فایل کانفیگ"),
            "uploaded_at": datetime.now(timezone.utc), "expires_at":datetime.now(timezone.utc)+timedelta(days=7),
            "date_str": today_str(), "branded": True, "active":True, "downloads":0,
        })
        await message.answer(f"✅ فایل {CONFIG_LABELS[category]} با کپشن @Ajor_pareh ذخیره شد. مورد بعدی رو بفرست یا /cancel بزن.")
        return

    if message.from_user.id in broadcast_sessions:
        broadcast_sessions.discard(message.from_user.id)
        await do_broadcast(message.from_user.id, message)
        return
        
    group = await groups_col.find_one({"admin_id": message.from_user.id, "is_active": True})
    if not group:
        return await message.answer("❌ ابتدا گروه جدید بسازید.")
        
    group_uuid = group["group_uuid"]
    if message.document:
        file_id = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name or "document"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
        file_name = "ویدئو"
    else:
        return
        
    file_uuid = str(uuid.uuid4())[:8]
    caption = message.caption if message.caption else DEFAULT_CAPTION
    await files_col.insert_one({
        "uuid": file_uuid,
        "group_uuid": group_uuid,
        "file_id": file_id,
        "type": file_type,
        "name": file_name,
        "caption": caption,
        "uploaded_at": datetime.now(timezone.utc),
    })
    await groups_col.update_one({"group_uuid": group_uuid}, {"$inc": {"file_count": 1}})
    updated = await groups_col.find_one({"group_uuid": group_uuid})
    await message.answer(f"✅ فایل `{file_name}` اضافه شد.\nتعداد فایل‌ها: {updated['file_count']}", parse_mode="Markdown")


@dp.message(F.animation)
async def handle_admin_animation(message: types.Message):
    config = promo_sticker_sessions.get(message.from_user.id)
    if config and is_admin(message.from_user.id):
        if not config["rewards"].get("gif"):
            return await message.answer("این کد منتظر استیکر است؛ یک Sticker بفرست یا /cancel بزن.")
        promo_sticker_sessions.pop(message.from_user.id, None)
        item = await save_promo_code(config, message.animation.file_id)
        return await message.answer(
            f"✅ کد گیف <code>{config['code']}</code> ساخته شد.\n🎁 {html.escape(promo_reward_summary(item))}",
            parse_mode="HTML",
        )
    if message.from_user.id in gif_sessions:
        if int(message.animation.file_size or 0) > 19 * 1024 * 1024:
            return await message.answer("❌ حجم GIF بیشتر از ۱۹ مگابایته؛ فایل کوچیک‌تری بفرست یا /cancel بزن.")
        gif_sessions.discard(message.from_user.id)
        suffix = ".gif" if "gif" in (message.animation.mime_type or "").lower() else ".mp4"
        await send_gif_result(message, message.animation, suffix)
        return
    if not is_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    if user_id in repost_edit_sessions:
        await replace_repost_item(message)
        return
    if user_id in scheduled_add_sessions:
        await append_scheduled_payload(message)
        return
    if user_id in scheduled_edit_sessions:
        await replace_scheduled_payload(message)
        return
    if user_id in instant_repost_sessions:
        await publish_instant_repost(message)
        return
    if user_id in repost_sessions:
        await stage_repost(message)


def stored_group_date(group: dict) -> str:
    if group.get("date_str"):
        return str(group["date_str"])
    created = group.get("created_at")
    if isinstance(created, datetime):
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created.astimezone(timezone(timedelta(hours=3, minutes=30))).strftime("%Y-%m-%d")
    return "بدون-تاریخ"


@dp.callback_query(F.data == "manage_groups")
async def manage_groups_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    groups = await groups_col.find({"admin_id": callback.from_user.id}).sort("created_at", -1).limit(500).to_list(length=500)
    if not groups:
        await callback.message.answer("📋 هنوز فایل یا گروهی ایجاد نکرده‌ای.")
        return await callback.answer()
    dates: dict[str, dict] = {}
    for group in groups:
        day = stored_group_date(group)
        bucket = dates.setdefault(day, {"groups": 0, "files": 0})
        bucket["groups"] += 1; bucket["files"] += int(group.get("file_count", 0))
    rows = [[InlineKeyboardButton(
        text=f"📅 {day} · {info['files']} فایل در {info['groups']} گروه",
        callback_data=f"filedate:{day}:0",
    )] for day, info in sorted(dates.items(), reverse=True)[:80]]
    rows.append([InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin_panel")])
    await callback.message.answer("🗂 <b>مدیریت فایل‌ها براساس تاریخ</b>\nیک تاریخ را انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("filedate:"))
async def files_by_date_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        _, day, page_text = callback.data.split(":", 2); page = max(0, int(page_text))
    except ValueError:
        return await callback.answer("درخواست نامعتبر است.", show_alert=True)
    all_groups = await groups_col.find({"admin_id": callback.from_user.id}).sort("created_at", -1).limit(500).to_list(length=500)
    groups = [group for group in all_groups if stored_group_date(group) == day]
    group_ids = [group["group_uuid"] for group in groups]
    files = await files_col.find({"group_uuid": {"$in": group_ids}}).sort("uploaded_at", 1).to_list(length=1000) if group_ids else []
    per_page = 6; max_page = max(0, (len(files) - 1) // per_page); page = min(page, max_page); chunk = files[page * per_page:(page + 1) * per_page]
    lines = [f"📅 <b>فایل‌های {html.escape(day)}</b>", f"تعداد کل: <b>{len(files)}</b> · صفحه {page + 1}/{max_page + 1}", ""]
    for index, item in enumerate(chunk, page * per_page + 1):
        lines.extend([
            f"<b>{index}. {html.escape(str(item.get('name', 'بی‌نام')))}</b>",
            f"شناسه داخلی: <code>{html.escape(str(item.get('uuid', '-')))}</code>",
            f"شناسه گروه: <code>{html.escape(str(item.get('group_uuid', '-')))}</code>",
            f"File ID: <code>{html.escape(str(item.get('file_id', '-')))}</code>", "",
        ])
    if not chunk:
        lines.append("در این تاریخ فایلی ذخیره نشده.")
    rows = []
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="➡️ قبلی", callback_data=f"filedate:{day}:{page-1}"))
    if page < max_page: nav.append(InlineKeyboardButton(text="بعدی ⬅️", callback_data=f"filedate:{day}:{page+1}"))
    if nav: rows.append(nav)
    rows.extend([[InlineKeyboardButton(text=f"📁 گروه {g['group_uuid']} · {g.get('file_count', 0)} فایل", callback_data=f"group_info_{g['group_uuid']}")] for g in groups[:15]])
    rows.append([InlineKeyboardButton(text="🔙 تاریخ‌ها", callback_data="manage_groups")])
    await callback.message.answer("\n".join(lines)[:4000], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("group_info_"))
async def group_info_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    group_uuid = callback.data.split("_", 2)[2]
    group = await groups_col.find_one({"group_uuid": group_uuid})
    if not group:
        return await callback.answer("❌ گروه یافت نشد.", show_alert=True)
    files = await files_col.find({"group_uuid": group_uuid}).sort("uploaded_at", 1).to_list(length=200)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=group_{group_uuid}"
    title = str(group.get("title") or group_uuid)
    views = int(group.get("views", 0) or 0)
    lines = [
        f"📁 <b>گروه: {html.escape(title)}</b>",
        f"شناسه: <code>{html.escape(group_uuid)}</code>",
        f"تاریخ: {stored_group_date(group)} · فایل‌ها: <b>{len(files)}</b> · بازدید: <b>{views:,}</b>",
        f"وضعیت: {'🟢 فعال (در حال دریافت فایل)' if group.get('is_active') else '✅ منتشرشده'}",
        "",
        f"🔗 لینک انتشار:\n<code>{link}</code>",
        "",
    ]
    for index, item in enumerate(files, 1):
        lines.append(f"{index}. {html.escape(str(item.get('name', 'بی‌نام')))} · <code>{html.escape(str(item.get('uuid', '-')))}</code>")
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="📋 کپی لینک", callback_data=f"grouplink:{group_uuid}"),
         InlineKeyboardButton(text="📤 اشتراک‌گذاری", url=f"https://t.me/share/url?url={link}")],
        [InlineKeyboardButton(text="✏️ تغییر نام", callback_data=f"grouprename:{group_uuid}"),
         InlineKeyboardButton(text="🗑 حذف گروه", callback_data=f"groupdel:{group_uuid}")],
        [InlineKeyboardButton(text="🔙 مدیریت فایل‌ها", callback_data="manage_groups")],
    ]
    await callback.message.answer("\n".join(lines)[:4000], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("grouplink:"))
async def group_link_copy_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    group_uuid = callback.data.split(":", 1)[1]
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=group_{group_uuid}"
    await callback.answer(link, show_alert=True)


group_rename_sessions: dict[int, str] = {}


@dp.callback_query(F.data.startswith("grouprename:"))
async def group_rename_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    group_uuid = callback.data.split(":", 1)[1]
    group = await groups_col.find_one({"group_uuid": group_uuid})
    if not group:
        return await callback.answer("❌ گروه یافت نشد.", show_alert=True)
    group_rename_sessions[callback.from_user.id] = group_uuid
    await callback.message.answer(
        "✏️ <b>تغییر نام گروه</b>\n\nنام جدید را بفرست (حداکثر ۶۰ حرف). /cancel",
        parse_mode="HTML", reply_markup=admin_files_reply_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("groupdel:"))
async def group_delete_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    group_uuid = callback.data.split(":", 1)[1]
    group = await groups_col.find_one({"group_uuid": group_uuid})
    if not group:
        return await callback.answer("❌ گروه یافت نشد.", show_alert=True)
    await files_col.delete_many({"group_uuid": group_uuid})
    await groups_col.delete_one({"group_uuid": group_uuid})
    await log_activity(callback.from_user.id, "admin_group_delete", f"group={group_uuid},files={group.get('file_count',0)}")
    await callback.message.answer(f"🗑 گروه <code>{html.escape(group_uuid)}</code> و همه فایل‌هایش حذف شد.", parse_mode="HTML", reply_markup=admin_files_reply_menu())
    await callback.answer("حذف شد ✅")

# ======== پروکسی و کانفیگ اختصاصی (کاربر) ========
@dp.callback_query(F.data == "get_proxy")
async def get_proxy_callback(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
        return
    item = await get_random_config("proxy")
    if not item:
        await callback.message.answer("❌ امروز هنوز پروکسی‌ای آپلود نشده. کمی بعد دوباره امتحان کن.")
        await callback.answer()
        return
    await send_config_item(callback.message, item, "🌐 پروکسی تلگرام شما:")
    await log_activity(callback.from_user.id, "get_proxy", "دریافت پروکسی رندوم")
    await callback.answer()

@dp.callback_query(F.data == "config_menu")
async def config_menu_callback(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
        return
    await callback.message.answer("🔐 نوع کانفیگ اختصاصی مورد نظرت رو انتخاب کن:", reply_markup=config_type_menu())
    await callback.answer()

@dp.callback_query(F.data.in_({"get_config_v2ray", "get_config_npv"}))
async def get_config_callback(callback: types.CallbackQuery):
    if not await is_member(callback.from_user.id):
        await callback.answer("❌ اول مراحل عضویت رو کامل کن!", show_alert=True)
        return
    category = "v2ray" if callback.data == "get_config_v2ray" else "npv"
    item = await get_random_config(category)
    if not item:
        await callback.message.answer(f"❌ امروز هنوز {CONFIG_LABELS[category]}‌ای آپلود نشده. کمی بعد دوباره امتحان کن.")
        await callback.answer()
        return
    await send_config_item(callback.message, item, f"🔐 {CONFIG_LABELS[category]} شما:")
    await log_activity(callback.from_user.id, f"get_config_{category}", "دریافت کانفیگ رندوم")
    await callback.answer()

# ======== مدیریت پروکسی و کانفیگ (ادمین) ========
@dp.callback_query(F.data == "admin_config_panel")
async def admin_config_panel_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    await callback.message.answer("🌐 مدیریت پروکسی و کانفیگ اختصاصی:", reply_markup=admin_config_menu())
    await callback.answer()

@dp.callback_query(F.data == "admin_config_manage")
async def admin_config_manage_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    proxy_count, v2ray_count, npv_count = await asyncio.gather(
        configs_col.count_documents({"category": "proxy"}),
        configs_col.count_documents({"category": "v2ray"}),
        configs_col.count_documents({"category": "npv"}),
    )
    await callback.message.answer(
        "📋 <b>لیست و حذف پروکسی/کانفیگ</b>\n\nیک دسته را انتخاب کن:",
        reply_markup=config_manage_categories_menu({"proxy": proxy_count, "v2ray": v2ray_count, "npv": npv_count}),
        parse_mode="HTML",
    )
    await callback.answer()


def config_item_label(item: dict) -> str:
    if item.get("content_type") == "text":
        preview = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
        preview = preview[:28] + ("…" if len(preview) > 28 else "")
    else:
        preview = str(item.get("file_name") or "فایل کانفیگ")[:28]
    date_label = item.get("date_str") or "بدون تاریخ";status="🟢" if item.get("active",True) else "⚪"
    return f"{status} {date_label} · {preview or 'بدون عنوان'} · ↓{item.get('downloads',0)}"


async def render_config_list(message: types.Message, category: str, page: int = 0):
    if category not in CONFIG_LABELS:
        return await message.answer("دسته نامعتبر است.")
    per_page = 7
    total = await configs_col.count_documents({"category": category})
    max_page = max(0, (total - 1) // per_page)
    page = max(0, min(page, max_page))
    items = await configs_col.find({"category": category}).sort("uploaded_at", -1).skip(page * per_page).limit(per_page).to_list(length=per_page)
    rows = []
    for item in items:
        object_id = str(item["_id"])
        rows.append([
            InlineKeyboardButton(text=config_item_label(item), callback_data=f"cfginfo:{object_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"cfgdel:{object_id}"),
        ])
    if not items:
        rows.append([InlineKeyboardButton(text="— موردی ثبت نشده —", callback_data="cfgnoop")])
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="➡️ قبلی", callback_data=f"cfglist:{category}:{page - 1}"))
    if page < max_page:
        navigation.append(InlineKeyboardButton(text="بعدی ⬅️", callback_data=f"cfglist:{category}:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.extend([
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"cfglist:{category}:{page}")],
        [InlineKeyboardButton(text="🔙 دسته‌ها", callback_data="admin_config_manage")],
    ])
    await message.answer(
        f"📦 <b>{CONFIG_LABELS[category]}</b>\nتعداد کل: <b>{total}</b> · صفحه {page + 1} از {max_page + 1}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("cfglist:"))
async def config_list_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        _, category, page_text = callback.data.split(":", 2)
        page = int(page_text)
    except (ValueError, TypeError):
        return await callback.answer("درخواست نامعتبر است.", show_alert=True)
    await render_config_list(callback.message, category, page)
    await callback.answer()


@dp.callback_query(F.data == "cfgnoop")
async def config_noop_callback(callback: types.CallbackQuery):
    await callback.answer("هنوز چیزی در این دسته ثبت نشده.")


@dp.callback_query(F.data.startswith("cfginfo:"))
async def config_info_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        object_id = ObjectId(callback.data.split(":", 1)[1])
    except InvalidId:
        return await callback.answer("شناسه نامعتبر است.", show_alert=True)
    item = await configs_col.find_one({"_id": object_id})
    if not item:
        return await callback.answer("این مورد حذف شده است.", show_alert=True)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏯ فعال/غیرفعال", callback_data=f"cfgtoggle:{object_id}"), InlineKeyboardButton(text="🗑 حذف این مورد", callback_data=f"cfgdel:{object_id}")],
        [InlineKeyboardButton(text="🔙 لیست", callback_data=f"cfglist:{item['category']}:0")],
    ])
    title = f"{CONFIG_LABELS.get(item.get('category'), 'کانفیگ')} · {item.get('date_str', 'بدون تاریخ')}"
    if item.get("content_type") == "document":
        try:
            await callback.message.answer_document(item["file_id"], caption=title, reply_markup=keyboard)
        except TelegramBadRequest:
            await callback.message.answer(f"📄 {html.escape(title)}\nفایل تلگرام دیگر در دسترس نیست.", reply_markup=keyboard, parse_mode="HTML")
    else:
        content = html.escape(str(item.get("text", ""))[:3500])
        await callback.message.answer(f"📄 <b>{html.escape(title)}</b>\n\n<code>{content}</code>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "config_purge_expired")
async def config_purge_expired(callback:types.CallbackQuery):
    if not has_permission(callback.from_user.id,"configs"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    result=await configs_col.delete_many({"expires_at":{"$lte":datetime.now(timezone.utc)}});await audit_admin_action(callback.from_user.id,"config_purge",str(result.deleted_count));await callback.answer(f"{result.deleted_count} مورد منقضی حذف شد.",show_alert=True)


@dp.callback_query(F.data.startswith("cfgtoggle:"))
async def config_toggle_callback(callback:types.CallbackQuery):
    if not has_permission(callback.from_user.id,"configs"):return await callback.answer("⛔ دسترسی ندارید.",show_alert=True)
    try:oid=ObjectId(callback.data.split(":",1)[1])
    except InvalidId:return await callback.answer("نامعتبر.",show_alert=True)
    item=await configs_col.find_one({"_id":oid});active=not item.get("active",True);await configs_col.update_one({"_id":oid},{"$set":{"active":active}});await callback.answer("فعال شد." if active else "غیرفعال شد.",show_alert=True)


@dp.callback_query(F.data.startswith("cfgdel:"))
async def config_delete_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    try:
        object_id = ObjectId(callback.data.split(":", 1)[1])
    except InvalidId:
        return await callback.answer("شناسه نامعتبر است.", show_alert=True)
    item = await configs_col.find_one_and_delete({"_id": object_id})
    if not item:
        return await callback.answer("این مورد قبلاً حذف شده.", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await log_activity(callback.from_user.id, "config_deleted", f"category={item.get('category')},id={object_id}")
    await callback.message.answer(
        f"🗑 {CONFIG_LABELS.get(item.get('category'), 'مورد')} حذف شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data=f"cfglist:{item.get('category', 'proxy')}:0")]
        ]),
    )
    await callback.answer("حذف شد ✅")


@dp.callback_query(F.data.in_({"admin_upload_proxy", "admin_upload_v2ray", "admin_upload_npv"}))
async def admin_upload_config_start(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    category = callback.data.split("_", 2)[2]  # proxy / v2ray / npv
    # حالت‌های لینک/کامنت قبلی نباید URL کانفیگ را به دانلود رسانه بفرستند.
    media_request_sessions.pop(callback.from_user.id, None)
    instagram_comment_sessions.discard(callback.from_user.id)
    config_upload_sessions[callback.from_user.id] = category
    await callback.message.answer(
        f"📤 حالا {CONFIG_LABELS[category]} رو بفرست؛ می‌تونی متن لینک (مثل vmess/vless/ss یا لینک پروکسی) یا یک فایل بفرستی.\n"
        f"می‌تونی پشت سر هم چند تا بفرستی، هر کدوم جدا ذخیره میشه.\n"
        f"وقتی تموم شد /cancel رو بزن.",
        parse_mode="Markdown",
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_config_stats")
async def admin_config_stats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ دسترسی ندارید!", show_alert=True)
    today = today_str()
    proxy_count = await configs_col.count_documents({"category": "proxy", "date_str": today})
    v2ray_count = await configs_col.count_documents({"category": "v2ray", "date_str": today})
    npv_count = await configs_col.count_documents({"category": "npv", "date_str": today})
    await callback.message.answer(
        f"📊 **آمار پروکسی/کانفیگ امروز ({today})**\n\n"
        f"🌐 پروکسی: {proxy_count}\n"
        f"⚡️ V2Ray: {v2ray_count}\n"
        f"🌀 NPV: {npv_count}",
        parse_mode="Markdown",
    )
    await callback.answer()

@dp.message(Command("help"))
async def help_command(message: types.Message):
    text = (
        "📖 <b>راهنمای Ajorpareh</b>\n\n"
        "/start — منوی اصلی\n"
        "/profile — امتیاز، رتبه و استریک\n"
        "/games — بازی‌های سرگرمی\n"
        "/app — بازکردن Mini App\n"
        "/ai — چت، تصویر، ترجمه، خلاصه و ابزارهای هوش مصنوعی\n"
        "/voice — تبدیل ویس و فایل صوتی به متن\n"
        "/download — دانلود محتوای عمومی شبکه‌ها\n"
        "/igcomment — کپی متن کامنت عمومی اینستاگرام از روی لینک\n"
        "/remind — ساخت یادآور شخصی\n"
        "/reminders — فهرست یادآورهای فعال\n"
        "/caption — کپشن‌ساز وایرال\n"
        "/truth — جرأت یا حقیقت\n"
        "/emoji_api — راهنمای API شکلک‌های سفارشی برای برنامه‌نویسان\n"
        "/weather — آب‌وهوا · /rate — نرخ ارز · /crypto — کریپتو · /wiki — ویکی‌پدیا\n"
        "/book — کتاب · /country — کشور · /time — ساعت جهانی · /checkpass — امنیت رمز\n"
        "/calendar — تقویم شمسی با مناسبت‌ها\n"
        "/mystats — آمار شخصی · /short — لینک کوتاه · /summarize — خلاصهٔ هوشمند\n"
        "/pray — اوقات شرعی · /fal — فال حافظ\n"
        "/joke — جوک روز\n"
        "/quote — جمله انگیزشی\n"
        "/time — ساعت تهران\n"
        "/id — آیدی تلگرام\n"
        "/cancel — لغو عملیات فعال\n\n"
        "برای گزارش مشکل از دکمه «پشتیبانی و پیشنهاد» استفاده کن."
    )
    if is_admin(message.from_user.id):
        text += (
            "\n\n⚙️ <b>دستورات مدیریت</b>\n"
            "/admin — پنل مدیریت\n/channels — کانال‌های اجباری\n"
            "/repost — بازنشر گروهی\n/quickpost — انتشار فوری\n/configs — مدیریت کانفیگ‌ها\n/search — جستجوی کاربر\n"
            "/activity [ID] — فعالیت کاربر\n/ban [ID] [دلیل]\n/unban [ID]"
        )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("profile"))
async def profile_command(message: types.Message):
    db_user = await users_col.find_one({"_id": message.from_user.id}) or {}
    xp = int(db_user.get("xp", 0))
    higher = await users_col.count_documents({"xp": {"$gt": xp}, "is_banned": {"$ne": True}})
    await message.answer(
        f"👤 <b>{html.escape(message.from_user.full_name)}</b>\n"
        f"🆔 <code>{message.from_user.id}</code>\n\n"
        f"⚡ XP: <b>{xp:,}</b> · رتبه: <b>#{higher + 1}</b>\n"
        f"🔥 استریک: {int(db_user.get('streak', 0))} روز\n"
        f"🎮 بازی: {int(db_user.get('games_played', 0))} · برد: {int(db_user.get('games_won', 0))}\n"
        f"🪙 سکه: {int(db_user.get('coins', 0))}",
        parse_mode="HTML",
    )


@dp.message(Command("games"))
async def games_command(message: types.Message):
    await message.answer("🎮 یکی رو انتخاب کن:", reply_markup=game_menu())


@dp.message(Command("app"))
async def app_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 باز کردن Ajorpareh", web_app=WebAppInfo(url=MINI_APP_URL))]
    ])
    await message.answer("🕹 آرکید، چالش روزانه و جدول رکوردها:", reply_markup=keyboard)


@dp.message(Command("ai"))
async def ai_command(message: types.Message):
    await show_ai_menu(message)


@dp.message(Command("voice"))
async def voice_command(message: types.Message):
    ai_sessions[message.from_user.id] = {
        "mode": "voice", "history": [], "started_at": time.monotonic(), "last_used_at": time.monotonic()
    }
    await message.answer(AI_MODE_CONFIG["voice"]["instruction"], reply_markup=ai_reply_menu())


@dp.message(Command("remind"))
async def remind_command(message: types.Message):
    content = (message.text or "").partition(" ")[2].strip()
    if content:
        try:
            repeat, scheduled_at, reminder_text = parse_recurring_input(content)
            item = await create_user_reminder(message.from_user.id, reminder_text, scheduled_at, "bot", repeat)
        except ValueError as exc:
            return await message.answer(
                f"❌ {exc}\nنمونه‌ها:\n<code>/remind فردا 09:00 | تماس با علی</code>\n<code>/remind هر روز 09:00 | نوشیدن آب</code>\n<code>/remind شنبه 10:00 | جلسه</code>",
                parse_mode="HTML",
            )
        repeat_label = {"daily": "🔁 هر روز", "weekly": "🔁 هر هفته", "monthly": "🔁 هر ماه"}.get(item.get("repeat"))
        repeat_line = f"\n{repeat_label}" if repeat_label else ""
        return await message.answer(
            f"✅ یادآور ثبت شد.{repeat_line}\n🕒 اولین اجرا: {format_tehran_datetime(item['scheduled_at'])}\n📝 {html.escape(item['text'])}",
            parse_mode="HTML",
            reply_markup=tools_reply_menu(),
        )
    reminder_sessions.add(message.from_user.id)
    await message.answer(
        "⏰ زمان و متن رو بفرست.\nنمونه: <code>فردا 09:00 | تماس با علی</code>\nیا: <code>1405/05/20 18:30 | خرید دارو</code>\n/cancel برای لغو",
        parse_mode="HTML",
        reply_markup=tools_reply_menu(),
    )


@dp.message(Command("reminders"))
async def reminders_command(message: types.Message):
    await send_user_reminders_list(message)


@dp.callback_query(F.data.startswith("remcancel:"))
async def reminder_cancel_callback(callback: types.CallbackQuery):
    reminder_id = callback.data.split(":", 1)[1]
    result = await reminders_col.update_one(
        {"_id": reminder_id, "user_id": callback.from_user.id, "status": "pending"},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc)}},
    )
    await callback.answer("حذف شد ✅" if result.modified_count else "یادآور پیدا نشد.", show_alert=True)
    if result.modified_count:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass


@dp.message(Command("qr"))
async def qr_command(message: types.Message):
    content = (message.text or "").partition(" ")[2].strip()
    if content: return await send_qr_result(message, content)
    qr_sessions.add(message.from_user.id); await message.answer("📱 متن یا لینک رو بفرست تا QR بسازم. برای انصراف /cancel")


@dp.message(Command("sticker"))
async def sticker_command(message: types.Message):
    gif_sessions.discard(message.from_user.id)
    sticker_sessions.add(message.from_user.id)
    await message.answer(
        "🪄 یک عکس بفرست تا به استیکر ۵۱۲×۵۱۲ تبدیل و داخل پک تلگرامت ذخیره کنم. /cancel",
        reply_markup=media_maker_reply_menu(),
    )


@dp.message(Command("gif"))
async def gif_command(message: types.Message):
    sticker_sessions.discard(message.from_user.id)
    gif_sessions.add(message.from_user.id)
    await message.answer(
        "🎞 عکس، ویدئو یا GIF کمتر از ۱۹ مگابایت بفرست. از عکس یک گیف زوم‌دار و از ویدئو/GIF یک Animation تلگرامی تا ۱۲ ثانیه می‌سازم. /cancel",
        reply_markup=media_maker_reply_menu(),
    )


@dp.message(Command("caption"))
async def caption_command(message: types.Message):
    caption_sessions.add(message.from_user.id)
    await message.answer("✨ موضوع عکس یا پستت رو بفرست تا برات کپشن وایرال بسازم. برای انصراف /cancel")


@dp.message(Command("emoji_api"))
async def emoji_api_command(message: types.Message):
    await message.answer(EMOJI_API_GUIDE, parse_mode="HTML", reply_markup=tools_reply_menu())


@dp.message(Command("truth"))
async def truth_command(message: types.Message):
    await message.answer("🎭 جرأت یا حقیقت؟", reply_markup=truth_dare_menu())


@dp.message(Command("time"))
async def time_command(message: types.Message):
    city = (message.text or "").partition(" ")[2].strip()
    if not city:
        t = get_tehran_time()
        return await message.answer(f"🕒 ساعت تهران: {t.strftime('%H:%M:%S')}\n💡 برای شهرهای دیگه: /time لندن", reply_markup=info_reply_menu())
    try:
        wt = await world_time(city)
    except MediaServiceError as exc:
        return await message.answer(f"❌ {exc.message}", reply_markup=info_reply_menu())
    except Exception as exc:
        log.warning("time failed: %s", exc)
        return await message.answer("❌ دریافت ساعت جهانی ناموفق بود.", reply_markup=info_reply_menu())
    await message.answer(
        f"🕐 <b>ساعت {html.escape(city[:40])}</b>\n\n⏰ <b>{wt['time']}</b> · {wt['day_name']}\n📅 {wt['date']}\n🗺 {wt['zone']}",
        parse_mode="HTML", reply_markup=info_reply_menu(),
    )

@dp.message(Command("id"))
async def id_command(message: types.Message):
    await message.answer(f"🆔 آیدی شما: <code>{message.from_user.id}</code>", parse_mode="HTML")

@dp.message(Command("joke"))
async def joke_command(message: types.Message):
    waiting = await message.answer("🔄 دارم یه جوک باحال پیدا می‌کنم...")
    ai_joke = await ask_ai(
        "یک جوک سالم، جدید، کوتاه و واقعاً خنده‌دار به زبان فارسی محاوره‌ای بگو.",
        user_id=message.from_user.id,
        feature="joke",
    )
    joke = ai_joke[:3800] if ai_joke else random.choice(JOKES)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😂 یکی دیگه", callback_data="joke_again"),
         InlineKeyboardButton(text="✨ یه انگیزشی", callback_data="quote_again")]
    ])
    await waiting.edit_text(joke, reply_markup=keyboard)
    await log_activity(message.from_user.id, "joke", "جوک جدید")


@dp.message(Command("quote"))
async def quote_command(message: types.Message):
    waiting = await message.answer("✨ دارم یه جمله خوب برات پیدا می‌کنم...")
    ai_quote = await ask_ai(
        "یک جمله انگیزشی عمیق، کاربردی و کوتاه به زبان فارسی بگو؛ کلیشه‌ای نباشد.",
        user_id=message.from_user.id,
        feature="quote",
    )
    quote = ai_quote[:3800] if ai_quote else random.choice(QUOTES)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ یکی دیگه", callback_data="quote_again"),
         InlineKeyboardButton(text="😂 یه جوک", callback_data="joke_again")]
    ])
    await waiting.edit_text(quote, reply_markup=keyboard)
    await log_activity(message.from_user.id, "quote", "جمله انگیزشی")


@dp.callback_query(F.data.in_({"joke_again", "quote_again"}))
async def refresh_fun_text(callback: types.CallbackQuery):
    if callback.data == "joke_again":
        text = random.choice(JOKES)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="😂 باز یکی دیگه", callback_data="joke_again"),
             InlineKeyboardButton(text="✨ انگیزشی", callback_data="quote_again")]
        ])
    else:
        text = random.choice(QUOTES)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ باز یکی دیگه", callback_data="quote_again"),
             InlineKeyboardButton(text="😂 جوک", callback_data="joke_again")]
        ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer("تازه شد ⚡")

@dp.callback_query(F.data.startswith("riddle:"))
async def reveal_riddle_answer(callback: types.CallbackQuery):
    try:
        index = int(callback.data.split(":", 1)[1])
        answer = FUN_RIDDLES[index][1]
    except (ValueError, IndexError):
        return await callback.answer("معما پیدا نشد.", show_alert=True)
    await callback.answer(f"✅ جواب: {answer}", show_alert=True)


async def send_fun_riddle(message: types.Message):
    index = random.randrange(len(FUN_RIDDLES))
    question, _ = FUN_RIDDLES[index]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👀 دیدن جواب", callback_data=f"riddle:{index}"),
        InlineKeyboardButton(text="🧩 معمای بعدی", callback_data="fun:riddle"),
    ]])
    await message.answer(f"🧩 <b>معمای فوری</b>\n\n{html.escape(question)}", parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "fun:riddle")
async def next_fun_riddle(callback: types.CallbackQuery):
    await send_fun_riddle(callback.message)
    await callback.answer("معمای تازه 🧩")


# =============== ابزارهای دانش و اطلاعات (بدون کلید) ===============

@dp.message(Command("weather"))
async def weather_command(message: types.Message):
    city = (message.text or "").partition(" ")[2].strip()
    if not city:
        info_sessions.add(message.from_user.id)
        return await message.answer("☀️ نام شهر را بفرست (فارسی یا انگلیسی). /cancel", reply_markup=info_reply_menu())
    wait = await message.answer(f"☀️ در حال دریافت آب‌وهوای «{html.escape(city[:40])}»…", parse_mode="HTML")
    try:
        w = await weather(city)
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: await message.answer(f"❌ {exc.message}", reply_markup=info_reply_menu())
        return
    except Exception as exc:
        log.warning("weather failed: %s", exc)
        try: await wait.edit_text("❌ دریافت آب‌وهوا ناموفق بود؛ دوباره تلاش کن.")
        except TelegramBadRequest: pass
        return
    days = ""
    for d in (w.get("daily") or [])[1:]:
        days += f"\n    {d['date'][5:]} · 🌡 {d['min']} تا {d['max']}°"
    text = (
        f"{w['icon']} <b>آب‌وهوای {html.escape(w['city'])}</b>{'، ' + html.escape(w['country']) if w.get('country') else ''}\n\n"
        f"🌡 دما: <b>{w['temp']}°</b> (حس: {w['feels']}°) · {w['label']}\n"
        f"💧 رطوبت: {w['humidity']}٪ · 💨 باد: {w['wind']} km/h\n"
        f"📊 امروز: {w['today_min']} تا {w['today_max']}°"
        + (f" · ☔ احتمال بارش: {w['rain_prob']}٪" if w.get("rain_prob") is not None else "")
        + (f"\n\n🔮 ۲ روز بعد:{days}" if days else "")
    )
    try: await wait.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest: await message.answer(text, parse_mode="HTML", reply_markup=info_reply_menu())


@dp.message(Command("rate"))
async def rate_command(message: types.Message):
    parts = (message.text or "").partition(" ")[2].split()
    if len(parts) < 2:
        return await message.answer("💱 فرمت: <code>/rate usd eur</code> یا <code>/rate دلار تومان</code>", parse_mode="HTML", reply_markup=info_reply_menu())
    try:
        r = await exchange_rate(parts[0], parts[1])
    except MediaServiceError as exc:
        return await message.answer(f"❌ {exc.message}", reply_markup=info_reply_menu())
    except Exception as exc:
        log.warning("rate failed: %s", exc)
        return await message.answer("❌ دریافت نرخ ارز ناموفق بود؛ دوباره تلاش کن.", reply_markup=info_reply_menu())
    if r["to"] == "IRR":
        text = f"💱 <b>هر {r['from']} = {int(r['rate']):,} ریال</b>\n≈ {int(r['rate'] / 1000):,} تومان"
    else:
        text = f"💱 <b>1 {r['from']} = {r['rate']:.4f} {r['to']}</b>"
    if r.get("approx"):
        text += "\n(تقریبی)"
    await message.answer(text, parse_mode="HTML", reply_markup=info_reply_menu())


@dp.message(Command("crypto"))
async def crypto_command(message: types.Message):
    raw = (message.text or "").partition(" ")[2].strip()
    symbols = [s for s in raw.replace("،", " ").split() if s] or ["btc"]
    if len(symbols) > 6:
        return await message.answer("حداکثر ۶ ارز دیجیتال را یکجا بفرست.", reply_markup=info_reply_menu())
    wait = await message.answer("🪙 در حال دریافت قیمت‌ها…")
    try:
        items = await crypto_price(symbols)
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: pass
        return
    except Exception as exc:
        log.warning("crypto failed: %s", exc)
        try: await wait.edit_text("❌ دریافت قیمت کریپتو ناموفق بود.")
        except TelegramBadRequest: pass
        return
    lines = ["🪙 <b>قیمت لحظه‌ای ارزهای دیجیتال</b>", ""]
    for item in items:
        change = item.get("change_24h")
        change_text = ""
        if change is not None:
            arrow = "📈" if change >= 0 else "📉"
            change_text = f" · {arrow} {change:+.1f}٪ (۲۴h)"
        price = f"${item['price_usd']:,.2f}" if item["price_usd"] else "—"
        lines.append(f"<b>{item['name']}</b> ({item['symbol']})\n    💵 {price}{change_text}")
    try: await wait.edit_text("\n".join(lines), parse_mode="HTML")
    except TelegramBadRequest: pass


@dp.message(Command("wiki"))
async def wiki_command(message: types.Message):
    query = (message.text or "").partition(" ")[2].strip()
    if not query:
        info_sessions.add(message.from_user.id)
        return await message.answer("📚 موضوع را بفرست؛ مثلاً «نوروز» یا «اینشتین». /cancel", reply_markup=info_reply_menu())
    wait = await message.answer(f"📚 در حال جستجوی «{html.escape(query[:60])}»…", parse_mode="HTML")
    try:
        w = await wiki_summary(query, "fa")
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: pass
        return
    except Exception as exc:
        log.warning("wiki failed: %s", exc)
        try: await wait.edit_text("❌ جستجوی ویکی‌پدیا ناموفق بود.")
        except TelegramBadRequest: pass
        return
    extract = (w.get("extract") or "")[:800]
    text = f"📚 <b>{html.escape(w['title'])}</b>\n\n{html.escape(extract)}"
    if w.get("url"):
        text += f'\n\n🔗 <a href="{w["url"]}">مشاهده در ویکی‌پدیا</a>'
    keyboard = info_reply_menu()
    if w.get("thumbnail"):
        try:
            await wait.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            return
        except TelegramBadRequest:
            pass
    try: await wait.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@dp.message(Command("book"))
async def book_command(message: types.Message):
    query = (message.text or "").partition(" ")[2].strip()
    if not query:
        info_sessions.add(message.from_user.id)
        return await message.answer("📖 نام کتاب را بفرست؛ مثلاً «بوف کور». /cancel", reply_markup=info_reply_menu())
    wait = await message.answer(f"📖 در حال جستجوی «{html.escape(query[:60])}»…", parse_mode="HTML")
    try:
        books = await book_search(query, 4)
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: pass
        return
    except Exception as exc:
        log.warning("book failed: %s", exc)
        try: await wait.edit_text("❌ جستجوی کتاب ناموفق بود.")
        except TelegramBadRequest: pass
        return
    lines = ["📖 <b>نتایج جستجوی کتاب</b>", ""]
    for b in books:
        authors = "، ".join(b.get("authors") or []) or "ناشناس"
        year = b.get("year") or "؟"
        lines.append(f"• <b>{html.escape(b['title'])}</b>\n    ✍️ {html.escape(authors)} · 📅 {year}")
        if b.get("url"):
            lines.append(f'    🔗 <a href="{b["url"]}">openlibrary.org</a>')
    try: await wait.edit_text("\n".join(lines), parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=info_reply_menu())


@dp.message(Command("country"))
async def country_command(message: types.Message):
    name = (message.text or "").partition(" ")[2].strip()
    if not name:
        info_sessions.add(message.from_user.id)
        return await message.answer("🌍 نام کشور را بفرست؛ مثلاً «ایران». /cancel", reply_markup=info_reply_menu())
    wait = await message.answer(f"🌍 در حال جستجوی «{html.escape(name[:40])}»…", parse_mode="HTML")
    try:
        c = await country_info(name)
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: pass
        return
    except Exception as exc:
        log.warning("country failed: %s", exc)
        try: await wait.edit_text("❌ اطلاعات کشور ناموفق بود.")
        except TelegramBadRequest: pass
        return
    text = f"{c['flag']} <b>{html.escape(c['name'])}</b>\n\n{html.escape((c.get('extract') or '')[:700])}"
    if c.get("url"):
        text += f'\n\n🔗 <a href="{c["url"]}">ویکی‌پدیا</a>'
    try: await wait.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(text, parse_mode="HTML", reply_markup=info_reply_menu())


@dp.message(Command("checkpass"))
async def checkpass_command(message: types.Message):
    password = (message.text or "").partition(" ")[2].strip()
    if not password:
        return await message.answer("🔐 رمز را بفرست تا بررسی کنم چند بار در هک‌ها لو رفته. (فقط ۵ کاراکتر اول هش ارسال می‌شود — رمز کامل جایی نمی‌ره) /cancel", reply_markup=info_reply_menu())
    wait = await message.answer("🔐 در حال بررسی دیتابیس هک‌ها…")
    count = await asyncio.to_thread(pwned_password_count, password)
    if count < 0:
        try: await wait.edit_text("❌ بررسی ناموفق بود؛ دوباره تلاش کن.")
        except TelegramBadRequest: pass
        return
    if count == 0:
        text = "🟢 <b>رمز خوبه!</b>\nاین رمز در دیتابیس‌های هک‌شده پیدا نشد. بازم پیشنهاد می‌کنم برای هر سرویس رمز جدا داشته باشی."
    elif count < 100:
        text = f"🟡 <b>این رمز {count:,} بار لو رفته!</b>\nبهتره عوضش کنی."
    else:
        text = f"🔴 <b>این رمز {count:,} بار در هک‌ها لو رفته!</b>\nفوراً عوضش کن و از رمزهای تکراری استفاده نکن."
    try: await wait.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(text, parse_mode="HTML", reply_markup=info_reply_menu())


# =============== کوئیز جهانی ===============

quiz_state: dict[int, dict] = {}


@dp.message(Command("quiz"))
async def quiz_command(message: types.Message):
    await message.answer("🧠 در حال دریافت سؤال از بانک جهانی… (Open Trivia DB)")
    try:
        questions = await opentdb_quiz(1)
    except MediaServiceError as exc:
        return await message.answer(f"❌ {exc.message}", reply_markup=info_reply_menu())
    except Exception as exc:
        log.warning("quiz failed: %s", exc)
        return await message.answer("❌ دریافت سؤال ناموفق بود؛ دوباره تلاش کن.", reply_markup=info_reply_menu())
    if not questions:
        return await message.answer("❌ سؤالی دریافت نشد؛ دوباره تلاش کن.", reply_markup=info_reply_menu())
    q = questions[0]
    quiz_state[message.from_user.id] = {
        "question": q["question"],
        "correct": q["correct"],
        "options": q["options"],
        "category": q["category"],
    }
    import random as _random
    options = q["options"][:]
    _random.shuffle(options)
    rows = [[InlineKeyboardButton(text=f"{chr(0x1F1E6 + i)} {opt[:40]}", callback_data=f"quiz_ans:{opt}")] for i, opt in enumerate(options)]
    rows.append([InlineKeyboardButton(text="⏭ سؤال بعدی", callback_data="quiz_next")])
    diff_label = {"easy": "آسان", "medium": "متوسط", "hard": "سخت"}.get(q["difficulty"], q["difficulty"])
    await message.answer(
        f"🧠 <b>کوئیز جهانی</b> · {html.escape(q['category'])} · {diff_label}\n\n{html.escape(q['question'])}",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("quiz_ans:"))
async def quiz_answer_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    answer = callback.data.split(":", 1)[1]
    state = quiz_state.get(user_id)
    if not state:
        return await callback.answer("این سؤال منقضی شده؛ /quiz بزن.", show_alert=True)
    correct = state["correct"]
    won = answer == correct
    await record_game(user_id, "quiz", won, 20 if won else 5)
    await callback.message.edit_text(
        f"{'🎉 <b>درست بود!</b>' if won else '❌ <b>اشتباه بود!</b>'}\n\n"
        f"📌 جواب درست: <b>{html.escape(correct)}</b>\n"
        f"🏅 {'+۲۰ امتیاز' if won else '+۵ امتیاز'}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ سؤال بعدی", callback_data="quiz_next")],
        ]),
    )
    await callback.answer("🎯" if won else "😅")


@dp.callback_query(F.data == "quiz_next")
async def quiz_next_callback(callback: types.CallbackQuery):
    quiz_state.pop(callback.from_user.id, None)
    await callback.answer()
    await quiz_command(callback.message)


# =============== تقویم شمسی ===============

def calendar_month_text(jy: int, jm: int) -> str:
    grid = cal_month_grid(jy, jm)
    today = cal_today_jalali()
    occ_map = {o["day"]: o["occasions"] for o in cal_month_occasions(jy, jm)}
    header = "ش ی د س چ پ ج"
    lines = [
        f"📅 <b>{grid['month_name']} {grid['year']}</b>"
        + (" (کبیسه)" if grid["leap"] else ""),
        "",
        f"<code>{header}</code>",
    ]
    row = ""
    for i, cell in enumerate(grid["days"]):
        day = cell["day"]
        is_today = cell["current"] and day == today[2] and jm == today[1] and jy == today[0]
        has_occ = cell["current"] and day in occ_map
        marker = "●" if has_occ else " "
        if is_today:
            text = f"<b>{day:>2}</b>"
        else:
            text = f"{day:>2}"
        row += f"{text}{marker} "
        if (i + 1) % 7 == 0:
            lines.append(f"<code>{row}</code>")
            row = ""
    if row.strip():
        lines.append(f"<code>{row}</code>")
    lines.append("")
    lines.append("🔴 امروز · ● مناسبت دارد")
    return "\n".join(lines)


def calendar_month_keyboard(jy: int, jm: int) -> InlineKeyboardMarkup:
    prev_m = jm - 1 if jm > 1 else 12
    prev_y = jy if jm > 1 else jy - 1
    next_m = jm + 1 if jm < 12 else 1
    next_y = jy if jm < 12 else jy + 1
    today = cal_today_jalali()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ ماه قبل", callback_data=f"cal:{prev_y}:{prev_m}"),
         InlineKeyboardButton(text="📌 امروز", callback_data=f"cal:{today[0]}:{today[1]}"),
         InlineKeyboardButton(text="ماه بعد ⬅️", callback_data=f"cal:{next_y}:{next_m}")],
        [InlineKeyboardButton(text="🗓 مناسبت‌های این ماه", callback_data=f"calocc:{jy}:{jm}")],
        [InlineKeyboardButton(text="🔙 ابزارها", callback_data="back_tools")],
    ])


# =============== تبدیل متن به صدا (ElevenLabs) ===============

async def get_tts_voice(user_id: int) -> str:
    user = await users_col.find_one({"_id": user_id}, {"tts_voice": 1})
    voice = (user or {}).get("tts_voice") or "bella"
    return voice if voice in TTS_VOICES else "bella"


async def tts_quota_left(user_id: int) -> int:
    """باقی‌ماندهٔ سهمیهٔ روزانهٔ تبدیل متن به صدا (کاراکتر)."""
    if is_admin(user_id):
        return 10_000_000
    day = today_str()
    user = await users_col.find_one({"_id": user_id}, {"tts_day": 1, "tts_chars": 1})
    if not user or user.get("tts_day") != day:
        return TTS_DAILY_CHAR_LIMIT
    used = int(user.get("tts_chars", 0) or 0)
    return max(0, TTS_DAILY_CHAR_LIMIT - used)


async def consume_tts_chars(user_id: int, chars: int) -> None:
    day = today_str()
    user = await users_col.find_one({"_id": user_id}, {"tts_day": 1, "tts_chars": 1})
    used = int(user.get("tts_chars", 0) or 0) if user and user.get("tts_day") == day else 0
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"tts_day": day, "tts_chars": used + chars}},
        upsert=True,
    )


async def elevenlabs_tts(text: str, voice_id: str) -> bytes:
    """تولید صوت از متن با ElevenLabs — برمی‌گرداند بایت‌های MP3."""
    if not ELEVENLABS_API_KEY:
        raise MediaServiceError("unconfigured", "سرویس صدا هنوز فعال نشده است.")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {"text": text, "model_id": TTS_MODEL}
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    try:
        async with http_session.post(url, json=payload, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=90)) as resp:
            if resp.status == 200:
                data = await resp.read()
                if not data or len(data) < 2048:
                    raise MediaServiceError("empty", "فایل صوتی خالی دریافت شد؛ دوباره تلاش کن.")
                return data
            body = (await resp.text()).lower()
            if resp.status == 401:
                raise MediaServiceError("auth_error", "کلید سرویس صدا نامعتبر است.")
            if resp.status == 402 or "paid_plan" in body:
                raise MediaServiceError("plan_quota", "سهمیهٔ ماهانهٔ سرویس صدا پر شده است.")
            if resp.status == 429:
                raise MediaServiceError("rate_limited", "درخواست‌های صدا زیاد شد؛ کمی بعد دوباره تلاش کن.")
            raise MediaServiceError("http_error", f"سرویس صدا با خطای HTTP {resp.status} پاسخ داد.")
    except asyncio.TimeoutError as exc:
        raise MediaServiceError("timeout", "تولید صدا طول کشید؛ دوباره تلاش کن.") from exc
    except aiohttp.ClientError as exc:
        raise MediaServiceError("network", "اتصال به سرویس صدا برقرار نشد.") from exc


# =============== آمار شخصی کاربر /mystats ===============

# =============== اوقات شرعی و فال حافظ ===============

@dp.message(Command("pray"))
async def pray_command(message: types.Message):
    city = (message.text or "").partition(" ")[2].strip() or "تهران"
    wait = await message.answer(f"🕌 در حال دریافت اوقات شرعی «{html.escape(city[:40])}»…", parse_mode="HTML")
    try:
        data = await prayer_times(city)
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: pass
        return
    except Exception as exc:
        log.warning("prayer failed: %s", exc)
        try: await wait.edit_text("❌ دریافت اوقات شرعی ناموفق بود؛ دوباره تلاش کن.")
        except TelegramBadRequest: pass
        return
    try:
        await wait.edit_text(format_prayer_text(data), parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(format_prayer_text(data), parse_mode="HTML", reply_markup=info_reply_menu())
    await log_activity(message.from_user.id, "prayer", f"city={data.get('city')}")


@dp.message(Command("fal"))
async def fal_command(message: types.Message):
    wait = await message.answer("🍷 در حال تفأل به حافظ…")
    try:
        data = await hafez_fal()
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: pass
        return
    except Exception as exc:
        log.warning("hafez fal failed: %s", exc)
        try: await wait.edit_text("❌ دریافت فال ناموفق بود؛ دوباره تلاش کن.")
        except TelegramBadRequest: pass
        return
    try:
        text = build_fal_message(data, morning=False)
    except ValueError:
        return await wait.edit_text("❌ پاسخ فال خالی بود؛ دوباره تلاش کن.")
    try:
        await wait.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(text, parse_mode="HTML", reply_markup=info_reply_menu())
    await log_activity(message.from_user.id, "hafez_fal")


@dp.message(F.chat.type == "private", F.text.regexp(r"^🕌 اوقات شرعی$"))
async def info_pray_prompt(message: types.Message):
    await pray_command(message)


@dp.message(F.chat.type == "private", F.text.regexp(r"^🍷 فال حافظ$"))
async def info_fal_prompt(message: types.Message):
    await fal_command(message)


@dp.message(Command("falsub"))
async def falsub_command(message: types.Message):
    user_id = message.from_user.id
    user = await users_col.find_one({"_id": user_id}, {"fal_subscribed": 1})
    current = bool((user or {}).get("fal_subscribed"))
    new_state = not current
    await users_col.update_one({"_id": user_id}, {"$set": {"fal_subscribed": new_state}}, upsert=True)
    status = "✅ اشتراک فال روزانه فعال شد! هر روز ساعت ۷ صبح فال حافظ برات میاد." if new_state else "⏸ اشتراک فال روزانه لغو شد."
    await message.answer(
        f"🍷 <b>فال روزانه صبحگاهی</b>\n\n{status}\n\n"
        "اگه نظرت عوض شد دوباره /falsub بزن.",
        parse_mode="HTML", reply_markup=info_reply_menu(),
    )
    await log_activity(user_id, "fal_sub", "on" if new_state else "off")


@dp.message(Command("praysub"))
async def praysub_command(message: types.Message):
    user_id = message.from_user.id
    user = await users_col.find_one({"_id": user_id}, {"prayer_subscribed": 1})
    current = bool((user or {}).get("prayer_subscribed"))
    new_state = not current
    await users_col.update_one({"_id": user_id}, {"$set": {"prayer_subscribed": new_state}}, upsert=True)
    status = (
        "🔔 <b>اذان‌گوی شخصی فعال شد!</b>\nهر وقت نماز شد (اذان صبح، ظهر، عصر، مغرب، عشاء)، اذان برات پیام میاد. 🕌"
        if new_state else "🔕 اذان‌گوی شخصی لغو شد."
    )
    await message.answer(
        f"🕌 <b>اذان‌گوی شخصی</b>\n\n{status}\n\n"
        "اگه نظرت عوض شد دوباره /praysub بزن.",
        parse_mode="HTML", reply_markup=info_reply_menu(),
    )
    await log_activity(user_id, "praysub", "on" if new_state else "off")


@dp.message(F.chat.type == "private", F.text.regexp(r"^🔔 فال روزانه$"))
async def info_falsub_prompt(message: types.Message):
    await falsub_command(message)


@dp.message(F.chat.type == "private", F.text.regexp(r"^🕌 اذان‌گوی شخصی$"))
async def info_praysub_prompt(message: types.Message):
    await praysub_command(message)


@dp.message(Command("mystats"))
async def mystats_command(message: types.Message):
    user_id = message.from_user.id
    user = await users_col.find_one({"_id": user_id}) or {}
    name = (user.get("name") or "کاربر")[:60]
    # شمارش از فعالیت‌ها با یک کوئری aggregate
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    try:
        rows = await activities_col.aggregate(pipeline).to_list(length=200)
    except Exception:
        rows = []
    counts: dict[str, int] = {r["_id"]: r["count"] for r in rows}
    def cat(prefixes: tuple) -> int:
        return sum(v for k, v in counts.items() if any(k.startswith(p) for p in prefixes))
    games = cat(("game_", "hit_run", "rps", "dice", "dart", "coin", "guess", "quiz", "memory", "bj"))
    ai_uses = cat(("ai_",))
    downloads = cat(("media_", "youtube_", "get_proxy", "get_config"))
    music = cat(("music_", "media_music"))
    reminders = cat(("reminder",))
    stickers = cat(("sticker_", "gif_"))
    total_actions = sum(counts.values())
    # رتبه
    rank = 1
    try:
        better = await users_col.count_documents({"xp": {"$gt": int(user.get("xp", 0))}})
        rank = better + 1
    except Exception:
        pass
    lines = [
        f"📊 <b>آمار {html.escape(name)}</b>",
        "",
        f"⚡ امتیاز (XP): <b>{int(user.get('xp', 0)):,}</b> · رتبه: <b>#{rank}</b>",
        f"🪙 سکه: <b>{int(user.get('coins', 0)):,}</b> · 💵 کیف پول: <b>{int(user.get('wallet_toman', 0)):,}</b> تومان",
        f"🔥 استریک: <b>{int(user.get('streak', 0))}</b> روز · 🎮 بازی‌ها: <b>{int(user.get('games_played', 0))}</b>",
        f"🤝 دعوت‌ها: <b>{int(user.get('referral_count', 0))}</b>",
        "",
        f"🎮 تعداد بازی: {games:,}",
        f"🤖 استفاده از AI: {ai_uses:,}",
        f"📥 دانلود و رسانه: {downloads:,}",
        f"🎵 موزیک: {music:,}",
        f"⏰ یادآورها: {reminders:,}",
        f"🪄 استیکر/گیف: {stickers:,}",
        f"📋 کل رویدادها: {total_actions:,}",
        "",
        "💡 با /profile جزئیات بیشتر و با /leaderboard رتبه‌ها رو ببین.",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


# =============== لینک کوتاه‌ساز /short (is.gd — بدون کلید) ===============

@dp.message(Command("short"))
async def short_command(message: types.Message):
    url = (message.text or "").partition(" ")[2].strip()
    if not url:
        short_sessions.add(message.from_user.id)
        return await message.answer(
            "🔗 لینکی که می‌خوای کوتاه کنم رو بفرست. /cancel",
            reply_markup=tools_reply_menu(),
        )
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    wait = await message.answer("🔗 در حال کوتاه‌کردن لینک…")
    try:
        params = {"format": "json", "url": url}
        async with http_session.get("https://is.gd/create.php", params=params,
                                     timeout=aiohttp.ClientTimeout(total=20)) as resp:
            data = await resp.json(content_type=None)
        if resp.status != 200 or not data.get("shorturl"):
            raise MediaServiceError("short_failed", "کوتاه‌سازی ناموفق بود؛ لینک را بررسی کن.")
        short_url = data["shorturl"]
        await wait.edit_text(
            f"🔗 <b>لینک کوتاه شد!</b>\n\n"
            f"📥 لینک اصلی:\n<code>{html.escape(url[:200])}</code>\n\n"
            f"🔗 <b>لینک کوتاه:</b>\n{short_url}\n\n"
            f'✅ <a href="{short_url}">کلیک برای تست</a>',
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 کپی لینک", callback_data=f"shortcopy:{short_url}")],
            ]),
        )
        await log_activity(message.from_user.id, "shorten", url[:120])
    except MediaServiceError as exc:
        try: await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest: pass
    except Exception as exc:
        log.warning("short failed: %s", exc)
        try: await wait.edit_text("❌ کوتاه‌سازی ناموفق بود؛ دوباره تلاش کن.")
        except TelegramBadRequest: pass


short_sessions: set[int] = set()


@dp.callback_query(F.data.startswith("shortcopy:"))
async def short_copy_callback(callback: types.CallbackQuery):
    short_url = callback.data.split(":", 1)[1]
    await callback.answer(short_url, show_alert=True)


# =============== خلاصه‌سازی با AI /summarize ===============

@dp.message(Command("summarize"))
async def summarize_command(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        summarize_sessions.add(message.from_user.id)
        return await message.answer(
            "📝 <b>خلاصه‌سازی هوشمند</b>\n\n"
            "متن طولانی، مقاله، خبر یا لینک رو بفرست تا خلاصه‌اش کنم. /cancel",
            parse_mode="HTML", reply_markup=tools_reply_menu(),
        )
    await run_summarize(message, text)


async def run_summarize(message: types.Message, text: str) -> None:
    text = text.strip()
    if len(text) < 40:
        return await message.answer("متن خیلی کوتاهه؛ یک متن طولانی‌تر بفرست.", reply_markup=tools_reply_menu())
    if len(text) > 12000:
        text = text[:12000]
    wait = await message.answer("📝 در حال خلاصه‌سازی با هوش مصنوعی…")
    result = await ai_service.ask_text(
        text,
        user_id=message.from_user.id,
        feature="summarize",
        system_prompt=(
            "تو یک خلاصه‌ساز حرفه‌ای فارسی هستی. متن داده‌شده را در ۴ تا ۶ خط کوتاه و روان خلاصه کن. "
            "نکات کلیدی را با بولت جدا کن و در انتها ۳ هشتگ مرتبط بده. از تکرار مطلب خودداری کن."
        ),
    )
    if not result.ok:
        reason_msg = {
            "quota": "❌ سهمیهٔ روزانه‌ات برای AI تمام شده؛ فردا دوباره تلاش کن.",
            "unconfigured": "❌ هوش مصنوعی هنوز تنظیم نشده.",
            "empty_input": "❌ ورودی خالی است.",
        }.get(result.reason, "❌ خلاصه‌سازی ناموفق بود؛ دوباره تلاش کن.")
        try: await wait.edit_text(reason_msg)
        except TelegramBadRequest:
            await message.answer(reason_msg, reply_markup=tools_reply_menu())
        return
    answer = (result.text or "").strip()
    try:
        await wait.edit_text(f"📝 <b>خلاصهٔ هوشمند</b>\n\n{answer}", parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(f"📝 <b>خلاصهٔ هوشمند</b>\n\n{answer}", parse_mode="HTML", reply_markup=tools_reply_menu())
    await log_activity(message.from_user.id, "summarize", f"chars={len(text)}")


summarize_sessions: set[int] = set()


@dp.message(Command("tts"))
async def tts_command(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        tts_sessions.add(message.from_user.id)
        return await message.answer(
            "🎤 <b>متن به صدا</b>\n\nمتنی که می‌خوای به ویس تبدیل بشه رو بفرست (حداکثر ۵۰۰ کاراکتر).\n"
            "💡 با /ttsvoice می‌تونی بین صدای زن (Bella) و مرد (Adam) انتخاب کنی. /cancel",
            parse_mode="HTML", reply_markup=tools_reply_menu(),
        )
    await run_tts(message, text)


async def run_tts(message: types.Message, text: str) -> None:
    user_id = message.from_user.id
    text = text.strip()[:2000]
    if not text:
        return await message.answer("متن خالی است؛ چیزی بنویس.", reply_markup=tools_reply_menu())
    chars = len(text)
    left = await tts_quota_left(user_id)
    if chars > left:
        return await message.answer(
            f"❌ سهمیهٔ روزانهٔ شما برای تبدیل صدا <b>{left:,} کاراکتر</b> باقی مانده.\n"
            "فردا دوباره شارژ می‌شود.",
            parse_mode="HTML", reply_markup=tools_reply_menu(),
        )
    voice_key = await get_tts_voice(user_id)
    voice = TTS_VOICES[voice_key]
    wait = await message.answer(f"{voice['emoji']} در حال ساخت ویس با صدای {voice['name']}… ({chars:,} کاراکتر)")
    try:
        data = await elevenlabs_tts(text, voice["id"])
    except MediaServiceError as exc:
        try:
            await wait.edit_text(f"❌ {exc.message}")
        except TelegramBadRequest:
            pass
        return
    except Exception as exc:
        log.warning("tts failed: %s", exc)
        try:
            await wait.edit_text("❌ ساخت صدا ناموفق بود؛ دوباره تلاش کن.")
        except TelegramBadRequest:
            pass
        return
    await consume_tts_chars(user_id, chars)
    try:
        await bot.send_chat_action(user_id, "record_voice")
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    with tempfile.TemporaryDirectory(prefix="ajor-tts-") as folder:
        path = Path(folder) / "ajorpareh-voice.mp3"
        path.write_bytes(data)
        upload = FSInputFile(str(path), filename="ajorpareh-voice.mp3")
        try:
            await bot.send_voice(
                user_id, upload,
                caption=f"🎤 ویس ساخته‌شده با {voice['emoji']} {voice['name']}",
                reply_markup=tools_reply_menu(),
                request_timeout=120,
            )
        except TelegramBadRequest:
            try:
                await bot.send_audio(
                    user_id, upload,
                    title="آجُرپاره TTS",
                    performer=voice["name"],
                    reply_markup=tools_reply_menu(),
                    request_timeout=120,
                )
            except TelegramBadRequest:
                await bot.send_document(
                    user_id, upload, caption="🎤 ویس ساخته‌شده",
                    reply_markup=tools_reply_menu(), request_timeout=120,
                )
    try:
        await wait.delete()
    except TelegramBadRequest:
        pass
    await log_activity(user_id, "tts", f"chars={chars},voice={voice_key}")
    await message.answer(
        f"✅ ویس آماده شد! ({chars:,} کاراکتر)\n"
        f"سهمیهٔ باقی‌ماندهٔ امروز: <b>{(await tts_quota_left(user_id)):,}</b> کاراکتر\n"
        "💡 با /ttsvoice صدای زن یا مرد رو انتخاب کن.",
        parse_mode="HTML", reply_markup=tools_reply_menu(),
    )


@dp.message(Command("ttsvoice"))
async def tts_voice_command(message: types.Message):
    current = await get_tts_voice(message.from_user.id)
    rows = []
    for key, voice in TTS_VOICES.items():
        label = f"{voice['emoji']} {voice['name']}" + (" ✅" if key == current else "")
        rows.append([InlineKeyboardButton(text=label, callback_data=f"ttsvoice:{key}")])
    await message.answer(
        "🎤 <b>انتخاب صدا</b>\n\nکدوم صدا رو می‌خوای؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("ttsvoice:"))
async def tts_voice_callback(callback: types.CallbackQuery):
    key = callback.data.split(":", 1)[1]
    if key not in TTS_VOICES:
        return await callback.answer("صدای نامعتبر.", show_alert=True)
    await users_col.update_one({"_id": callback.from_user.id}, {"$set": {"tts_voice": key}}, upsert=True)
    voice = TTS_VOICES[key]
    await callback.answer(f"صدای {voice['name']} انتخاب شد ✅")
    try:
        await callback.message.edit_text(
            f"✅ صدای {voice['emoji']} <b>{voice['name']}</b> انتخاب شد.\n"
            "حالا /tts متن را بفرست.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎤 تبدیل متن به صدا", callback_data="tts_prompt")],
            ]),
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "tts_prompt")
async def tts_prompt_callback(callback: types.CallbackQuery):
    tts_sessions.add(callback.from_user.id)
    await callback.message.answer("🎤 متنی که می‌خوای به ویس تبدیل بشه رو بفرست. /cancel", reply_markup=tools_reply_menu())
    await callback.answer()


tts_sessions: set[int] = set()


@dp.message(F.chat.type == "private", F.text.regexp(r"^🎤 تبدیل متن به صدا$"))
async def tts_menu_entry(message: types.Message):
    tts_sessions.add(message.from_user.id)
    left = await tts_quota_left(message.from_user.id)
    voice_key = await get_tts_voice(message.from_user.id)
    voice = TTS_VOICES[voice_key]
    await message.answer(
        f"🎤 <b>تبدیل متن به صدا</b>\n\n"
        f"صدای فعلی: {voice['emoji']} {voice['name']} (با /ttsvoice عوضش کن)\n"
        f"سهمیهٔ امروز: <b>{left:,}</b> کاراکتر\n\n"
        "متنی که می‌خوای بفرست. /cancel",
        parse_mode="HTML", reply_markup=tools_reply_menu(),
    )


@dp.message(Command("calendar"))
async def calendar_command(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    jy, jm, jd = cal_today_jalali()
    if text:
        parts = text.replace("،", " ").split()
        try:
            if len(parts) == 1:
                month_idx = JALALI_MONTHS.index(parts[0].replace("ماه", "").strip())
                jm = month_idx + 1
            elif len(parts) >= 2:
                jm = int(parts[0])
                jy = int(parts[1])
        except (ValueError, IndexError):
            pass
    info = cal_today_info()
    today_text = (
        f"🗓 امروز: <b>{info['weekday']} {info['jd']} {info['month_name']} {info['jy']}</b>\n"
        f"🌙 {info['islamic']} · 📆 {info['gregorian']}"
    )
    occ = info["occasions"]
    if occ:
        today_text += "\n" + "\n".join(f"   {o}" for o in occ)
    await message.answer(
        calendar_month_text(jy, jm) + "\n\n" + today_text,
        parse_mode="HTML",
        reply_markup=calendar_month_keyboard(jy, jm),
    )


@dp.callback_query(F.data.startswith("cal:"))
async def calendar_nav_callback(callback: types.CallbackQuery):
    try:
        _, jy, jm = callback.data.split(":")
        jy, jm = int(jy), int(jm)
    except (IndexError, ValueError):
        return await callback.answer("درخواست نامعتبر.", show_alert=True)
    if not (1 <= jm <= 12):
        return await callback.answer("ماه نامعتبر است.", show_alert=True)
    info = cal_today_info()
    today_text = f"🗓 امروز: <b>{info['weekday']} {info['jd']} {info['month_name']} {info['jy']}</b>"
    try:
        await callback.message.edit_text(
            calendar_month_text(jy, jm) + "\n\n" + today_text,
            parse_mode="HTML",
            reply_markup=calendar_month_keyboard(jy, jm),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@dp.callback_query(F.data.startswith("calocc:"))
async def calendar_occasions_callback(callback: types.CallbackQuery):
    try:
        _, jy, jm = callback.data.split(":")
        jy, jm = int(jy), int(jm)
    except (IndexError, ValueError):
        return await callback.answer("درخواست نامعتبر.", show_alert=True)
    items = cal_month_occasions(jy, jm)
    lines = [f"🗓 <b>مناسبت‌های {JALALI_MONTHS[jm-1]} {jy}</b>", ""]
    if not items:
        lines.append("در این ماه مناسبت خاصی ثبت نشده.")
    for item in items:
        for occ in item["occasions"]:
            lines.append(f"• <b>{item['day']}</b> {html.escape(occ)}")
    try:
        await callback.message.edit_text(
            "\n".join(lines)[:4000],
            parse_mode="HTML",
            reply_markup=calendar_month_keyboard(jy, jm),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# =============== منوی اطلاعات ===============

info_sessions: set[int] = set()


@dp.message(F.chat.type == "private", F.text.regexp(r"^📅 تقویم شمسی$"))
async def calendar_menu_entry(message: types.Message):
    await calendar_command(message)


@dp.message(F.chat.type == "private", F.text.regexp(r"^🌍 دانش و اطلاعات$"))
async def info_menu_entry(message: types.Message):
    await message.answer("🌍 <b>دانش و اطلاعات</b>\nهر چی می‌خوای بدونی، انتخاب کن:", parse_mode="HTML", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^☀️ آب‌وهوا$"))
async def info_weather_prompt(message: types.Message):
    info_sessions.add(message.from_user.id)
    await message.answer("☀️ نام شهر را بفرست (فارسی یا انگلیسی). /cancel", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^💱 نرخ ارز$"))
async def info_rate_prompt(message: types.Message):
    await message.answer("💱 فرمت: <code>usd eur</code> یا <code>دلار تومان</code> را بفرست.", parse_mode="HTML", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^🪙 قیمت کریپتو$"))
async def info_crypto_prompt(message: types.Message):
    await message.answer("🪙 نماد ارز دیجیتال را بفرست؛ مثلاً <code>btc</code> یا <code>بیت‌کوین</code>.", parse_mode="HTML", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^🕐 ساعت جهانی$"))
async def info_time_prompt(message: types.Message):
    await message.answer("🕐 نام شهر را بفرست؛ مثلاً «تهران» یا «لندن». /cancel", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^📚 خلاصه ویکی‌پدیا$"))
async def info_wiki_prompt(message: types.Message):
    info_sessions.add(message.from_user.id)
    await message.answer("📚 موضوع را بفرست؛ مثلاً «نوروز». /cancel", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^📖 جستجوی کتاب$"))
async def info_book_prompt(message: types.Message):
    info_sessions.add(message.from_user.id)
    await message.answer("📖 نام کتاب را بفرست؛ مثلاً «بوف کور». /cancel", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^🌍 اطلاعات کشورها$"))
async def info_country_prompt(message: types.Message):
    info_sessions.add(message.from_user.id)
    await message.answer("🌍 نام کشور را بفرست؛ مثلاً «ایران» یا «آلمان». /cancel", reply_markup=info_reply_menu())


@dp.message(F.chat.type == "private", F.text.regexp(r"^🧠 کوئیز جهانی$"))
async def info_quiz_prompt(message: types.Message):
    await quiz_command(message)


@dp.message(F.chat.type == "private", F.text.regexp(r"^🔐 بررسی امنیت رمز$"))
async def info_checkpass_prompt(message: types.Message):
    await message.answer("🔐 رمز را بفرست تا بررسی کنم. (فقط هش بررسی می‌شود — رمز کامل ذخیره/ارسال نمی‌شود) /cancel", reply_markup=info_reply_menu())


@dp.message(Command("ping"))
async def ping_command(message: types.Message):
    await message.answer("✅ ربات آنلاین است!")

@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ دسترسی ندارید!")
    await message.answer("⚙️ پنل مدیریت پایین چت باز شد:", reply_markup=admin_reply_menu())


@dp.message(Command("channels"))
async def channels_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ دسترسی ندارید!")
    await message.answer("📣 مدیریت کانال‌های اجباری:", reply_markup=required_channels_admin_menu())


@dp.message(Command("repost"))
async def repost_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ دسترسی ندارید!")
    await show_repost_start(message, message.from_user.id)


@dp.message(Command("quickpost"))
async def quickpost_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ دسترسی ندارید!")
    if repost_batches.get(message.from_user.id, {}).get("items"):
        return await message.answer("اول گروه بازنشر باز رو منتشر یا کنسل کن.")
    cancel_album_buffers(message.from_user.id)
    instant_repost_sessions[message.from_user.id] = []
    await message.answer("⚡ انتشار فوری فعال شد؛ هر پست را بفرستی مستقیم در کانال منتشر می‌شود.", reply_markup=instant_repost_keyboard())


@dp.message(Command("configs"))
async def configs_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ دسترسی ندارید!")
    counts = {
        "proxy": await configs_col.count_documents({"category": "proxy"}),
        "v2ray": await configs_col.count_documents({"category": "v2ray"}),
        "npv": await configs_col.count_documents({"category": "npv"}),
    }
    await message.answer("📋 مدیریت پروکسی و کانفیگ‌ها:", reply_markup=config_manage_categories_menu(counts))


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def moderate_group_text(message: types.Message):
    await managed_chats_col.update_one(
        {"_id": message.chat.id},
        {"$set": {"title": message.chat.title, "username": message.chat.username, "type": getattr(message.chat.type, "value", str(message.chat.type)), "updated_at": datetime.now(timezone.utc)}, "$setOnInsert": {"status": "active", "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    if not message.from_user or message.from_user.is_bot or (message.text or "").startswith("/"):
        return
    if await is_chat_admin(message.chat.id, message.from_user.id):
        return
    settings = await get_group_settings(message.chat.id)
    if message.from_user.id in settings.get("trusted_users", []): return
    reason = None
    now = time.monotonic(); key = (message.chat.id, message.from_user.id)
    recent = [stamp for stamp in group_message_times.get(key, []) if now - stamp < 8]
    recent.append(now); group_message_times[key] = recent
    if settings["anti_spam"] and len(recent) >= 6:
        reason = "ارسال اسپم و پیام‌های پشت‌سرهم"; group_message_times[key] = []
    elif settings["block_forwards"] and message.forward_origin:
        reason = "ارسال پیام فورواردشده در حالت قفل فوروارد"
    elif settings["block_links"] and re.search(r"(?:https?://|t\.me/|telegram\.me/|www\.)", message.text or "", flags=re.I):
        urls=re.findall(r"(?:https?://|www\.)[^\s]+",message.text or "",flags=re.I);allowed=settings.get("allowed_domains",[])
        if not urls or any(not is_allowed_url(url, allowed) for url in urls): reason = "ارسال لینک در حالت قفل لینک"
    else:
        normalized = normalize_chat_text(message.text or "")
        custom = [word for word in settings.get("blocked_words", []) if word and word in normalized]
        profanity = detect_profanity(message.text or "") if settings["anti_profanity"] else set()
        if profanity or custom:
            reason = "استفاده از الفاظ یا عبارت ممنوع"
    if not reason:
        return
    try:
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    await issue_group_warning(message, reason, automatic=True)


PROMPT_REFRESH_DAYS = 7
PROMPT_CATALOG_VERSION = "2026.08.400"
PROMPT_CATALOG = [
    {
        "id": "cinematic_portrait",
        "category": "image",
        "title": "🎨 پرتره سینمایی شبانه",
        "kind": "تصویر",
        "trend": 100,
        "prompt": "Create a photorealistic cinematic portrait at night, soft warm key light, cool rim light, deep shadows, natural skin texture, realistic hair and fabric, 50mm lens, shallow depth of field, documentary photography, high detail, natural color grading, no text, no watermark. If a reference image is attached, preserve the person's actual gender, identity, facial structure, age range, hairstyle and skin tone; do not change the person into another gender or another person.",
        "sample": "نمونه تصویر: پرتره‌ای واقع‌گرایانه در شب با نور گرم روی صورت و پس‌زمینهٔ جنگلی تاریک.",
    },
    {
        "id": "black_white_emotion",
        "category": "image",
        "title": "🖤 سیاه‌وسفید احساسی",
        "kind": "تصویر",
        "trend": 98,
        "prompt": "Convert the reference portrait into a timeless black-and-white cinematic photograph, high contrast, soft film grain, deep shadows, expressive eyes, gentle side light, authentic documentary mood, preserve identity and composition, no color, no text, no watermark.",
        "sample": "نمونه تصویر: ادیت سیاه‌وسفید کنتراست‌بالا با حس مستند و سینمایی.",
    },
    {
        "id": "old_photo_restore",
        "category": "image",
        "title": "🧼 ترمیم عکس قدیمی",
        "kind": "تصویر",
        "trend": 92,
        "prompt": "Restore this old photograph with natural realistic detail, remove scratches and noise, recover facial details, correct exposure and colors, preserve the original identity, pose and background, avoid plastic skin and over-sharpening.",
        "sample": "نمونه تصویر: عکس قدیمی تمیزتر و واضح‌تر، بدون تغییر چهره.",
    },
    {
        "id": "editorial_fashion",
        "category": "image",
        "title": "👕 فشن ادیتوریال",
        "kind": "تصویر",
        "trend": 90,
        "prompt": "Create a premium editorial fashion portrait, natural confident pose, soft studio lighting, muted luxury color palette, realistic fabric folds, professional magazine composition, 85mm lens, clean background, high-end photography, no logos or text.",
        "sample": "نمونه تصویر: عکس مجله‌ای با نور استودیویی و لباس با جزئیات واقعی.",
    },
    {
        "id": "product_ad",
        "category": "image",
        "title": "🛍 تبلیغ محصول",
        "kind": "تصویر",
        "trend": 88,
        "prompt": "Create a polished product advertisement for the described object, premium studio lighting, realistic materials, elegant minimal background, clear focal point, commercial photography, balanced negative space for a headline, no fake brand logo and no extra text.",
        "sample": "نمونه تصویر: شات تبلیغاتی تمیز برای محصول با فضای خالی مناسب تیتر.",
    },
    {
        "id": "remove_background",
        "category": "edit",
        "title": "✂️ حذف و تعویض پس‌زمینه",
        "kind": "تصویر",
        "trend": 86,
        "prompt": "Remove the background cleanly around the subject, preserve hair strands, hands and clothing edges, then place the subject in a realistic cinematic environment with matching light direction, shadows and perspective. Do not change the face or identity.",
        "sample": "نمونه تصویر: سوژه جداشده با لبه‌های طبیعی مو و نور هماهنگ با محیط جدید.",
    },
    {
        "id": "viral_caption",
        "category": "content",
        "title": "📣 کپشن وایرال",
        "kind": "متن",
        "trend": 94,
        "prompt": "برای موضوع زیر سه کپشن فارسی محاوره‌ای بنویس: یکی احساسی، یکی کوتاه و وایرال، یکی طنز. هرکدام حداکثر دو جمله باشد و در پایان ۳ تا ۵ هشتگ طبیعی و مرتبط بده. ادعای ساختگی نساز.",
        "sample": "نمونه خروجی: سه کپشن متفاوت با لحن احساسی، وایرال و طنز به‌همراه هشتگ.",
    },
    {
        "id": "reels_script",
        "category": "content",
        "title": "🎬 سناریوی ریلز",
        "kind": "متن",
        "trend": 91,
        "prompt": "برای یک ویدئوی کوتاه دربارهٔ موضوع زیر سناریوی ۳۰ ثانیه‌ای بساز: هوک ۳ ثانیه‌ای، متن روی تصویر، دیالوگ/نریشن، پیشنهاد کات‌ها و CTA نهایی. لحن فارسی طبیعی و قابل اجرا باشد.",
        "sample": "نمونه خروجی: سناریوی زمان‌بندی‌شده با هوک، کات، نریشن و دعوت به اقدام.",
    },
    {
        "id": "code_debug",
        "category": "utility",
        "title": "💻 رفع خطای کد",
        "kind": "متن",
        "trend": 84,
        "prompt": "این کد را مثل یک مهندس ارشد بررسی کن: خطاهای قطعی، ریسک‌های امنیتی، مشکل عملکرد و نسخهٔ اصلاح‌شدهٔ قابل اجرا را جداگانه بنویس. اگر اطلاعات کافی نیست، فقط سؤال‌های ضروری را بپرس.",
        "sample": "نمونه خروجی: تشخیص خطا، علت، پچ اصلاحی و تست پیشنهادی.",
    },
    {
        "id": "smart_summary",
        "category": "utility",
        "title": "🧠 خلاصهٔ هوشمند",
        "kind": "متن",
        "trend": 82,
        "prompt": "متن زیر را در ۵ bullet کوتاه خلاصه کن؛ سپس نتیجهٔ اصلی، نکات قابل اقدام و ۳ کلیدواژه را بنویس. هیچ ادعای تازه‌ای به متن اضافه نکن.",
        "sample": "نمونه خروجی: خلاصه، نتیجه، اقدامات بعدی و کلیدواژه‌ها.",
    },
    {
        "id": "trend_storyboard",
        "category": "trending",
        "title": "🔥 استوری‌بورد ترند",
        "kind": "متن",
        "trend": 99,
        "prompt": "برای یک ویدئوی عمودی ترند، ۶ شات کوتاه با قاب‌بندی، حرکت دوربین، نور، متن روی تصویر و زمان هر شات پیشنهاد بده. خروجی را طوری بنویس که مستقیماً به ابزار تولید ویدئو داده شود.",
        "sample": "نمونه خروجی: شش شات آماده با زمان، حرکت دوربین و متن روی تصویر.",
    },
]

# ۴۰۰ پرامپت ساختاریافتهٔ جدید؛ کاتالوگ قدیمی عمداً حفظ شده است.
PROMPT_CATALOG.extend(EXTENDED_PROMPTS)
PROMPT_NEW_COUNT = EXTENDED_PROMPT_COUNT
PROMPTS_PER_PAGE = 8
PROMPT_CATEGORIES = {"image", "edit", "content", "utility", "trending"}


def _prompt_cycle() -> int:
    return int(time.time() // (PROMPT_REFRESH_DAYS * 86400))


def _prompt_items(category: str) -> list[dict]:
    """Return one category in deterministic weekly order.

    ``trending`` is intentionally a real category, not every item with a high
    score.  That keeps the ۴۰۰-entry catalog usable and lets the weekly trend
    collection remain a focused shortlist.
    """
    if category not in PROMPT_CATEGORIES:
        return []
    if category == "trending":
        items = [
            item for item in PROMPT_CATALOG
            if item["category"] == "trending" and item.get("trend", 0) >= 90
        ]
    else:
        items = [item for item in PROMPT_CATALOG if item["category"] == category]
    cycle = _prompt_cycle()
    return sorted(
        items,
        key=lambda item: hashlib.sha256(f"{cycle}:{item['id']}".encode()).hexdigest(),
    )


def _prompt_by_id(prompt_id: str) -> dict | None:
    return next((item for item in PROMPT_CATALOG if item["id"] == prompt_id), None)


PROMPT_CATEGORY_LABELS = {
    "image": "🎨 تصویرسازی",
    "edit": "🖼 ویرایش عکس",
    "content": "📣 تولید محتوا",
    "utility": "🧰 کاربردی",
    "trending": "🔥 پرامپت‌های ترند",
}


def _prompt_page_count(category: str) -> int:
    total = len(_prompt_items(category))
    return max(1, (total + PROMPTS_PER_PAGE - 1) // PROMPTS_PER_PAGE)


def _clamp_prompt_page(category: str, page: int) -> int:
    return max(0, min(page, _prompt_page_count(category) - 1))


def _prompt_page_keyboard(category: str, page: int) -> InlineKeyboardMarkup:
    """Build a Telegram-safe page with at most eight prompt buttons."""
    items = _prompt_items(category)
    total_pages = max(1, (len(items) + PROMPTS_PER_PAGE - 1) // PROMPTS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * PROMPTS_PER_PAGE
    visible = items[start:start + PROMPTS_PER_PAGE]
    rows: list[list[InlineKeyboardButton]] = []
    for offset in range(0, len(visible), 2):
        rows.append([
            InlineKeyboardButton(
                text=item["title"],
                callback_data=f"promptview:{item['id']}",
            )
            for item in visible[offset:offset + 2]
        ])

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️ صفحهٔ قبل",
                callback_data=f"promptpage:{category}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                text="⏭ صفحهٔ بعد",
                callback_data=f"promptpage:{category}:{page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="🔙 دسته‌ها", callback_data="prompts_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prompt_center_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 تصویرسازی", callback_data="promptcat:image"), InlineKeyboardButton(text="🖼 ویرایش عکس", callback_data="promptcat:edit")],
        [InlineKeyboardButton(text="📣 تولید محتوا", callback_data="promptcat:content"), InlineKeyboardButton(text="🧰 کاربردی", callback_data="promptcat:utility")],
        [InlineKeyboardButton(text="🔥 پرامپت‌های ترند", callback_data="promptcat:trending")],
        [InlineKeyboardButton(text="🆕 بروزرسانی هفتگی", callback_data="prompt_refresh")],
    ])


async def show_prompt_center(message: types.Message) -> None:
    await message.answer(
        "🧠 <b>کتابخانهٔ پرامپت‌های Ajorpareh</b>\n\n"
        "۴۰۰ پرامپت جدید کنار مجموعهٔ قبلی اضافه شده؛ اولویت با ساخت تصویر و ویرایش عکسه. "
        "برای هر مورد نمونهٔ خروجی، متن آماده و دکمهٔ کپی داری.\n\n"
        f"📚 مجموع فعلی: <b>{len(PROMPT_CATALOG)}</b> پرامپت\n"
        f"🔄 فهرست ترند هر {PROMPT_REFRESH_DAYS} روز دوباره مرتب و تازه می‌شود.",
        parse_mode="HTML", reply_markup=prompt_center_keyboard(),
    )


async def _edit_prompt_category(callback: types.CallbackQuery, category: str, page: int) -> bool:
    if category not in PROMPT_CATEGORIES:
        await callback.answer("دستهٔ پرامپت نامعتبر است.", show_alert=True)
        return False
    items = _prompt_items(category)
    if not items:
        await callback.answer("برای این دسته هنوز پرامپتی ثبت نشده.", show_alert=True)
        return False
    page = _clamp_prompt_page(category, page)
    total_pages = _prompt_page_count(category)
    label = PROMPT_CATEGORY_LABELS[category]
    await callback.message.edit_text(
        f"🧠 <b>{label}</b>\n\n"
        f"{len(items)} پرامپت آماده است · صفحهٔ {page + 1} از {total_pages}\n"
        "یکی را انتخاب کن:",
        parse_mode="HTML",
        reply_markup=_prompt_page_keyboard(category, page),
    )
    return True


@dp.callback_query(F.data.startswith("promptcat:"))
async def prompt_category_callback(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    category = parts[1] if len(parts) > 1 else ""
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    if await _edit_prompt_category(callback, category, page):
        await callback.answer()


@dp.callback_query(F.data.startswith("promptpage:"))
async def prompt_page_callback(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    category = parts[1] if len(parts) > 1 else ""
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    if await _edit_prompt_category(callback, category, page):
        await callback.answer()


@dp.callback_query(F.data == "prompts_open")
async def prompts_open_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🧠 <b>دستهٔ پرامپت‌ها</b>\n\nتصویر، ویرایش، محتوا یا ترند را انتخاب کن.",
        parse_mode="HTML", reply_markup=prompt_center_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "prompt_refresh")
async def prompt_refresh_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"🆕 <b>پرامپت‌های چرخهٔ {_prompt_cycle()}</b>\n\n"
        f"کاتالوگ شامل {len(PROMPT_CATALOG)} مورد است و {PROMPT_NEW_COUNT} مورد جدید دارد. "
        "برای دیدن ترندهای تازه، روی «پرامپت‌های ترند» بزن.",
        parse_mode="HTML", reply_markup=prompt_center_keyboard(),
    )
    await callback.answer("لیست هفتگی بروزرسانی شد ✅")


async def _edit_prompt_detail(callback: types.CallbackQuery, item: dict) -> None:
    items = _prompt_items(item["category"])
    try:
        index = next(i for i, candidate in enumerate(items) if candidate["id"] == item["id"])
    except StopIteration:
        index = 0
    body = (
        f"🧠 <b>{html.escape(item['title'])}</b>\n"
        f"🏷 نوع: {html.escape(item['kind'])}\n"
        f"🔢 مورد {index + 1} از {len(items)}\n\n"
        f"📝 <b>پرامپت آماده:</b>\n<pre>{html.escape(item['prompt'])}</pre>\n\n"
        f"🧪 <b>نمونه کار:</b>\n{html.escape(item['sample'])}"
    )
    rows = [[InlineKeyboardButton(text="📋 ارسال نسخهٔ قابل‌کپی", callback_data=f"promptcopy:{item['id']}")]]
    if item["category"] in {"image", "edit"}:
        rows.append([
            InlineKeyboardButton(text="🖼 ساخت تصویر با این پرامپت", callback_data=f"promptgen:{item['id']}"),
            InlineKeyboardButton(text="🎨 آماده‌سازی برای ویرایش عکس", callback_data=f"promptuse:{item['id']}"),
        ])
    if len(items) > 1:
        rows.append([
            InlineKeyboardButton(
                text="⏮ پرامپت قبلی",
                callback_data=f"promptprev:{item['category']}:{index}",
            ),
            InlineKeyboardButton(
                text="⏭ پرامپت بعدی",
                callback_data=f"promptnext:{item['category']}:{index}",
            ),
        ])
    rows.append([
        InlineKeyboardButton(
            text="🔙 برگشت به دسته",
            callback_data=f"promptpage:{item['category']}:{index // PROMPTS_PER_PAGE}",
        )
    ])
    await callback.message.edit_text(
        body,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("promptview:"))
async def prompt_view_callback(callback: types.CallbackQuery):
    item = _prompt_by_id(callback.data.split(":", 1)[1])
    if not item:
        return await callback.answer("این پرامپت دیگر موجود نیست.", show_alert=True)
    await _edit_prompt_detail(callback, item)
    await callback.answer()


async def _navigate_prompt_detail(callback: types.CallbackQuery, direction: int) -> None:
    parts = callback.data.split(":")
    category = parts[1] if len(parts) > 1 else ""
    try:
        index = int(parts[2]) if len(parts) > 2 else -1
    except ValueError:
        index = -1
    items = _prompt_items(category)
    if not items or not 0 <= index < len(items):
        await callback.answer("این مسیر پرامپت معتبر نیست.", show_alert=True)
        return
    target = items[(index + direction) % len(items)]
    await _edit_prompt_detail(callback, target)
    await callback.answer()


@dp.callback_query(F.data.startswith("promptnext:"))
async def prompt_next_callback(callback: types.CallbackQuery):
    await _navigate_prompt_detail(callback, 1)


@dp.callback_query(F.data.startswith("promptprev:"))
async def prompt_previous_callback(callback: types.CallbackQuery):
    await _navigate_prompt_detail(callback, -1)


@dp.callback_query(F.data.startswith("promptcopy:"))
async def prompt_copy_callback(callback: types.CallbackQuery):
    item = _prompt_by_id(callback.data.split(":", 1)[1])
    if not item:
        return await callback.answer("پرامپت پیدا نشد.", show_alert=True)
    await callback.message.answer(f"📋 <b>نسخهٔ قابل‌کپی:</b>\n\n<pre>{html.escape(item['prompt'])}</pre>", parse_mode="HTML")
    await callback.answer("ارسال شد ✅")


@dp.callback_query(F.data.startswith("promptgen:"))
async def prompt_generate_image_callback(callback: types.CallbackQuery):
    """ساخت مستقیم تصویر با پرامپت کتابخانه (بدون نیاز به کپی یا عکس مرجع)."""
    item = _prompt_by_id(callback.data.split(":", 1)[1])
    if not item:
        return await callback.answer("پرامپت پیدا نشد.", show_alert=True)
    user_id = callback.from_user.id
    prompt = str(item.get("prompt") or "").strip()
    if not prompt:
        return await callback.answer("این پرامپت متنی برای ساخت تصویر ندارد.", show_alert=True)
    profanity = detect_profanity(prompt)
    if profanity:
        return await issue_private_warning(callback.message, profanity)
    lock = ai_request_lock(user_id)
    if lock.locked():
        return await callback.answer("⏳ درخواست قبلیت هنوز در حال پردازشه؛ چند ثانیه صبر کن.", show_alert=True)
    await callback.answer("🎨 شروع ساخت تصویر...")
    ai_sessions.pop(user_id, None)
    prompt_image_sessions.pop(user_id, None)
    instant_repost_sessions.pop(user_id, None)
    repost_sessions.discard(user_id)
    async with lock:
        waiting = await callback.message.answer(
            f"🖼 <b>در حال ساخت تصویر با پرامپت:</b>\n<pre>{html.escape(prompt[:300])}</pre>",
            parse_mode="HTML",
        )
        await bot.send_chat_action(callback.message.chat.id, "upload_photo")
        result = await ai_service.generate_image(
            prompt,
            user_id=user_id,
            unlimited=is_admin(user_id),
        )
        try:
            await waiting.delete()
        except TelegramBadRequest:
            pass
        if not result.ok or not result.image:
            return await callback.message.answer(
                ai_error_text(result.reason, image=True), reply_markup=ai_reply_menu()
            )
        extension = "jpg" if "jpeg" in result.mime_type else "webp" if "webp" in result.mime_type else "png"
        upload = BufferedInputFile(result.image, filename=f"ajorpareh-prompt-{item['id']}.{extension}")
        caption = f"🖼 تصویر ساخته‌شده با پرامپت «{html.escape(item['title'])}»"
        if result.caption:
            caption += f"\n\n{result.caption[:800]}"
        if len(result.image) <= 9_500_000:
            await callback.message.answer_photo(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
        else:
            await callback.message.answer_document(upload, caption=caption[:1024], reply_markup=ai_reply_menu())
        await users_col.update_one(
            {"_id": user_id},
            {"$inc": {"ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        await log_activity(user_id, "ai_prompt_image", f"prompt={item['id']},provider={result.provider or 'none'}")


@dp.callback_query(F.data.startswith("promptuse:"))
async def prompt_use_callback(callback: types.CallbackQuery):
    item = _prompt_by_id(callback.data.split(":", 1)[1])
    if not item:
        return await callback.answer("پرامپت پیدا نشد.", show_alert=True)
    if item["category"] not in {"image", "edit"}:
        return await callback.answer("این پرامپت برای ساخت تصویر نیست.", show_alert=True)
    prompt_image_sessions[callback.from_user.id] = item["prompt"]
    ai_sessions.pop(callback.from_user.id, None)
    instant_repost_sessions.pop(callback.from_user.id, None)
    repost_sessions.discard(callback.from_user.id)
    await callback.message.answer(
        "🎨 پرامپت آماده شد. حالا عکس مرجعت رو بفرست؛ جنسیت، چهره، مدل مو و هویت عکس حفظ می‌شه.\n\n"
        f"<pre>{html.escape(item['prompt'])}</pre>\n\n"
        "اگر فقط متن می‌خوای، دکمهٔ «📋 ارسال نسخهٔ قابل‌کپی» رو بزن. /cancel",
        parse_mode="HTML", reply_markup=ai_reply_menu(),
    )
    await callback.answer("منتظر عکس مرجع هستم ✅")


KEYWORD_HELP_TEXT = (
    "🔑 <b>کلیدواژه‌های سریع ربات</b>\n\n"
    "• <code>پنل</code> یا <code>مدیریت</code> → پنل مدیریت (فقط مدیر)\n"
    "• <code>انتشار</code> یا <code>گزینه‌های انتشار</code> → ابزارهای انتشار (فقط مدیر)\n"
    "• <code>جوک</code>، <code>جوک بگو</code> یا <code>ربات جوک بگو</code> → جوک فوری\n"
    "• <code>دانلود</code> یا <code>مرکز دانلود</code> → مرکز دانلود و رسانه\n"
    "• <code>موسیقی</code> → جستجو، ترند و تشخیص آهنگ\n"
    "• <code>بازی</code> → منوی بازی‌ها\n"
    "• <code>پروفایل</code> → پروفایل و امتیازها\n"
    "• <code>کیف پول</code> یا <code>اعتبار</code> → موجودی و جوایز\n"
    "• <code>پروکسی</code> یا <code>کانفیگ</code> → دریافت پروکسی/کانفیگ\n"
    "• <code>کامنت</code> یا <code>کپی کامنت</code> → استخراج متن کامنت اینستاگرام\n"
    "• <code>راهنما</code>، <code>کمک</code> یا <code>دستورات</code> → راهنمای ربات\n\n"
    "کلیدواژه‌ها فقط وقتی پیام دقیقاً با یکی از عبارت‌های بالا برابر باشد فعال می‌شوند تا با چت معمولی و حالت هوش مصنوعی قاطی نشوند."
)


async def send_keyword_joke(message: types.Message) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="😂 یکی دیگه", callback_data="joke_again"),
        InlineKeyboardButton(text="✨ انگیزشی", callback_data="quote_again"),
    ]])
    await log_activity(message.from_user.id, "keyword_joke", "جوک")
    await message.answer(random.choice(JOKES), reply_markup=keyboard)


async def handle_keyword_command(message: types.Message) -> bool:
    """مسیرهای دقیق منویی؛ قبل از AI اجرا می‌شوند و substring نیستند."""
    key = normalize_chat_text(message.text or "")
    user_id = message.from_user.id
    if key in {"کلیدواژه", "کلیدواژه ها", "راهنمای کلیدواژه", "راهنمای دستورات", "دستورات"}:
        await message.answer(KEYWORD_HELP_TEXT, parse_mode="HTML")
        return True
    if key in {"پنل", "پنل مدیریت", "مدیریت"}:
        if is_admin(user_id):
            await message.answer("⚙️ پنل مدیریت پایین چت باز شد:", reply_markup=admin_reply_menu())
        else:
            await message.answer("⛔ این کلیدواژه فقط برای مدیر ربات فعال است.")
        return True
    if key in {"انتشار", "گزینه های انتشار", "گزینه های انتشار پست", "مدیریت انتشار"}:
        if is_admin(user_id):
            await message.answer("📢 ابزارهای انتشار:", reply_markup=admin_content_reply_menu())
        else:
            await message.answer("⛔ ابزارهای انتشار فقط برای مدیر ربات فعال است.")
        return True
    if key in {"جوک", "جوک بگو", "یه جوک", "یک جوک", "ربات جوک بگو", "منو بخندون"}:
        await send_keyword_joke(message)
        return True
    if key in {"دانلود", "مرکز دانلود", "مرکز رسانه", "دانلود رسانه"}:
        await message.answer("📥 مرکز دانلود و رسانه:", reply_markup=media_download_reply_menu())
        return True
    if key in {"پرامپت", "پرامپت ها", "کتابخانه پرامپت", "پرامپت های ترند"}:
        await show_prompt_center(message)
        return True
    if key in {"موسیقی", "آهنگ", "مرکز موسیقی"}:
        await message.answer("🎵 بخش موسیقی:", reply_markup=music_reply_menu())
        return True
    if key in {"بازی", "بازی ها", "مرکز بازی"}:
        await message.answer("🎮 منوی بازی‌ها:", reply_markup=games_reply_menu())
        return True
    if key in {"پروفایل", "پروفایل من"}:
        await profile_command(message)
        return True
    if key in {"کیف پول", "اعتبار", "موجودی"}:
        wallet = await wallet_snapshot(user_id)
        await message.answer(
            f"💰 موجودی تو: <b>{wallet['wallet_toman']:,} تومان</b>\n"
            f"🪙 سکه: {wallet['coins']:,}\n⚡ XP: {wallet['points']:,}",
            parse_mode="HTML", reply_markup=rewards_reply_menu(),
        )
        return True
    if key == "پروکسی":
        await run_callback_from_reply(message, "get_proxy", get_proxy_callback)
        return True
    if key == "کانفیگ":
        await run_callback_from_reply(message, "config_menu", config_menu_callback)
        return True
    if key in {"کامنت", "کپی کامنت", "کامنت اینستاگرام", "کپی کامنت اینستاگرام"}:
        await start_instagram_comment_session(message)
        return True
    if key in {"راهنما", "کمک", "راهنمای ربات"}:
        await help_command(message)
        return True
    if key in {"منو", "menu", "منوی اصلی"}:
        await handle_menu_trigger(message)
        return True
    return False


@dp.message(F.chat.type == "private", F.text)
async def handle_text(message: types.Message):
    text = (message.text or "").strip()
    if text.startswith("/"):
        return

    user_id = message.from_user.id
    lowered = normalize_chat_text(text)

    # سشن‌های اصلاح/افزودن باید قبل از کلیدواژه و AI اجرا شوند؛
    # حتی اگر متن نسخهٔ جدید شبیه یکی از دکمه‌های منو باشد.
    if is_admin(user_id) and user_id in repost_edit_sessions:
        return await replace_repost_item(message)
    if is_admin(user_id) and user_id in scheduled_add_sessions:
        return await append_scheduled_payload(message)
    if is_admin(user_id) and user_id in scheduled_edit_sessions:
        return await replace_scheduled_payload(message)

    # پاک‌سازی خودکار پیام دکمه‌های ReplyKeyboard — چت شلوغ نشه
    if text in REPLY_BUTTON_LABELS:
        asyncio.create_task(_auto_delete_button_msg(message, 0.3))

    if await pause_publication_for_control(message):
        return await handle_text(message)

    # کلیدواژه‌های دقیق باید قبل از AI و سشن‌های عادی مسیر خودشان را بگیرند.
    if await handle_keyword_command(message):
        return

    if user_id in qr_sessions:
        qr_sessions.discard(user_id)
        await send_qr_result(message, text)
        return

    if user_id in sticker_sessions:
        return await message.answer("🪄 منتظر عکس هستم؛ یک تصویر بفرست یا /cancel رو بزن.")
    if user_id in gif_sessions:
        return await message.answer("🎞 منتظر عکس، ویدئو یا GIF هستم؛ فایل رو بفرست یا /cancel رو بزن.")

    if user_id in promo_sticker_sessions:
        media_name = "استیکر" if promo_sticker_sessions[user_id]["rewards"].get("sticker") else "گیف"
        return await message.answer(f"🎁 منتظر {media_name} هدیه هستم؛ فایل رو بفرست یا /cancel بزن.")

    if user_id in music_search_sessions:
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات", "↩️ مرکز دانلود و آپلود"}:
            music_search_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            if text == "↩️ مرکز دانلود و آپلود":
                return await message.answer("📥 مرکز رسانه:", reply_markup=media_download_reply_menu())
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        if text == "/cancel":
            music_search_sessions.discard(user_id)
            return await message.answer("لغو شد.", reply_markup=music_reply_menu())
        music_search_sessions.discard(user_id)
        await message.answer(f"🔎 در حال جستجوی «{html.escape(text[:80])}»…", parse_mode="HTML")
        return await present_music_results(user_id, text)

    if user_id in instagram_comment_sessions:
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات", "↩️ مرکز دانلود و آپلود"}:
            instagram_comment_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            if text == "↩️ مرکز دانلود و آپلود":
                return await message.answer("📥 مرکز رسانه:", reply_markup=media_download_reply_menu())
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        return await copy_instagram_comment_from_message(message)

    if user_id in prompt_image_sessions:
        return await message.answer(
            "🎨 این پرامپت برای عکس مرجعه؛ لطفاً عکس رو بفرست یا /cancel بزن.",
            reply_markup=ai_reply_menu(),
        )

    if user_id in media_request_sessions:
        mode = media_request_sessions[user_id]
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات"}:
            media_request_sessions.pop(user_id, None)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        if mode == "inspect":
            media_request_sessions.pop(user_id, None)
            return await send_link_inspection(message, text)
        media_request_sessions.pop(user_id, None)
        return await queue_media_from_message(message, mode)

    if user_id in short_sessions:
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات"}:
            short_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        short_sessions.discard(user_id)
        return await short_command(message)

    if user_id in summarize_sessions:
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات"}:
            summarize_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        summarize_sessions.discard(user_id)
        return await run_summarize(message, text)

    if user_id in tts_sessions:
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات"}:
            tts_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        tts_sessions.discard(user_id)
        return await run_tts(message, text)

    if user_id in info_sessions:
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات"}:
            info_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        info_sessions.discard(user_id)
        # نرخ ارز: دو کلمه
        parts = text.split()
        if len(parts) == 2 and not text.startswith(("📚", "☀️", "📖", "🌍", "🕐")):
            try:
                r = await exchange_rate(parts[0], parts[1])
                if r["to"] == "IRR":
                    return await message.answer(f"💱 <b>هر {r['from']} = {int(r['rate']):,} ریال</b>\n≈ {int(r['rate'] / 1000):,} تومان", parse_mode="HTML", reply_markup=info_reply_menu())
                return await message.answer(f"💱 <b>1 {r['from']} = {r['rate']:.4f} {r['to']}</b>", parse_mode="HTML", reply_markup=info_reply_menu())
            except MediaServiceError:
                pass
        # کریپتو: یک کلمه معروف
        if len(parts) == 1:
            try:
                items = await crypto_price(parts)
                if items:
                    item = items[0]
                    change = item.get("change_24h")
                    change_text = ""
                    if change is not None:
                        arrow = "📈" if change >= 0 else "📉"
                        change_text = f" · {arrow} {change:+.1f}٪"
                    return await message.answer(
                        f"🪙 <b>{item['name']}</b> ({item['symbol']})\n💵 <b>${item['price_usd']:,.2f}</b>{change_text}",
                        parse_mode="HTML", reply_markup=info_reply_menu(),
                    )
            except MediaServiceError:
                pass
        # تشخیص نوع درخواست از روی منو
        if text in {"☀️ آب‌وهوا", "📚 خلاصه ویکی‌پدیا", "📖 جستجوی کتاب", "🌍 اطلاعات کشورها", "🕐 ساعت جهانی"}:
            info_sessions.add(user_id)
            return await message.answer("❓ چی؟ یک پیام متنی بفرست.", reply_markup=info_reply_menu())
        # پیش‌فرض: جستجو در همه ابزارها
        wait = await message.answer(f"🌍 در حال جستجوی «{html.escape(text[:60])}»…", parse_mode="HTML")
        # تلاش هوش مصنوعی برای فهمیدن منظور + نتایج ابزارها
        results = []
        try:
            w = await weather(text)
            results.append(f"{w['icon']} آب‌وهوای {w['city']}: <b>{w['temp']}°</b> · {w['label']}")
        except Exception:
            pass
        try:
            wiki = await wiki_summary(text, "fa")
            results.append(f"📚 {wiki['title']}: {html.escape((wiki.get('extract') or '')[:160])}")
        except Exception:
            pass
        try:
            co = await country_info(text)
            results.append(f"{co['flag']} {co['name']}: {html.escape((co.get('extract') or '')[:160])}")
        except Exception:
            pass
        if not results:
            try: await wait.edit_text("❌ نتیجه‌ای پیدا نشد؛ از منوی «🌍 دانش و اطلاعات» گزینه دقیق را انتخاب کن.")
            except TelegramBadRequest: pass
            return
        try:
            await wait.edit_text("\n\n".join(results), parse_mode="HTML")
        except TelegramBadRequest:
            await message.answer("\n\n".join(results), parse_mode="HTML", reply_markup=info_reply_menu())
        return

    if user_id in reminder_sessions:
        if text in {"🏠 منوی اصلی", "↩️ ابزارهای ربات"}:
            reminder_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
        try:
            repeat, scheduled_at, reminder_text = parse_recurring_input(text)
            item = await create_user_reminder(user_id, reminder_text, scheduled_at, "bot", repeat)
        except ValueError as exc:
            return await message.answer(
                f"❌ {exc}\nدوباره بفرست یا /cancel بزن.\nنمونه: <code>فردا 09:00 | تماس با علی</code>",
                parse_mode="HTML",
            )
        reminder_sessions.discard(user_id)
        return await message.answer(
            f"✅ یادآور ثبت شد.\n🕒 {format_tehran_datetime(item['scheduled_at'])}\n📝 {html.escape(item['text'])}",
            parse_mode="HTML",
            reply_markup=tools_reply_menu(),
        )

    if user_id in gift_redeem_sessions:
        if text == "🏠 منوی اصلی":
            gift_redeem_sessions.discard(user_id)
            return await handle_menu_trigger(message)
        gift_redeem_sessions.discard(user_id)
        await ensure_user(user_id, message.from_user.full_name, username=message.from_user.username)
        result = await redeem_promo_code(user_id, text)
        return await send_promo_redemption_result(message, result)

    if user_id in service_shop_setting_sessions and is_owner(user_id):
        action = service_shop_setting_sessions[user_id]
        try:
            if action == "offer":
                parts = [part.strip() for part in normalize_digits(text).split("|")]
                if len(parts) != 3:
                    raise ValueError("فرمت آفر باید درصد | عنوان | ساعت باشد")
                percent, hours = int(parts[0]), int(parts[2])
                if not (1 <= percent <= 90) or not (1 <= hours <= 24 * 365):
                    raise ValueError("درصد باید ۱ تا ۹۰ و مدت حداقل یک ساعت باشد")
                service_shop_settings.update({
                    "offer_active": True, "offer_percent": percent,
                    "offer_title": clean_profile_value(parts[1], 100) or "آفر ویژه",
                    "offer_expires_at": datetime.now(timezone.utc) + timedelta(hours=hours),
                })
            elif action == "card":
                parts = [part.strip() for part in normalize_digits(text).split("|", 1)]
                card = re.sub(r"\D", "", parts[0])
                if len(parts) != 2 or not is_valid_card_number(card) or len(parts[1]) < 3:
                    raise ValueError("شماره کارت معتبر و نام صاحب کارت لازم است")
                service_shop_settings["card_number"] = card
                service_shop_settings["card_holder"] = clean_profile_value(parts[1], 80)
            elif action == "note":
                note = clean_profile_value(text, 300)
                if len(note) < 5: raise ValueError("متن راهنما خیلی کوتاه است")
                service_shop_settings["payment_note"] = note
            else:
                raise ValueError("تنظیم نامعتبر است")
        except ValueError as exc:
            return await message.answer(f"❌ {exc}\nدوباره بفرست یا /cancel بزن.")
        service_shop_setting_sessions.pop(user_id, None)
        await settings_col.update_one({"_id": "service_shop"}, {"$set": dict(service_shop_settings)}, upsert=True)
        return await message.answer("✅ تنظیم فروشگاه ذخیره شد.", reply_markup=admin_finance_reply_menu())

    if user_id in service_delivery_sessions and is_admin(user_id):
        order_id = service_delivery_sessions.pop(user_id)
        service = await complete_service_delivery(user_id, order_id, "text", text[:3000])
        return await message.answer("✅ سرویس برای کاربر تحویل شد." if service else "❌ سفارش دیگر آماده تحویل نیست.", reply_markup=admin_finance_reply_menu())

    if user_id in reschedule_sessions and is_admin(user_id):
        try: scheduled_at=parse_schedule_time(text)
        except (ValueError,OverflowError) as exc:return await message.answer(f"❌ {exc}")
        job_id=reschedule_sessions.pop(user_id);await scheduled_posts_col.update_one({"_id":job_id,"status":{"$in":["pending","failed"]}},{"$set":{"scheduled_at":scheduled_at,"status":"pending"}});return await message.answer(f"✅ زمان جدید: {format_tehran_datetime(scheduled_at)}")

    if user_id in raffle_create_sessions and is_admin(user_id):
        parts=[part.strip() for part in text.split("|")]
        if len(parts)!=4:return await message.answer("فرمت: عنوان | هزینه | ساعت | سقف هر کاربر")
        try:cost,hours,max_entries=map(int,parts[1:])
        except ValueError:return await message.answer("مقادیر عددی نامعتبر است.")
        if min(cost,hours,max_entries)<=0:return await message.answer("مقادیر باید مثبت باشند.")
        raffle_create_sessions.discard(user_id);await raffles_col.insert_one({"title":parts[0][:80],"cost":cost,"max_entries_per_user":max_entries,"status":"active","entries":0,"pool":0,"ends_at":datetime.now(timezone.utc)+timedelta(hours=hours),"created_by":user_id,"created_at":datetime.now(timezone.utc)});return await message.answer("✅ قرعه‌کشی ساخته شد.")

    if user_id in prediction_create_sessions and is_admin(user_id):
        parts=[part.strip() for part in text.split("|")]
        if len(parts)!=3:return await message.answer("فرمت: سؤال | گزینه۱,گزینه۲ | ساعت")
        options=[x.strip() for x in parts[1].split(",") if x.strip()][:4]
        try:hours=int(parts[2])
        except ValueError:return await message.answer("ساعت نامعتبر است.")
        if len(options)<2 or hours<=0:return await message.answer("حداقل دو گزینه و مدت مثبت لازم است.")
        prediction_create_sessions.discard(user_id);await predictions_col.insert_one({"question":parts[0][:180],"options":options,"status":"active","pool":0,"option_pools":{},"ends_at":datetime.now(timezone.utc)+timedelta(hours=hours),"created_by":user_id,"created_at":datetime.now(timezone.utc)});return await message.answer("✅ پیش‌بینی ترند ساخته شد.")

    if user_id in promo_create_sessions and is_admin(user_id):
        parts = [part.strip() for part in text.split("|")]
        if len(parts) != 4:
            return await message.answer("فرمت: CODE | پاداش‌ها | سقف استفاده | اعتبار روز")
        code = re.sub(r"[^A-Z0-9_]", "", parts[0].upper())[:20]
        try:
            rewards = parse_promo_rewards(parts[1])
            max_uses, days = int(normalize_digits(parts[2])), int(normalize_digits(parts[3]))
        except ValueError as exc:
            return await message.answer(f"❌ {exc}")
        if not re.fullmatch(r"[A-Z0-9_]{4,20}", code) or not (1 <= max_uses <= 1_000_000) or not (1 <= days <= 3650):
            return await message.answer("کد، سقف استفاده یا مدت اعتبار نامعتبر است.")
        if await promo_codes_col.find_one({"_id": code}):
            return await message.answer("این نام کد قبلاً استفاده شده؛ برای جلوگیری از پرداخت تکراری یک کد تازه انتخاب کن.")
        config = {"code": code, "rewards": rewards, "max_uses": max_uses, "days": days, "created_by": user_id}
        promo_create_sessions.discard(user_id)
        if rewards.get("sticker") or rewards.get("gif"):
            promo_sticker_sessions[user_id] = config
            media_name = "استیکر" if rewards.get("sticker") else "گیف"
            return await message.answer(f"✅ مشخصات ذخیره شد. حالا {media_name} هدیه رو بفرست. /cancel")
        item = await save_promo_code(config)
        return await message.answer(
            f"✅ کد <code>{code}</code> ساخته شد.\n🎁 {html.escape(promo_reward_summary(item))}\nسقف: {max_uses} · اعتبار: {days} روز",
            parse_mode="HTML",
        )

    if user_id in mission_create_sessions and is_admin(user_id):
        parts = [part.strip() for part in text.split("|")]
        allowed_types = set(MISSION_FIELD_MAP)
        if len(parts) not in {4, 5} or parts[1] not in allowed_types:
            return await message.answer("فرمت یا نوع مأموریت نامعتبر است.")
        try:
            target, points = int(parts[2]), int(parts[3])
            coins = int(parts[4]) if len(parts) == 5 else 0
        except ValueError:
            return await message.answer("هدف، XP و سکه باید عدد باشند.")
        if target <= 0 or points < 0 or coins < 0 or target > 1_000_000:
            return await message.answer("مقادیر مأموریت خارج از محدوده است.")
        mission_create_sessions.discard(user_id)
        await missions_col.insert_one({
            "title": parts[0][:80],
            "description": "مأموریت سفارشی مدیریت",
            "type": parts[1],
            "target": target,
            "points": points,
            "coins": coins,
            "active": True,
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc),
        })
        return await message.answer("✅ مأموریت ساخته شد.")

    if user_id in template_create_sessions and is_admin(user_id):
        parts = [part.strip() for part in text.split("|", 1)]
        if len(parts) != 2 or not all(parts): return await message.answer("فرمت: نام قالب | متن قالب")
        template_create_sessions.discard(user_id); await content_templates_col.insert_one({"name": parts[0][:60], "content": parts[1][:3500], "created_by": user_id, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
        await audit_admin_action(user_id, "template_create", parts[0]); return await message.answer("✅ قالب ذخیره شد.")

    if user_id in ticket_reply_sessions and is_admin(user_id):
        ticket_id = ticket_reply_sessions.pop(user_id); ticket = await tickets_col.find_one({"ticket_id": ticket_id})
        if not ticket: return await message.answer("تیکت پیدا نشد.")
        await tickets_col.update_one({"_id": ticket["_id"]}, {"$set": {"status": "in_progress", "assigned_to": user_id, "last_reply_at": datetime.now(timezone.utc)}, "$push": {"history": {"at": datetime.now(timezone.utc), "admin_id": user_id, "text": text[:2000]}}})
        try: await bot.send_message(ticket["user_id"], f"💬 <b>پاسخ پشتیبانی به تیکت #{ticket_id}</b>\n\n{html.escape(text[:2000])}", parse_mode="HTML")
        except Exception: pass
        await audit_admin_action(user_id, "ticket_reply", target=ticket_id); return await message.answer("✅ پاسخ برای کاربر ارسال شد.")

    if user_id in manual_balance_sessions and is_admin(user_id):
        return await complete_manual_balance_change(message)

    if user_id in repost_cta_sessions and is_admin(user_id):
        repost_cta_sessions.discard(user_id)
        new_text = "" if lowered in {"خاموش", "حذف", "بدون متن"} else text.strip()[:300]
        runtime_settings["repost_cta"] = new_text
        await settings_col.update_one({"_id": "runtime"}, {"$set": {"repost_cta": new_text}}, upsert=True)
        if new_text:
            await message.answer(f"✅ متن دعوت بازنشر ذخیره شد:\n\n{new_text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ ویرایش دوباره", callback_data="repost_cta_settings"), InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")]]))
        else:
            await message.answer("✅ متن دعوت انتهای پست‌ها غیرفعال شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ تنظیم متن", callback_data="repost_cta_settings"), InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")]]))
        return

    if user_id in economy_setting_sessions and is_admin(user_id):
        key = economy_setting_sessions[user_id]
        try: value = int(normalize_digits(text).replace(",", "").strip())
        except ValueError: return await message.answer("فقط عدد معتبر بفرست؛ مثلاً 100000")
        validation_error = validate_economy_setting_value(key, value)
        if validation_error:
            return await message.answer(validation_error)
        economy_setting_sessions.pop(user_id, None); economy_settings[key] = value
        await settings_col.update_one({"_id": "runtime"}, {"$set": {f"economy.{key}": value}}, upsert=True)
        if key == "referral_ai_bonus_cap":
            await users_col.update_many(
                {"ai_referral_text_bonus": {"$gt": value}},
                {"$set": {"ai_referral_text_bonus": value}},
            )
        await message.answer(f"✅ تنظیم جدید ذخیره شد: {value:,}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 بازگشت به تنظیمات اقتصاد", callback_data="economy_settings")]]))
        return

    if user_id in schedule_time_sessions and is_admin(user_id):
        batch = repost_batches.get(user_id)
        if not batch or not batch["items"]:
            schedule_time_sessions.discard(user_id)
            return await message.answer("گروه بازنشر خالی یا منقضی شده؛ دوباره شروع کن.")
        try:
            scheduled_at = parse_schedule_time(text)
        except (ValueError, OverflowError) as exc:
            return await message.answer(f"❌ {exc}\nنمونه درست: <code>فردا 09:00</code> یا <code>1405/05/08 18:30</code>", parse_mode="HTML")
        job_id = uuid.uuid4().hex[:10]
        await scheduled_posts_col.insert_one({
            "_id": job_id,
            "admin_id": user_id,
            "channel_id": CHANNEL_ID,
            "items": [item["payload"] for item in batch["items"]],
            "scheduled_at": scheduled_at,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        })
        count = len(batch["items"])
        schedule_time_sessions.discard(user_id)
        repost_sessions.discard(user_id)
        repost_batches.pop(user_id, None)
        await message.answer(
            f"✅ گروه شامل <b>{count} پست</b> برای <b>{format_tehran_datetime(scheduled_at)}</b> به وقت تهران زمان‌بندی شد.\nشناسه: <code>{job_id}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏰ مدیریت زمان‌بندی‌ها", callback_data="scheduled_posts")]]),
            parse_mode="HTML",
        )
        await log_activity(user_id, "scheduled_repost_created", f"id={job_id},count={count},at={scheduled_at.isoformat()}")
        return

    if user_id in instant_repost_sessions and is_admin(user_id):
        await publish_instant_repost(message)
        return

    if user_id in repost_sessions and is_admin(user_id):
        await stage_repost(message)
        return

    if user_id in daily_fal_channel_sessions and is_admin(user_id):
        return await connect_daily_fal_target(message, text)
    if user_id in music_daily_target_sessions and is_admin(user_id):
        return await connect_daily_music_target(message, text)
    if user_id in music_daily_time_sessions and is_admin(user_id):
        return await save_daily_music_time(message, text)
    if user_id in music_playlist_upload_sessions and is_admin(user_id):
        if text in {"پایان آپلود", "پایان", "تمام شد"}:
            count = music_playlist_upload_sessions.pop(user_id, 0)
            return await message.answer(f"✅ آپلود گروهی پلی‌لیست پایان یافت؛ {count} آهنگ ثبت شد.", reply_markup=music_reply_menu())
        return await message.answer("🎵 فایل صوتی بعدی را بفرست یا «پایان آپلود» را بزن.", reply_markup=music_reply_menu())

    if user_id in greeting_target_sessions and is_admin(user_id):
        return await connect_scheduled_greeting_target(message, text)
    if user_id in greeting_add_sessions and is_admin(user_id):
        session = greeting_add_sessions[user_id]
        kind = session.get("kind") if isinstance(session, dict) else session
        return await save_greeting_sentence(message, kind, text)
    if user_id in greeting_edit_sessions and is_admin(user_id):
        kind, item_id = greeting_edit_sessions[user_id]
        return await edit_greeting_sentence(message, kind, item_id, text)

    if user_id in channel_add_sessions and is_admin(user_id):
        parts = [part.strip() for part in text.split("|")]
        raw_identifier = parts[0] if parts else ""
        identifier: int | str
        join_url = ""
        custom_title = ""
        if raw_identifier.lstrip("-").isdigit():
            identifier = int(raw_identifier)
            join_url = parts[1] if len(parts) > 1 else ""
            custom_title = parts[2] if len(parts) > 2 else ""
            if not join_url.startswith("https://t.me/"):
                return await message.answer("برای کانال خصوصی باید بعد از آیدی عددی، لینک دعوت https://t.me/... را هم بفرستی.")
        else:
            match = re.match(r"^(?:https://t\.me/)?@?([A-Za-z0-9_]{5,})/?$", raw_identifier)
            if not match:
                return await message.answer("فرمت کانال عمومی درست نیست. نمونه: <code>@channelname | عنوان</code>", parse_mode="HTML")
            username = match.group(1)
            identifier = f"@{username}"
            join_url = f"https://t.me/{username}"
            custom_title = parts[1] if len(parts) > 1 else ""
        try:
            chat = await bot.get_chat(identifier)
            chat_type = getattr(chat.type, "value", str(chat.type))
            if chat_type not in {"channel", "supergroup"}:
                return await message.answer("این آدرس مربوط به کانال یا سوپرگروه نیست.")
            bot_info = await bot.get_me()
            bot_member = await bot.get_chat_member(chat.id, bot_info.id)
            if bot_member.status not in ("administrator", "creator"):
                return await message.answer("❌ اول ربات را در این کانال ادمین کن و دوباره اطلاعات را بفرست.")
        except Exception as exc:
            log.warning("افزودن کانال اجباری ناموفق بود: %s", exc)
            return await message.answer("❌ کانال پیدا نشد یا ربات داخلش ادمین نیست. اطلاعات را بررسی و دوباره ارسال کن.")
        channel_add_sessions.discard(user_id)
        document = {
            "_id": chat.id,
            "title": (custom_title or chat.title or getattr(chat, "username", None) or str(chat.id))[:80],
            "username": getattr(chat, "username", None),
            "join_url": join_url,
            "active": True,
            "added_at": datetime.now(timezone.utc),
            "added_by": user_id,
        }
        stored_document = {key: value for key, value in document.items() if key != "_id"}
        await required_channels_col.update_one({"_id": chat.id}, {"$set": stored_document}, upsert=True)
        await settings_col.update_one({"_id": "runtime"}, {"$set": {"channels_initialized": True}}, upsert=True)
        await refresh_required_channels()
        await message.answer(
            f"✅ کانال «{html.escape(document['title'])}» به عضویت اجباری اضافه شد.",
            reply_markup=required_channels_admin_menu(),
            parse_mode="HTML",
        )
        return

    if user_id in engagement_post_sessions and is_admin(user_id):
        parts = [part.strip() for part in text.split("|")]
        post_url = parts[0] if parts else ""
        if not re.match(r"^https://t\.me/[A-Za-z0-9_+/-]+$", post_url):
            return await message.answer("❌ لینک باید با https://t.me/ شروع شود. دوباره بفرست یا /cancel بزن.")
        instruction = parts[1] if len(parts) > 1 and parts[1] else "۱۰ پست آخر کانال را ببین و روی یکی از آن‌ها واکنش بزن."
        try:
            wait_seconds = max(8, min(60, int(parts[2]))) if len(parts) > 2 else 15
        except ValueError:
            return await message.answer("زمان انتظار باید یک عدد بین ۸ تا ۶۰ ثانیه باشد.")
        engagement_post_sessions.discard(user_id)
        engagement_gate_cache.update({
            "enabled": True,
            "version": uuid.uuid4().hex[:10],
            "url": post_url,
            "instruction": instruction[:240],
            "wait_seconds": wait_seconds,
        })
        await settings_col.update_one(
            {"_id": "runtime"},
            {"$set": {"engagement_gate": dict(engagement_gate_cache)}},
            upsert=True,
        )
        await message.answer(
            "✅ مرحله مشاهده پست‌ها فعال شد. از این به بعد کاربران بعد از عضویت کانال‌ها باید این مرحله را هم انجام دهند.",
            reply_markup=required_channels_admin_menu(),
        )
        return

    if user_id in admin_search_sessions and is_admin(user_id):
        admin_search_sessions.discard(user_id)
        query = text.lstrip("@").strip()
        if query.isdigit():
            users = await users_col.find({"_id": int(query)}).to_list(length=1)
        else:
            users = await users_col.find({"$or": [
                {"name": {"$regex": re.escape(query), "$options": "i"}},
                {"username": {"$regex": f"^{re.escape(query)}$", "$options": "i"}},
            ]}).limit(10).to_list(length=10)
        if not users:
            return await message.answer("❌ کاربری پیدا نشد.")
        rows = [[InlineKeyboardButton(
            text=f"👤 {(user.get('name') or 'بدون نام')[:25]} · {user['_id']}",
            callback_data=f"admin_user_{user['_id']}",
        )] for user in users]
        return await message.answer("🔎 نتیجه جستجو:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    if user_id in caption_sessions:
        caption_sessions.discard(user_id)
        topic = text.strip()[:220]
        if len(topic) < 2:
            return await message.answer("موضوع خیلی کوتاهه؛ یکم بیشتر توضیح بده تا کپشن بهتری بسازم.")
        waiting = await message.answer("✨ دارم یه کپشن وایرال برات می‌سازم...")
        prompt = (
            "برای موضوع زیر سه کپشن فارسی محاوره‌ای و خلاق بساز. هر کپشن حداکثر دو جمله، "
            "با ایموجی مناسب و در پایان 3 تا 5 هشتگ مرتبط باشد. لحن‌ها متفاوت باشند: باحال، احساسی و طنز. "
            f"موضوع: {topic}"
        )
        generated = await ask_ai(prompt, user_id=user_id, feature="caption")
        if generated:
            result = generated[:3900]
        else:
            templates = random.sample(CAPTION_TEMPLATES, k=min(3, len(CAPTION_TEMPLATES)))
            result = "\n\n———\n\n".join(template.format(topic=topic) for template in templates)
        await waiting.edit_text(result)
        await log_activity(user_id, "caption_maker", topic)
        return

    if user_id in review_sessions:
        if text in {"↩️ پشتیبانی", "🏠 منوی اصلی"}:
            review_sessions.discard(user_id)
            if text == "🏠 منوی اصلی":
                return await handle_menu_trigger(message)
            return await message.answer("💬 منوی پشتیبانی:", reply_markup=support_reply_menu())
        try:
            review = await create_user_review(
                user_id,
                message.from_user.full_name,
                message.from_user.username,
                text,
                "bot",
            )
        except (ValueError, DuplicateKeyError) as exc:
            return await message.answer(f"❌ {exc}\nدوباره بفرست یا /cancel بزن.", reply_markup=reviews_reply_menu())
        review_sessions.discard(user_id)
        await log_activity(user_id, "review_submitted", review["_id"])
        return await message.answer(
            "✅ نظرت ثبت شد و بعد از بررسی برای بقیه نمایش داده می‌شه. ممنون! 🌟",
            reply_markup=reviews_reply_menu(),
        )

    if user_id in support_sessions:
        support_sessions.discard(user_id)
        ticket_id = uuid.uuid4().hex[:6].upper()
        await tickets_col.insert_one({
            "ticket_id": ticket_id,
            "user_id": user_id,
            "name": message.from_user.full_name,
            "username": message.from_user.username,
            "text": text[:3500],
            "status": "open",
            "created_at": datetime.now(timezone.utc),
        })
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🎫 مشاهده #{ticket_id}", callback_data=f"ticket_view_{ticket_id}")]
        ])
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🎫 تیکت جدید #{ticket_id}\n👤 {html.escape(message.from_user.full_name)} · <code>{user_id}</code>\n\n{html.escape(text[:1000])}",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await log_activity(user_id, "support_ticket", f"ticket={ticket_id}")
        return await message.answer(f"✅ تیکت #{ticket_id} ثبت شد. نتیجه از همین ربات برات میاد.")

    if user_id in config_upload_sessions and is_admin(user_id):
        category = config_upload_sessions[user_id]
        sanitized = sanitize_config_text(text)
        if not sanitized:
            return await message.answer("❌ محتوای قابل ذخیره‌ای پیدا نشد؛ کانفیگ را دوباره بفرست.")
        content_hash=hashlib.sha256(sanitized.encode()).hexdigest()
        duplicate=await configs_col.find_one({"category":category,"content_hash":content_hash,"active":{"$ne":False}})
        if duplicate:return await message.answer("⚠️ این کانفیگ تکراریه و قبلاً ذخیره شده.")
        await configs_col.insert_one({
            "category": category, "content_type": "text", "text": sanitized, "content_hash":content_hash,
            "uploaded_at": datetime.now(timezone.utc), "expires_at":datetime.now(timezone.utc)+timedelta(days=7),
            "date_str": today_str(), "branded": True, "active":True, "downloads":0,
        })
        await message.answer(f"✅ {CONFIG_LABELS[category]} با برچسب @Ajor_pareh ذخیره شد. مورد بعدی رو بفرست یا /cancel بزن.")
        return

    if lowered in ("منو", "menu", "منوی اصلی", "🏠 منوی اصلی", "نمایش منو"):
        ai_sessions.pop(user_id, None)
        await handle_menu_trigger(message)
        return

    if text == "🎮 بازی‌ها":
        return await message.answer("🎮 منوی بازی‌ها باز شد؛ از پایین انتخاب کن:", reply_markup=games_reply_menu())
    if text == "🎁 جوایز و کیف پول":
        return await message.answer("🎁 منوی جوایز و کیف پول باز شد:", reply_markup=rewards_reply_menu())
    if text == "📰 اخبار و ترندها":
        return await message.answer("📰 منوی خبر و سرگرمی باز شد:", reply_markup=news_reply_menu())
    if text == "🧰 ابزارهای ربات":
        return await message.answer("🧰 منوی ابزارها باز شد:", reply_markup=tools_reply_menu())
    if text == "🤖 هوش مصنوعی":
        return await show_ai_menu(message)
    if text == "🛍 سرویس اختصاصی":
        return await message.answer("🛍 مرکز سرویس اختصاصی V2Ray و NPV:", reply_markup=service_reply_menu())
    if text == "🚀 خرید سرویس جدید":
        return await message.answer("نوع سرویس اختصاصی رو انتخاب کن:", reply_markup=service_type_keyboard())
    if text == "📱 سرویس‌های من": return await show_user_services(message)
    if text == "♻️ تمدید سرویس": return await show_user_services(message)
    if text == "📊 وضعیت سفارش": return await show_service_orders(message)
    if text == "💰 اعتبار من":
        wallet = await wallet_snapshot(user_id)
        return await message.answer(
            f"💰 اعتبار کیف پول: <b>{wallet['wallet_toman']:,} تومان</b>\n🪙 سکه: {wallet['coins']:,}\n⚡ XP: {wallet['points']:,}",
            parse_mode="HTML", reply_markup=service_reply_menu(),
        )
    if text == "🎁 تخفیف و آفر ویژه":
        offer = active_service_offer()
        if not offer:
            return await message.answer("🎁 فعلاً تخفیف یا آفر فعالی موجود نیست.", reply_markup=service_reply_menu())
        return await message.answer(
            f"🔥 <b>{html.escape(offer['title'])}</b>\nتخفیف: <b>{offer['percent']}٪</b> روی همه پلن‌های V2Ray و NPV\nاعتبار تا: {format_tehran_datetime(offer['expires_at'])}",
            parse_mode="HTML", reply_markup=service_reply_menu(),
        )
    if text == "🏆 کاربران برتر": return await run_callback_from_reply(message, "leaderboard", leaderboard_callback)
    if text == "👥 معرفی به دوستان": return await run_callback_from_reply(message, "invite", invite_callback)
    if text == "💡 آموزش استفاده":
        return await message.answer(
            "💡 <b>راهنمای سرویس اختصاصی</b>\n\n"
            "⚡ V2Ray: مناسب V2rayNG اندروید، V2Box آیفون و کلاینت‌های دسکتاپ.\n"
            "🌀 NPV: مناسب برنامه NapsternetV.\n\n"
            "بعد از پرداخت، مدیر کانفیگ اختصاصی را همین‌جا تحویل می‌دهد. لینک را کپی یا Import کن و با اپ پیشنهادی متصل شو. اطلاعات سرویس را با دیگران به اشتراک نگذار.",
            parse_mode="HTML", reply_markup=service_reply_menu(),
        )
    if text == "👨‍💻 تماس با پشتیبانی":
        support_sessions.add(user_id)
        return await message.answer("مشکل سرویس یا سفارشت رو همراه شناسه سفارش بفرست. /cancel", reply_markup=service_reply_menu())
    if text == "📥 مرکز دانلود و آپلود":
        return await message.answer("📥 لینک عمومی رسانه یا فایل رو انتخاب و ارسال کن:", reply_markup=media_download_reply_menu())
    if text == INSTAGRAM_COMMENT_BUTTON:
        return await start_instagram_comment_session(message)
    if text in {"📸 دانلود اینستاگرام", "🎵 دانلود تیک‌تاک", "▶️ دانلود یوتیوب", "🌐 دانلود سایر شبکه‌ها", "🎬 دانلود یوتیوب"}:
        media_request_sessions[user_id] = "social"
        return await message.answer(
            "📥 لینک عمومی پست/Reel/Shorts/ویدئو رو بفرست.\n\n"
            "🌍 پلتفرم‌های پشتیبانی‌شده: اینستاگرام، تیک‌تاک، یوتیوب، X، فیسبوک، ردیت، پینترست، تردز، ویمیو، دیلی‌موشن، توییچ، ساندکلود، بندکمپ، VK، OK، روتوب، بیلی‌بیلی، استریمبل، رامبل، آدیسی، آرکایو، کیسک، گوگل‌درایو، دراپ‌باکس و ده‌ها سایت دیگه.\n"
            "🔎 حتی اگه سایت خاصی تو لیست نباشه، تلاش می‌کنم ویدئوش رو پیدا کنم.\n\n"
            "📊 برای کلیپ/پست اینستاگرام، کپشن، تعداد لایک، بازدید و کامنت هم کنار فایل می‌فرستم.\n"
            "🖼 برای عکس پروفایل اینستاگرام، دکمهٔ «🖼 پروفایل اینستاگرام» رو بزن.\n\n"
            "🎬 ویدئوهای بزرگ خودکار فشرده‌سازی می‌شن تا قابل ارسال باشن + دکمه استخراج صوت MP3.\n"
            "محتوای خصوصی، نیازمند ورود یا DRM قابل دریافت نیست. /cancel",
            reply_markup=media_download_reply_menu(),
        )
    if text == "🖼 پروفایل اینستاگرام":
        media_request_sessions[user_id] = "social"
        return await message.answer(
            "🖼 لینک صفحهٔ پروفایل اینستاگرام رو بفرست؛ مثلاً:\n"
            "<code>https://www.instagram.com/username/</code>\n\n"
            "عکس پروفایل پیج‌های عمومی رو بدون نیاز به ورود دریافت می‌کنم. "
            "پیج‌های خصوصی یا محدود قابل دریافت نیستن.\n"
            "🎟 هر دریافت، ۱ توکن از سهمیهٔ دانلودت کم می‌کنه. /cancel",
            parse_mode="HTML", reply_markup=media_download_reply_menu(),
        )
    if text == "🔗 آپلود فایل از URL":
        media_request_sessions[user_id] = "direct"
        return await message.answer(
            "🔗 لینک مستقیم HTTPS هر فایل عمومی رو بفرست: ویدئو، عکس، صوت، APK، EXE، PDF، کتاب الکترونیکی، Word/Excel/PowerPoint، ZIP/RAR/7z، فونت، زیرنویس، JSON و تقریباً هر فرمت دیگه.\n\n"
            f"فقط صفحهٔ سایت (HTML) قبول نیست؛ لینک باید مستقیم به خود فایل باشه و حداکثر {media_size_label()}. /cancel",
            reply_markup=media_download_reply_menu(),
        )
    if text == "🛡 بررسی امنیت لینک":
        media_request_sessions[user_id] = "inspect"
        return await message.answer("🛡 لینک کامل رو بفرست تا دامنه، HTTPS، کوتاه‌کننده و نشانه‌های مشکوک بررسی بشه. /cancel", reply_markup=media_download_reply_menu())
    if text == "🔄 ویدئو به دایره‌ای":
        video_round_sessions.add(user_id)
        return await message.answer(
            "🔵 <b>تبدیل ویدئو به ویدئو مسیج دایره‌ای</b>\n\n"
            "یک ویدئو بفرست تا به <b>ویدئو مسیج دایره‌ای</b> تلگرام تبدیل بشه.\n"
            "⏱ حداکثر ۶۰ ثانیه · 📦 تا ۲۰۰ مگابایت · 🎬 با انیمیشن پیشرفت آماده‌سازی\n\n"
            "حالا ویدئوت رو بفرست. /cancel",
            parse_mode="HTML", reply_markup=media_download_reply_menu(),
        )
    if text == "📋 دانلودهای اخیر": return await show_media_jobs(message)
    if text == "📊 سهمیه دانلود": return await show_download_quota(message)
    if text == "ℹ️ راهنمای دانلود":
        return await message.answer(
            "ℹ️ <b>مرکز رسانه</b>\n\n"
            "📸 دانلود: اینستاگرام، تیک‌تاک، یوتیوب، X، فیسبوک، ردیت، دیلی‌موشن، توییچ، ساندکلود، گوگل‌درایو و ده‌ها سایت دیگه؛ فقط لینک عمومی و بدون ورود.\n"
            "🖼 پروفایل اینستاگرام: لینک صفحهٔ کاربر رو بفرست تا عکس پروفایلش رو بگیرم (فقط پیج عمومی).\n"
            "📊 کلیپ/پست اینستاگرام: همراه فایل، کپشن، تعداد لایک، بازدید و کامنت هم می‌فرستم.\n"
            f"🔗 آپلود URL: لینک مستقیم هر فایل عمومی تا {media_size_label()}؛ تقریباً هر فرمتی (به‌جز صفحهٔ سایت).\n"
            "🎬 ویدئوهای بزرگ‌تر از سقف، خودکار فشرده‌سازی می‌شن و قابل ارسال می‌شن.\n"
            "🎵 بعد از هر ویدئو، دکمه استخراج صوت MP3 هم داری.\n"
            "🛡 بررسی لینک: تحلیل ساختاری است و جای آنتی‌ویروس را نمی‌گیرد.\n\n"
            "از دانلود و بازنشر محتوایی که اجازه‌اش را نداری خودداری کن. رمز یا کوکی هیچ سایتی را برای ربات نفرست.",
            parse_mode="HTML", reply_markup=media_download_reply_menu(),
        )
    if text in {"🕛 00:00", "00:00"}:
        return await show_scheduled_greeting_control(message, "midnight")
    if text in {"🌅 صبح بخیر", "صبح بخیر"}:
        return await show_scheduled_greeting_control(message, "morning")
    if text == "📱 QR ساز":
        qr_sessions.add(user_id)
        return await message.answer("📱 متن، لینک، شماره تماس یا هر محتوایی رو بفرست تا QR بسازم. برای انصراف /cancel")
    if text in {"🎨 گیف و استیکرساز", "🪄 استیکرساز"}:
        return await message.answer("🎨 چی دوست داری بسازی؟", reply_markup=media_maker_reply_menu())
    if text == "🪄 ساخت استیکر":
        gif_sessions.discard(user_id)
        sticker_sessions.add(user_id)
        return await message.answer("🪄 یک عکس بفرست تا استیکر بسازم و داخل پک واقعی تلگرامت قرار بدم. /cancel", reply_markup=media_maker_reply_menu())
    if text == "🎞 ساخت گیف":
        sticker_sessions.discard(user_id)
        gif_sessions.add(user_id)
        return await message.answer("🎞 عکس، ویدئو یا GIF کمتر از ۱۹ مگابایت بفرست. خروجی Animation تلگرام با گزینه Save GIF می‌گیری. /cancel", reply_markup=media_maker_reply_menu())
    if text == "📦 پک استیکرهای من":
        user = await users_col.find_one({"_id": user_id}, {"last_sticker_pack": 1}) or {}
        pack_name = user.get("last_sticker_pack")
        if not pack_name:
            return await message.answer("هنوز پک استیکری نساختی؛ اول یک عکس رو به استیکر تبدیل کن.", reply_markup=media_maker_reply_menu())
        return await message.answer(
            "📦 پک اختصاصی تو آماده‌ست:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="➕ بازکردن و افزودن پک", url=f"https://t.me/addstickers/{pack_name}")
            ]]),
        )
    if text == "ℹ️ راهنمای گیف و استیکر":
        return await message.answer(
            "ℹ️ <b>راهنما</b>\n\n"
            "🪄 استیکر: یک عکس بفرست؛ داخل پک واقعی تلگرامت ذخیره می‌شه.\n"
            "🎞 گیف: عکس، ویدئو یا GIF بفرست؛ خروجی به‌صورت Animation بدون صدا میاد. روی Animation بزن و Save GIF رو انتخاب کن.\n"
            "📥 فایل WEBP و MP4 قابل دانلود هم جدا ارسال می‌شن.",
            parse_mode="HTML", reply_markup=media_maker_reply_menu(),
        )
    if text == "💬 پشتیبانی":
        return await message.answer("💬 منوی پشتیبانی باز شد:", reply_markup=support_reply_menu())
    if text == "📖 معرفی ربات":
        return await message.answer(about_bot_text(), reply_markup=support_reply_menu(), parse_mode="HTML")
    if text == "⚙️ پنل مدیریت":
        if is_admin(user_id):
            return await message.answer("⚙️ پنل مدیریت پایین چت باز شد:", reply_markup=admin_reply_menu())
        return await message.answer("⛔ شما مجاز به دسترسی به این قسمت نیستید.")

    if text == "↩️ پنل مدیریت":
        if is_admin(user_id): return await message.answer("⚙️ پنل مدیریت:", reply_markup=admin_reply_menu())
        return await message.answer("⛔ دسترسی ندارید.")
    if text == "↩️ بازی‌ها":
        return await message.answer("🎮 منوی بازی‌ها:", reply_markup=games_reply_menu())

    # زیرمنوی هوش مصنوعی
    if text in AI_BUTTON_TO_MODE:
        mode = AI_BUTTON_TO_MODE[text]
        previous_history = ai_sessions.get(user_id, {}).get("history", []) if mode == "chat" else []
        ai_sessions[user_id] = {
            "mode": mode,
            "history": previous_history,
            "started_at": time.monotonic(),
            "last_used_at": time.monotonic(),
        }
        details = AI_MODE_CONFIG[mode]
        extra = "\n\nبرای خروج /cancel یا «🏠 منوی اصلی» رو بزن."
        return await message.answer(
            f"{details['title']} فعال شد.\n\n{details['instruction']}{extra}",
            reply_markup=ai_reply_menu(),
        )
    if text == "📊 سهمیه من":
        quota = await ai_service.quota_snapshot(user_id, unlimited=is_admin(user_id))
        if quota["unlimited"]:
            quota_text = "♾ سهمیه هوش مصنوعی برای مدیریت نامحدوده."
        else:
            quota_text = (
                f"📊 سهمیه امروز به وقت تهران\n\n"
                f"📝 متن و تحلیل تصویر: {quota['text_used']} مصرف‌شده · {quota['text_remaining']} باقی‌مانده\n"
                f"🎨 ساخت و ویرایش تصویر: {quota['image_used']} مصرف‌شده · {quota['image_remaining']} باقی‌مانده\n"
                f"🎁 هدیه مدیر: +{quota.get('admin_text_bonus', 0)} متن · +{quota.get('admin_image_bonus', 0)} تصویر\n"
                f"👥 هدیه رفرال: +{quota.get('referral_text_bonus', 0)} متن روزانه\n"
                f"🎟 هدیه کدها: +{quota.get('gift_text_bonus', 0)} متن · +{quota.get('gift_image_bonus', 0)} تصویر\n\n"
                "سهمیه ناموفق‌ها کم نمی‌شه و هر روز تازه می‌شه."
            )
        return await message.answer(quota_text, reply_markup=ai_reply_menu())
    if text == "🧹 پاک‌کردن گفتگو":
        ai_sessions.pop(user_id, None)
        return await message.answer(
            "🧹 حافظه گفت‌وگوی این نشست پاک شد. یک ابزار تازه انتخاب کن:",
            reply_markup=ai_reply_menu(),
        )

    # زیرمنوی بازی‌ها
    if text == "🏃 بزن در رو": return await run_callback_from_reply(message, "hit_run_start", hit_run_start)
    if text == "🧠 کوئیز فوری": return await run_callback_from_reply(message, "quick_quiz", quick_quiz_callback)
    if text == "🎲 تاس": return await run_callback_from_reply(message, "dice", dice)
    if text == "🎯 دارت": return await run_callback_from_reply(message, "dart", dart)
    if text == "🪨 سنگ‌کاغذ‌قیچی": return await message.answer("انتخابت؟", reply_markup=rps_reply_menu())
    if text == "🪙 شیر یا خط": return await message.answer("شیر یا خط؟", reply_markup=coin_reply_menu())
    if text == "🔢 حدس عدد": return await run_callback_from_reply(message, "guess_game", guess_game)
    if text == "🧠 جورچین حافظه": return await run_callback_from_reply(message, "mem_start", mem_start)
    if text == "🃏 بیست و یک": return await run_callback_from_reply(message, "bj_start", bj_start)
    if text == "🎭 جرأت یا حقیقت": return await message.answer("جرأت یا حقیقت؟", reply_markup=truth_reply_menu())
    if text in {"🪨 سنگ", "📄 کاغذ", "✂️ قیچی"}:
        data = {"🪨 سنگ": "rps_stone", "📄 کاغذ": "rps_paper", "✂️ قیچی": "rps_scissors"}[text]
        await run_callback_from_reply(message, data, rps_play); return await message.answer("دوباره انتخاب کن یا برگرد:", reply_markup=rps_reply_menu())
    if text in {"🪙 شیر", "🪙 خط"}:
        data = "coin_heads" if text == "🪙 شیر" else "coin_tails"
        await run_callback_from_reply(message, data, coin_play); return await message.answer("دوباره انتخاب کن یا برگرد:", reply_markup=coin_reply_menu())
    if text in {"💬 حقیقت", "🔥 جرأت", "🎲 شانسی", "❤️ کاپلی"}:
        data = {"💬 حقیقت": "td_truth", "🔥 جرأت": "td_dare", "🎲 شانسی": "td_random", "❤️ کاپلی": "td_couple"}[text]
        await run_callback_from_reply(message, data, truth_dare_play); return await message.answer("یکی دیگه؟", reply_markup=truth_reply_menu())

    # زیرمنوی جوایز
    if text == "🔥 جایزه روزانه": return await run_callback_from_reply(message, "daily_reward", daily_reward_callback)
    if text == "💳 کیف پول":
        data = await wallet_snapshot(user_id)
        return await message.answer(f"💳 کیف پول\n⚡ امتیاز: {data['points']:,}\n🪙 سکه: {data['coins']:,}\n💵 تومان: {data['wallet_toman']:,}\n🎁 رفرال: {data['referral_count']}", reply_markup=rewards_reply_menu())
    if text == "🎁 دعوت دوستان": return await run_callback_from_reply(message, "invite", invite_callback)
    if text == "🎟 کد هدیه":
        gift_redeem_sessions.add(user_id)
        return await message.answer("🎟 کد هدیه رو بفرست؛ مثال: <code>AJOR100</code>\n/cancel برای لغو", parse_mode="HTML", reply_markup=rewards_reply_menu())
    if text == "🎯 مأموریت‌های جایزه": return await user_missions_handler(message)
    if text == "🏆 رتبه‌بندی": return await run_callback_from_reply(message, "leaderboard", leaderboard_callback)

    # زیرمنوی خبر و سرگرمی
    if text in {"📰 اخبار زنده", "📰 خبرهای روز"}:
        return await message.answer("📰 دسته خبر رو انتخاب کن:", reply_markup=live_news_reply_menu())
    if text == "🇮🇷 اخبار ایران": return await send_live_news_to_bot(message, "iran")
    if text == "🌍 اخبار جهان": return await send_live_news_to_bot(message, "world")
    if text == "💻 اخبار فناوری": return await send_live_news_to_bot(message, "tech")
    if text == "🔄 تازه‌ترین خبرها": return await send_live_news_to_bot(message, refresh=True)
    if text == "↩️ خبر و سرگرمی": return await message.answer("🎉 خبر و سرگرمی:", reply_markup=news_reply_menu())
    if text in {"😂 جوک تازه", "😂 جوک تصادفی"}:
        return await joke_command(message)
    if text == "🧠 دانستنی عجیب": return await message.answer(random.choice(WEIRD_FACTS), reply_markup=news_reply_menu())
    if text == "🧩 معمای فوری": return await send_fun_riddle(message)
    if text == "🎭 این یا اون":
        option_a, option_b = random.choice(WOULD_YOU_RATHER)
        return await message.answer_poll(
            question="🎭 این یا اون؛ کدوم رو انتخاب می‌کنی؟",
            options=[option_a, option_b],
            is_anonymous=True,
        )
    if text == "⚡ چالش ۳۰ ثانیه": return await message.answer(f"⚡ <b>چالش فوری</b>\n\n{html.escape(random.choice(QUICK_FUN_CHALLENGES))}", parse_mode="HTML", reply_markup=news_reply_menu())
    if text == "🤡 میم متنی": return await message.answer(random.choice(TEXT_MEMES), reply_markup=news_reply_menu())
    if text == "🔮 فال فان امروز":
        fortune_index = int(hashlib.sha256(f"fortune:{user_id}:{today_str()}".encode()).hexdigest(), 16) % len(FUN_FORTUNES)
        return await message.answer(f"🔮 <b>فال فان امروزت</b>\n\n{FUN_FORTUNES[fortune_index]}\n\n<i>صرفاً برای سرگرمی 😄</i>", parse_mode="HTML", reply_markup=news_reply_menu())
    if text == "✨ جمله انگیزشی": return await message.answer(random.choice(QUOTES), reply_markup=news_reply_menu())
    if text == "🔥 داغ‌های کانال": return await send_channel_trends_to_bot(message)
    if text == "📣 کانال Ajorpareh": return await message.answer(f"📣 کانال رسمی:\n{CHANNEL_LINK}", reply_markup=news_reply_menu())
    if text == "✨ کپشن‌ساز": caption_sessions.add(user_id); return await message.answer("موضوع پستت رو بفرست؛ /cancel برای لغو", reply_markup=tools_reply_menu())
    if text == "🧠 پرامپت‌ها": return await show_prompt_center(message)
    if text == "🧮 ماشین‌حساب": return await run_callback_from_reply(message, "open_calc", open_calculator)
    if text == "🎬 دانلود یوتیوب": return await run_callback_from_reply(message, "youtube", youtube)
    if text == "🎭 حال‌سنج": return await run_callback_from_reply(message, "mood_meter", mood_meter_callback)
    if text == "⏰ یادآور هوشمند":
        return await message.answer("⏰ یادآورهای روزمره:", reply_markup=reminder_reply_menu())
    if text == "➕ یادآور جدید":
        reminder_sessions.add(user_id)
        return await message.answer(
            "زمان و متن رو بفرست؛ نمونه:\n<code>فردا 09:00 | تماس با علی</code>\n/cancel برای لغو",
            parse_mode="HTML", reply_markup=reminder_reply_menu(),
        )
    if text == "📋 یادآورهای من":
        return await send_user_reminders_list(message)
    if text == "↩️ ابزارهای ربات":
        return await message.answer("🧰 منوی ابزارها:", reply_markup=tools_reply_menu())
    if text in {"🧩 API شکلک سفارشی", "🤖 راهنمای برنامه‌نویسان"}:
        return await message.answer(EMOJI_API_GUIDE, parse_mode="HTML", reply_markup=tools_reply_menu())
    if text == "🌐 پروکسی": return await run_callback_from_reply(message, "get_proxy", get_proxy_callback)
    if text == "🔐 کانفیگ": return await run_callback_from_reply(message, "config_menu", config_menu_callback)

    # زیرمنوی پشتیبانی
    if text == "👤 پروفایل من": return await profile_command(message)
    if text == "✍️ ارسال پیام پشتیبانی": support_sessions.add(user_id); return await message.answer("پیامت رو بفرست؛ همراه آیدی تلگرامت مستقیم برای مدیر می‌ره. /cancel", reply_markup=support_reply_menu())
    if text == "💬 نظرات کاربران": return await message.answer("نظرها و بازخوردها:", reply_markup=reviews_reply_menu())
    if text == "👀 دیدن نظرات": return await send_reviews_to_bot(message)
    if text == "✍️ نوشتن نظر":
        review_sessions.add(user_id)
        return await message.answer(
            "نظرت رو بفرست. می‌تونی امتیاز هم بنویسی:\n<code>5 | چالش‌ها خیلی خفن بودن!</code>\n/cancel برای لغو",
            parse_mode="HTML", reply_markup=reviews_reply_menu(),
        )
    if text == "↩️ پشتیبانی": return await message.answer("💬 منوی پشتیبانی:", reply_markup=support_reply_menu())
    if text == "❓ راهنمای ربات": await help_command(message); return await message.answer("از منوی پایین ادامه بده:", reply_markup=support_reply_menu())
    if text == "🔄 بروزرسانی و رفع مشکل": return await run_user_self_heal(message)

    if user_id in awaiting_prayer_city and is_admin(user_id):
        awaiting_prayer_city.discard(user_id)
        city_name = (message.text or "").strip()
        if not city_name:
            return await message.answer("❌ نام شهر خالی بود؛ دوباره بفرست.")
        try:
            data = await prayer_times(city_name)
            found = data.get("city") or city_name
            runtime_settings["daily_prayer_city"] = found
            await settings_col.update_one({"_id": "runtime"}, {"$set": {"daily_prayer_city": found}}, upsert=True)
            return await message.answer(
                f"✅ شهر اذان روزانه تنظیم شد: <b>{html.escape(found)}</b>\n\n{format_prayer_text(data)}",
                parse_mode="HTML",
            )
        except Exception as exc:
            log.warning("prayer city set failed: %s", exc)
            return await message.answer("❌ شهری با این نام پیدا نشد. یه اسم دیگه بفرست یا با /pray <نام شهر> امتحان کن.")

    # دسته‌های پنل مدیریت
    if text == "📊 آمار و گزارش" and is_admin(user_id):
        await run_callback_from_reply(message, "stats", stats_callback); return await message.answer("گزینه بعدی رو انتخاب کن:", reply_markup=admin_reply_menu())
    if text == "📡 رصد فعالیت‌ها" and is_admin(user_id):
        return await message.answer(
            "📡 پنل رصد و نظارت:",
            reply_markup=persistent_keyboard([
                ["📡 رصد زنده فعالیت‌ها", "🕵️ فعالیت یک کاربر"],
                ["🔥 کاربران فعال", "↩️ پنل مدیریت"],
            ]),
        )
    if text == "🔥 کاربران فعال" and is_admin(user_id):
        return await run_callback_from_reply(message, "admin_active_users", admin_active_users_callback)
    if text == "📡 رصد زنده فعالیت‌ها" and is_admin(user_id):
        return await run_callback_from_reply(message, "admin_live_activity", admin_live_activity_callback)
    if text == "🕵️ فعالیت یک کاربر" and is_admin(user_id):
        return await run_callback_from_reply(message, "admin_activity_user", admin_activity_user_callback)
    if text == "📊 آمار رسانه" and is_admin(user_id):
        return await run_callback_from_reply(message, "admin_media_stats", admin_media_stats_callback)
    if text == "🧹 پاکسازی صف رسانه" and is_admin(user_id):
        return await run_callback_from_reply(message, "admin_media_cleanup", admin_media_cleanup_callback)
    if text == "📈 آمار هوش مصنوعی" and is_admin(user_id):
        return await run_callback_from_reply(message, "admin_ai_stats", admin_ai_stats_callback)
    if text == "👥 کاربران و تیکت‌ها" and is_admin(user_id):
        return await message.answer(
            "بخش کاربران و پشتیبانی:",
            reply_markup=persistent_keyboard([
                ["👥 مدیریت کاربران", "🎫 تیکت‌های پشتیبانی"],
                ["💰 افزایش موجودی کاربر", "🔎 جستجوی کاربر"],
                ["📥 خروجی CSV"], ["↩️ پنل مدیریت"],
            ]),
        )
    if text == "📢 محتوا و انتشار" and is_admin(user_id): return await message.answer("مدیریت محتوا:", reply_markup=admin_content_reply_menu())
    if text == "💰 مالی و اقتصاد" and is_admin(user_id): return await message.answer("مدیریت مالی:", reply_markup=admin_finance_reply_menu())
    if text == "🌐 کانفیگ و فایل‌ها" and is_admin(user_id): return await message.answer("مدیریت فایل و کانفیگ:", reply_markup=admin_files_reply_menu())
    if text == "🛡 گروه و کانال" and is_admin(user_id): return await message.answer("مدیریت گروه و کانال:", reply_markup=admin_groups_reply_menu())
    if text == "🎯 کمپین و جوایز" and is_admin(user_id): return await message.answer("کمپین‌ها:", reply_markup=admin_campaign_reply_menu())
    if text == "👮 مدیران و امنیت" and is_admin(user_id): return await message.answer("مدیران و امنیت:", reply_markup=admin_security_reply_menu())
    if text == "🩺 سلامت و پشتیبان" and is_admin(user_id): return await message.answer("سلامت و پشتیبان:", reply_markup=admin_health_reply_menu())

    # عملیات ثابت پنل؛ فهرست‌های پویا همچنان در پیام نمایش داده می‌شوند ولی ناوبری از منوی پایین انجام می‌شود.
    admin_routes = {
        "👥 مدیریت کاربران": ("list_users", list_users_callback), "🎫 تیکت‌های پشتیبانی": ("admin_tickets", admin_tickets_callback),
        "🔎 جستجوی کاربر": ("admin_search_user", admin_search_user_callback), "📥 خروجی CSV": ("admin_export_users", admin_export_users_callback),
        "⚡ انتشار فوری": ("instant_repost_start", instant_repost_start_callback), "♻️ بازنشر گروهی": ("repost_start", repost_start_callback),
        "⏰ پست زمان‌دار": ("scheduled_posts", scheduled_posts_callback), "✍️ متن دعوت بازنشر": ("repost_cta_settings", repost_cta_settings_callback),
        "📢 پیام همگانی": ("broadcast_menu", broadcast_menu_callback), "📝 قالب‌های محتوا": ("template_manage", template_manage_callback),
        "💰 افزایش موجودی کاربر": ("admin_balance_user", admin_balance_user_callback),
        "💸 برداشت‌های در انتظار": ("admin_withdrawals", admin_withdrawals_callback), "💰 تنظیمات اقتصاد": ("economy_settings", economy_settings_callback),
        "🛒 فروش و سفارش سرویس": ("admin_service_shop", admin_service_shop_callback),
        "📊 گزارش مالی و ضدتقلب": ("admin_finance", admin_finance_callback), "🌐 مدیریت پروکسی و کانفیگ": ("admin_config_panel", admin_config_panel_callback),
        "📁 مدیریت فایل‌ها": ("manage_groups", manage_groups_callback), "📤 گروه فایل جدید": ("upload_file", upload_file_callback),
        "✅ انتشار گروه فایل": ("publish_group", publish_group_callback), "🛡 گروه‌ها و کانال‌ها": ("managed_chats", managed_chats_callback),
        "📣 کانال‌های عضویت اجباری": ("admin_required_channels", admin_required_channels_callback), "🎟 کدهای جایزه": ("promo_manage", promo_manage_callback),
        "🎯 مأموریت‌ها": ("mission_manage", mission_manage_callback), "🎡 قرعه‌کشی‌ها": ("raffle_manage", raffle_manage_callback),
        "📈 پیش‌بینی ترند": ("prediction_manage", prediction_manage_callback), "👮 نقش مدیران": ("admin_roles", admin_roles_callback),
        "📜 گزارش فعالیت مدیران": ("admin_audit", admin_audit_callback), "🩺 سلامت ربات": ("admin_health", admin_health_callback),
        "🤖 وضعیت هوش مصنوعی": ("admin_ai_status", admin_ai_status_callback), "💾 دریافت پشتیبان": ("admin_backup", admin_backup_callback),
    }
    if text in admin_routes and is_admin(user_id):
        data, handler = admin_routes[text]; return await run_callback_from_reply(message, data, handler)
    if text == "🟢/🔴 حالت تعمیرات" and is_admin(user_id): return await run_callback_from_reply(message, "toggle_maintenance", admin_toggle_setting)
    if text == "✅/☑️ عضویت اجباری" and is_admin(user_id): return await run_callback_from_reply(message, "toggle_force_join", admin_toggle_setting)
    if text == "🍷 فال روزانه صبحگاهی" and is_admin(user_id): return await run_callback_from_reply(message, "toggle_daily_fal", toggle_daily_fal_callback)
    if text == "📈 پست خودکار نرخ ارز" and is_admin(user_id): return await run_callback_from_reply(message, "toggle_auto_rates", toggle_auto_rates_callback)
    if text == "🕌 پست اذان روزانه در کانال" and is_admin(user_id): return await run_callback_from_reply(message, "toggle_daily_prayer", toggle_daily_prayer_callback)
    if text == "📊 آمار مالی هفتگی در کانال" and is_admin(user_id): return await run_callback_from_reply(message, "toggle_weekly_finance", toggle_weekly_finance_callback)
    if text == "📤 ارسال گزارش مالی به کانال" and is_admin(user_id): return await run_callback_from_reply(message, "weekly_finance_send_now", weekly_finance_send_now_callback)
    if text == "🔄 خودترمیم و بروزرسانی" and is_admin(user_id): return await run_user_self_heal(message, admin_mode=True)

    if await is_banned(user_id):
        return await message.answer("🚫 شما از ربات بن شده‌اید.")

    if user_id in broadcast_sessions and is_admin(user_id):
        broadcast_sessions.discard(user_id)
        await do_broadcast(user_id, message)
        return

    if not await is_member(user_id):
        return await message.answer("❌ اول مراحل عضویت و دسترسی رو کامل کن:", reply_markup=channel_check_menu())

    if is_flooding(user_id):
        return

    # دانلود خودکار لینک عمداً خاموش است؛ فقط بعد از انتخاب نوع دانلود،
    # media_request_sessions وارد این بخش می‌شود و لینک را صف می‌کند.
    if contains_media_link(text):
        if is_instagram_comment_url(text):
            return await message.answer(
                "💬 این لینک مربوط به یک کامنت اینستاگرام است. برای دریافت متنش، "
                "از مرکز دانلود گزینهٔ «کپی متن کامنت اینستاگرام» را بزن.",
                reply_markup=media_download_reply_menu(),
            )
        return await message.answer(
            "🔗 لینک دریافت شد، اما دانلود خودکار خاموش است.\n\n"
            "برای دانلود، اول از «مرکز دانلود و آپلود» نوع کار را انتخاب کن؛ "
            "بعد لینک را بفرست.",
            reply_markup=media_download_reply_menu(),
        )

    profanity = detect_profanity(text)
    if profanity:
        await log_activity(user_id, "private_profanity", ",".join(sorted(profanity)))
        return await issue_private_warning(message, profanity)

    if user_id in ai_sessions:
        mode = ai_sessions[user_id].get("mode")
        if mode in {"vision", "edit_image"}:
            return await message.answer(
                "📷 برای این ابزار باید عکس بفرستی؛ توضیحت رو داخل کپشن همون عکس بنویس.",
                reply_markup=ai_reply_menu(),
            )
        if mode == "voice":
            return await message.answer(
                "🎙 برای این ابزار یک پیام صوتی یا فایل صوتی بفرست.",
                reply_markup=ai_reply_menu(),
            )
        return await execute_ai_text_mode(message, ai_sessions[user_id], text)

    if lowered in {"جوک", "یه جوک", "یک جوک", "جوک بگو", "یه جوک بگو", "منو بخندون"}:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="😂 یکی دیگه", callback_data="joke_again"),
             InlineKeyboardButton(text="✨ انگیزشی", callback_data="quote_again")]
        ])
        await log_activity(user_id, "joke_keyword", text)
        return await message.answer(random.choice(JOKES), reply_markup=keyboard)

    if lowered in {"پنل", "پنل مدیریت", "مدیریت"}:
        if is_admin(user_id):
            return await message.answer("⚙️ پنل مدیریت پایین چت باز شد:", reply_markup=admin_reply_menu())
        return await message.answer("⛔ شما مجاز به دسترسی به این قسمت نیستید.")

    if any(phrase in lowered for phrase in ["چطوری", "خوبی", "تو خوبی", "تو چطوری", "حالت چطوره"]):
        response = random.choice(BOT_MOOD_RESPONSES)
        await log_activity(user_id, "ask_bot_mood", text)
        return await message.answer(response)

    mood = detect_mood(text)
    if mood:
        responses = MOOD_RESPONSES.get(mood, ["متوجه نشدم 😅"])
        await log_activity(user_id, f"mood_{mood}", text)
        return await message.answer(random.choice(responses))

    chat_response = get_chat_response(text)
    if chat_response:
        await log_activity(user_id, "chat_intent", lowered[:120])
        return await message.answer(chat_response)

    ai_msg = await message.answer("⚡ یه لحظه رفیق، دارم جواب درست‌وحسابی می‌چینم...")
    history = casual_chat_history.get(user_id, [])[-8:]
    ai_result = await ask_ai_detailed(
        text,
        user_id=user_id,
        feature="implicit_chat",
        system_prompt=CASUAL_AI_SYSTEM_PROMPT,
        history=history,
    )
    if ai_result.ok and ai_result.text:
        conversation = [*history, {"role": "user", "content": text[:1500]}, {"role": "assistant", "content": ai_result.text[:1500]}]
        casual_chat_history[user_id] = conversation[-8:]
        await log_activity(user_id, "ai_chat", f"provider={ai_result.provider or 'none'}")
        await deliver_ai_text(message, ai_msg, ai_result.text)
    elif ai_result.reason == "quota":
        await log_activity(user_id, "ai_quota", "implicit_chat")
        await ai_msg.edit_text(ai_error_text("quota"))
    else:
        await log_activity(user_id, "fallback", text)
        await ai_msg.edit_text(random.choice(FUNNY_FALLBACKS))

def clear_user_transient_sessions(user_id: int):
    for collection in [guess_games, hit_run_sessions, memory_games, twenty_one_games, calculator_sessions, broadcast_targets, config_upload_sessions, admin_search_sessions, admin_role_sessions, economy_setting_sessions, reschedule_sessions, ticket_reply_sessions, manual_balance_sessions, ai_sessions, casual_chat_history, promo_sticker_sessions, service_shop_setting_sessions, service_delivery_sessions, service_receipt_sessions, media_request_sessions, prompt_image_sessions, music_search_sessions, music_recognize_sessions, music_playlist_upload_sessions, music_search_cache, quick_quiz_recent, tts_sessions, short_sessions, summarize_sessions, instant_repost_sessions, repost_edit_sessions, scheduled_add_sessions, scheduled_edit_sessions, greeting_add_sessions, greeting_edit_sessions]:
        collection.pop(user_id, None)
    for collection in [broadcast_sessions, withdrawal_sessions, support_sessions, review_sessions, caption_sessions, channel_add_sessions, engagement_post_sessions, repost_sessions, schedule_time_sessions, repost_cta_sessions, promo_create_sessions, gift_redeem_sessions, mission_create_sessions, raffle_create_sessions, prediction_create_sessions, template_create_sessions, qr_sessions, daily_fal_channel_sessions, greeting_target_sessions, music_daily_target_sessions, music_daily_time_sessions, sticker_sessions, gif_sessions, reminder_sessions]:
        collection.discard(user_id)
    cancel_album_buffers(user_id)


async def refresh_runtime_state():
    saved = await settings_col.find_one({"_id": "runtime"}) or {}
    stored_shop = await settings_col.find_one({"_id": "service_shop"}) or {}
    for key in service_shop_settings:
        if key in stored_shop:
            service_shop_settings[key] = stored_shop[key]
    runtime_settings["maintenance"] = bool(saved.get("maintenance", False))
    runtime_settings["force_join"] = bool(saved.get("force_join", FORCE_JOIN_DEFAULT))
    runtime_settings["scheduler_paused"] = bool(saved.get("scheduler_paused", False))
    runtime_settings["repost_cta"] = str(saved.get("repost_cta", DEFAULT_REPOST_CTA) or "")[:300]
    load_daily_fal_runtime(saved)
    load_greeting_runtime(saved)
    load_daily_music_runtime(saved)
    for key, value in (saved.get("economy") or {}).items():
        if key in economy_settings: economy_settings[key] = value
    await refresh_required_channels()
    stored_gate = saved.get("engagement_gate")
    if isinstance(stored_gate, dict): engagement_gate_cache.update(stored_gate)
    delegated = await admins_col.find({"active": {"$ne": False}}).to_list(length=100)
    delegated_admins_cache.clear()
    for item in delegated:
        roles = set(item.get("roles") or ([item.get("role")] if item.get("role") else ["analyst"])); roles.discard(None); delegated_admins_cache[int(item["_id"])] = roles


async def perform_self_heal():
    checks = {"mongo": False, "webhook": False, "commands": False}
    await mongo_client.admin.command("ping"); checks["mongo"] = True
    await refresh_runtime_state()
    await scheduled_posts_col.update_many({"status": "publishing", "publishing_started_at": {"$lt": datetime.now(timezone.utc)-timedelta(minutes=15)}}, {"$set": {"status": "pending"}, "$unset": {"publishing_started_at": ""}})
    await reminders_col.update_many(
        {"status": "sending", "sending_started_at": {"$lt": datetime.now(timezone.utc)-timedelta(minutes=10)}},
        {"$set": {"status": "pending"}, "$unset": {"sending_started_at": ""}},
    )
    await configs_col.delete_many({"expires_at": {"$lte": datetime.now(timezone.utc)}})
    # پاک‌سازی حافظه: حذف کلیدهای قدیمی group_message_times (بیش از ۶۰ ثانیه)
    _now_mono = time.monotonic()
    stale_keys = [k for k, v in group_message_times.items() if not v or _now_mono - v[-1] > 60]
    for k in stale_keys:
        group_message_times.pop(k, None)
    # پاک‌سازی لاک‌های قدیمی ai_request_locks (بیش از ۱ ساعت بدون استفاده)
    stale_locks = [k for k, lk in ai_request_locks.items() if not lk.locked()]
    if len(stale_locks) > 500:
        for k in stale_locks[:len(stale_locks)//2]:
            ai_request_locks.pop(k, None)
    # پاک‌سازی کش کاربران قدیمی
    stale_cache = [k for k, (ts, _) in _user_cache.items() if _now_mono - ts > _USER_CACHE_TTL * 5]
    for k in stale_cache:
        _user_cache.pop(k, None)
    # پاک‌سازی فایل‌های موقت قدیمی (بیش از ۱ ساعت)
    _tmp_cleaned = 0
    for _tmp_dir in Path("/tmp").glob("ajor-*"):
        try:
            if _tmp_dir.is_dir() and time.monotonic() - _tmp_dir.stat().st_mtime > 7200:
                shutil.rmtree(_tmp_dir, ignore_errors=True)
                _tmp_cleaned += 1
        except Exception:
            pass
    if _tmp_cleaned:
        log.info("پاک‌سازی %d پوشه موقت قدیمی", _tmp_cleaned)
    news_cache["expires_at"] = 0; occasion_cache["expires_at"] = 0
    await configure_telegram_ui(); checks["commands"] = True
    if USE_WEBHOOK:
        expected = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"; info = await bot.get_webhook_info()
        if info.url != expected:
            await bot.set_webhook(url=expected, secret_token=WEBHOOK_SECRET, allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=False, max_connections=40)
        checks["webhook"] = True
    else: checks["webhook"] = True
    return checks


async def run_user_self_heal(message: types.Message, admin_mode: bool = False):
    status = await message.answer("🔄 در حال بررسی نسخه، اتصال‌ها و بروزرسانی تنظیمات...")
    try:
        if not admin_mode: clear_user_transient_sessions(message.from_user.id)
        checks = await perform_self_heal()
        version = os.getenv("RAILWAY_GIT_COMMIT_SHA", "نسخه فعال Railway")[:8]
        await status.edit_text(
            "✅ ربات بروزرسانی و خودترمیم شد.\n\n"
            f"MongoDB: {'✅' if checks['mongo'] else '❌'}\nWebhook: {'✅' if checks['webhook'] else '❌'}\n"
            f"منوها و تنظیمات: {'✅' if checks['commands'] else '❌'}\nنسخه: <code>{version}</code>\n\n"
            "ربات آماده انجام دستورات است ⚡",
            parse_mode="HTML",
        )
    except Exception as exc:
        log.exception("خودترمیم دستی ناموفق بود: %s", exc)
        try:
            await health_events_col.insert_one({"type": "self_heal_failed", "message": str(exc)[:1000], "created_at": datetime.now(timezone.utc)})
        except Exception:
            pass
        try:
            await configure_telegram_ui()
        except Exception:
            pass
        if admin_mode:
            await status.edit_text("⚠️ بخشی از بررسی فنی کامل نشد؛ خطا ثبت شد و ربات آنلاین باقی ماند.")
        else:
            await status.edit_text(
                "✅ بروزرسانی رابط ربات انجام شد.\n\n"
                "منوها تازه شدند و ربات آنلاین و آماده استفاده است ⚡\n"
                "اگر مشکل قبلی ادامه داشت، از بخش پشتیبانی گزارش بده."
            )
    await message.answer("منوی فعلی پایین چت باقی می‌مونه.", reply_markup=admin_health_reply_menu() if admin_mode else support_reply_menu())


async def self_heal_worker():
    await asyncio.sleep(120)
    while True:
        try: await perform_self_heal()
        except asyncio.CancelledError: raise
        except Exception as exc:
            log.warning("خودترمیم دوره‌ای ناموفق بود: %s", exc)
            try: await health_events_col.insert_one({"type": "periodic_self_heal_failed", "message": str(exc)[:1000], "created_at": datetime.now(timezone.utc)})
            except Exception: pass
        await asyncio.sleep(15 * 60)


@dp.errors()
async def global_error_handler(event: types.ErrorEvent):
    log.error("خطای پردازش‌نشده: %s", event.exception, exc_info=event.exception)
    try: await health_events_col.insert_one({"type":"unhandled_error","message":str(event.exception)[:1000],"created_at":datetime.now(timezone.utc)})
    except Exception: pass
    return True


async def publish_scheduled_job(job: dict):
    sent = 0
    failed_payloads = []
    for payload in job.get("items", []):
        try:
            await send_repost_payload(int(job.get("channel_id", CHANNEL_ID)), payload)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await send_repost_payload(int(job.get("channel_id", CHANNEL_ID)), payload)
                sent += 1
            except Exception as retry_exc:
                failed_payloads.append(payload)
                log.warning("پست زمان‌دار بعد از retry ناموفق بود: %s", retry_exc)
        except Exception as exc:
            failed_payloads.append(payload)
            log.warning("انتشار پست زمان‌دار ناموفق بود: %s", exc)
        await asyncio.sleep(0.7)
    status = "completed" if not failed_payloads else "failed"
    await scheduled_posts_col.update_one(
        {"_id": job["_id"]},
        {"$set": {
            "status": status,
            "published_at": datetime.now(timezone.utc),
            "sent_count": sent,
            "failed_count": len(failed_payloads),
            "failed_items": failed_payloads,
        }},
    )
    if status == "completed" and job.get("repeat") in {"daily", "weekly"}:
        delta = timedelta(days=1 if job["repeat"] == "daily" else 7)
        next_job = {key: value for key, value in job.items() if key not in {"_id", "status", "publishing_started_at"}}
        next_job.update({"_id": uuid.uuid4().hex[:10], "status": "pending", "scheduled_at": job["scheduled_at"] + delta, "created_at": datetime.now(timezone.utc)})
        await scheduled_posts_col.insert_one(next_job)
    text = (
        f"✅ زمان‌بندی #{job['_id']} منتشر شد؛ {sent} پست موفق."
        if status == "completed"
        else f"⚠️ زمان‌بندی #{job['_id']} ناقص بود؛ {sent} موفق و {len(failed_payloads)} ناموفق."
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


async def scheduled_posts_worker():
    while True:
        try:
            if runtime_settings.get("scheduler_paused"):
                await asyncio.sleep(10); continue
            job = await scheduled_posts_col.find_one_and_update(
                {"status": "pending", "scheduled_at": {"$lte": datetime.now(timezone.utc)}},
                {"$set": {"status": "publishing", "publishing_started_at": datetime.now(timezone.utc)}},
                sort=[("scheduled_at", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if not job:
                await asyncio.sleep(10)
                continue
            await publish_scheduled_job(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("خطای worker پست زمان‌دار: %s", exc)
            await asyncio.sleep(10)


def _next_recurrence(previous: datetime, repeat: str) -> datetime:
    """زمان بعدی یادآور تکراری بر اساس اجرای قبلی."""
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    if repeat == "daily":
        return previous + timedelta(days=1)
    if repeat == "weekly":
        return previous + timedelta(days=7)
    if repeat == "monthly":
        # ماه بعد (حداکثر ۲۸ روز برای پایداری)
        month = previous.month + 1
        year = previous.year + (1 if month > 12 else 0)
        month = ((month - 1) % 12) + 1
        day = min(previous.day, 28)
        return previous.replace(year=year, month=month, day=day)
    return previous + timedelta(days=1)


async def user_reminders_worker():
    while True:
        try:
            reminder = await reminders_col.find_one_and_update(
                {"status": "pending", "scheduled_at": {"$lte": datetime.now(timezone.utc)}},
                {"$set": {"status": "sending", "sending_started_at": datetime.now(timezone.utc)}},
                sort=[("scheduled_at", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if not reminder:
                await asyncio.sleep(5)
                continue
            try:
                await bot.send_message(
                    int(reminder["user_id"]),
                    "⏰ <b>یادآوری Ajorpareh</b>\n\n"
                    f"{html.escape(reminder['text'])}\n\n"
                    "برای ساخت یادآور جدید /remind",
                    parse_mode="HTML",
                )
                now_utc = datetime.now(timezone.utc)
                if reminder.get("repeat"):
                    # یادآور تکراری: زمان بعدی را محاسبه و دوباره زمان‌بندی کن
                    next_at = _next_recurrence(reminder["scheduled_at"], reminder["repeat"])
                    if next_at and next_at <= now_utc + timedelta(days=370):
                        await reminders_col.update_one(
                            {"_id": reminder["_id"]},
                            {"$set": {
                                "status": "pending", "scheduled_at": next_at,
                                "last_sent_at": now_utc,
                            }, "$unset": {"sending_started_at": ""}},
                        )
                        continue
                await reminders_col.update_one(
                    {"_id": reminder["_id"]},
                    {"$set": {"status": "sent", "sent_at": now_utc}},
                )
            except TelegramRetryAfter as exc:
                await reminders_col.update_one(
                    {"_id": reminder["_id"]},
                    {"$set": {
                        "status": "pending",
                        "scheduled_at": datetime.now(timezone.utc) + timedelta(seconds=exc.retry_after + 1),
                    }, "$unset": {"sending_started_at": ""}},
                )
            except (TelegramForbiddenError, TelegramBadRequest) as exc:
                await reminders_col.update_one(
                    {"_id": reminder["_id"]},
                    {"$set": {"status": "failed", "failure": type(exc).__name__, "failed_at": datetime.now(timezone.utc)}},
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("خطای worker یادآورها: %s", exc)
            await asyncio.sleep(8)


async def initialize_database():
    await mongo_client.admin.command("ping")
    await missions_col.create_index("slug", unique=True, sparse=True)
    # ===== ایندکس‌های بهینه برای مقیاس‌پذیری (فاز ۳: Scalability) =====
    _index_specs = [
        (activities_col, [("timestamp", -1)]),
        (activities_col, [("user_id", 1), ("timestamp", -1)]),
        (media_jobs_col, [("status", 1), ("created_at", 1)]),
        (media_jobs_col, [("user_id", 1), ("created_at", -1)]),
        (reminders_col, [("status", 1), ("scheduled_at", 1)]),
        (users_col, [("last_activity", -1)]),
        (users_col, [("xp", -1)]),
        (scheduled_posts_col, [("status", 1), ("scheduled_at", 1)]),
        (scheduled_greetings_col, [("kind", 1), ("order", 1)]),
        (scheduled_greetings_col, [("kind", 1), ("active", 1)]),
        (scheduled_message_history_col, [("kind", 1), ("sent_at", -1)]),
        (scheduled_message_history_col, [("sent_at", 1)]),
        (public_music_playlist_col, [("active", 1), ("created_at", -1)]),
        (reviews_col, [("status", 1), ("created_at", -1)]),
        (wallet_transactions_col, [("user_id", 1), ("created_at", -1)]),
        (coin_transactions_col, [("user_id", 1), ("created_at", -1)]),
    ]
    _created = 0
    for _col, _spec in _index_specs:
        try:
            await _col.create_index(_spec, background=True)
            _created += 1
        except Exception:
            pass  # ایندکس از قبل با همین نام/کلید موجود است — مشکلی نیست
    if _created:
        log.info("✅ %d ایندکس دیتابیس ساخته شد", _created)
    await ensure_builtin_missions()
    await seed_scheduled_greetings()
    await scheduled_message_history_col.delete_many({
        "sent_at": {
            "$lt": datetime.now(timezone.utc) - timedelta(days=DAILY_MUSIC_NO_REPEAT_DAYS + 14)
        }
    })
    saved = await settings_col.find_one({"_id": "runtime"}) or {}
    stored_shop = await settings_col.find_one({"_id": "service_shop"}) or {}
    for key in service_shop_settings:
        if key in stored_shop:
            service_shop_settings[key] = stored_shop[key]
    delegated_admins_cache.clear()
    delegated = await admins_col.find({"active": {"$ne": False}}).to_list(length=100)
    for item in delegated:
        roles = set(item.get("roles") or ([item.get("role")] if item.get("role") else ["analyst"]))
        roles.discard(None); delegated_admins_cache[int(item["_id"])] = roles
        if "roles" not in item:
            await admins_col.update_one({"_id": item["_id"]}, {"$set": {"roles": sorted(roles)}, "$unset": {"role": ""}})
    runtime_settings["maintenance"] = bool(saved.get("maintenance", False))
    runtime_settings["force_join"] = bool(saved.get("force_join", FORCE_JOIN_DEFAULT))
    runtime_settings["scheduler_paused"] = bool(saved.get("scheduler_paused", False))
    runtime_settings["repost_cta"] = str(saved.get("repost_cta", DEFAULT_REPOST_CTA) or "")[:300]
    load_daily_fal_runtime(saved)
    load_greeting_runtime(saved)
    load_daily_music_runtime(saved)
    stored_economy = saved.get("economy") or {}
    for key in economy_settings:
        if key in stored_economy:
            economy_settings[key] = stored_economy[key]
    await scheduled_posts_col.update_many(
        {"status": "publishing", "publishing_started_at": {"$lt": datetime.now(timezone.utc) - timedelta(minutes=15)}},
        {"$set": {"status": "pending"}, "$unset": {"publishing_started_at": ""}},
    )
    await reminders_col.update_many(
        {"status": "sending", "sending_started_at": {"$lt": datetime.now(timezone.utc) - timedelta(minutes=10)}},
        {"$set": {"status": "pending"}, "$unset": {"sending_started_at": ""}},
    )

    # مهاجرت خودکار کانال قدیمی به سیستم چندکاناله، فقط در اولین اجرا.
    if not saved.get("channels_initialized"):
        if await required_channels_col.count_documents({}) == 0:
            await required_channels_col.insert_one({
                "_id": CHANNEL_ID,
                "title": "کانال Ajorpareh",
                "join_url": CHANNEL_LINK,
                "active": True,
                "added_at": datetime.now(timezone.utc),
                "added_by": ADMIN_ID,
            })
        await settings_col.update_one(
            {"_id": "runtime"},
            {"$set": {"channels_initialized": True}},
            upsert=True,
        )
    await refresh_required_channels()

    stored_gate = saved.get("engagement_gate")
    if isinstance(stored_gate, dict):
        engagement_gate_cache.update(stored_gate)

    # ایندکس‌ها جلوی دعوت/تیکت تکراری را می‌گیرند و پنل را سریع نگه می‌دارند.
    await asyncio.gather(
        users_col.create_index("last_activity"),
        users_col.create_index([("xp", -1), ("games_won", -1)]),
        users_col.create_index("username"),
        activities_col.create_index([("user_id", 1), ("timestamp", -1)]),
        activities_col.create_index("timestamp", expireAfterSeconds=60 * 60 * 24 * 90),
        tickets_col.create_index("ticket_id", unique=True),
        tickets_col.create_index([("status", 1), ("created_at", 1)]),
        withdrawals_col.create_index("withdrawal_id", unique=True),
        withdrawals_col.create_index([("status", 1), ("created_at", 1)]),
        broadcasts_col.create_index("created_at"),
        configs_col.create_index([("category", 1), ("uploaded_at", -1)]),
        required_channels_col.create_index("active"),
        profiles_col.create_index("updated_at"),
        scheduled_posts_col.create_index([("status", 1), ("scheduled_at", 1)]),
        managed_chats_col.create_index([("status", 1), ("updated_at", -1)]),
        warnings_col.create_index([("chat_id", 1), ("count", -1)]),
        channel_posts_col.create_index("published_at"),
        channel_reaction_events_col.create_index([("user_id", 1), ("created_at", -1)]),
        channel_reaction_events_col.create_index([("chat_id", 1), ("message_id", -1)]),
        wallet_transactions_col.create_index([("user_id", 1), ("created_at", -1)]),
        miniapp_rewards_col.create_index([("user_id", 1), ("day", 1)]),
        admin_audit_col.create_index("created_at"),
        referral_events_col.create_index([("referrer_id", 1), ("created_at", -1)]),
        promo_codes_col.create_index("expires_at"),
        promo_redemptions_col.create_index([("user_id", 1), ("created_at", -1)]),
        missions_col.create_index([("active", 1), ("created_at", -1)]),
        missions_col.create_index("slug", unique=True, sparse=True),
        mission_claims_col.create_index([("user_id", 1), ("created_at", -1)]),
        content_templates_col.create_index("updated_at"),
        health_events_col.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 30),
        coin_transactions_col.create_index([("user_id", 1), ("created_at", -1)]),
        score_events_col.create_index([("created_at", -1), ("user_id", 1)]),
        shop_purchases_col.create_index([("user_id", 1), ("created_at", -1)]),
        raffles_col.create_index([("status", 1), ("ends_at", 1)]),
        raffle_entries_col.create_index([("raffle_id", 1), ("user_id", 1)]),
        predictions_col.create_index([("status", 1), ("ends_at", 1)]),
        prediction_bets_col.create_index([("prediction_id", 1), ("user_id", 1)]),
        sponsor_rewards_col.create_index([("user_id", 1), ("created_at", -1)]),
        wheel_spins_col.create_index([("user_id", 1), ("created_at", -1)]),
        service_orders_col.create_index([("user_id", 1), ("created_at", -1)]),
        service_orders_col.create_index([("status", 1), ("created_at", 1)]),
        user_services_col.create_index([("user_id", 1), ("expires_at", -1)]),
        ai_usage_col.create_index([("user_id", 1), ("day", -1)]),
        ai_usage_col.create_index("expires_at", expireAfterSeconds=0),
        ai_provider_metrics_col.create_index([("provider", 1), ("day", -1)]),
        ai_provider_metrics_col.create_index("expires_at", expireAfterSeconds=0),
        reminders_col.create_index([("status", 1), ("scheduled_at", 1)]),
        reminders_col.create_index([("user_id", 1), ("status", 1), ("scheduled_at", 1)]),
        reviews_col.create_index([("user_id", 1), ("day", 1)], unique=True),
        reviews_col.create_index([("status", 1), ("published_at", -1)]),
        media_jobs_col.create_index([("status", 1), ("created_at", 1)]),
        media_jobs_col.create_index([("user_id", 1), ("created_at", -1)]),
        media_jobs_col.create_index("expires_at", expireAfterSeconds=0),
        group_settings_col.create_index("_id"),
    )


def group_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="modpanel", description="پنل مدیریت گروه"),
        BotCommand(command="commands", description="راهنمای همه دستورات مدیریت"),
        BotCommand(command="warn", description="اخطار به کاربر (با ریپلای)"),
        BotCommand(command="mute", description="سکوت کاربر؛ مثال /mute 60"),
        BotCommand(command="unmute", description="رفع سکوت کاربر"),
        BotCommand(command="kick", description="حذف کاربر از گروه"),
        BotCommand(command="ban", description="بن کاربر از گروه"),
        BotCommand(command="unban", description="رفع بن با آیدی"),
        BotCommand(command="del", description="حذف پیام ریپلای‌شده"),
        BotCommand(command="warnings", description="نمایش اخطارهای کاربر"),
        BotCommand(command="setwelcome", description="تنظیم پیام خوش‌آمد"),
        BotCommand(command="filter", description="مدیریت کلمات ممنوع"),
        BotCommand(command="trust", description="افزودن کاربر به لیست سفید"),
        BotCommand(command="untrust", description="حذف کاربر از لیست سفید"),
        BotCommand(command="allowdomain", description="مدیریت دامنه‌های مجاز"),
    ]


async def install_group_commands(chat_id: int | None = None):
    scope = BotCommandScopeChat(chat_id=chat_id) if chat_id is not None else BotCommandScopeAllGroupChats()
    await bot.set_my_commands(group_bot_commands(), scope=scope)


TELEGRAM_PROFILE_LOCALIZATIONS = (
    {
        "language_code": None,
        "name": "🧱 آجُرپاره | هوش مصنوعی و ابزار تلگرام",
        "short_description": "هوش مصنوعی فارسی، دانلود عمومی، آپلود URL، بازی، یادآور، QR، استیکر، GIF و ابزارهای کاربردی تلگرام.",
        "description": (
            "⚡ آجُرپاره؛ سوپربات فارسی تلگرام\n"
            "🤖 چت، ترجمه، خلاصه، کدنویسی و ساخت تصویر با هوش مصنوعی\n"
            "📥 دانلود محتوای عمومی شبکه‌های اجتماعی و آپلود فایل مستقیم از URL\n"
            "🎮 بازی، جایزه، مأموریت، کیف پول و رتبه‌بندی\n"
            "🛠 یادآور، QR، استیکر، GIF، خبر و ابزار مدیریت گروه\n\n"
            "برای شروع /start یا /menu را بفرست و Mini App را باز کن.\n"
            "کانال رسمی: @Ajor_pareh"
        ),
    },
    {
        "language_code": "fa",
        "name": "🧱 آجُرپاره | هوش مصنوعی و ابزار تلگرام",
        "short_description": "هوش مصنوعی فارسی، دانلود عمومی، آپلود URL، بازی، یادآور، QR، استیکر، GIF و ابزارهای کاربردی تلگرام.",
        "description": (
            "⚡ آجُرپاره؛ سوپربات فارسی تلگرام\n"
            "🤖 چت، ترجمه، خلاصه، کدنویسی و ساخت تصویر با هوش مصنوعی\n"
            "📥 دانلود محتوای عمومی شبکه‌های اجتماعی و آپلود فایل مستقیم از URL\n"
            "🎮 بازی، جایزه، مأموریت، کیف پول و رتبه‌بندی\n"
            "🛠 یادآور، QR، استیکر، GIF، خبر و ابزار مدیریت گروه\n\n"
            "برای شروع /start یا /menu را بفرست و Mini App را باز کن.\n"
            "کانال رسمی: @Ajor_pareh"
        ),
    },
    {
        "language_code": "en",
        "name": "Ajorpareh | AI & Telegram Tools",
        "short_description": "Persian AI, public media downloads, URL uploads, games, reminders, QR, stickers, GIFs and Telegram tools.",
        "description": (
            "Ajorpareh is a Persian Telegram super bot for AI chat, translation, summaries, coding and image creation; "
            "public social-media downloads; direct URL uploads; reminders, QR codes, stickers, GIFs, games, rewards "
            "and group tools. Send /start or /menu to begin. Official channel: @Ajor_pareh"
        ),
    },
)
telegram_profile_synced = False


async def configure_telegram_profile():
    global telegram_profile_synced
    if telegram_profile_synced:
        return
    synced = True
    for profile in TELEGRAM_PROFILE_LOCALIZATIONS:
        language_code = profile["language_code"]
        kwargs = {"language_code": language_code} if language_code else {}
        try:
            current_name = await bot.get_my_name(**kwargs)
            if current_name.name != profile["name"]:
                await bot.set_my_name(name=profile["name"], **kwargs)
            current_short = await bot.get_my_short_description(**kwargs)
            if current_short.short_description != profile["short_description"]:
                await bot.set_my_short_description(short_description=profile["short_description"], **kwargs)
            current_description = await bot.get_my_description(**kwargs)
            if current_description.description != profile["description"]:
                await bot.set_my_description(description=profile["description"], **kwargs)
        except Exception as exc:
            synced = False
            log.warning("بروزرسانی پروفایل تلگرام برای زبان %s ناموفق بود: %s", language_code or "default", exc)
    telegram_profile_synced = synced


async def configure_telegram_ui():
    await configure_telegram_profile()
    user_commands = [
        BotCommand(command="start", description="شروع آجُرپاره و فعال‌کردن منوی فارسی"),
        BotCommand(command="menu", description="نمایش منوی کامل ابزارها و خدمات"),
        BotCommand(command="app", description="بازکردن Mini App بازی و ابزارها"),
        BotCommand(command="ai", description="هوش مصنوعی فارسی؛ چت، متن و تصویر"),
        BotCommand(command="voice", description="تبدیل ویس و فایل صوتی به متن"),
        BotCommand(command="download", description="دانلود محتوای عمومی شبکه‌های اجتماعی"),
        BotCommand(command="igcomment", description="کپی متن کامنت عمومی اینستاگرام از روی لینک"),
        BotCommand(command="uploadurl", description="ارسال فایل مستقیم از URL به تلگرام"),
        BotCommand(command="checklink", description="بررسی ساختار و نشانه‌های مشکوک لینک"),
        BotCommand(command="remind", description="ساخت یادآور شخصی؛ زمان | متن"),
        BotCommand(command="reminders", description="نمایش یادآورهای فعال من"),
        BotCommand(command="games", description="بازی‌ها، چالش‌ها و جایزه‌ها"),
        BotCommand(command="qr", description="ساخت QR از متن یا لینک"),
        BotCommand(command="sticker", description="ساخت استیکر و پک اختصاصی تلگرام"),
        BotCommand(command="gif", description="ساخت GIF تلگرامی از عکس یا ویدئو"),
        BotCommand(command="caption", description="ساخت کپشن جذاب و هشتگ"),
        BotCommand(command="truth", description="بازی جرأت یا حقیقت"),
        BotCommand(command="emoji_api", description="راهنمای API شکلک‌های سفارشی"),
        BotCommand(command="weather", description="آب‌وهوای شهرها (فارسی/انگلیسی)"),
        BotCommand(command="rate", description="نرخ ارز؛ مثال: /rate usd eur"),
        BotCommand(command="crypto", description="قیمت ارز دیجیتال؛ مثال: /crypto btc"),
        BotCommand(command="wiki", description="خلاصه ویکی‌پدیا؛ مثال: /wiki نوروز"),
        BotCommand(command="book", description="جستجوی کتاب؛ مثال: /book بوف کور"),
        BotCommand(command="country", description="اطلاعات کشور؛ مثال: /country ایران"),
        BotCommand(command="time", description="ساعت جهانی؛ مثال: /time تهران"),
        BotCommand(command="checkpass", description="بررسی امنیت رمز عبور"),
        BotCommand(command="quiz", description="کوئیز جهانی Open Trivia"),
        BotCommand(command="calendar", description="تقویم شمسی با مناسبت‌ها"),
        BotCommand(command="tts", description="تبدیل متن به صدا؛ مثال: /tts سلام"),
        BotCommand(command="ttsvoice", description="انتخاب صدای زن یا مرد"),
        BotCommand(command="mystats", description="آمار شخصی تو در ربات"),
        BotCommand(command="short", description="کوتاه‌کردن لینک"),
        BotCommand(command="summarize", description="خلاصه‌سازی متن با هوش مصنوعی"),
        BotCommand(command="pray", description="اوقات شرعی؛ مثال: /pray تهران"),
        BotCommand(command="fal", description="فال حافظ"),
        BotCommand(command="falsub", description="فال روزانه صبحگاهی (اشتراک)"),
        BotCommand(command="praysub", description="اذان‌گوی شخصی (اشتراک)"),
        BotCommand(command="song", description="جستجو و دانلود آهنگ"),
        BotCommand(command="profile", description="امتیاز، رتبه، سکه و استریک من"),
        BotCommand(command="joke", description="دریافت یک جوک باحال"),
        BotCommand(command="quote", description="دریافت جمله انگیزشی"),
        BotCommand(command="help", description="راهنمای ربات و ارتباط با پشتیبانی"),
        BotCommand(command="cancel", description="لغو عملیات فعال"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    await install_group_commands()
    # محدوده اختصاصی هر گروه، تنظیمات قدیمی یا کش تلگرام را هم بازنویسی می‌کند.
    managed_groups = await managed_chats_col.find({"type": {"$in": ["group", "supergroup"]}, "status": {"$in": ["administrator", "creator", "member", "active"]}}, {"_id": 1}).limit(100).to_list(length=100)
    for managed in managed_groups:
        try:
            await install_group_commands(managed["_id"])
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            log.warning("ثبت دستورات گروه %s ممکن نشد: %s", managed["_id"], exc)
    admin_commands = user_commands + [
        BotCommand(command="admin", description="پنل مدیریت حرفه‌ای"),
        BotCommand(command="channels", description="مدیریت کانال‌های اجباری"),
        BotCommand(command="repost", description="بازنشر گروهی و برندینگ"),
        BotCommand(command="quickpost", description="انتشار فوری بدون تأیید"),
        BotCommand(command="configs", description="لیست و حذف پروکسی/کانفیگ"),
        BotCommand(command="search", description="جستجوی کاربر"),
        BotCommand(command="activity", description="فعالیت کاربر با آیدی"),
        BotCommand(command="ban", description="مسدودکردن کاربر"),
        BotCommand(command="unban", description="رفع مسدودی کاربر"),
        BotCommand(command="ping", description="بررسی سلامت ربات"),
    ]
    for admin_id in set(ADMIN_IDS) | set(delegated_admins_cache):
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramBadRequest as exc:
            # اگر ادمین هنوز /start نزده باشد، تلگرام scope اختصاصی را رد می‌کند.
            log.warning("ثبت منوی ادمین %s ممکن نشد: %s", admin_id, exc)
    # آیکون Mini App پایین چت حفظ می‌شود؛ منوی بزرگ دکمه‌ای توسط ReplyKeyboardMarkup داخل چت نمایش داده می‌شود.
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🎮 بازی کن", web_app=WebAppInfo(url=MINI_APP_URL)))


def clean_feed_text(value: str | None, limit: int = 240) -> str:
    if not value:
        return ""
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit] + ("…" if len(value) > limit else "")


def parse_feed_date(value: str | None) -> tuple[float, str | None]:
    if not value:
        return 0.0, None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        return parsed.timestamp(), parsed.isoformat()
    except (TypeError, ValueError, OverflowError):
        return 0.0, None


def parse_rss_items(xml_body: bytes, source: str, category: str, icon: str) -> list[dict]:
    root = ElementTree.fromstring(xml_body)
    result: list[dict] = []
    for item in root.findall(".//item")[:8]:
        title = clean_feed_text(item.findtext("title"), 170)
        link = clean_feed_text(item.findtext("link"), 500)
        item_source = clean_feed_text(item.findtext("source"), 60) or source
        description = item.findtext("description") or ""
        published_raw = item.findtext("pubDate") or item.findtext("date")
        timestamp, published_at = parse_feed_date(published_raw)
        image = ""
        image_match = re.search(r"<img[^>]+src=[\"']([^\"']+)", description, flags=re.I)
        if image_match:
            image = image_match.group(1)
        for node in item.iter():
            local_tag = node.tag.rsplit("}", 1)[-1].lower()
            if local_tag in {"thumbnail", "content", "enclosure"} and node.attrib.get("url"):
                candidate = node.attrib["url"]
                media_type = node.attrib.get("type", "")
                if "image" in media_type or re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)", candidate, re.I):
                    image = candidate
                    break
        if category in {"tech", "iran"} and title and not re.search(r"[\u0600-\u06FF]", title):
            continue
        if title and link.startswith("http"):
            result.append({
                "title": title,
                "url": link,
                "summary": clean_feed_text(description, 230),
                "source": item_source,
                "category": category,
                "icon": icon,
                "image": image,
                "published_at": published_at,
                "_timestamp": timestamp,
            })
    return result


async def fetch_news_feed(url: str, source: str, category: str, icon: str) -> list[dict]:
    if http_session is None:
        return []
    try:
        headers = {"User-Agent": "Ajorpareh-News/1.0 (+https://t.me/Ajor_pareh)"}
        async with http_session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as response:
            if response.status != 200:
                log.warning("RSS %s returned %s", source, response.status)
                return []
            return parse_rss_items(await response.read(), source, category, icon)
    except (aiohttp.ClientError, asyncio.TimeoutError, ElementTree.ParseError, ValueError) as exc:
        log.warning("RSS %s failed: %s", source, exc)
        return []


async def get_live_news_items(refresh: bool = False) -> list[dict]:
    now = time.monotonic()
    async with news_cache_lock:
        if refresh or not news_cache["items"] or now >= news_cache["expires_at"]:
            batches = await asyncio.gather(*(fetch_news_feed(*feed) for feed in NEWS_FEEDS))
            seen: set[str] = set()
            items: list[dict] = []
            for entry in sorted(
                (row for batch in batches for row in batch),
                key=lambda row: row["_timestamp"],
                reverse=True,
            ):
                normalized = re.sub(r"\W+", "", entry["title"].lower())
                if normalized in seen:
                    continue
                seen.add(normalized)
                item = {key: value for key, value in entry.items() if key != "_timestamp"}
                items.append(item)
                if len(items) >= 24:
                    break
            if items:
                news_cache.update({
                    "items": items,
                    "expires_at": now + NEWS_CACHE_TTL,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
    return list(news_cache["items"])


async def send_live_news_to_bot(message: types.Message, category: str | None = None, refresh: bool = False):
    waiting = await message.answer("📡 دارم خبرهای تازه رو از منابع RSS می‌گیرم...")
    items = await get_live_news_items(refresh=refresh)
    if category:
        items = [item for item in items if item.get("category") == category]
    items = items[:6]
    if not items:
        try:
            await waiting.edit_text(
                "⚠️ فعلاً منبع خبری جواب نداد. چند دقیقه دیگه «🔄 تازه‌ترین خبرها» رو بزن.",
            )
        except TelegramBadRequest:
            await message.answer("⚠️ خبرها موقتاً در دسترس نیستند.", reply_markup=live_news_reply_menu())
        return
    labels = {"iran": "ایران", "world": "جهان", "tech": "فناوری"}
    lines = [f"📰 <b>خبرهای تازه {labels.get(category, 'روز')}</b>", ""]
    for index, item in enumerate(items, 1):
        title = html.escape(item.get("title") or "بدون عنوان")
        url = html.escape(item.get("url") or "", quote=True)
        source = html.escape(item.get("source") or "RSS")
        lines.append(f"{index}. <a href=\"{url}\">{title}</a>\n   <i>{source}</i>")
    lines.extend(["", "منبع هر خبر مشخص است؛ برای متن کامل روی عنوان بزن."])
    try:
        await waiting.edit_text(
            "\n".join(lines)[:4000],
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramBadRequest:
        await message.answer(
            "\n".join(lines)[:4000],
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=live_news_reply_menu(),
        )


async def news_api(request: web.Request):
    items = await get_live_news_items(refresh=request.query.get("refresh") == "1")
    response = web.json_response({
        "ok": bool(items),
        "items": items,
        "updated_at": news_cache["updated_at"],
        "cache_seconds": NEWS_CACHE_TTL,
        "notice": "عنوان‌ها و خلاصه‌ها از RSS عمومی منابع نمایش داده می‌شوند.",
    })
    response.headers["Cache-Control"] = "public, max-age=120"
    return response


async def fetch_public_channel_posts() -> list[dict]:
    if http_session is None:
        return []
    try:
        async with http_session.get(
            "https://t.me/s/Ajor_pareh",
            headers={"User-Agent": "Mozilla/5.0 (Ajorpareh Mini App)"},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as response:
            if response.status != 200:
                return []
            body = await response.text(errors="ignore")
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return []
    post_ids = re.findall(r'data-post="ajor_pareh/(\d+)"', body, flags=re.I)
    texts = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', body, flags=re.I | re.S)
    posts = []
    for post_id, raw_text in zip(post_ids, texts, strict=False):
        text = clean_feed_text(raw_text, 500)
        if not text:
            continue
        posts.append({
            "id": int(post_id),
            "text": text,
            "title": text[:95] + ("…" if len(text) > 95 else ""),
            "url": f"https://t.me/Ajor_pareh/{post_id}",
            "media_type": "channel",
        })
    return list(reversed(posts[-12:]))


async def send_channel_trends_to_bot(message: types.Message):
    stored = await channel_posts_col.find().sort("_id", -1).limit(6).to_list(length=6)
    items = [{
        "text": clean_feed_text(item.get("text"), 150),
        "url": item.get("url") or f"https://t.me/Ajor_pareh/{item['_id']}",
    } for item in stored]
    if not items:
        online = await fetch_public_channel_posts()
        items = [{"text": item.get("title") or item.get("text") or "پست جدید", "url": item.get("url")} for item in online[:6]]
    if not items:
        return await message.answer(f"فعلاً پست تازه‌ای پیدا نکردم؛ مستقیم کانال رو ببین:\n{CHANNEL_LINK}", reply_markup=news_reply_menu())
    lines = ["🔥 <b>داغ‌های تازه @Ajor_pareh</b>", ""]
    for index, item in enumerate(items, 1):
        lines.append(f"{index}. <a href=\"{html.escape(item['url'] or CHANNEL_LINK, quote=True)}\">{html.escape(item['text'] or 'پست جدید')}</a>")
    await message.answer(
        "\n\n".join(lines)[:4000],
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=news_reply_menu(),
    )


async def channel_posts_api(request: web.Request):
    stored = await channel_posts_col.find().sort("_id", -1).limit(12).to_list(length=12)
    items = [{
        "id": item["_id"],
        "text": clean_feed_text(item.get("text"), 500),
        "title": clean_feed_text(item.get("text"), 95),
        "url": item.get("url"),
        "media_type": item.get("media_type", "text"),
        "published_at": item.get("published_at").isoformat() if isinstance(item.get("published_at"), datetime) else None,
    } for item in stored]
    if len(items) < 6:
        online = await fetch_public_channel_posts()
        known = {item["url"] for item in items}
        items.extend(item for item in online if item["url"] not in known)
    response = web.json_response({"ok": True, "channel": "@Ajor_pareh", "items": items[:12]})
    response.headers["Cache-Control"] = "public, max-age=120"
    return response


async def joke_api(request: web.Request):
    fresh = request.query.get("fresh") == "1"
    if fresh:
        joke = random.choice(WEB_JOKES)
    else:
        seed = f"{today_str()}:{request.query.get('user', 'guest')}"
        joke = WEB_JOKES[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(WEB_JOKES)]
    return web.json_response({"ok": True, "joke": joke, "date": today_str()})


async def challenges_api(request: web.Request):
    day_seed = int(hashlib.sha256(today_str().encode()).hexdigest(), 16)
    challenges = [
        {"id": "reverse", "title": "تایپ معکوس", "description": "کلمه را در ۱۲ ثانیه برعکس تایپ کن.", "xp": 90, "emoji": "🔄"},
        {"id": "memory", "title": "حافظه میم", "description": "۶ جفت ایموجی را با کمترین حرکت پیدا کن.", "xp": 140, "emoji": "🧠"},
        {"id": "tap", "title": "طوفان ضربه", "description": "در ۱۰ ثانیه رکورد لمس بساز.", "xp": 120, "emoji": "👆"},
        {"id": "laugh", "title": "نخندیدن", "description": "۱۰ ثانیه با صورت کاملاً جدی مقاومت کن.", "xp": 250, "emoji": "😐"},
    ]
    featured = challenges[day_seed % len(challenges)]
    # چالش روزانه ویژه با جایزه دوبرابر
    daily_game_ids = ["snake", "ajorchin", "reflex", "memory", "tap"]
    daily_game = daily_game_ids[day_seed % len(daily_game_ids)]
    daily_titles = {"snake": "🐍 مار غذایی", "ajorchin": "🧱 آجرچین", "reflex": "⚡ شکار لحظه", "memory": "🧠 حافظه میم", "tap": "👆 طوفان ضربه"}
    return web.json_response({"ok": True, "featured": featured, "items": challenges, "date": today_str(),
        "daily_challenge": {
            "game": daily_game,
            "title": daily_titles.get(daily_game, daily_game),
            "target_score": (day_seed % 5 + 2) * 500,
            "bonus_xp": 200,
            "bonus_coins": 50,
            "description": f"بازی {daily_titles.get(daily_game, daily_game)} رو انجام بده و امتیاز بالا بزن!",
        }
    })


def translate_online_occasion(title: str) -> str:
    normalized = str(title or "").strip().replace("’", "'")
    translated = ONLINE_OCCASION_TRANSLATIONS.get(title) or ONLINE_OCCASION_TRANSLATIONS.get(normalized)
    if translated:
        return translated
    lowered = normalized.lower()
    if "men" in lowered and "day" in lowered:
        return "روز جهانی مردان"
    if "women" in lowered and "day" in lowered:
        return "روز جهانی زنان"
    if lowered.startswith("world ") and lowered.endswith(" day"):
        subject = normalized[6:-4].strip()
        generic_subjects = {
            "music": "موسیقی",
            "water": "آب",
            "poetry": "شعر",
            "theatre": "تئاتر",
            "theater": "تئاتر",
            "sleep": "خواب",
            "consumer rights": "حقوق مصرف‌کننده",
            "press freedom": "آزادی مطبوعات",
        }
        return f"روز جهانی {generic_subjects.get(subject.lower(), 'یک موضوع جهانی')}"
    if lowered.startswith("international ") and lowered.endswith(" day"):
        return "مناسبت بین‌المللی امروز"
    # هیچ عنوان انگلیسی خام را به Mini App تحویل نمی‌دهیم.
    return "مناسبت بین‌المللی امروز"


async def fetch_online_occasions(year: int, month: int, day: int) -> list[dict]:
    if http_session is None:
        return []
    url = f"https://www.checkiday.com/{month}/{day}/{year}"
    try:
        async with http_session.get(
            url,
            headers={"User-Agent": "Ajorpareh-Calendar/1.0 (+https://t.me/Ajor_pareh)"},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as response:
            if response.status != 200:
                return []
            body = await response.text(errors="ignore")
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return []
    titles = re.findall(r"<h2[^>]*>\s*<a[^>]*>(.*?)</a>", body, flags=re.I | re.S)
    cleaned: list[str] = []
    for raw_title in titles:
        title = clean_feed_text(raw_title, 100)
        if title and title not in {"Daily Updates"} and title not in cleaned:
            # مناسبت‌های ملی کشورهای خارجی (National ...) برای کاربر ایرانی معنا ندارند
            lowered = title.lower()
            if lowered.startswith("national "):
                continue
            if lowered.startswith("on this day"):
                continue
            cleaned.append(title)
    # مناسبت‌های جهانی/بین‌المللی و Rain Day بر مناسبت‌های صرفاً ملی اولویت دارند.
    cleaned.sort(
        key=lambda title: (
            0 if title in ONLINE_OCCASION_TRANSLATIONS else
            1 if title.startswith(("World ", "International ")) or title == "Rain Day" else 2,
            title,
        )
    )
    return [
        {"title": translate_online_occasion(title), "original_title": title, "source": "Checkiday"}
        for title in cleaned[:6]
    ]


async def occasion_api(request: web.Request):
    tehran_now = get_tehran_time()
    key = f"{tehran_now.month}-{tehran_now.day}"
    cache_key = tehran_now.strftime("%Y-%m-%d")
    now_monotonic = time.monotonic()
    async with occasion_cache_lock:
        if occasion_cache["key"] != cache_key or now_monotonic >= occasion_cache["expires_at"]:
            online = await fetch_online_occasions(tehran_now.year, tehran_now.month, tehran_now.day)
            occasion_cache.update({"key": cache_key, "expires_at": now_monotonic + OCCASION_CACHE_TTL, "online": online})
    curated = CURATED_WORLD_DAYS.get(key, [])
    items: list[dict] = []
    known_titles: set[str] = set()
    # اول مناسبت‌های شمسی و قمری (تقویم ایرانی) — مهم‌ترین‌ها برای کاربر
    try:
        cal_info = cal_today_info(tehran_now)
        for title in cal_info.get("occasions") or []:
            t = str(title).strip()
            if t and t not in known_titles:
                items.append({"title": t, "source": "تقویم شمسی"})
                known_titles.add(t)
    except Exception:
        pass
    # بعد مناسبت‌های جهانی میلادی (کاتالوگ داخلی)
    for title in curated:
        if title not in known_titles:
            items.append({"title": title, "source": "تقویم Ajorpareh"})
            known_titles.add(title)
    # در آخر مناسبت‌های آنلاین (فقط اگر چیزی نداشتیم؛ مناسبت‌های خارجی اولویت آخر دارند)
    for item in occasion_cache["online"]:
        if item["title"] not in known_titles and len(items) < 6:
            items.append(item)
            known_titles.add(item["title"])
    primary = items[0]["title"] if items else "مناسبت‌های امروز در حال بروزرسانی است"
    response = web.json_response({
        "ok": True,
        "tehran_date": cache_key,
        "gregorian": {"year": tehran_now.year, "month": tehran_now.month, "day": tehran_now.day},
        "primary": primary,
        "items": items[:8],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "refresh_seconds": OCCASION_CACHE_TTL,
    })
    response.headers["Cache-Control"] = "public, max-age=900"
    return response


def verify_telegram_init_data(raw_init_data: str) -> dict | None:
    if not raw_init_data or len(raw_init_data) > 10_000:
        return None
    try:
        pairs = dict(parse_qsl(raw_init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", "")
        auth_date = int(pairs.get("auth_date", "0"))
        now = int(time.time())
        if not received_hash or auth_date > now + 60 or now - auth_date > 24 * 60 * 60:
            return None
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            return None
        user = json.loads(pairs.get("user", "{}"))
        return user if isinstance(user, dict) and isinstance(user.get("id"), int) else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def clean_profile_value(value, max_length: int) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", "", str(value or ""))
    return re.sub(r"\s+", " ", value).strip()[:max_length]


def clean_multiline_value(value, max_length: int) -> str:
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value.strip()[:max_length]


async def require_miniapp_user(request: web.Request) -> dict:
    telegram_user = verify_telegram_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if not telegram_user:
        raise web.HTTPUnauthorized(text="Valid Telegram Mini App session required")
    user_id = int(telegram_user["id"])
    if await is_banned(user_id):
        raise web.HTTPForbidden(text="Bot access is restricted")
    await ensure_user(
        user_id,
        " ".join(filter(None, [telegram_user.get("first_name"), telegram_user.get("last_name")])).strip() or "Telegram User",
        username=telegram_user.get("username"),
    )
    return telegram_user


async def miniapp_ai_status_api(request: web.Request):
    user = await require_miniapp_user(request)
    status = ai_service.public_status()
    quota = await ai_service.quota_snapshot(user["id"], unlimited=is_admin(user["id"]))
    response = web.json_response({
        "ok": True,
        "ai": {
            "providers": status["text_providers"],
            "image_providers": status["image_providers"],
            "image_generation": status["image_generation"],
            "quota": quota,
            "modes": ["chat", "rewrite", "translate", "summary", "study", "code", "content", "ideas"],
        },
    })
    response.headers["Cache-Control"] = "no-store"
    return response


async def miniapp_ai_text_api(request: web.Request):
    user = await require_miniapp_user(request)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise web.HTTPBadRequest(text="Invalid JSON") from exc
    mode = str(payload.get("mode", "chat")).strip().lower()
    allowed = {"chat", "rewrite", "translate", "summary", "study", "code", "content", "ideas"}
    if mode not in allowed:
        raise web.HTTPBadRequest(text="Unsupported AI mode")
    prompt = clean_multiline_value(payload.get("prompt"), ai_service.config.max_input_chars)
    if len(prompt) < 2:
        raise web.HTTPBadRequest(text="Prompt is too short")
    history: list[dict[str, str]] = []
    if mode == "chat" and isinstance(payload.get("history"), list):
        for item in payload["history"][-8:]:
            if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
                continue
            content = clean_multiline_value(item.get("content"), 1500)
            if content:
                history.append({"role": item["role"], "content": content})
    details = AI_MODE_CONFIG.get(mode, AI_MODE_CONFIG["chat"])
    result = await ask_ai_detailed(
        prompt,
        user_id=user["id"],
        feature=f"miniapp_{mode}",
        system_prompt=details.get("system", AI_BASE_SYSTEM_PROMPT),
        history=history,
    )
    if not result.ok or not result.text:
        status_code = 429 if result.reason == "quota" else 503
        return web.json_response(
            {"ok": False, "reason": result.reason, "message": ai_error_text(result.reason)},
            status=status_code,
            headers={"Cache-Control": "no-store"},
        )
    await log_activity(user["id"], f"miniapp_ai_{mode}", f"provider={result.provider or 'none'}")
    return web.json_response({
        "ok": True,
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "latency_ms": result.latency_ms,
    }, headers={"Cache-Control": "no-store"})


async def miniapp_ai_image_api(request: web.Request):
    user = await require_miniapp_user(request)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise web.HTTPBadRequest(text="Invalid JSON") from exc
    prompt = clean_profile_value(payload.get("prompt"), ai_service.config.max_input_chars)
    if len(prompt) < 3:
        raise web.HTTPBadRequest(text="Prompt is too short")
    result = await ai_service.generate_image(
        prompt,
        user_id=user["id"],
        unlimited=is_admin(user["id"]),
    )
    if not result.ok or not result.image:
        status_code = 429 if result.reason == "quota" else 503
        return web.json_response(
            {"ok": False, "reason": result.reason, "message": ai_error_text(result.reason, image=True)},
            status=status_code,
            headers={"Cache-Control": "no-store"},
        )
    await users_col.update_one(
        {"_id": user["id"]},
        {"$inc": {"ai_requests_count": 1}, "$set": {"last_ai_request_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    await log_activity(user["id"], "miniapp_ai_image", f"provider={result.provider or 'none'}")
    return web.Response(
        body=result.image,
        content_type=result.mime_type if result.mime_type.startswith("image/") else "image/png",
        headers={
            "Cache-Control": "no-store",
            "X-AI-Provider": result.provider or "unknown",
            "Content-Disposition": "inline; filename=ajorpareh-ai-image",
        },
    )


async def miniapp_reminders_api(request: web.Request):
    user = await require_miniapp_user(request)
    user_id = user["id"]
    if request.method == "POST":
        try:
            payload = await request.json()
            reminder_text = clean_profile_value(payload.get("text"), 500)
            scheduled_at = parse_miniapp_datetime(payload.get("scheduled_at", ""))
            if len(reminder_text) < 2:
                raise ValueError("متن یادآوری خیلی کوتاه است")
            item = await create_user_reminder(user_id, reminder_text, scheduled_at, "miniapp")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response({
            "ok": True,
            "reminder": {
                "id": item["_id"], "text": item["text"],
                "scheduled_at": item["scheduled_at"].isoformat(),
                "display_time": format_tehran_datetime(item["scheduled_at"]),
            },
        }, status=201, headers={"Cache-Control": "no-store"})
    items = await reminders_col.find(
        {"user_id": user_id, "status": "pending"}
    ).sort("scheduled_at", 1).limit(30).to_list(length=30)
    return web.json_response({
        "ok": True,
        "items": [{
            "id": item["_id"], "text": item["text"],
            "scheduled_at": item["scheduled_at"].isoformat(),
            "display_time": format_tehran_datetime(item["scheduled_at"]),
        } for item in items],
    }, headers={"Cache-Control": "no-store"})


async def miniapp_reminder_delete_api(request: web.Request):
    user = await require_miniapp_user(request)
    reminder_id = request.match_info.get("reminder_id", "")
    if not re.fullmatch(r"[a-f0-9]{12}", reminder_id):
        raise web.HTTPBadRequest(text="Invalid reminder id")
    result = await reminders_col.update_one(
        {"_id": reminder_id, "user_id": user["id"], "status": "pending"},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc)}},
    )
    if not result.modified_count:
        raise web.HTTPNotFound(text="Reminder not found")
    return web.json_response({"ok": True}, headers={"Cache-Control": "no-store"})


async def miniapp_profile_api(request: web.Request):
    telegram_user = await require_miniapp_user(request)
    user_id = telegram_user["id"]
    if request.method == "POST":
        try:
            payload = await request.json()
        except Exception as exc:
            raise web.HTTPBadRequest(text="Invalid JSON") from exc
        display_name = clean_profile_value(payload.get("display_name"), 50)
        bio = clean_profile_value(payload.get("bio"), 120)
        if not display_name:
            raise web.HTTPBadRequest(text="Display name is required")
        update = {
            "display_name": display_name,
            "bio": bio,
            "updated_at": datetime.now(timezone.utc),
            "telegram_username": telegram_user.get("username"),
        }
        if payload.get("reset_avatar"):
            update["avatar_data"] = None
        elif "avatar_data" in payload:
            avatar_data = payload.get("avatar_data")
            if avatar_data:
                match = re.match(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$", avatar_data)
                if not match or len(avatar_data) > 400_000:
                    raise web.HTTPBadRequest(text="Avatar must be a small PNG, JPEG or WebP image")
                try:
                    decoded = base64.b64decode(match.group(2), validate=True)
                except ValueError as exc:
                    raise web.HTTPBadRequest(text="Invalid avatar encoding") from exc
                if len(decoded) > 280_000:
                    raise web.HTTPRequestEntityTooLarge(max_size=280_000, actual_size=len(decoded))
                update["avatar_data"] = avatar_data
            else:
                update["avatar_data"] = None
        await profiles_col.update_one(
            {"_id": user_id},
            {"$set": update, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    profile = await profiles_col.find_one({"_id": user_id}) or {}
    telegram_name = " ".join(filter(None, [telegram_user.get("first_name"), telegram_user.get("last_name")])).strip()
    response = web.json_response({
        "ok": True,
        "profile": {
            "user_id": user_id,
            "display_name": profile.get("display_name") or telegram_name or "بازیکن Ajorpareh",
            "username": telegram_user.get("username"),
            "bio": profile.get("bio") or "میم‌باز رسمی Ajorpareh ⚡",
            "avatar": profile.get("avatar_data") or telegram_user.get("photo_url") or None,
            "has_custom_avatar": bool(profile.get("avatar_data")),
        },
    })
    response.headers["Cache-Control"] = "no-store"
    return response


async def wallet_snapshot(user_id: int) -> dict:
    user = await users_col.find_one({"_id": user_id}) or {}
    pending, higher = await asyncio.gather(
        withdrawals_col.find({"user_id": user_id, "status": "pending"}).sort("created_at", -1).limit(10).to_list(length=10),
        users_col.count_documents({"xp": {"$gt": int(user.get("xp", 0))}, "is_banned": {"$ne": True}}),
    )
    games = max(0, int(user.get("games_played", 0)))
    wins = max(0, int(user.get("games_won", 0)))
    return {
        "points": int(user.get("xp", 0)),
        "coins": int(user.get("coins", 0)),
        "wallet_toman": int(user.get("wallet_toman", 0)),
        "referral_count": int(user.get("referral_count", 0)),
        "games_played": games,
        "games_won": wins,
        "win_rate": round(wins * 100 / games) if games else 0,
        "streak": max(0, int(user.get("streak", 0))),
        "rank": int(higher) + 1,
        "level": max(1, int(user.get("xp", 0)) // 500 + 1),
        "point_toman_rate": int(economy_settings["point_toman_rate"]),
        "min_convert_points": int(economy_settings["min_convert_points"]),
        "min_withdraw_toman": int(economy_settings["min_withdraw_toman"]),
        "usdt_toman_rate": int(economy_settings["usdt_toman_rate"]),
        "usdt_network": economy_settings["usdt_network"],
        "referral_points": int(economy_settings["referral_points"]),
        "invite_url": f"https://t.me/Ajorparehbot?start=ref_{user_id}",
        "pending": [{
            "id": item.get("withdrawal_id"), "method": item.get("method", "card"),
            "amount_toman": int(item.get("amount_toman", 0)), "amount_usdt": item.get("amount_usdt"),
            "created_at": item.get("created_at").isoformat() if isinstance(item.get("created_at"), datetime) else None,
        } for item in pending],
    }


async def miniapp_wallet_api(request: web.Request):
    telegram_user = await require_miniapp_user(request)
    return web.json_response({"ok": True, "wallet": await wallet_snapshot(telegram_user["id"])})


async def miniapp_wallet_convert_api(request: web.Request):
    telegram_user = await require_miniapp_user(request)
    try:
        payload = await request.json(); points = int(payload.get("points", 0))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid points") from exc
    user_state = await users_col.find_one({"_id": telegram_user["id"]}, {"wallet_frozen": 1}) or {}
    if user_state.get("wallet_frozen"): raise web.HTTPForbidden(text="Wallet is frozen by admin")
    minimum = int(economy_settings["min_convert_points"])
    if points < minimum or points % 100 != 0:
        raise web.HTTPBadRequest(text=f"Minimum {minimum} points; use multiples of 100")
    amount_toman = points * int(economy_settings["point_toman_rate"])
    result = await users_col.update_one(
        {"_id": telegram_user["id"], "xp": {"$gte": points}},
        {"$inc": {"xp": -points, "wallet_toman": amount_toman}},
    )
    if not result.modified_count:
        raise web.HTTPConflict(text="Not enough points")
    await wallet_transactions_col.insert_one({
        "user_id": telegram_user["id"], "type": "points_to_toman", "points": -points,
        "amount_toman": amount_toman, "rate": economy_settings["point_toman_rate"], "created_at": datetime.now(timezone.utc),
    })
    return web.json_response({"ok": True, "converted_points": points, "amount_toman": amount_toman, "wallet": await wallet_snapshot(telegram_user["id"])})


async def miniapp_wallet_withdraw_api(request: web.Request):
    telegram_user = await require_miniapp_user(request)
    try:
        payload = await request.json(); amount_toman = int(payload.get("amount_toman", 0))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid amount") from exc
    method = str(payload.get("method", "card")).lower()
    minimum = int(economy_settings["min_withdraw_toman"])
    if amount_toman < minimum or amount_toman % 1000 != 0:
        raise web.HTTPBadRequest(text=f"Minimum withdrawal is {minimum} toman")
    user_state = await users_col.find_one({"_id": telegram_user["id"]}, {"wallet_frozen": 1}) or {}
    if user_state.get("wallet_frozen"): raise web.HTTPForbidden(text="Wallet is frozen by admin")
    pending = await withdrawals_col.find_one({"user_id": telegram_user["id"], "status": "pending"})
    if pending: raise web.HTTPConflict(text="A withdrawal is already pending")
    daily = await withdrawals_col.aggregate([
        {"$match": {"user_id": telegram_user["id"], "date_str": today_str(), "status": {"$in": ["pending", "paid"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_toman"}}},
    ]).to_list(length=1)
    daily_total = int(daily[0].get("total", 0)) if daily else 0
    if daily_total + amount_toman > int(economy_settings["daily_withdraw_limit"]):
        raise web.HTTPForbidden(text="Daily withdrawal limit exceeded")
    details = {}; amount_usdt = None
    if method == "card":
        card = re.sub(r"\D", "", str(payload.get("card_number", "")))
        holder = clean_profile_value(payload.get("card_holder"), 80)
        if not is_valid_card_number(card) or len(holder) < 3:
            raise web.HTTPBadRequest(text="Valid card number and holder name required")
        details = {"card_number": card, "card_masked": mask_card(card), "card_holder": holder}
    elif method == "usdt":
        rate = int(economy_settings["usdt_toman_rate"])
        wallet_address = str(payload.get("wallet_address", "")).strip()
        if rate <= 0:
            raise web.HTTPServiceUnavailable(text="USDT rate is not configured")
        if not re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{33}", wallet_address):
            raise web.HTTPBadRequest(text="Valid TRC20 address required")
        amount_usdt = round(amount_toman / rate, 2)
        details = {"wallet_address": wallet_address, "network": "TRC20", "usdt_rate": rate}
    else:
        raise web.HTTPBadRequest(text="Unsupported withdrawal method")
    debit = await users_col.update_one(
        {"_id": telegram_user["id"], "wallet_toman": {"$gte": amount_toman}, "withdrawal_pending": {"$ne": True}},
        {"$inc": {"wallet_toman": -amount_toman}, "$set": {"withdrawal_pending": True}},
    )
    if not debit.modified_count:
        raise web.HTTPConflict(text="Insufficient wallet balance")
    withdrawal_id = uuid.uuid4().hex[:8]
    name = " ".join(filter(None, [telegram_user.get("first_name"), telegram_user.get("last_name")])).strip()
    document = {
        "withdrawal_id": withdrawal_id, "user_id": telegram_user["id"], "name": name,
        "username": telegram_user.get("username"), "method": method, "amount_toman": amount_toman,
        "amount_usdt": amount_usdt, "status": "pending", "date_str": today_str(),
        "requires_second_approval": amount_toman >= int(economy_settings["large_withdraw_threshold"]) and len(set(ADMIN_IDS) | set(delegated_admins_cache)) >= 2,
        "approvals": [], "created_at": datetime.now(timezone.utc), **details,
    }
    try:
        await withdrawals_col.insert_one(document)
    except Exception:
        await users_col.update_one({"_id": telegram_user["id"]}, {"$inc": {"wallet_toman": amount_toman}, "$set": {"withdrawal_pending": False}})
        raise
    method_text = f"کارت‌به‌کارت · {details.get('card_masked')} · {details.get('card_holder')}" if method == "card" else f"USDT-TRC20 · {amount_usdt} USDT · {details['wallet_address']}"
    invoice = (
        f"💸 <b>پیش‌فاکتور برداشت #{withdrawal_id}</b>\n"
        f"کاربر: {html.escape(name or 'بدون نام')}\nآیدی: <code>{telegram_user['id']}</code>\n"
        f"یوزرنیم: @{html.escape(telegram_user.get('username') or 'ندارد')}\n"
        f"مبلغ: <b>{amount_toman:,} تومان</b>\nروش: <code>{html.escape(method_text)}</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👁 بررسی درخواست", callback_data=f"withdraw_view_{withdrawal_id}")]])
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, invoice, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            log.warning("اعلان برداشت برای ادمین %s ارسال نشد: %s", admin_id, exc)
    return web.json_response({"ok": True, "withdrawal_id": withdrawal_id, "message": "واریزی شما تا ۲۴ ساعت آینده انجام می‌شود و رسید تراکنش برای شما ارسال خواهد شد.", "wallet": await wallet_snapshot(telegram_user["id"])})


def calculate_game_reward(game: str, score: float) -> int:
    if game == "reflex": return 120 if score < 300 else 80 if score < 500 else 40
    if game in {"emoji", "fact"}: return min(160, 30 + max(0, int(score)) * 10)
    if game == "memory": return max(50, min(150, 190 - max(6, int(score)) * 5))
    if game == "tap": return max(30, min(150, 30 + max(0, int(score)) * 2))
    if game == "reverse": return 90
    if game == "laugh": return 150
    if game == "ajorchin": return max(20, min(200, 20 + max(0, int(score)) // 50))
    if game == "snake": return max(20, min(200, 15 + max(0, int(score)) // 20))
    return 0


async def miniapp_game_reward_api(request: web.Request):
    telegram_user = await require_miniapp_user(request)
    try:
        payload = await request.json(); game = str(payload.get("game", "")); score = float(payload.get("score", 0))
    except (ValueError, TypeError, json.JSONDecodeError) as exc: raise web.HTTPBadRequest(text="Invalid game result") from exc
    reward = calculate_game_reward(game, score)
    if reward <= 0: raise web.HTTPBadRequest(text="Unsupported game")
    day = today_str(); reward_id = f"{telegram_user['id']}:{day}:{game}"
    existing = await miniapp_rewards_col.find_one({"_id": reward_id}) or {}
    if int(existing.get("count", 0)) >= 5:
        return web.json_response({"ok": True, "awarded": 0, "limit_reached": True, "wallet": await wallet_snapshot(telegram_user["id"])})
    # ریست اتمیک شمارندهٔ روزانه با شرط $ne: فقط اولین درخواستِ روز ریست می‌کند؛
    # درخواست‌های هم‌زمان به‌جای read-then-write قدیمی، مقدار تازه را از دیتابیس می‌خوانند.
    reset = await users_col.update_one(
        {"_id": telegram_user["id"], "miniapp_reward_date": {"$ne": day}},
        {"$set": {"miniapp_reward_date": day, "miniapp_reward_today": 0}},
        upsert=True,
    )
    if reset.modified_count or reset.upserted_id:
        daily_total = 0
    else:
        fresh = await users_col.find_one({"_id": telegram_user["id"]}, {"miniapp_reward_today": 1}) or {}
        daily_total = int(fresh.get("miniapp_reward_today", 0))
    reward = min(reward, max(0, 1000 - daily_total))
    if reward <= 0:
        return web.json_response({"ok": True, "awarded": 0, "daily_limit_reached": True, "wallet": await wallet_snapshot(telegram_user["id"])})
    play_number = int(existing.get("count", 0)) + 1
    await miniapp_rewards_col.update_one({"_id": reward_id}, {"$inc": {"count": 1, "points": reward}, "$set": {"user_id": telegram_user["id"], "game": game, "day": day, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    await users_col.update_one(
        {"_id": telegram_user["id"]},
        {"$inc": {"xp": reward, "miniapp_reward_today": reward, "games_played": 1}, "$set": {"last_game": f"miniapp_{game}", "last_game_at": datetime.now(timezone.utc)}},
    )
    await record_score_event(telegram_user["id"], reward, f"game_{game}", f"score:{reward_id}:{play_number}", {"score": score})
    coin_tx = await apply_coin_transaction(telegram_user["id"], max(2, reward // 5), f"game_{game}", f"coin:{reward_id}:{play_number}", {"score": score}, apply_multiplier=True)
    return web.json_response({"ok": True, "awarded": reward, "awarded_coins": coin_tx.get("amount", 0), "coins": coin_tx.get("balance", 0), "wallet": await wallet_snapshot(telegram_user["id"])})


async def miniapp_economy_api(request: web.Request):
    user = await require_miniapp_user(request); user_id = user["id"]
    db_user = await users_col.find_one({"_id": user_id}) or {}
    purchases = await shop_purchases_col.find({"user_id": user_id, "status": "completed"}).to_list(length=100)
    owned = [item["item_id"] for item in purchases]
    today = today_str(); free_spin = db_user.get("wheel_free_date") != today
    raffles = await raffles_col.find({"status": "active", "ends_at": {"$gt": datetime.now(timezone.utc)}}).sort("ends_at", 1).limit(10).to_list(length=10)
    predictions = await predictions_col.find({"status": "active", "ends_at": {"$gt": datetime.now(timezone.utc)}}).sort("ends_at", 1).limit(10).to_list(length=10)
    missions = await mission_snapshots(user_id)
    return web.json_response({"ok": True, "economy": {
        "coins": await coin_balance(user_id), "reward_multiplier": round(await economy_reward_multiplier(), 3),
        "free_spin": free_spin, "paid_spin_cost": int(economy_settings["paid_spin_cost"]),
        "wheel": WHEEL_TABLE, "shop": [{"id": key, **value, "owned": key in owned} for key, value in SHOP_CATALOG.items()],
        "raffles": [{"id": str(item["_id"]), "title": item["title"], "cost": item["cost"], "ends_at": item["ends_at"].isoformat(), "entries": item.get("entries", 0)} for item in raffles],
        "predictions": [{"id": str(item["_id"]), "question": item["question"], "options": item["options"], "ends_at": item["ends_at"].isoformat()} for item in predictions],
        "missions": missions,
    }})


async def miniapp_gift_redeem_api(request: web.Request):
    user = await require_miniapp_user(request)
    try:
        payload = await request.json()
        code = str(payload.get("code", ""))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid gift code") from exc
    result = await redeem_promo_code(user["id"], code)
    if not result.get("ok"):
        status = 409 if result.get("reason") in {"capacity", "processing"} else 404
        return web.json_response({"ok": False, "reason": result.get("reason")}, status=status)
    if result.get("sticker_file_id"):
        try: await bot.send_sticker(user["id"], result["sticker_file_id"])
        except (TelegramForbiddenError, TelegramBadRequest): pass
    if result.get("animation_file_id"):
        try: await bot.send_animation(user["id"], result["animation_file_id"], caption="🎁 گیف هدیه شما")
        except (TelegramForbiddenError, TelegramBadRequest): pass
    return web.json_response({
        "ok": True,
        "duplicate": bool(result.get("duplicate")),
        "summary": promo_reward_summary(result.get("rewards") or {}),
        "rewards": result.get("rewards") or {},
        "wallet": await wallet_snapshot(user["id"]),
    })


async def miniapp_mission_claim_api(request: web.Request):
    user = await require_miniapp_user(request)
    try:
        payload = await request.json()
        mission_id = ObjectId(str(payload.get("mission_id", "")))
    except (InvalidId, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid mission") from exc
    result = await claim_mission_reward(user["id"], mission_id)
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "not_found":
            raise web.HTTPNotFound(text="Mission not found")
        raise web.HTTPConflict(text="Mission incomplete or already claimed")
    result["missions"] = await mission_snapshots(user["id"])
    return web.json_response(result)


async def miniapp_spin_api(request: web.Request):
    user = await require_miniapp_user(request); user_id = user["id"]
    try:
        payload = await request.json()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid spin request") from exc
    request_id = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("request_id", "")))[:64]
    if len(request_id) < 8: raise web.HTTPBadRequest(text="request_id required")
    spin_id = f"spin:{user_id}:{request_id}"
    old = await wheel_spins_col.find_one({"_id": spin_id})
    if old and old.get("status") == "completed": return web.json_response({"ok": True, "result": old["result"], "coins": await coin_balance(user_id), "duplicate": True})
    try: await wheel_spins_col.insert_one({"_id": spin_id, "user_id": user_id, "status": "pending", "created_at": datetime.now(timezone.utc)})
    except DuplicateKeyError: raise web.HTTPConflict(text="Spin already processing") from None
    day = today_str(); free = False
    free_result = await users_col.update_one({"_id": user_id, "wheel_free_date": {"$ne": day}}, {"$set": {"wheel_free_date": day}})
    free = bool(free_result.modified_count)
    cost = 0 if free else int(economy_settings["paid_spin_cost"])
    if cost:
        spend = await apply_coin_transaction(user_id, -cost, "wheel_spin", f"coin:{spin_id}:cost", {"free": False})
        if not spend.get("ok"):
            await wheel_spins_col.delete_one({"_id": spin_id}); raise web.HTTPPaymentRequired(text="Not enough coins")
    result = random.choices(WHEEL_TABLE, weights=[item["weight"] for item in WHEEL_TABLE], k=1)[0]
    if result["coins"]:
        await apply_coin_transaction(user_id, result["coins"], "wheel_reward", f"coin:{spin_id}:reward", {"label": result["label"]})
    if result.get("xp"):
        await users_col.update_one({"_id": user_id}, {"$inc": {"xp": result["xp"]}})
    if result.get("badge"):
        await users_col.update_one({"_id": user_id}, {"$addToSet": {"badges": result["badge"]}})
    if result.get("ai_quota"):
        ai_key = f"ai_bonus:{user_id}:{today_str()}"
        try:
            await coin_transactions_col.insert_one({"_id": ai_key, "user_id": user_id, "amount": 0, "direction": "mint", "reason": "ai_quota_bonus", "metadata": {"quota": result["ai_quota"]}, "status": "completed", "created_at": datetime.now(timezone.utc)})
            await users_col.update_one({"_id": user_id}, {"$inc": {"ai_bonus_quota": result["ai_quota"]}})
        except DuplicateKeyError:
            pass
    await wheel_spins_col.update_one({"_id": spin_id}, {"$set": {"status": "completed", "result": result, "free": free, "cost": cost, "completed_at": datetime.now(timezone.utc)}})
    return web.json_response({"ok": True, "result": result, "free": free, "cost": cost, "coins": await coin_balance(user_id)})


async def miniapp_shop_purchase_api(request: web.Request):
    user = await require_miniapp_user(request); user_id = user["id"]
    try:
        payload = await request.json()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid purchase request") from exc
    item_id = str(payload.get("item_id", "")); request_id = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("request_id", "")))[:64]
    item = SHOP_CATALOG.get(item_id)
    if not item or len(request_id) < 8: raise web.HTTPBadRequest(text="Invalid purchase")
    purchase_id = f"shop:{user_id}:{request_id}"
    try: await shop_purchases_col.insert_one({"_id": purchase_id, "user_id": user_id, "item_id": item_id, "price": item["price"], "status": "pending", "created_at": datetime.now(timezone.utc)})
    except DuplicateKeyError:
        old = await shop_purchases_col.find_one({"_id": purchase_id}); return web.json_response({"ok": old.get("status") == "completed", "duplicate": True, "coins": await coin_balance(user_id)})
    spend = await apply_coin_transaction(user_id, -int(item["price"]), "shop_purchase", f"coin:{purchase_id}", {"item_id": item_id})
    if not spend.get("ok"):
        await shop_purchases_col.update_one({"_id": purchase_id}, {"$set": {"status": "failed"}}); raise web.HTTPPaymentRequired(text="Not enough coins")
    update = {"$addToSet": {"badges": item_id}} if item["kind"] == "badge" else {"$set": {f"entitlements.{item_id}": datetime.now(timezone.utc) + timedelta(days=int(item.get("days", 1)))}}
    await users_col.update_one({"_id": user_id}, update)
    await shop_purchases_col.update_one({"_id": purchase_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}})
    return web.json_response({"ok": True, "item": {"id": item_id, **item}, "coins": await coin_balance(user_id)})


async def miniapp_shop_services_api(request: web.Request):
    await require_miniapp_user(request)  # احراز هویت + بررسی بن مینیاپ
    try:
        rate = await stars_toman_rate()
    except Exception:
        rate = 10000
    services = []
    for stype, item in SERVICE_CATALOG.items():
        plans = []
        for months in sorted(SERVICE_PLANS):
            _, final, _ = service_plan_price(months)
            stars = max(1, int(final) // rate)
            plans.append({"months": months, "price_toman": int(final), "stars": stars})
        services.append({
            "type": stype,
            "title": item.get("title", stype),
            "app": item.get("app", ""),
            "emoji": item.get("emoji", "🛒"),
            "plans": plans,
        })
    return web.json_response({"ok": True, "rate_toman": rate, "services": services})


async def miniapp_shop_stars_invoice_api(request: web.Request):
    user = await require_miniapp_user(request)
    user_id = user["id"]
    try:
        payload = await request.json()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid invoice request") from exc
    service_type = str(payload.get("service_type", ""))
    try:
        months = int(payload.get("months", 0))
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text="Invalid months") from exc
    if service_type not in SERVICE_CATALOG or months not in SERVICE_PLANS:
        raise web.HTTPBadRequest(text="Invalid service")
    # جلوی اسپم سفارش: اگر همین کاربر برای همین سرویس/پلن در ۱۵ دقیقهٔ اخیر سفارش «created» دارد، همان را استفاده مجدد کن
    order = None
    try:
        reuse_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        order = await service_orders_col.find_one(
            {"user_id": user_id, "service_type": service_type, "months": months, "payment_method": "stars", "status": "created", "created_at": {"$gte": reuse_cutoff}},
            sort=[("created_at", -1)],
        )
    except Exception:
        order = None
    if order is None:
        try:
            order = await create_service_order(user_id, service_type, months, "stars")
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
    rate = await stars_toman_rate()
    stars = max(1, int(order["final_price"]) // rate)
    title = f"{SERVICE_CATALOG[service_type].get('title', 'سرویس')} — {months} ماهه"
    try:
        invoice = await bot.create_invoice_link(
            title=title,
            description=f"پرداخت سرویس {title} با ستاره‌های تلگرام",
            payload=f"svc:{order['_id']}",
            currency="XTR",
            prices=[types.LabeledPrice(label=title, amount=stars)],
        )
    except Exception as exc:
        log.warning("miniapp stars invoice failed: %s", exc)
        await service_orders_col.update_one({"_id": order["_id"]}, {"$set": {"status": "cancelled"}})
        raise web.HTTPInternalServerError(text="Invoice failed") from exc
    await service_orders_col.update_one({"_id": order["_id"]}, {"$set": {"stars": stars}})
    await log_activity(user_id, "shop_stars_invoice", f"order={order['_id']},stars={stars}")
    return web.json_response({"ok": True, "invoice_url": invoice, "stars": stars, "order_id": order["_id"]})


async def miniapp_raffle_join_api(request: web.Request):
    user = await require_miniapp_user(request); user_id = user["id"]
    try:
        payload = await request.json()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="Invalid raffle request") from exc
    try: raffle_id = ObjectId(str(payload.get("raffle_id")))
    except InvalidId as exc: raise web.HTTPBadRequest(text="Invalid raffle") from exc
    raffle = await raffles_col.find_one({"_id": raffle_id, "status": "active", "ends_at": {"$gt": datetime.now(timezone.utc)}})
    if not raffle: raise web.HTTPNotFound(text="Raffle unavailable")
    max_entries = int(raffle.get("max_entries_per_user", 5))
    # ثبت اتمیک جایگاه ورودی قبل از کسر سکه؛ درخواست‌های هم‌زمان روی شمارهٔ بعدی رقابت می‌کنند
    entry_id = None
    for _ in range(3):
        count = await raffle_entries_col.count_documents({"raffle_id": raffle_id, "user_id": user_id})
        if count >= max_entries: raise web.HTTPForbidden(text="Entry limit reached")
        candidate = f"raffle:{raffle_id}:{user_id}:{count + 1}"
        try:
            await raffle_entries_col.insert_one({"_id": candidate, "raffle_id": raffle_id, "user_id": user_id, "created_at": datetime.now(timezone.utc)})
            entry_id = candidate
            break
        except DuplicateKeyError:
            continue  # درخواست موازی همان جایگاه را گرفت؛ دوباره تلاش کن
    if entry_id is None: raise web.HTTPConflict(text="Entry already processing")
    entries_count = int(entry_id.rsplit(":", 1)[-1])
    spend = await apply_coin_transaction(user_id, -int(raffle["cost"]), "raffle_entry", f"coin:{entry_id}", {"raffle_id": str(raffle_id)})
    if not spend.get("ok"):
        await raffle_entries_col.delete_one({"_id": entry_id})  # آزادسازی جایگاه؛ سکه‌ای کسر نشده
        raise web.HTTPPaymentRequired(text="Not enough coins")
    await raffles_col.update_one({"_id": raffle_id}, {"$inc": {"entries": 1, "pool": int(raffle["cost"])}})
    return web.json_response({"ok": True, "entries": entries_count, "coins": await coin_balance(user_id)})


async def miniapp_prediction_bet_api(request: web.Request):
    user = await require_miniapp_user(request); user_id = user["id"]; payload = await request.json()
    try: prediction_id = ObjectId(str(payload.get("prediction_id"))); option = int(payload.get("option")); stake = int(payload.get("stake", 20))
    except (InvalidId, ValueError, TypeError) as exc: raise web.HTTPBadRequest(text="Invalid prediction") from exc
    prediction = await predictions_col.find_one({"_id": prediction_id, "status": "active", "ends_at": {"$gt": datetime.now(timezone.utc)}})
    if not prediction or option < 0 or option >= len(prediction["options"]) or stake not in {10, 20, 50, 100}: raise web.HTTPBadRequest(text="Invalid bet")
    bet_id = f"prediction:{prediction_id}:{user_id}"
    # ایدمپوتنسی اتمیک: اول خود رأی را با کلید یکتا ثبت می‌کنیم تا درخواست‌های موازی/تکراری
    # (دابل‌کلیک، retry شبکه) هرگز دوبار سکه کسر نکنند؛ کسر سکه فقط بعد از ثبت موفق انجام می‌شود.
    try:
        await prediction_bets_col.insert_one({"_id": bet_id, "prediction_id": prediction_id, "user_id": user_id, "option": option, "stake": stake, "created_at": datetime.now(timezone.utc), "status": "open"})
    except DuplicateKeyError:
        raise web.HTTPConflict(text="Already predicted") from None
    spend = await apply_coin_transaction(user_id, -stake, "prediction_stake", f"coin:{bet_id}:stake", {"prediction_id": str(prediction_id), "option": option})
    if not spend.get("ok"):
        # سکه کافی نبود؛ رأی ثبت‌شده را برمی‌گردانیم تا کاربر بعداً بتواند دوباره تلاش کند
        await prediction_bets_col.delete_one({"_id": bet_id})
        raise web.HTTPPaymentRequired(text="Not enough coins")
    await predictions_col.update_one({"_id": prediction_id}, {"$inc": {f"option_pools.{option}": stake, "pool": stake}})
    return web.json_response({"ok": True, "coins": await coin_balance(user_id)})


async def miniapp_leaderboard_api(request: web.Request):
    period = request.query.get("period", "weekly")
    now = datetime.now(timezone.utc)
    if period == "monthly": since = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    elif period == "all": since = None
    else: since = now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    if since:
        pipeline = [{"$match": {"created_at": {"$gte": since}}}, {"$group": {"_id": "$user_id", "points": {"$sum": "$points"}}}, {"$sort": {"points": -1}}, {"$limit": 20}]
        rows = await score_events_col.aggregate(pipeline).to_list(length=20)
    else:
        users = await users_col.find({"is_banned": {"$ne": True}}, {"xp": 1}).sort("xp", -1).limit(20).to_list(length=20); rows = [{"_id": item["_id"], "points": item.get("xp", 0)} for item in users]
    ids = [row["_id"] for row in rows]; users = {item["_id"]: item async for item in users_col.find({"_id": {"$in": ids}}, {"name": 1, "username": 1})}
    return web.json_response({"ok": True, "period": period, "items": [{"user_id": row["_id"], "name": users.get(row["_id"], {}).get("name", "بازیکن"), "username": users.get(row["_id"], {}).get("username"), "points": int(row["points"])} for row in rows]})


async def miniapp_media_jobs_api(request: web.Request):
    user = await require_miniapp_user(request)
    user_id = user["id"]
    if request.method == "POST":
        try:
            payload = await request.json()
            url = str(payload.get("url", "")).strip()
            mode = str(payload.get("mode", "social")).strip().lower()
            job = await enqueue_media_job(user_id, url, mode, "miniapp")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise web.HTTPBadRequest(text="Invalid media request") from exc
        except MediaServiceError as exc:
            return web.json_response({"ok": False, "reason": exc.reason, "message": exc.message}, status=400)
        return web.json_response({"ok": True, "job_id": job["_id"], "status": "queued"}, status=201)
    jobs = await media_jobs_col.find({"user_id": user_id}).sort("created_at", -1).limit(15).to_list(length=15)
    return web.json_response({
        "ok": True,
        "jobs": [{
            "id": item["_id"], "mode": item.get("mode"), "status": item.get("status"),
            "host": normalized_host(item.get("url", "")),
            "title": item.get("title"), "item_count": item.get("item_count", 0),
            "created_at": item.get("created_at").isoformat() if isinstance(item.get("created_at"), datetime) else None,
            "failure": item.get("failure"),
        } for item in jobs],
        "daily_limit": MEDIA_JOB_DAILY_LIMIT,
    }, headers={"Cache-Control": "no-store"})


async def miniapp_instagram_comment_api(request: web.Request):
    """استخراج متن یک کامنت عمومی اینستاگرام از داخل Mini App."""
    await require_miniapp_user(request)
    try:
        payload = await request.json()
        url = str(payload.get("url", "")).strip()
        result = await extract_instagram_comment(url)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text="Invalid Instagram comment URL") from exc
    except InstagramCommentError as exc:
        return web.json_response({"ok": False, "reason": exc.reason, "message": exc.message}, status=400)
    return web.json_response({
        "ok": True,
        "comment": {
            "id": result.comment_id,
            "text": result.text,
            "author": result.author,
            "source_url": result.source_url,
        },
    }, headers={"Cache-Control": "no-store"})


async def miniapp_link_inspection_api(request: web.Request):
    await require_miniapp_user(request)
    try:
        payload = await request.json()
        report = await inspect_link(str(payload.get("url", "")))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text="Invalid link") from exc
    except MediaServiceError as exc:
        return web.json_response({"ok": False, "reason": exc.reason, "message": exc.message}, status=400)
    return web.json_response({"ok": True, "report": report}, headers={"Cache-Control": "no-store"})


async def miniapp_music_api(request: web.Request):
    await require_miniapp_user(request)
    if http_session is None:
        raise web.HTTPServiceUnavailable(text="Music service not ready")
    try:
        if request.path.endswith("/search"):
            query = str(request.query.get("q", "")).strip()[:120]
            if not query:
                raise web.HTTPBadRequest(text="Missing q")
            items = await search_songs(http_session, query, 8)
        else:
            region = str(request.query.get("region", "")).strip().lower()
            if region == "iranian":
                items = await trending_iranian_songs(http_session, 10)
            elif region == "remix":
                items = await search_iranian_songs(http_session, "ریمیکس ایرانی رپ پاپ سنتی", 10)
            else:
                items = await trending_songs(http_session, 10)
    except MediaServiceError as exc:
        return web.json_response({"ok": False, "reason": exc.reason, "message": exc.message}, status=400)
    except Exception as exc:
        log.warning("miniapp music api failed: %s", exc)
        return web.json_response({"ok": False, "reason": "unavailable", "message": "سرویس موسیقی موقتاً در دسترس نیست."}, status=503)
    try:
        host = await audius_host(http_session)
    except Exception:
        host = ""
    for item in items:
        if item.get("source") == "audius" and host and item.get("id"):
            item["stream_url"] = f"{host}/v1/tracks/{item['id']}/stream?app_name=Ajorpareh"
        elif item.get("preview_url"):
            # پیش‌نمایش رسمی ۳۰ ثانیه (دیزر/اپل)
            item["stream_url"] = item["preview_url"]
            item["is_preview"] = True
        item["download_query"] = f"{item.get('title') or ''} {item.get('artist') or ''}".strip()[:120]
        item["badge"] = item.get("provider") or ""
    return web.json_response({"ok": True, "items": items}, headers={"Cache-Control": "no-store"})


def _hokm_room_state(game: HokmGame, viewer_seat: int) -> dict:
    state = game.public_state(viewer_seat)
    state["room_link"] = f"https://t.me/{SUPPORT_USERNAME}/app?startapp=hokm_{game.room_id}"
    return state


async def miniapp_hokm_api(request: web.Request):
    """API بازی حکم آنلاین: create / join / state / move / leave."""
    user = await require_miniapp_user(request)
    user_id = int(user["id"])
    _hokm_room_expiry()
    if request.method == "GET" and request.path.endswith("/state"):
        room_id = str(request.query.get("room", "")).strip()[:40]
        game = hokm_rooms.get(room_id)
        if not game:
            raise web.HTTPNotFound(text="room not found")
        seat = next((s for s, u in game.seats.items() if u == user_id), None)
        if seat is None:
            raise web.HTTPForbidden(text="not in room")
        return web.json_response({"ok": True, **game.public_state(seat)}, headers={"Cache-Control": "no-store"})

    try:
        payload = await request.json() if request.body_exists else {}
    except Exception:
        payload = {}
    action = str(payload.get("action") or "")

    if action == "create":
        room_id = uuid.uuid4().hex[:10]
        seat_a = random.choice([0, 2])
        game = HokmGame(room_id, seat_a, user_id, user.get("first_name") or "بازیکن", difficulty=str(payload.get("difficulty") or "medium"))
        hokm_rooms[room_id] = game
        await log_activity(user_id, "hokm_create", f"room={room_id}")
        return web.json_response({"ok": True, "room": room_id, "seat": seat_a, "link": f"https://t.me/{SUPPORT_USERNAME}/app?startapp=hokm_{room_id}"}, headers={"Cache-Control": "no-store"})

    if action == "join":
        room_id = str(payload.get("room") or "").strip()[:40]
        game = hokm_rooms.get(room_id)
        if not game:
            raise web.HTTPNotFound(text="room not found")
        if game.phase != "waiting":
            raise web.HTTPConflict(text="game already started")
        seat_b = 1 if 1 not in [s for s, u in game.seats.items() if u] else 3
        if seat_b in [s for s, u in game.seats.items() if u]:
            raise web.HTTPConflict(text="room full")
        game.seats[seat_b] = user_id
        game.names[seat_b] = user.get("first_name") or "بازیکن ۲"
        game.human_seats = [s for s, u in game.seats.items() if u is not None]
        game.add_log(f"👥 {game.names[seat_b]} به بازی پیوست!")
        game.start()
        await _hokm_auto_advance(game)
        await log_activity(user_id, "hokm_join", f"room={room_id}")
        return web.json_response({"ok": True, **game.public_state(seat_b)}, headers={"Cache-Control": "no-store"})

    if action == "move":
        room_id = str(payload.get("room") or "").strip()[:40]
        game = hokm_rooms.get(room_id)
        if not game:
            raise web.HTTPNotFound(text="room not found")
        seat = next((s for s, u in game.seats.items() if u == user_id), None)
        if seat is None:
            raise web.HTTPForbidden(text="not in room")
        # اعلام حکم
        if game.phase == "bid" and game.hakem == seat:
            trump = str(payload.get("trump") or "")[:1]
            if not game.declare_trump(seat, trump):
                return web.json_response({"ok": False, "reason": "invalid_trump"})
            await _hokm_auto_advance(game)
            return web.json_response({"ok": True, **game.public_state(seat)}, headers={"Cache-Control": "no-store"})
        # شروع دست بعدی
        if game.phase == "dealing":
            game.next_hand()
            await _hokm_auto_advance(game)
            return web.json_response({"ok": True, **game.public_state(seat)}, headers={"Cache-Control": "no-store"})
        # بازی کردن کارت
        if game.phase == "play" and game.turn == seat:
            card = payload.get("card") or {}
            if not game.play(seat, {"s": str(card.get("s") or "")[:1], "v": int(card.get("v") or 0)}):
                return web.json_response({"ok": False, "reason": "invalid_move"})
            await _hokm_auto_advance(game)
            return web.json_response({"ok": True, **game.public_state(seat)}, headers={"Cache-Control": "no-store"})
        return web.json_response({"ok": False, "reason": "not_your_turn"})

    if action == "state":
        room_id = str(payload.get("room") or "").strip()[:40]
        game = hokm_rooms.get(room_id)
        if not game:
            raise web.HTTPNotFound(text="room not found")
        seat = next((s for s, u in game.seats.items() if u == user_id), None)
        if seat is None:
            raise web.HTTPForbidden(text="not in room")
        return web.json_response({"ok": True, **game.public_state(seat)}, headers={"Cache-Control": "no-store"})

    if action == "leave":
        room_id = str(payload.get("room") or "").strip()[:40]
        hokm_rooms.pop(room_id, None)
        return web.json_response({"ok": True})

    raise web.HTTPBadRequest(text="unknown action")


async def _hokm_auto_advance(game: HokmGame) -> None:
    guard = 0
    while guard < 60:
        guard += 1
        if game.phase == "dealing":
            game.next_hand()
            continue
        if game.phase == "bid":
            if game.hakem in game.human_seats:
                return
            game._ai_declare_trump()
            continue
        if game.phase == "play":
            if game.turn in game.human_seats:
                return
            if game.turn is None:
                return
            game.ai_move(game.turn)
            continue
        return


# ===== دوئل ۱v۱ =====
async def miniapp_duel_api(request: web.Request):
    user = await require_miniapp_user(request)
    user_id = int(user["id"])
    now_ts = time.time()
    expired = [rid for rid, r in duel_rooms.items() if now_ts - r.get("updated_at", 0) > 1800]
    for rid in expired: duel_rooms.pop(rid, None)
    if request.method == "GET":
        room_id = str(request.query.get("room", "")).strip()[:30]
        room = duel_rooms.get(room_id)
        if not room: raise web.HTTPNotFound(text="room not found")
        return web.json_response({"ok": True, **_duel_public(room, user_id)}, headers={"Cache-Control": "no-store"})
    try: payload = await request.json() if request.body_exists else {}
    except Exception: payload = {}
    action = str(payload.get("action") or "")
    if action == "create":
        game_type = str(payload.get("game_type", "tap")).strip()
        if game_type not in {"tap", "quiz", "math"}: game_type = "tap"
        room_id = uuid.uuid4().hex[:8]
        room = {"room_id": room_id, "type": game_type, "phase": "waiting", "players": {str(user_id): {"name": user.get("first_name") or "بازیکن", "score": 0, "submitted": False}}, "round": 1, "max_rounds": 3, "created_at": now_ts, "updated_at": now_ts, "questions": _generate_duel_questions(game_type)}
        duel_rooms[room_id] = room
        await log_activity(user_id, "duel_create", f"room={room_id},type={game_type}")
        return web.json_response({"ok": True, "room": room_id, "link": f"https://t.me/{SUPPORT_USERNAME}/app?startapp=duel_{room_id}"}, headers={"Cache-Control": "no-store"})
    if action == "join":
        room_id = str(payload.get("room", "")).strip()[:30]
        room = duel_rooms.get(room_id)
        if not room: raise web.HTTPNotFound(text="room not found")
        if room["phase"] != "waiting": raise web.HTTPConflict(text="game already started")
        if str(user_id) in room["players"]: raise web.HTTPConflict(text="already in room")
        room["players"][str(user_id)] = {"name": user.get("first_name") or "بازیکن ۲", "score": 0, "submitted": False}
        room["phase"] = "playing"; room["updated_at"] = now_ts
        await log_activity(user_id, "duel_join", f"room={room_id}")
        return web.json_response({"ok": True, **_duel_public(room, user_id)}, headers={"Cache-Control": "no-store"})
    if action == "submit":
        room_id = str(payload.get("room", "")).strip()[:30]
        room = duel_rooms.get(room_id)
        if not room: raise web.HTTPNotFound(text="room not found")
        pid = str(user_id)
        if pid not in room["players"]: raise web.HTTPForbidden(text="not in room")
        if room["phase"] != "playing": raise web.HTTPConflict(text="not playing")
        answer = payload.get("answer"); time_ms = int(payload.get("time_ms", 9999))
        p = room["players"][pid]
        if p["submitted"]: raise web.HTTPConflict(text="already submitted")
        q = room["questions"][room["round"] - 1] if room["round"] - 1 < len(room["questions"]) else None
        correct = False
        if q:
            if room["type"] == "tap": correct = True; p["score"] += max(0, 1000 - time_ms)
            elif room["type"] == "quiz":
                correct = (answer == q.get("answer"))
                if correct: p["score"] += max(100, 1000 - time_ms)
            elif room["type"] == "math":
                try: correct = (int(answer) == int(q.get("answer", 0)))
                except (ValueError, TypeError): correct = False
                if correct: p["score"] += max(100, 1000 - time_ms)
        p["submitted"] = True; room["updated_at"] = now_ts
        all_sub = all(v["submitted"] for v in room["players"].values())
        if all_sub:
            room["round"] += 1
            if room["round"] > room["max_rounds"]:
                room["phase"] = "finished"
                scores = sorted(room["players"].items(), key=lambda x: x[1]["score"], reverse=True)
                room["winner"] = scores[0][0]
                for apid, _av in room["players"].items():
                    won = (apid == room["winner"])
                    await record_game(int(apid), f"duel_{room['type']}", won=won, xp=50 if won else 20)
            else:
                for v in room["players"].values(): v["submitted"] = False
        return web.json_response({"ok": True, **_duel_public(room, user_id)}, headers={"Cache-Control": "no-store"})
    if action == "leave":
        room_id = str(payload.get("room", "")).strip()[:30]; duel_rooms.pop(room_id, None)
        return web.json_response({"ok": True})
    raise web.HTTPBadRequest(text="unknown action")


def _generate_duel_questions(game_type: str) -> list:
    questions = []
    if game_type == "tap":
        for _ in range(3): questions.append({"type": "tap", "instruction": "ضربه بزن!"})
    elif game_type == "quiz":
        all_q = [
            {"question": "کدام حیوان سه قلب دارد؟", "options": ["دلفین", "اختاپوس", "پنگوئن"], "answer": 1},
            {"question": "سرعت نور چند km/s است؟", "options": ["۳۰ هزار", "۳۰۰ هزار", "۳ میلیون"], "answer": 1},
            {"question": "پایتخت ژاپن؟", "options": ["سئول", "توکیو", "پکن"], "answer": 1},
            {"question": "کدام ایموجی واژه سال ۲۰۱۵ شد؟", "options": ["😂", "❤️", "🔥"], "answer": 0},
            {"question": "بزرگ‌ترین اقیانوس؟", "options": ["اطلس", "آرام", "هند"], "answer": 1},
            {"question": "کدام فلز مایع است؟", "options": ["آهن", "جیوه", "مس"], "answer": 1},
            {"question": "کدام زبان بیشترین گویشور را دارد؟", "options": ["انگلیسی", "چینی", "اسپانیایی"], "answer": 1},
        ]
        random.shuffle(all_q); questions = all_q[:3]
    elif game_type == "math":
        for _ in range(3):
            a, b = random.randint(10, 50), random.randint(10, 50)
            op = random.choice(["+", "-", "×"])
            if op == "+": ans = a + b
            elif op == "-": ans = max(0, a - b)
            else: ans = a * b
            questions.append({"question": f"{a} {op} {b} = ?", "answer": ans})
    return questions


def _duel_public(room: dict, viewer_id: int) -> dict:
    pid = str(viewer_id)
    q_idx = min(room["round"] - 1, len(room["questions"]) - 1)
    cq = room["questions"][q_idx] if 0 <= q_idx < len(room["questions"]) else None
    q_pub = None
    if cq:
        q_pub = {"type": cq.get("type", room["type"]), "question": cq.get("question", cq.get("instruction", ""))}
        if cq.get("options"): q_pub["options"] = cq["options"]
    players_pub = {}
    for k, v in room["players"].items():
        players_pub[k] = {"name": v["name"], "score": v["score"], "submitted": v["submitted"], "is_you": k == pid}
    return {"room": room["room_id"], "type": room["type"], "phase": room["phase"], "round": room["round"], "max_rounds": room["max_rounds"], "players": players_pub, "question": q_pub, "winner": room.get("winner"), "room_link": f"https://t.me/{SUPPORT_USERNAME}/app?startapp=duel_{room['room_id']}"}


async def miniapp_reviews_api(request: web.Request):
    if request.method == "POST":
        telegram_user = await require_miniapp_user(request)
        try:
            payload = await request.json()
            rating = max(1, min(5, int(payload.get("rating", 5))))
            review_text = clean_profile_value(payload.get("text"), 500)
            review = await create_user_review(
                telegram_user["id"],
                " ".join(filter(None, [telegram_user.get("first_name"), telegram_user.get("last_name")])).strip(),
                telegram_user.get("username"),
                f"{rating} | {review_text}",
                "miniapp",
            )
        except (ValueError, TypeError, json.JSONDecodeError, DuplicateKeyError) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(
            {"ok": True, "review_id": review["_id"], "status": "pending"},
            status=201,
            headers={"Cache-Control": "no-store"},
        )
    items = await reviews_col.find({"status": "published"}).sort("published_at", -1).limit(20).to_list(length=20)
    return web.json_response({
        "ok": True,
        "demo_items": DEMO_REVIEWS,
        "items": [{
            "id": item["_id"],
            "name": item.get("name") or "کاربر Ajorpareh",
            "rating": max(1, min(5, int(item.get("rating", 5)))),
            "text": item.get("text") or "",
            "published_at": item.get("published_at").isoformat() if isinstance(item.get("published_at"), datetime) else None,
            "demo": False,
        } for item in items],
    }, headers={"Cache-Control": "no-store"})


async def miniapp_support_api(request: web.Request):
    telegram_user = await require_miniapp_user(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="Invalid JSON") from exc
    message_text = clean_profile_value(payload.get("text"), 2000)
    ticket_type = clean_profile_value(payload.get("type"), 60) or "گزارش Mini App"
    if len(message_text) < 8:
        raise web.HTTPBadRequest(text="Message is too short")
    ticket_id = uuid.uuid4().hex[:6].upper()
    name = " ".join(filter(None, [telegram_user.get("first_name"), telegram_user.get("last_name")])).strip()
    await tickets_col.insert_one({
        "ticket_id": ticket_id,
        "user_id": telegram_user["id"],
        "name": name,
        "username": telegram_user.get("username"),
        "text": message_text,
        "type": ticket_type,
        "source": "miniapp",
        "status": "open",
        "created_at": datetime.now(timezone.utc),
    })
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎫 مشاهده #{ticket_id}", callback_data=f"ticket_view_{ticket_id}")]
    ])
    alert = (
        f"🎫 <b>گزارش جدید Mini App #{ticket_id}</b>\n"
        f"نوع: {html.escape(ticket_type)}\n"
        f"کاربر: {html.escape(name or 'بدون نام')}\n"
        f"آیدی: <code>{telegram_user['id']}</code>\n"
        f"یوزرنیم: @{html.escape(telegram_user.get('username') or 'ندارد')}\n\n"
        f"{html.escape(message_text)}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, alert, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            log.warning("اعلان تیکت برای ادمین %s ارسال نشد: %s", admin_id, exc)
    return web.json_response({"ok": True, "ticket_id": ticket_id})


async def health_check(request):
    uptime = int(time.monotonic() - BOT_STARTED_AT)
    db_ok = False
    try:
        await mongo_client.admin.command("ping", serverSelectionTimeoutMS=2000)
        db_ok = True
    except Exception:
        pass
    return web.json_response({
        "ok": True,
        "service": "ajorpareh-bot",
        "mode": "webhook" if USE_WEBHOOK else "polling",
        "uptime_seconds": uptime,
        "mini_app": MINI_APP_URL,
        "database": "connected" if db_ok else "disconnected",
        "ai": ai_service.public_status(),
    })


@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    raised_exception = False
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
        raised_exception = True
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' https://telegram.org; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors https://web.telegram.org https://*.telegram.org",
    )
    if request.path.startswith("/api/") and "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    elif request.path == "/":
        response.headers.setdefault("Cache-Control", "no-cache")
    elif request.path == "/app/":
        response.headers.setdefault("Cache-Control", "no-cache")
    elif request.path.startswith("/app/"):
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    if raised_exception:
        raise response
    return response


# ===== ریت‌لیمیت APIهای مینیاپ (ضد اسپم/بروت‌فورس؛ کلید = کاربر تأییدشده وگرنه IP) =====
API_RATE_WINDOW_SECONDS = 60
API_RATE_MAX_REQUESTS = 120
_api_rate_hits: dict[str, "deque[float]"] = {}


def _api_rate_key(request: web.Request) -> str:
    raw = request.headers.get("X-Telegram-Init-Data", "")
    if raw:
        user = verify_telegram_init_data(raw)
        if user:
            return f"u:{user['id']}"
    return f"ip:{request.remote or 'unknown'}"


@web.middleware
async def api_rate_limit_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    now = time.time()
    key = _api_rate_key(request)
    hits = _api_rate_hits.get(key)
    if hits is None:
        hits = _api_rate_hits[key] = deque()
    cutoff = now - API_RATE_WINDOW_SECONDS
    while hits and hits[0] < cutoff:
        hits.popleft()
    if len(hits) >= API_RATE_MAX_REQUESTS:
        retry_after = max(1, int(hits[0] + API_RATE_WINDOW_SECONDS - now) + 1)
        raise web.HTTPTooManyRequests(
            text=json.dumps({"ok": False, "message": "درخواست‌ها زیاد شد؛ چند لحظه صبر کن."}, ensure_ascii=False),
            content_type="application/json",
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)
    if len(_api_rate_hits) > 20_000:  # پاکسازی سبک کلیدهای قدیمی برای جلوگیری از رشد حافظه
        stale = [k for k, dq in _api_rate_hits.items() if not dq or dq[-1] < cutoff]
        for k in stale[:10_000]:
            _api_rate_hits.pop(k, None)
    return await handler(request)


async def google_site_verification(request: web.Request):
    if not GOOGLE_VERIFICATION_FILE.is_file():
        raise web.HTTPNotFound(text="Google verification file is missing")
    return web.FileResponse(
        GOOGLE_VERIFICATION_FILE,
        headers={"Cache-Control": "public, max-age=300"},
    )


async def robots_txt(request: web.Request):
    base = WEBHOOK_BASE_URL or "https://ajor2-production.up.railway.app"
    return web.Response(
        text=f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: {WEBHOOK_PATH}\nSitemap: {base}/sitemap.xml\n",
        content_type="text/plain",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def sitemap_xml(request: web.Request):
    base = WEBHOOK_BASE_URL or "https://ajor2-production.up.railway.app"
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{base}/</loc><lastmod>{updated}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>\n"
        f"  <url><loc>{base}/app/</loc><lastmod>{updated}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>\n"
        "</urlset>\n"
    )
    return web.Response(
        text=body, content_type="application/xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def root_landing(request: web.Request):
    # درخواست صریح JSON و پارامتر format=json برای سازگاری مانیتورها حفظ می‌شود؛
    # مرورگر، شبکه‌های اجتماعی و خزنده‌های وب صفحه معرفی قابل ایندکس را می‌گیرند.
    accept = request.headers.get("Accept", "").lower()
    if request.query.get("format") == "json" or ("application/json" in accept and "text/html" not in accept):
        return await health_check(request)
    if not LANDING_FILE.is_file():
        raise web.HTTPNotFound(text="Landing page is missing")
    return web.FileResponse(LANDING_FILE)


async def miniapp_redirect(request):
    raise web.HTTPFound("/app/")


async def miniapp_index(request):
    index_file = WEBAPP_DIR / "index.html"
    if not index_file.exists():
        raise web.HTTPNotFound(text="Mini App files are missing")
    return web.FileResponse(index_file)


# ===== پرداخت با ستاره تلگرام (Telegram Stars) =====

@dp.pre_checkout_query()
async def pre_checkout_handler(query: types.PreCheckoutQuery):
    payload = str(query.invoice_payload or "")
    if payload.startswith("svc:"):
        order_id = payload.split(":", 1)[1]
        order = await service_orders_col.find_one({"_id": order_id})
        if not order or order.get("user_id") != query.from_user.id:
            await query.answer(ok=False, error_message="سفارش معتبر نیست.")
            return
        await query.answer(ok=True)
        return
    await query.answer(ok=False, error_message="پرداخت نامعتبر است.")


@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment
    payload = str(payment.invoice_payload or "")
    user_id = message.from_user.id
    if not payload.startswith("svc:"):
        return
    order_id = payload.split(":", 1)[1]
    order = await service_orders_col.find_one({"_id": order_id, "user_id": user_id})
    if not order:
        return
    stars = int(payment.total_amount or 0)
    await service_orders_col.update_one(
        {"_id": order_id},
        {"$set": {"status": "paid", "payment_method": "stars", "stars_paid": stars,
                  "paid_at": datetime.now(timezone.utc)}},
    )
    await mark_service_order_paid(order_id)
    await wallet_transactions_col.insert_one({
        "user_id": user_id, "type": "service_stars_purchase",
        "amount_toman": 0, "stars": stars, "order_id": order_id,
        "created_at": datetime.now(timezone.utc),
    })
    await log_activity(user_id, "service_stars_paid", f"order={order_id},stars={stars}")
    await message.answer(
        f"⭐ پرداخت شما با {stars:,} ستاره تأیید شد!\n"
        "✅ سفارش در انتظار تحویل توسط مدیر است.",
        reply_markup=service_reply_menu(),
    )


async def telegram_webhook(request: web.Request):
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not WEBHOOK_SECRET or not received_secret or not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        raise web.HTTPForbidden(text="invalid webhook secret")
    try:
        payload = await request.json()
        update = types.Update.model_validate(payload, context={"bot": bot})
    except Exception as exc:
        log.warning("Webhook payload نامعتبر: %s", exc)
        raise web.HTTPBadRequest(text="invalid update") from None

    task = asyncio.create_task(dp.feed_update(bot, update))
    task.add_done_callback(
        lambda finished: log.error("خطای task وبهوک: %s", finished.exception())
        if not finished.cancelled() and finished.exception()
        else None
    )
    return web.Response(text="OK")


async def main():
    global http_session
    http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    ai_service.set_session(http_session)
    runner = None
    webhook_started = False
    schedule_worker_task = None
    reminder_worker_task = None
    maintenance_worker_task = None
    greeting_worker_task = None
    daily_music_worker_task = None
    media_worker_tasks: list[asyncio.Task] = []
    heal_worker_task = None
    try:
        app = web.Application(
            client_max_size=2 * 1024 * 1024,
            middlewares=[api_rate_limit_middleware, security_headers_middleware],
        )
        app.router.add_get("/", root_landing)
        app.router.add_get("/health", health_check)
        app.router.add_get(f"/{GOOGLE_VERIFICATION_FILENAME}", google_site_verification)
        app.router.add_get("/robots.txt", robots_txt)
        app.router.add_get("/sitemap.xml", sitemap_xml)
        app.router.add_get("/api/news", news_api)
        app.router.add_get("/api/channel-posts", channel_posts_api)
        app.router.add_get("/api/joke", joke_api)
        app.router.add_get("/api/challenges", challenges_api)
        app.router.add_get("/api/occasion", occasion_api)
        app.router.add_get("/api/ai/status", miniapp_ai_status_api)
        app.router.add_post("/api/ai/text", miniapp_ai_text_api)
        app.router.add_post("/api/ai/image", miniapp_ai_image_api)
        app.router.add_get("/api/reminders", miniapp_reminders_api)
        app.router.add_post("/api/reminders", miniapp_reminders_api)
        app.router.add_delete("/api/reminders/{reminder_id}", miniapp_reminder_delete_api)
        app.router.add_get("/api/profile", miniapp_profile_api)
        app.router.add_post("/api/profile", miniapp_profile_api)
        app.router.add_post("/api/support", miniapp_support_api)
        app.router.add_get("/api/media/jobs", miniapp_media_jobs_api)
        app.router.add_post("/api/media/jobs", miniapp_media_jobs_api)
        app.router.add_post("/api/instagram/comment", miniapp_instagram_comment_api)
        app.router.add_post("/api/link/inspect", miniapp_link_inspection_api)
        app.router.add_get("/api/music/search", miniapp_music_api)
        app.router.add_get("/api/music/trending", miniapp_music_api)
        app.router.add_get("/api/hokm/state", miniapp_hokm_api)
        app.router.add_post("/api/hokm", miniapp_hokm_api)
        app.router.add_get("/api/duel", miniapp_duel_api)
        app.router.add_post("/api/duel", miniapp_duel_api)
        app.router.add_get("/api/reviews", miniapp_reviews_api)
        app.router.add_post("/api/reviews", miniapp_reviews_api)
        app.router.add_get("/api/wallet", miniapp_wallet_api)
        app.router.add_post("/api/wallet/convert", miniapp_wallet_convert_api)
        app.router.add_post("/api/wallet/withdraw", miniapp_wallet_withdraw_api)
        app.router.add_post("/api/game/reward", miniapp_game_reward_api)
        app.router.add_get("/api/economy", miniapp_economy_api)
        app.router.add_post("/api/gift/redeem", miniapp_gift_redeem_api)
        app.router.add_post("/api/mission/claim", miniapp_mission_claim_api)
        app.router.add_post("/api/spin", miniapp_spin_api)
        app.router.add_post("/api/shop/purchase", miniapp_shop_purchase_api)
        app.router.add_get("/api/shop/services", miniapp_shop_services_api)
        app.router.add_post("/api/shop/stars-invoice", miniapp_shop_stars_invoice_api)
        app.router.add_post("/api/raffle/join", miniapp_raffle_join_api)
        app.router.add_post("/api/prediction/bet", miniapp_prediction_bet_api)
        app.router.add_get("/api/leaderboard", miniapp_leaderboard_api)
        app.router.add_get("/app", miniapp_redirect)
        app.router.add_get("/app/", miniapp_index)
        app.router.add_static("/app/", str(WEBAPP_DIR), show_index=False)
        if USE_WEBHOOK:
            app.router.add_post(WEBHOOK_PATH, telegram_webhook)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", "8080"))
        # Railway requires the container service to listen on all interfaces.
        site = web.TCPSite(runner, "0.0.0.0", port)  # nosec B104
        await site.start()

        await initialize_database()
        try:
            rt = await settings_col.find_one({"_id": "runtime"})
            if rt:
                runtime_settings.update({k: v for k, v in rt.items() if k != "_id"})
        except Exception:
            pass
        schedule_worker_task = asyncio.create_task(scheduled_posts_worker(), name="scheduled-posts-worker")
        reminder_worker_task = asyncio.create_task(user_reminders_worker(), name="user-reminders-worker")
        maintenance_worker_task = asyncio.create_task(maintenance_recovery_worker(), name="maintenance-recovery-worker")
        for index in range(4):
            media_worker_tasks.append(
                asyncio.create_task(media_jobs_worker(), name=f"media-jobs-worker-{index + 1}")
            )
        asyncio.create_task(auto_rates_worker(), name="auto-rates-worker")
        greeting_worker_task = asyncio.create_task(scheduled_greetings_worker(), name="scheduled-greetings-worker")
        daily_music_worker_task = asyncio.create_task(daily_music_worker(), name="daily-music-worker")
        asyncio.create_task(daily_fal_worker(), name="daily-fal-worker")
        asyncio.create_task(daily_prayer_worker(), name="daily-prayer-worker")
        asyncio.create_task(prayer_azan_worker(), name="prayer-azan-worker")
        asyncio.create_task(weekly_finance_worker(), name="weekly-finance-worker")
        heal_worker_task = asyncio.create_task(self_heal_worker(), name="self-heal-worker")
        await configure_telegram_ui()


        if USE_WEBHOOK:
            webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
            await dp.emit_startup(bot=bot)
            webhook_started = True
            await bot.set_webhook(
                url=webhook_url,
                secret_token=WEBHOOK_SECRET,
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=False,
                max_connections=40,
            )
            info = await bot.get_webhook_info()
            log.info("🤖 Webhook فعال شد: %s | pending=%s", info.url, info.pending_update_count)
            await asyncio.Event().wait()
        else:
            await bot.delete_webhook(drop_pending_updates=False)
            log.info("🤖 ربات در حالت Polling فعال شد. برای Webhook دامنه Railway را تنظیم کنید.")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for worker in [schedule_worker_task, reminder_worker_task, maintenance_worker_task, greeting_worker_task, daily_music_worker_task, heal_worker_task, *media_worker_tasks]:
            if worker:
                worker.cancel()
                try: await worker
                except asyncio.CancelledError: pass
        if webhook_started:
            await dp.emit_shutdown(bot=bot)
        if http_session and not http_session.closed:
            await http_session.close()
        ai_service.set_session(None)
        await bot.session.close()
        mongo_client.close()
        if runner:
            await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("ربات متوقف شد.")
