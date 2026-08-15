"""سیستم چت ناشناس — ارسال پیام ناشناس با لینک اختصاصی.

جریان کامل:
1) کاربر از منوی «🎭 چت ناشناس» یک اسم مستعار می‌نویسد.
2) آیدی گیرنده را می‌نویسد (@username یا آیدی عددی).
3) متن پیام را می‌نویسد → در Mongo ذخیره می‌شود → لینک
   t.me/...?start=anon_<token> ساخته می‌شود.
4) گیرنده روی لینک می‌زند → پیام را می‌خواند و می‌تواند ناشناس پاسخ دهد.
5) پاسخ به فرستندهٔ اصلی برمی‌گردد (باز هم ناشناس) و برای او لینک/اطلاع ارسال می‌شود.

هویت فرستنده هیچ‌وقت در سند ذخیره‌شده به گیرنده نمایش داده نمی‌شود؛ فقط sender_id
برای ارسال پاسخ به فرستندهٔ اصلی استفاده می‌شود.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

# ---------- اتصال به کالکشن‌ها (در bot.py مقداردهی می‌شود) ----------
anon_messages_col = None
users_col = None
log = None

# hook برای پیدا کردن کاربر با @username خارج از دیتابیس (مثلاً bot.get_chat)
resolve_username_hook: Callable[[str], Awaitable[tuple[int, str] | None]] | None = None

# ---------- محدودیت‌ها ----------
ALIAS_MIN = 2
ALIAS_MAX = 25
TEXT_MAX = 1000
DAILY_LIMIT = 10  # حداکثر پیام ناشناس ارسالی هر کاربر در روز
MSG_TTL_DAYS = 30  # پیام‌ها بعد از ۳۰ روز خودکار پاک می‌شوند

_ALIAS_RE = re.compile(r"^[\w\u0600-\u06FF\sآ-ی]+$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def make_token() -> str:
    """توکن یکتا و URL-safe برای لینک پیام ناشناس."""
    return "a" + secrets.token_urlsafe(12)


def validate_alias(name: str) -> str | None:
    """اعتبارسنجی اسم مستعار؛ در صورت خطا پیام خطا برمی‌گرداند."""
    alias = (name or "").strip()
    if not alias:
        return "اسم مستعار نمی‌تونه خالی باشه."
    if len(alias) < ALIAS_MIN or len(alias) > ALIAS_MAX:
        return f"اسم مستعار باید بین {ALIAS_MIN} تا {ALIAS_MAX} حرف باشه."
    if not _ALIAS_RE.match(alias):
        return "اسم مستعار فقط می‌تونه شامل حروف، عدد، فاصله و خط تیره باشه."
    return None


def parse_target(text: str) -> tuple[str, str] | None:
    """تشخیص نوع آیدی گیرنده: ('username', 'foo') یا ('id', '123')."""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        username = raw[1:].strip().lower()
        if username:
            return ("username", username)
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if digits.isdigit() and digits:
        return ("id", digits)
    return None


async def resolve_target_id(raw: str) -> tuple[int | None, str | None, str | None]:
    """تبدیل متن آیدی به (target_id, display_name, error)."""
    parsed = parse_target(raw)
    if not parsed:
        return None, None, "آیدی نامعتبره؛ آیدی عددی یا @username بفرست."
    kind, value = parsed
    if kind == "id":
        try:
            target_id = int(value)
        except ValueError:
            return None, None, "آیدی عددی نامعتبره."
        if target_id <= 0:
            return None, None, "آیدی عددی نامعتبره."
        return target_id, None, None
    # @username → اول در دیتابیس، بعد از طریق hook (Telegram)
    if users_col is not None:
        try:
            doc = await users_col.find_one({"username": value})
            if doc and isinstance(doc.get("_id"), int):
                return doc["_id"], doc.get("name") or f"@{value}", None
        except Exception as exc:
            if log:
                log.warning("anon resolve db failed: %s", exc)
    if resolve_username_hook is not None:
        try:
            result = await resolve_username_hook(value)
            if result:
                return result[0], result[1] or f"@{value}", None
        except Exception as exc:
            if log:
                log.warning("anon resolve hook failed: %s", exc)
    return None, None, (
        "گیرنده پیدا نشد؛ املای یوزرنیم رو چک کن یا به‌جاش آیدی عددی بفرست. "
        "اگه یوزرنیمش رو اشتباه نوشتی یا صفحه‌اش خصوصیه، قابل پیدا کردن نیست."
    )


async def daily_sent_count(sender_id: int) -> int:
    """تعداد پیام‌های ناشناس ارسال‌شدهٔ امروز توسط کاربر (بدون احتساب پاسخ‌ها)."""
    if anon_messages_col is None:
        return 0
    start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    try:
        return await anon_messages_col.count_documents({
            "sender_id": sender_id,
            "kind": {"$ne": "reply"},
            "created_at": {"$gte": start},
        })
    except Exception:
        return 0


async def create_message(
    sender_id: int,
    sender_alias: str,
    target_id: int,
    text: str,
    reply_to: str | None = None,
    media_type: str | None = None,
    media_file_id: str | None = None,
) -> dict[str, Any] | None:
    """ساخت و ذخیرهٔ پیام ناشناس؛ در صورت موفقیت سند کامل برمی‌گرداند.

    رسانه‌های پشتیبانی‌شده (media_type): photo, voice, video, animation,
    video_note, audio, document, sticker — file_id در media_file_id ذخیره می‌شود
    و متن/کپشن کاربر در text.
    """
    if anon_messages_col is None:
        return None
    token = make_token()
    doc: dict[str, Any] = {
        "_id": token,
        "kind": "reply" if reply_to else "message",
        "sender_id": sender_id,
        "sender_alias": sender_alias[:ALIAS_MAX],
        "target_id": target_id,
        "text": (text or "")[:TEXT_MAX],
        "media_type": media_type,
        "media_file_id": media_file_id,
        "reply_to": reply_to,
        "created_at": now_utc(),
        "read": False,
        "delivered": False,
    }
    try:
        await anon_messages_col.insert_one(doc)
        return doc
    except Exception as exc:
        if log:
            log.warning("anon create failed: %s", exc)
        return None


async def get_message(token: str) -> dict[str, Any] | None:
    if anon_messages_col is None or not token:
        return None
    try:
        return await anon_messages_col.find_one({"_id": token[:64]})
    except Exception:
        return None


async def mark_read(token: str) -> None:
    if anon_messages_col is None:
        return
    try:
        await anon_messages_col.update_one(
            {"_id": token[:64]}, {"$set": {"read": True}}
        )
    except Exception:
        pass


async def mark_delivered(token: str) -> None:
    if anon_messages_col is None:
        return
    try:
        await anon_messages_col.update_one(
            {"_id": token[:64]}, {"$set": {"delivered": True}}
        )
    except Exception:
        pass
