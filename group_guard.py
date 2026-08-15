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
    doc.setdefault("cleanup", dict(DEFAULT_CLEANUP))
    for k, v in DEFAULT_LOCKS.items():
        doc["locks"].setdefault(k, v)
    for k, v in DEFAULT_ANTISPAM.items():
        doc["antispam"].setdefault(k, v)
    for k, v in DEFAULT_SHUTDOWN.items():
        doc["shutdown"].setdefault(k, v)
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

# ================== قابلیت‌های تکمیلی گروه ==================

DEFAULT_CLEANUP = {
    "enabled": False,
    "after_minutes": 60,   # پیام‌های قدیمی‌تر از این حذف شوند
    "types": ["text", "photo", "video"],  # انواع پیام
}

DEFAULT_RAFFLE = {
    "enabled": False,
    "winners": 1,
    "text": "🎉 قرعه‌کشی گروه! برای شرکت، دکمهٔ زیر را بزنید.",
}


async def cleanup_old_messages(chat_id: int, config: dict[str, Any]) -> None:
    """پاکسازی خودکار پیام‌های قدیمی (فقط پیام‌های ربات را حذف می‌کند)."""
    cleanup = config.get("cleanup") or {}
    if not cleanup.get("enabled"):
        return
    after = int(cleanup.get("after_minutes", 60))
    # پیام‌های ربات در گروه — هر پیام‌ی که بفرستیم را track می‌کنیم
    # (در bot.py پیام‌های ربات ثبت می‌شوند و اینجا حذف می‌شوند)
    from datetime import timedelta
    cutoff = now_utc() - timedelta(minutes=after)
    # پیاده‌سازی ساده: پیام‌های ثبت‌شده در collection را حذف کن
    try:
        from bot import cleanup_messages_col
        old = await cleanup_messages_col.find({
            "chat_id": chat_id,
            "created_at": {"$lt": cutoff},
        }).to_list(length=200)
        for msg in old:
            try:
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


async def create_raffle(chat_id: int, winners: int = 1, text: str = "") -> dict:
    """ساخت قرعه‌کشی گروه."""
    try:
        from bot import raffles_col
    except Exception:
        from bot import raffles_col
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
