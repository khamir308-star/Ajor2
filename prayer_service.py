"""Prayer times (اوقات شرعی) + Hafez fal (فال حافظ) for Ajorpareh.

Sources (free, no API keys):
- Aladhan API: prayer times by city coordinates (method 8 = Tehran/IRI)
- falehafez.org: daily Hafez poem with interpretation

All public content. No credentials required.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import aiohttp

from media_service import MediaServiceError

PRAYER_API = "https://api.aladhan.com/v1/timings"
HAFEZ_API = "https://api.falehafez.org/v1/faal"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# روش ۸ = سازمان اوقاف ایران (Tehran)
PRAYER_METHOD = 8

# نام فارسی اوقات
PRAYER_LABELS = {
    "Fajr": "🌅 اذان صبح",
    "Sunrise": "🌄 طلوع آفتاب",
    "Dhuhr": "☀️ اذان ظهر",
    "Asr": "🌇 اذان عصر",
    "Maghrib": "🌆 اذان مغرب",
    "Isha": "🌃 اذان عشاء",
    "Midnight": "🌙 نیمه‌شب شرعی",
    "Imsak": "🤲 امساک",
}

CITY_ALIASES = {
    "تهران": "Tehran", "tehran": "Tehran",
    "مشهد": "Mashhad", "mashhad": "Mashhad",
    "اصفهان": "Isfahan", "isfahan": "Isfahan",
    "شیراز": "Shiraz", "shiraz": "Shiraz",
    "تبریز": "Tabriz", "tabriz": "Tabriz",
    "کرج": "Karaj", "karaj": "Karaj",
    "اهواز": "Ahvaz", "ahvaz": "Ahvaz",
    "قم": "Qom", "qom": "Qom",
    "کرمانشاه": "Kermanshah", "kermanshah": "Kermanshah",
    "رشت": "Rasht", "rasht": "Rasht",
    "ارومیه": "Urmia", "urmia": "Urmia",
    "زاهدان": "Zahedan", "zahedan": "Zahedan",
    "همدان": "Hamedan", "hamedan": "Hamedan",
    "بندرعباس": "Bandar Abbas", "bandarabbas": "Bandar Abbas",
    "اراک": "Arak", "arak": "Arak",
    "یزد": "Yazd", "yazd": "Yazd",
    "ساری": "Sari", "sari": "Sari",
    "گرگان": "Gorgan", "gorgan": "Gorgan",
    "زنجان": "Zanjan", "zanjan": "Zanjan",
    "سنندج": "Sanandaj", "sanandaj": "Sanandaj",
    "بوشهر": "Bushehr", "bushehr": "Bushehr",
    "لندن": "London", "london": "London",
    "دبی": "Dubai", "dubai": "Dubai",
    "استانبول": "Istanbul", "istanbul": "Istanbul",
    "مکه": "Mecca", "mecca": "Mecca", "مکه مکرمه": "Mecca",
    "مدینه": "Medina", "medina": "Medina",
}


def normalize_prayer_city(name: str) -> str:
    return CITY_ALIASES.get(str(name or "").strip().lower(), str(name or "").strip())


async def _fetch_json(session: aiohttp.ClientSession, url: str, timeout: int = 25) -> Any:
    try:
        async with session.get(url, headers={"User-Agent": "AjorparehBot/1.0 (+https://t.me/Ajorparehbot)"},
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status not in (200, 201):
                raise MediaServiceError("http_error", f"سرویس با خطای HTTP {resp.status} پاسخ داد.")
            return await resp.json(content_type=None)
    except asyncio.TimeoutError as exc:
        raise MediaServiceError("timeout", "سرویس پاسخ نداد؛ کمی بعد دوباره تلاش کن.") from exc
    except aiohttp.ClientError as exc:
        raise MediaServiceError("network", "اتصال به سرویس برقرار نشد.") from exc


async def _city_coordinates(city_name: str) -> tuple[float, float, str, str]:
    """یافتن مختصات شهر از Open-Meteo geocoding (بدون کلید)."""
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
    try:
        geo = await _fetch_json(session, f"{GEOCODE_URL}?name={quote(city_name)}&count=1")
    finally:
        await session.close()
    results = (geo or {}).get("results") or []
    if not results:
        raise MediaServiceError("city_not_found", f"شهری به نام «{city_name}» پیدا نشد؛ املای انگلیسی را امتحان کن.")
    lat = results[0]["latitude"]
    lon = results[0]["longitude"]
    found = results[0].get("name") or city_name
    country = results[0].get("country") or ""
    return lat, lon, found, country


async def prayer_times(city: str) -> dict[str, Any]:
    """اوقات شرعی شهر — برمی‌گرداند زمان‌ها + تاریخ شمسی/قمری."""
    name = normalize_prayer_city(city)
    if not name:
        raise MediaServiceError("invalid_city", "نام شهر را بنویس؛ مثلاً /pray تهران")
    lat, lon, found_name, country = await _city_coordinates(name)
    import datetime as _dt
    today = _dt.date.today().strftime("%d-%m-%Y")
    url = (
        f"{PRAYER_API}/{today}?latitude={lat}&longitude={lon}"
        f"&method={PRAYER_METHOD}&timezonestring=Asia/Tehran"
    )
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    try:
        data = await _fetch_json(session, url, timeout=30)
    finally:
        await session.close()
    if not data or data.get("code") != 200:
        raise MediaServiceError("unavailable", "دریافت اوقات شرعی ناموفق بود؛ دوباره تلاش کن.")
    timings = data["data"]["timings"]
    date_info = data["data"]["date"]
    hijri = date_info.get("hijri") or {}
    return {
        "city": found_name,
        "country": country,
        "timings": timings,
        "gregorian": date_info.get("readable") or "",
        "hijri": f"{hijri.get('day')} {hijri.get('month', {}).get('en', '')} {hijri.get('year', '')}",
        "weekday": date_info.get("gregorian", {}).get("weekday", {}).get("en", "") if isinstance(date_info.get("gregorian"), dict) else "",
    }


def format_prayer_text(data: dict[str, Any]) -> str:
    lines = [
        f"🕌 <b>اوقات شرعی {html_escape(data['city'])}</b>"
        + (f"، {html_escape(data['country'])}" if data.get("country") else ""),
        f"📅 {data.get('gregorian')} · 🌙 {data.get('hijri')}",
        "",
    ]
    timings = data.get("timings") or {}
    for key, label in PRAYER_LABELS.items():
        value = timings.get(key)
        if value:
            lines.append(f"{label}: <b>{html_escape(str(value))}</b>")
    lines.append("")
    lines.append("🕰 روش محاسبه: سازمان اوقاف ایران (روش ۸)")
    return "\n".join(lines)


def html_escape(value: str) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def hafez_fal() -> dict[str, Any]:
    """فال حافظ — شعر + تفسیر."""
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    try:
        data = await _fetch_json(session, HAFEZ_API, timeout=30)
    finally:
        await session.close()
    if not data:
        raise MediaServiceError("unavailable", "دریافت فال حافظ ناموفق بود؛ دوباره تلاش کن.")
    poem = data.get("poem") or []
    interpretation = data.get("explanation") or data.get("interpretation") or ""
    return {
        "poem": poem,
        "interpretation": interpretation,
    }
