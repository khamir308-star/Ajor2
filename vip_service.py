"""سیستم اشتراک پرمیوم (VIP) — پلن‌ها، سفارش‌ها، پرداخت کارت‌به‌کارت و فعال‌سازی.

جریان کامل:
1) کاربر از منوی «👑 اشتراک پرمیوم» یک پلن انتخاب می‌کند → سفارش با status=pending ساخته می‌شود.
2) ادمین در پنل مدیریت «💳 درخواست‌های اشتراک» را می‌بیند و دکمهٔ «💳 ارسال شماره کارت» را می‌زند.
3) ربات پیش‌فاکتور + شماره کارت را برای کاربر می‌فرستد → status=waiting_receipt.
4) کاربر رسید را ارسال می‌کند → به ادمین‌ها اطلاع داده می‌شود → status=payment_review.
5) ادمین «✅ تأیید» می‌زند → اشتراک فعال می‌شود (expires_at) → status=approved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# ---------- پلن‌های اشتراک ----------
VIP_PLANS: list[dict[str, Any]] = [
    {"months": 1, "title": "یک ماهه", "price": 99_000, "emoji": "🥉"},
    {"months": 3, "title": "سه ماهه", "price": 239_000, "emoji": "🥈"},
    {"months": 6, "title": "شش ماهه", "price": 429_000, "emoji": "🥇"},
    {"months": 12, "title": "یک ساله", "price": 587_000, "emoji": "👑"},
]

# ---------- دسترسی به کالکشن‌ها (در bot.py مقداردهی می‌شود) ----------
users_col = None
vip_orders_col = None
settings_col = None
admin_audit_col = None
log = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def plan_by_months(months: int) -> dict[str, Any] | None:
    return next((p for p in VIP_PLANS if p["months"] == months), None)


def vip_remaining_days(user: dict) -> int:
    """روزهای باقی‌ماندهٔ اشتراک کاربر (۰ اگر ندارد)."""
    exp = user.get("vip_expires_at")
    if not exp:
        return 0
    try:
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        remaining = (exp - now_utc()).total_seconds()
        return max(0, int(remaining // 86400))
    except Exception:
        return 0


def vip_expiry(user: dict) -> datetime | None:
    exp = user.get("vip_expires_at")
    if not exp:
        return None
    try:
        if isinstance(exp, str):
            return datetime.fromisoformat(exp.replace("Z", "+00:00"))
        return exp
    except Exception:
        return None


async def extend_vip(user_id: int, months: int) -> datetime:
    """تمدید/افزودن اشتراک کاربر؛ اگر اشتراک فعال داشته باشد، به آن اضافه می‌شود."""
    user = await users_col.find_one({"_id": user_id}, {"vip_expires_at": 1}) or {}
    base = vip_expiry(user) or now_utc()
    new_exp = max(base, now_utc()) + timedelta(days=30 * int(months))
    await users_col.update_one({"_id": user_id}, {"$set": {"vip_expires_at": new_exp}}, upsert=True)
    return new_exp


async def create_order(user_id: int, months: int) -> dict:
    """ساخت سفارش جدید (فقط اگر سفارش باز نداشته باشد)."""
    open_order = await vip_orders_col.find_one({
        "user_id": user_id,
        "status": {"$in": ["pending", "waiting_receipt", "payment_review"]},
    })
    if open_order:
        raise ValueError("order_open", "شما یک سفارش باز دارید؛ اول آن را تکمیل یا منتظر تأیید بمانید.")
    plan = plan_by_months(months)
    if not plan:
        raise ValueError("bad_plan", "پلن نامعتبر است.")
    order = {
        "_id": f"vip-{user_id}-{int(now_utc().timestamp())}",
        "user_id": user_id,
        "months": months,
        "plan_title": plan["title"],
        "price": plan["price"],
        "status": "pending",  # pending → waiting_receipt → payment_review → approved / rejected
        "card_info": "",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await vip_orders_col.insert_one(order)
    return order


async def set_card(order_id: str, card_text: str) -> dict | None:
    """ادمین شماره کارت را برای سفارش ثبت می‌کند (پیش‌فاکتور بعداً توسط هندلر ارسال می‌شود)."""
    order = await vip_orders_col.find_one({"_id": order_id})
    if not order:
        return None
    await vip_orders_col.update_one(
        {"_id": order_id},
        {"$set": {"card_info": card_text[:300], "status": "waiting_receipt", "updated_at": now_utc()}},
    )
    order.update({"card_info": card_text[:300], "status": "waiting_receipt"})
    return order


async def mark_receipt(order_id: str, receipt_file_id: str) -> dict | None:
    """کاربر رسید ارسال کرد → برای بررسی ادمین."""
    order = await vip_orders_col.find_one({"_id": order_id})
    if not order:
        return None
    await vip_orders_col.update_one(
        {"_id": order_id},
        {"$set": {"status": "payment_review", "receipt_file_id": receipt_file_id, "updated_at": now_utc()}},
    )
    order.update({"status": "payment_review", "receipt_file_id": receipt_file_id})
    return order


async def approve_order(order_id: str, approved_by: int) -> dict | None:
    """تأیید نهایی ادمین → فعال‌سازی اشتراک."""
    order = await vip_orders_col.find_one({"_id": order_id})
    if not order:
        return None
    new_exp = await extend_vip(order["user_id"], order["months"])
    await vip_orders_col.update_one(
        {"_id": order_id},
        {"$set": {"status": "approved", "approved_by": approved_by, "approved_at": now_utc(), "updated_at": now_utc()}},
    )
    order.update({"status": "approved"})
    return {**order, "new_expires_at": new_exp}


async def reject_order(order_id: str, approved_by: int) -> dict | None:
    order = await vip_orders_col.find_one({"_id": order_id})
    if not order:
        return None
    await vip_orders_col.update_one(
        {"_id": order_id},
        {"$set": {"status": "rejected", "approved_by": approved_by, "approved_at": now_utc(), "updated_at": now_utc()}},
    )
    order.update({"status": "rejected"})
    return order


async def list_open_orders(limit: int = 20) -> list[dict]:
    cursor = vip_orders_col.find(
        {"status": {"$in": ["pending", "waiting_receipt", "payment_review"]}}
    ).sort("created_at", 1)
    return await cursor.to_list(length=limit)
