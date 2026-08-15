"""موتور مدیریت گروه — قفل‌ها، ضد اسپم و خاموشی.

شبیه پنل‌های حرفه‌ای (مثل TLPro):
- قفل‌ها: هر نوع پیام را برای کاربر عادی محدود می‌کند؛ کاربر ویژه آزاد است.
- ضد اسپم: محدودیت تعداد پیام + ضد تبچی.
- خاموشی: ساعت خاموش/روشن خودکار + خاموشی مدت‌دار.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------- قفل‌های پشتیبانی‌شده ----------
LOCKS = {
    "sticker": "استیکر",
    "gif": "گیف",
    "video": "ویدئو",
    "photo": "تصویر",
    "audio": "موزیک",
    "voice": "ویس",
    "video_note": "ویدئو گرد",
    "link": "لینک",
    "mention": "منشن",
    "forward": "فوروارد",
    "spoiler": "اسپویلر",
    "document": "فایل",
}

DEFAULT_LOCKS: dict[str, bool] = {k: False for k in LOCKS}

DEFAULT_ANTISPAM = {
    "enabled": False,
    "max_messages": 5,
    "window_minutes": 1,
    "action": "warn",  # warn | delete | mute | ban
}

DEFAULT_SHUTDOWN = {
    "enabled": False,
    "auto_off": "",      # "HH:MM"
    "auto_on": "",       # "HH:MM"
    "off_message": "🔇 گروه موقتاً خاموش است.",
    "on_message": "🔊 گروه روشن شد.",
    "duration_until": None,  # ISO datetime — خاموشی مدت‌دار
}


# ---------- دسترسی به کالکشن‌ها ----------
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
        }
    doc.setdefault("locks", dict(DEFAULT_LOCKS))
    doc.setdefault("antispam", dict(DEFAULT_ANTISPAM))
    doc.setdefault("shutdown", dict(DEFAULT_SHUTDOWN))
    for k, v in DEFAULT_LOCKS.items():
        doc["locks"].setdefault(k, v)
    for k, v in DEFAULT_ANTISPAM.items():
        doc["antispam"].setdefault(k, v)
    for k, v in DEFAULT_SHUTDOWN.items():
        doc["shutdown"].setdefault(k, v)
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


def classify_message(message) -> str | None:
    """نوع پیام را برمی‌گرداند (برای بررسی قفل‌ها)."""
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
    if message.forward_origin or getattr(message, "forward_date", None):
        return "forward"
    text = message.text or message.caption or ""
    if message.entities or message.caption_entities:
        for ent in (message.entities or []) + (message.caption_entities or []):
            et = getattr(ent, "type", "")
            if et in {"url", "text_link"}:
                return "link"
            if et in {"mention", "text_mention"}:
                return "mention"
    if "http://" in text or "https://" in text or "t.me/" in text or "www." in text:
        return "link"
    if "@" in text:
        return "mention"
    if "||" in text or getattr(message, "has_media_spoiler", False):
        return "spoiler"
    return None


async def is_shutdown_active(config: dict[str, Any], now: datetime) -> bool:
    """خاموشی مدت‌دار یا ساعتی فعال است؟"""
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


async def check_antispam(chat_id: int, user_id: int, config: dict[str, Any]) -> str | None:
    """بررسی ضد اسپم؛ برمی‌گرداند اکشن موردنیاز: warn/delete/mute/ban یا None."""
    antispam = config.get("antispam") or {}
    if not antispam.get("enabled"):
        return None
    if await is_vip(user_id):
        return None
    from datetime import timedelta
    window = timedelta(minutes=int(antispam.get("window_minutes", 1)))
    since = now_utc() - window
    count = await warnings_col.count_documents({
        "chat_id": chat_id,
        "user_id": user_id,
        "created_at": {"$gte": since},
    })
    max_msgs = int(antispam.get("max_messages", 5))
    if count >= max_msgs:
        return antispam.get("action", "warn")
    return None


async def record_message(chat_id: int, user_id: int) -> None:
    """ردیابی پیام برای ضد اسپم."""
    from datetime import timedelta
    window = timedelta(hours=24)
    await warnings_col.update_one(
        {"_id": f"spam:{chat_id}:{user_id}:{int(now_utc().timestamp())}"},
        {"$set": {"chat_id": chat_id, "user_id": user_id, "created_at": now_utc()}},
        upsert=True,
    )
    # پاک‌سازی قدیمی‌ها
    await warnings_col.delete_many({
        "chat_id": chat_id, "user_id": user_id,
        "created_at": {"$lt": now_utc() - window},
    })
