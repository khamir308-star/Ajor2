"""موتور مدیریت گروه — قفل‌ها، ضد اسپم، خاموشی و ویژگی‌های پیشرفته.

سطح امکانات: هم‌تراز پنل‌های حرفه‌ای (مثل TLPro)
- قفل‌ها: بیش از ۵۵ نوع پیام با جزئیات (اندازه ویدئو، تعداد ایموجی و...)
- ضد مزاحمت: ضد اسپم، ضد تبچی، ورود ربات‌ها، پیام تکراری، ضد خیانت، اخطار
- خاموشی: ساعتی + مدت‌دار + پیام سفارشی
- ویژگی‌ها: پاکسازی خودکار، فیلتر کلمات، قالب اجباری، کپشن اجباری، عضو اجباری
- قرعه‌کشی، لینک دعوت اختصاصی، آمار، اسپانسر
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

# ==================== قفل‌ها ====================
# مقدار قفل: True/False یا dict با جزئیات (مثلاً {"locked": True, "max_mb": 10})
LOCKS: dict[str, str] = {
    # --- متن ---
    "text_only": "فقط متن",
    "short_text": "متن کوتاه",
    "long_text": "متن بلند",
    "persian_typing": "تایپ فارسی",
    "english_typing": "تایپ انگلیسی",
    "emoji_count": "تعداد ایموجی",
    "custom_emoji_count": "تعداد ایموجی کاستوم",
    "caption_required": "کپشن اجباری",
    "template_required": "قالب اجباری",
    # --- لینک و شناسه ---
    "link": "لینک",
    "link_external": "لینک خارجی",
    "link_telegram": "لینک تلگرامی",
    "link_short": "لینک کوتاه",
    "link_instagram": "لینک اینستاگرام",
    "link_email": "ایمیل",
    "link_hidden": "لینک مخفی (هایپر)",
    "link_bot": "لینک ربات",
    "link_glass": "لینک شیشه‌ای",
    "link_bio": "لینک بیو",
    "channel_id": "آیدی کانال/گروه",
    "mention": "منشن",
    "mention_text": "منشن متنی",
    "phone": "شماره تلفن",
    "reply": "پاسخ/ریپلای",
    "reply_external": "ریپلای خارجی",
    # --- رسانه ---
    "photo": "تصویر",
    "video": "ویدئو",
    "audio": "موزیک",
    "voice": "ویس",
    "video_note": "ویدئو گرد",
    "gif": "گیف",
    "sticker": "استیکر",
    "document": "فایل",
    "location": "لوکیشن",
    "poll": "نظرسنجی",
    "story": "استوری",
    "game": "بازی",
    "app": "اپلیکیشن",
    "spoiler": "اسپویلر",
    "nsfw_attach": "پیوست مستهجن",
    "nsfw_sticker": "استیکر مستهجن",
    "edit_text": "ویرایش متن",
    "edit_caption": "ویرایش پیوست",
    # --- فوروارد ---
    "forward": "فوروارد",
    "forward_channel_public": "فوروارد کانال عمومی",
    "forward_channel_private": "فوروارد کانال خصوصی",
    "forward_user": "فوروارد کاربر",
    # --- رفتار و سایر ---
    "hidden_identity": "هویت مخفی",
    "ai": "هوش مصنوعی",
    "bot_message": "پیام رباتی",
    "like": "لایک",
    "music_finder": "موزیک یاب",
    "currency_price": "قیمت ارزها",
    "bio": "بیوگرافی",
    "private_chat": "چت خصوصی",
}

# دسته‌بندی قفل‌ها برای پنل
LOCK_CATEGORIES: dict[str, list[str]] = {
    "🔤 متن": ["text_only", "short_text", "long_text", "persian_typing", "english_typing",
               "emoji_count", "custom_emoji_count", "caption_required", "template_required"],
    "🔗 لینک و شناسه": ["link", "link_external", "link_telegram", "link_short", "link_instagram",
                      "link_email", "link_hidden", "link_bot", "link_glass", "link_bio",
                      "channel_id", "mention", "mention_text", "phone", "reply", "reply_external"],
    "🎬 رسانه": ["photo", "video", "audio", "voice", "video_note", "gif", "sticker",
                "document", "location", "poll", "story", "game", "app", "spoiler",
                "nsfw_attach", "nsfw_sticker", "edit_text", "edit_caption"],
    "📤 فوروارد": ["forward", "forward_channel_public", "forward_channel_private", "forward_user"],
    "🛡 سایر": ["hidden_identity", "ai", "bot_message", "like", "music_finder",
               "currency_price", "bio", "private_chat"],
}

DEFAULT_LOCKS: dict[str, Any] = {k: False for k in LOCKS}

# قفل‌های ویژه که مقدارشان dict است
DEFAULT_LOCK_VALUES: dict[str, Any] = {
    "video": {"locked": False, "mode": "free"},  # free | 10mb | 50mb | 100mb | 200mb | 500mb | all
    "emoji_count": {"locked": False, "max": 3},
    "custom_emoji_count": {"locked": False, "max": 3},
    "phone": {"locked": False, "mode": "normal"},  # normal | sensitive
    "edit_text": {"locked": False, "mode": "free"},  # free | instant | 1m | 3m | 5m | 10m | 30m
    "edit_caption": {"locked": False, "mode": "free"},
    "short_text": {"locked": False, "max_chars": 15},
    "long_text": {"locked": False, "min_chars": 500},
    "emoji": {"locked": False, "max": 3},
}

# ==================== ضد مزاحمت ====================
DEFAULT_ANTISPAM = {
    "enabled": False,
    "max_messages": 5,
    "window_minutes": 1,
    "action": "warn",  # warn | delete | mute | ban
    # --- کاربر ویژه ---
    "vip_max_messages": 20,
    "vip_window_minutes": 5,
    # --- ضد اسپم سریع (تعداد پیام در ثانیه) ---
    "fast_enabled": False,
    "fast_count": 8,       # چند پیام
    "fast_seconds": 5,     # در چند ثانیه
    # --- ضد تبچی ---
    "anti_tabchi": "off",  # off | on | very_sensitive
    # --- ورود ربات‌ها ---
    "bot_join": "kick",    # kick | kick_added | allow
    "allowed_bots": [],
    # --- اخراج کاربر جدید ---
    "kick_new_users": False,
    "kick_new_users_seconds": 0,  # 0 = فوری
    # --- پیام تکراری ---
    "duplicate_action": "none",  # none | mute | delete | warn
    # --- ضد خیانت ---
    "anti_betray": 0,      # تعداد اخراج/تحریم
    # --- حداکثر اخطار ---
    "max_warns": 3,
    "max_warns_action": "kick",  # kick | mute
    "warn_reset": "weekly",  # never | daily | every3days | weekly | biweekly | monthly
    # --- مدت اخراج/تحریم خودکار ---
    "ban_duration": 180,   # روز
    "mute_duration": 60,   # دقیقه
    # --- گزارشگر هوشمند ---
    "smart_reporter": "off",  # off | on
    "smart_reporter_count": 3,
    "smart_reporter_action": "kick",  # kick | mute
}

# ==================== خاموشی ====================
DEFAULT_SHUTDOWN = {
    "enabled": False,
    "auto_off": "",      # "HH:MM"
    "auto_on": "",       # "HH:MM"
    "off_message": "🔇 گروه موقتاً خاموش است.",
    "on_message": "🔊 گروه روشن شد.",
    "duration_until": None,  # ISO datetime — خاموشی مدت‌دار
    "delete_off_message": False,  # حذف خودکار پیام خاموشی
    "shutdown_for_admins": False,  # خاموشی حتی برای مدیران
}

# ==================== ویژگی‌ها ====================
DEFAULT_FEATURES = {
    # --- پاکسازی خودکار پیام قدیمی ---
    "auto_cleanup": {"enabled": False, "after": "1h", "types": ["text", "photo", "video", "voice", "document", "sticker", "video_note", "gif", "story", "audio"]},
    # --- قفل فایل اعضاء جدید ---
    "new_member_file_lock": {"enabled": False, "days": 1},
    # --- پاسخگوی خودکار ---
    "auto_reply": {"mode": "off"},  # off | similar | exact
    # --- عضو اجباری کانال/گروه ---
    "force_channel": {"enabled": False, "channels": []},  # ["@ch1", "@ch2"]
    "force_group": {"enabled": False, "groups": []},
    "force_join_required": False,
    # --- کاربر ویژه بی اجبار ---
    "vip_no_force": False,
    # --- کلمات فیلتر شده ---
    "filtered_words": [],
    "filter_action": "delete",  # delete | warn | mute | kick
    "filter_sensitivity": "normal",  # normal | strict
    # --- قالب اجباری پیام ---
    "template_words": [],
    "template_condition": "and",  # and | or
    "template_action": "warn",  # delete | warn | mute | kick
    # --- تایید دعوت ---
    "join_approval": "none",  # none | auto | text_confirm | captcha | phone
    # --- متن‌ها ---
    "texts": {
        "welcome": "👋 به {group} خوش اومدی {user}!\n{date}",
        "rules": "📜 قوانین گروه:\n۱) احترام متقابل\n۲) بدون تبلیغ",
        "left": "خداحافظ {user} 👋",
        "force_join": "⚠️ برای ادامه، اول عضو کانال شو:\n{channel}",
        "approval_text": "⏳ درخواست عضویت شما در حال بررسی است...",
    },
}

DEFAULT_CLEANUP = {
    "enabled": False,
    "after_minutes": 60,
    "types": ["text", "photo", "video"],
}

DEFAULT_RAFFLE = {
    "enabled": False,
    "winners": 1,
    "text": "🎉 قرعه‌کشی گروه! برای شرکت، دکمهٔ زیر را بزنید.",
}

# ==================== دسترسی به کالکشن‌ها ====================
group_settings_col = None
users_col = None
warnings_col = None
bot = None
log = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def get_group_config(chat_id: int) -> dict[str, Any]:
    doc = await group_settings_col.find_one({"_id": chat_id})
    if not doc:
        doc = {
            "_id": chat_id,
            "locks": dict(DEFAULT_LOCKS),
            "antispam": dict(DEFAULT_ANTISPAM),
            "shutdown": dict(DEFAULT_SHUTDOWN),
            "features": dict(DEFAULT_FEATURES),
            "cleanup": dict(DEFAULT_CLEANUP),
        }
    doc.setdefault("locks", dict(DEFAULT_LOCKS))
    doc.setdefault("antispam", dict(DEFAULT_ANTISPAM))
    doc.setdefault("shutdown", dict(DEFAULT_SHUTDOWN))
    doc.setdefault("features", dict(DEFAULT_FEATURES))
    doc.setdefault("cleanup", dict(DEFAULT_CLEANUP))
    # تکمیل کلیدهای پیش‌فرض (برای قفل‌های جدید)
    for k, v in DEFAULT_LOCKS.items():
        doc["locks"].setdefault(k, v)
    for k, v in DEFAULT_ANTISPAM.items():
        doc["antispam"].setdefault(k, v)
    for k, v in DEFAULT_SHUTDOWN.items():
        doc["shutdown"].setdefault(k, v)
    for k, v in DEFAULT_FEATURES.items():
        doc["features"].setdefault(k, v)
    for k, v in DEFAULT_CLEANUP.items():
        doc["cleanup"].setdefault(k, v)
    return doc


async def save_group_config(chat_id: int, config: dict[str, Any]) -> None:
    await group_settings_col.update_one({"_id": chat_id}, {"$set": config}, upsert=True)


async def is_vip(user_id: int) -> bool:
    user = await users_col.find_one({"_id": user_id}, {"vip_expires_at": 1}) or {}
    exp = user.get("vip_expires_at")
    if not exp:
        return False
    try:
        if isinstance(exp, str):
            exp = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        return exp > now_utc()
    except Exception:
        return False


# ==================== تشخیص نوع پیام (کامل) ====================

_FA_SHORTCUT = set("چجحخهعغفقثصضشسیبلاتنمکگظطزرذدپو")


def _text_of(message) -> str:
    return (message.text or message.caption or "")


def _is_persian(text: str) -> bool:
    if not text:
        return False
    fa = sum(1 for ch in text if ch in _FA_SHORTCUT or "\u0600" <= ch <= "\u06FF")
    return fa >= max(1, len(text) // 3)


def _is_english(text: str) -> bool:
    if not text:
        return False
    en = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return en >= max(1, len(text) // 3)


def _emoji_count(text: str) -> int:
    # شمارش تقریبی ایموجی‌ها
    count = 0
    for ch in text:
        if 0x1F300 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF:
            count += 1
    return count


def classify_message(message) -> str | None:
    """نوع پیام را برمی‌گرداند (برای بررسی قفل‌ها)."""
    # رسانه‌ها
    if message.sticker:
        return "sticker"
    if message.animation:
        return "gif"
    if message.video_note:
        return "video_note"
    if message.video:
        return "video"
    if message.photo:
        return "photo"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.document:
        return "document"
    if message.location or message.venue:
        return "location"
    if message.poll:
        return "poll"
    if message.game:
        return "game"
    if message.contact:
        return "phone"
    if getattr(message, "story", None):
        return "story"
    # اپلیکیشن (فایل apk)
    if message.document and (message.document.file_name or "").lower().endswith(".apk"):
        return "app"

    # فوروارد
    forward_origin = getattr(message, "forward_origin", None)
    if forward_origin or getattr(message, "forward_date", None):
        origin_type = getattr(forward_origin, "type", "") if forward_origin else ""
        if origin_type in {"channel"}:
            chat_origin = getattr(forward_origin, "chat", None)
            if chat_origin is not None:
                if getattr(chat_origin, "type", "") in {"channel"}:
                    # عمومی یا خصوصی؟ از روی username
                    if getattr(chat_origin, "username", None):
                        return "forward_channel_public"
                    return "forward_channel_private"
            return "forward_channel_public"
        if origin_type in {"user", "hidden_user"}:
            return "forward_user"
        return "forward"

    text = _text_of(message)
    entities = list(message.entities or []) + list(message.caption_entities or [])

    # هایپرلینک مخفی
    for ent in entities:
        if getattr(ent, "type", "") == "text_link":
            return "link_hidden"

    # انواع لینک
    lower = text.lower()
    if "https://t.me/" in lower or "http://t.me/" in lower or "t.me/" in lower:
        # لینک ربات یا کانال/گروه یا شیشه‌ای
        tme = lower.split("t.me/", 1)[1].split("?", 1)[0].split(" ", 1)[0].strip()
        if tme.endswith("bot") or "bot" in tme:
            return "link_bot"
        if tme.startswith("share") or tme.startswith("addstickers") or tme.startswith("s/"):
            return "link_glass"
        if tme.startswith("+"):
            return "link_telegram"
        if tme.startswith("c/"):
            return "channel_id"
        return "link_telegram"
    if "instagram.com/" in lower or "instagr.am/" in lower:
        return "link_instagram"
    if "youtu.be/" in lower or "youtube.com/" in lower or "twitter.com/" in lower or "x.com/" in lower or "tiktok.com/" in lower:
        return "link_external"
    # لینک کوتاه
    short_domains = ("bit.ly", "tinyurl.com", "goo.gl", "cutt.ly", "shorturl.at", "rb.gy", "lnk.bio", "1ll.ink")
    for d in short_domains:
        if d in lower:
            return "link_short"
    if "http://" in lower or "https://" in lower or "www." in lower:
        return "link_external"
    # ایمیل
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        return "link_email"
    # شماره تلفن (۰۹۱۲... یا 912... یا +98912...)
    digits_only = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if re.search(r"(?<!\d)((\+98|0098|98|0)?9\d{9})(?!\d)", digits_only):
        return "phone"
    # آیدی کانال/گروه (@channel)
    if re.search(r"@[A-Za-z][A-Za-z0-9_]{3,}", text):
        return "channel_id"
    # منشن
    for ent in entities:
        et = getattr(ent, "type", "")
        if et == "mention":
            return "mention"
        if et == "text_mention":
            return "mention_text"
    if "@" in text:
        return "mention"

    # اسپویلر
    if "||" in text or getattr(message, "has_media_spoiler", False):
        return "spoiler"

    # پاسخ/ریپلای
    reply_to = getattr(message, "reply_to_message", None)
    if reply_to is not None:
        return "reply"

    # متن
    if text:
        # تعداد ایموجی (قبل از متن کوتاه — متن ایموجی‌ای کوتاه است)
        if _emoji_count(text) > 3:
            return "emoji_count"
        # متن بلند / کوتاه
        if len(text) > 500:
            return "long_text"
        if len(text) <= 15:
            return "short_text"
        # تایپ فارسی/انگلیسی
        if _is_persian(text):
            return "persian_typing"
        if _is_english(text):
            return "english_typing"
        return None
    return None


# ==================== خاموشی ====================

async def is_shutdown_active(config: dict[str, Any], now: datetime) -> bool:
    shutdown = config.get("shutdown") or {}
    if not shutdown.get("enabled"):
        return False
    duration_until = shutdown.get("duration_until")
    if duration_until:
        try:
            if isinstance(duration_until, str):
                duration_until = datetime.fromisoformat(str(duration_until).replace("Z", "+00:00"))
            if duration_until > now:
                return True
        except Exception:
            pass
    auto_off = str(shutdown.get("auto_off") or "")
    auto_on = str(shutdown.get("auto_on") or "")
    if auto_off and auto_on and ":" in auto_off and ":" in auto_on:
        try:
            off_h, off_m = map(int, auto_off.split(":")[:2])
            on_h, on_m = map(int, auto_on.split(":")[:2])
            now_minutes = now.hour * 60 + now.minute
            off_min = off_h * 60 + off_m
            on_min = on_h * 60 + on_m
            if off_min < on_min:
                return off_min <= now_minutes < on_min
            return now_minutes >= off_min or now_minutes < on_min
        except Exception:
            return False
    return False


# ==================== ضد مزاحمت ====================

async def check_antispam(chat_id: int, user_id: int, config: dict[str, Any]) -> str | None:
    """بررسی ضد اسپم کلاسیک؛ برمی‌گرداند اکشن: warn/delete/mute/ban یا None."""
    antispam = config.get("antispam") or {}
    if not antispam.get("enabled"):
        return None
    if await is_vip(user_id):
        # کاربر ویژه — محدودیت بالاتر
        max_msgs = int(antispam.get("vip_max_messages", 20))
        window_min = int(antispam.get("vip_window_minutes", 5))
    else:
        max_msgs = int(antispam.get("max_messages", 5))
        window_min = int(antispam.get("window_minutes", 1))
    window = timedelta(minutes=window_min)
    since = now_utc() - window
    try:
        count = await warnings_col.count_documents({
            "chat_id": chat_id,
            "user_id": user_id,
            "kind": {"$in": ["spam", None]},
            "created_at": {"$gte": since},
        })
    except Exception:
        count = await warnings_col.count_documents({
            "chat_id": chat_id,
            "user_id": user_id,
            "created_at": {"$gte": since},
        })
    if count >= max_msgs:
        return antispam.get("action", "warn")
    return None


async def check_fast_spam(chat_id: int, user_id: int, config: dict[str, Any]) -> bool:
    """ضد اسپم سریع: چند پیام در چند ثانیه."""
    antispam = config.get("antispam") or {}
    if not antispam.get("fast_enabled"):
        return False
    if await is_vip(user_id):
        return False
    count = int(antispam.get("fast_count", 8))
    seconds = int(antispam.get("fast_seconds", 5))
    since = now_utc() - timedelta(seconds=seconds)
    try:
        n = await warnings_col.count_documents({
            "chat_id": chat_id,
            "user_id": user_id,
            "kind": "spam",
            "created_at": {"$gte": since},
        })
        return n >= count
    except Exception:
        return False


async def is_tabchi(user_id: int) -> bool:
    """تشخیص تبچی: کاربری که کمتر از ۷ روز ساخته شده و اکانت جدید دارد."""
    user = await users_col.find_one({"_id": user_id}, {"joined_at": 1}) or {}
    joined = user.get("joined_at")
    if not joined:
        return False
    try:
        if isinstance(joined, str):
            joined = datetime.fromisoformat(str(joined).replace("Z", "+00:00"))
        return (now_utc() - joined).days < 7
    except Exception:
        return False


async def check_duplicate(chat_id: int, user_id: int, text: str, config: dict[str, Any]) -> bool:
    """بررسی پیام تکراری (آخرین پیام همان کاربر)."""
    antispam = config.get("antispam") or {}
    action = antispam.get("duplicate_action", "none")
    if action == "none" or not text:
        return False
    try:
        last = await warnings_col.find_one(
            {"chat_id": chat_id, "user_id": user_id, "kind": "last_msg"},
            sort=[("created_at", -1)],
        )
        if last and last.get("text") == text[:200] and (now_utc() - last["created_at"]).total_seconds() < 300:
            return True
    except Exception:
        return False
    return False


async def record_message(chat_id: int, user_id: int, text: str = "") -> None:
    """ردیابی پیام برای ضد اسپم + ثبت آخرین متن (برای پیام تکراری)."""
    from datetime import timedelta
    window = timedelta(hours=24)
    _id = f"spam:{chat_id}:{user_id}:{int(now_utc().timestamp() * 1000)}"
    await warnings_col.update_one(
        {"_id": _id},
        {"$set": {"chat_id": chat_id, "user_id": user_id, "kind": "spam", "text": text[:200], "created_at": now_utc()}},
        upsert=True,
    )
    # آخرین پیام برای تشخیص تکراری
    if text:
        await warnings_col.update_one(
            {"_id": f"last:{chat_id}:{user_id}"},
            {"$set": {"chat_id": chat_id, "user_id": user_id, "kind": "last_msg", "text": text[:200], "created_at": now_utc()}},
            upsert=True,
        )
    # پاک‌سازی قدیمی‌ها
    try:
        await warnings_col.delete_many({
            "chat_id": chat_id, "user_id": user_id, "kind": "spam",
            "created_at": {"$lt": now_utc() - window},
        })
    except Exception:
        pass


# ==================== فیلتر کلمات و قالب ====================

def check_filtered_words(text: str, config: dict[str, Any]) -> str | None:
    """بررسی کلمات فیلتر شده؛ برمی‌گرداند کلمهٔ یافت‌شده یا None."""
    features = config.get("features") or {}
    words = features.get("filtered_words") or []
    if not words or not text:
        return None
    lower = text.lower()
    for word in words:
        w = str(word).strip().lower()
        if not w:
            continue
        # قفل کلمه: *کلمه* → کلمهٔ مستقل (نه جزئی از کلمهٔ دیگر)
        if w.startswith("*") and w.endswith("*") and len(w) > 2:
            core = re.escape(w.strip("*"))
            pattern = rf"(?<![\w\u0600-\u06FF]){core}(?![\w\u0600-\u06FF])"
            if re.search(pattern, lower):
                return word
        elif w.startswith("*"):
            if lower.endswith(w[1:]):
                return word
        elif w.endswith("*"):
            if lower.startswith(w[:-1]):
                return word
        elif w in lower:
            return word
    return None


def check_template(text: str, config: dict[str, Any]) -> bool:
    """بررسی قالب اجباری پیام؛ True اگر رعایت شده باشد."""
    features = config.get("features") or {}
    words = features.get("template_words") or []
    if not words:
        return True
    condition = features.get("template_condition", "and")
    lower = text.lower()
    if condition == "or":
        return any(str(w).strip().lower() in lower for w in words if str(w).strip())
    return all(str(w).strip().lower() in lower for w in words if str(w).strip())


# ==================== قابلیت‌های تکمیلی گروه ====================

async def cleanup_old_messages(chat_id: int, config: dict[str, Any]) -> None:
    """پاکسازی خودکار پیام‌های قدیمی (فقط پیام‌های ربات را حذف می‌کند)."""
    cleanup = config.get("cleanup") or {}
    if not cleanup.get("enabled"):
        return
    after = int(cleanup.get("after_minutes", 60))
    from datetime import timedelta
    cutoff = now_utc() - timedelta(minutes=after)
    try:
        from bot import cleanup_messages_col
        old = await cleanup_messages_col.find({
            "chat_id": chat_id,
            "created_at": {"$lt": cutoff},
        }).to_list(length=200)
        for msg in old:
            try:
                if bot is not None:
                    await bot.delete_message(chat_id, msg["message_id"])
            except Exception:
                pass
            await cleanup_messages_col.delete_one({"_id": msg["_id"]})
    except Exception:
        pass


async def group_stats(chat_id: int, days: int = 7) -> dict[str, Any]:
    """آمار گروه: تعداد پیام، کاربران فعال، برترین‌ها."""
    from datetime import timedelta
    from collections import Counter
    since = now_utc() - timedelta(days=days)
    try:
        from bot import group_stats_col
        rows = await group_stats_col.find({
            "chat_id": chat_id,
            "created_at": {"$gte": since},
        }).to_list(length=50000)
    except Exception:
        rows = []
    total = len(rows)
    users = Counter(r.get("user_id") for r in rows)
    active = len(users)
    top = users.most_common(10)
    return {
        "total_messages": total,
        "active_users": active,
        "days": days,
        "top_users": [{"user_id": uid, "count": cnt} for uid, cnt in top],
    }


# ==================== قرعه‌کشی ====================

async def create_raffle(chat_id: int, winners: int = 1, text: str = "") -> dict:
    """ساخت قرعه‌کشی گروه."""
    try:
        from bot import raffles_col
    except Exception:
        raise
    raffle = {
        "_id": f"raffle-{chat_id}-{int(now_utc().timestamp())}",
        "chat_id": chat_id,
        "winners": max(1, int(winners)),
        "text": text or DEFAULT_RAFFLE["text"],
        "status": "active",  # active → drawn → closed
        "entries": [],
        "created_at": now_utc(),
    }
    await raffles_col.insert_one(raffle)
    return raffle


async def join_raffle(raffle_id: str, user_id: int) -> bool:
    """شرکت در قرعه‌کشی (بدون تکرار)."""
    try:
        from bot import raffles_col
    except Exception:
        return False
    raffle = await raffles_col.find_one({"_id": raffle_id, "status": "active"})
    if not raffle:
        return False
    if user_id in raffle.get("entries", []):
        return False
    await raffles_col.update_one({"_id": raffle_id}, {"$push": {"entries": user_id}})
    return True


async def draw_raffle(raffle_id: str) -> list[int] | None:
    """انتخاب برندگان قرعه‌کشی."""
    import random
    try:
        from bot import raffles_col
    except Exception:
        return None
    raffle = await raffles_col.find_one({"_id": raffle_id, "status": "active"})
    if not raffle:
        return None
    entries = raffle.get("entries", [])
    if not entries:
        return None
    winners_count = min(int(raffle.get("winners", 1)), len(entries))
    winners = random.sample(entries, winners_count)
    await raffles_col.update_one(
        {"_id": raffle_id},
        {"$set": {"status": "drawn", "winners": winners, "drawn_at": now_utc()}},
    )
    return winners


# ==================== دعوت اختصاصی ====================

async def register_invite(chat_id: int, inviter_id: int, new_user_id: int) -> None:
    """ثبت دعوت موفق (برای لینک دعوت اختصاصی)."""
    try:
        from bot import invite_stats_col
    except Exception:
        return
    await invite_stats_col.update_one(
        {"_id": f"inv-{chat_id}-{inviter_id}-{new_user_id}"},
        {"$set": {
            "chat_id": chat_id, "inviter_id": inviter_id, "new_user_id": new_user_id,
            "created_at": now_utc(),
        }},
        upsert=True,
    )


async def invite_count(chat_id: int, inviter_id: int) -> int:
    """تعداد دعوت‌های موفق یک کاربر در گروه."""
    try:
        from bot import invite_stats_col
        return await invite_stats_col.count_documents({"chat_id": chat_id, "inviter_id": inviter_id})
    except Exception:
        return 0


# ==================== هشدارها ====================

async def add_warning(chat_id: int, user_id: int, reason: str = "") -> int:
    """افزودن اخطار به کاربر؛ برمی‌گرداند تعداد کل اخطارهای فعال."""
    _id = f"warn:{chat_id}:{user_id}:{int(now_utc().timestamp() * 1000)}"
    await warnings_col.insert_one({
        "_id": _id,
        "chat_id": chat_id,
        "user_id": user_id,
        "kind": "warning",
        "reason": reason[:200],
        "created_at": now_utc(),
    })
    return await warning_count(chat_id, user_id)


async def warning_count(chat_id: int, user_id: int) -> int:
    """تعداد اخطارهای فعال کاربر."""
    try:
        return await warnings_col.count_documents({
            "chat_id": chat_id, "user_id": user_id, "kind": "warning",
        })
    except Exception:
        return 0


async def clear_warnings(chat_id: int, user_id: int) -> None:
    """پاک‌سازی اخطارهای کاربر."""
    try:
        await warnings_col.delete_many({"chat_id": chat_id, "user_id": user_id, "kind": "warning"})
    except Exception:
        pass
