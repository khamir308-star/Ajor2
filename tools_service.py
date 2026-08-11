"""Free public-data tools for Ajorpareh — no API keys required.

Sources:
- Open-Meteo: weather (10k calls/day, no key)
- Frankfurter: ECB daily FX rates (unlimited, no key)
- CoinGecko: crypto prices (30/min, no key)
- Wikipedia REST: article summaries (fa/en)
- Open Library: book search (no key)
- REST Countries: country info (no key)
- Pwned Passwords (HIBP range API): password breach count (no key)
- Open Trivia DB: quiz questions (no key)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from media_service import MediaServiceError

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FRANKFURTER_URL = "https://api.frankfurter.app/latest"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
WIKIPEDIA_SEARCH_URL = "https://{lang}.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"
REST_COUNTRIES_URL = "https://restcountries.com/v3.1/name/{name}"
PWNED_URL = "https://api.pwnedpasswords.com/range/{prefix}"
OPENTDB_URL = "https://opentdb.com/api.php"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
OWM_URL = "https://api.openweathermap.org/data/2.5"
UPSTASH_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
UPSTASH_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()

OWM_ICONS: dict[str, tuple[str, str]] = {
    "01d": ("☀️", "آفتابی"), "01n": ("🌙", "شب صاف"),
    "02d": ("🌤", "کمی ابری"), "02n": ("🌙", "شب کمی ابری"),
    "03d": ("☁️", "ابری"), "03n": ("☁️", "ابری"),
    "04d": ("☁️", "ابری کامل"), "04n": ("☁️", "ابری کامل"),
    "09d": ("🌧", "بارون"), "09n": ("🌧", "بارون"),
    "10d": ("🌦", "بارون ملایم"), "10n": ("🌧", "بارون شبانه"),
    "11d": ("⛈", "رعد و برق"), "11n": ("⛈", "رعد و برق"),
    "13d": ("🌨", "برف"), "13n": ("🌨", "برف"),
    "50d": ("🌫", "مه"), "50n": ("🌫", "مه"),
}

WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("☀️ آفتابی", "صاف"),
    1: ("🌤", "کمی ابری"),
    2: ("⛅️", "نیمه‌ابری"),
    3: ("☁️", "ابری"),
    45: ("🌫", "مه"),
    48: ("🌫", "مه یخ‌زده"),
    51: ("🌦", "نم نم بارون"),
    53: ("🌦", "بارون خفیف"),
    55: ("🌧", "بارون ملایم"),
    61: ("🌧", "بارون"),
    63: ("🌧", "بارون نسبتاً شدید"),
    65: ("⛈", "بارون شدید"),
    71: ("🌨", "برف خفیف"),
    73: ("🌨", "برف"),
    75: ("❄️", "برف سنگین"),
    80: ("🌦", "رگبار"),
    81: ("🌧", "رگبار شدید"),
    82: ("⛈", "رگبار خیلی شدید"),
    95: ("⛈", "رعد و برق"),
    96: ("⛈", "رعد و برق با تگرگ"),
    99: ("⛈", "رعد و برق با تگرگ شدید"),
}

CITY_ALIASES = {
    "تهران": "Tehran", "tehran": "Tehran", "طهران": "Tehran",
    "مشهد": "Mashhad", "mashhad": "Mashhad",
    "اصفهان": "Isfahan", "isfahan": "Isfahan", "esfahan": "Isfahan",
    "شیراز": "Shiraz", "shiraz": "Shiraz",
    "تبریز": "Tabriz", "tabriz": "Tabriz",
    "کرج": "Karaj", "karaj": "Karaj",
    "اهواز": "Ahvaz", "ahvaz": "Ahvaz", "ahwaz": "Ahwaz",
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
    "قمصر": "Qamsar",
    "لندن": "London", "london": "London",
    "پاریس": "Paris", "paris": "Paris",
    "نیویورک": "New York", "new york": "New York", "nyc": "New York",
    "دبی": "Dubai", "dubai": "Dubai",
    "استانبول": "Istanbul", "istanbul": "Istanbul",
    "آنکارا": "Ankara", "ankara": "Ankara",
    "باکو": "Baku", "baku": "Baku",
    "برلین": "Berlin", "berlin": "Berlin",
    "توکیو": "Tokyo", "tokyo": "Tokyo",
    "لس‌آنجلس": "Los Angeles", "los angeles": "Los Angeles",
    "تورنتو": "Toronto", "toronto": "Toronto",
    "سیدنی": "Sydney", "sydney": "Sydney",
    "مسکو": "Moscow", "moscow": "Moscow",
}

CRYPTO_ALIASES = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "بیت‌کوین": "bitcoin", "بیتکوین": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum", "اتریوم": "ethereum",
    "usdt": "tether", "tether": "tether", "تتر": "tether",
    "bnb": "binancecoin", "binance coin": "binancecoin",
    "sol": "solana", "solana": "solana", "سولانا": "solana",
    "xrp": "ripple", "ripple": "ripple",
    "doge": "dogecoin", "dogecoin": "dogecoin", "دوج": "dogecoin",
    "ada": "cardano", "cardano": "cardano",
    "trx": "tron", "tron": "tron",
    "ton": "the-open-network", "the open network": "the-open-network",
    "ltc": "litecoin", "litecoin": "litecoin",
    "dot": "polkadot", "polkadot": "polkadot",
    "avax": "avalanche-2", "avalanche": "avalanche-2",
    "shib": "shiba-inu", "shiba": "shiba-inu",
    "matic": "polygon", "polygon": "polygon",
    "near": "near", "atom": "cosmos", "cosmos": "cosmos",
    "uni": "uniswap", "uniswap": "uniswap",
    "link": "chainlink", "chainlink": "chainlink",
}

CURRENCY_ALIASES = {
    "دلار": "USD", "usd": "USD", "$": "USD",
    "یورو": "EUR", "eur": "EUR", "€": "EUR",
    "پوند": "GBP", "gbp": "GBP", "£": "GBP",
    "درهم": "AED", "aed": "AED",
    "ریال": "IRR", "irr": "IRR", "تومان": "IRR",
    "لیر": "TRY", "try": "TRY",
    "یوان": "CNY", "cny": "CNY",
    "ین": "JPY", "jpy": "JPY",
    "روبل": "RUB", "rub": "RUB",
    "فرانک": "CHF", "chf": "CHF",
    "دلار کانادا": "CAD", "cad": "CAD",
    "دلار استرالیا": "AUD", "aud": "AUD",
    "کرون سوئد": "SEK", "sek": "SEK",
}


def normalize_city(name: str) -> str:
    return CITY_ALIASES.get(str(name or "").strip().lower(), str(name or "").strip())


def _parse_crypto_symbol(symbol: str) -> str:
    return CRYPTO_ALIASES.get(str(symbol or "").strip().lower(), str(symbol or "").strip().lower())


def _parse_currency(code: str) -> str:
    return CURRENCY_ALIASES.get(str(code or "").strip().lower(), str(code or "").strip().upper())


_shared_session: aiohttp.ClientSession | None = None
# کش سادهٔ حافظه‌ای با TTL — کاهش درخواست‌های تکراری به API های خارجی
_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 300  # ۵ دقیقه


def _redis_available() -> bool:
    return bool(UPSTASH_REST_URL and UPSTASH_REST_TOKEN)


async def _redis_get(key: str) -> Any | None:
    """خواندن از Upstash Redis (REST) — بدون نیاز به سرور Redis محلی."""
    if not _redis_available():
        return None
    session = await get_session()
    try:
        async with session.get(
            f"{UPSTASH_REST_URL}/get/{key}",
            headers={"Authorization": f"Bearer {UPSTASH_REST_TOKEN}"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
        raw = data.get("result") if isinstance(data, dict) else None
        if raw is None:
            return None
        return json_loads(raw)
    except Exception:
        return None


async def _redis_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS) -> bool:
    if not _redis_available():
        return False
    session = await get_session()
    try:
        raw = json_dumps(value)
        async with session.get(
            f"{UPSTASH_REST_URL}/set/{key}/{raw}/ex/{int(ttl)}",
            headers={"Authorization": f"Bearer {UPSTASH_REST_TOKEN}"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


async def _cache_get(key: str) -> Any | None:
    """کش دو لایه: Redis (مشترک بین نمونه‌ها) ← حافظهٔ محلی."""
    if _redis_available():
        value = await _redis_get(key)
        if value is not None:
            return value
    item = _cache.get(key)
    if item and item[0] > time.monotonic():
        return item[1]
    if item:
        _cache.pop(key, None)
    return None


async def _cache_set(key: str, value: Any, ttl: float = CACHE_TTL_SECONDS) -> None:
    """ست کش در هر دو لایه؛ خطای Redis بی‌صدا نادیده گرفته می‌شود (فال‌بک حافظه)."""
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic() + ttl, value)
    if _redis_available():
        try:
            await _redis_set(key, value, int(ttl))
        except Exception:
            pass


def json_dumps(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


def json_loads(raw: str) -> Any:
    import json
    try:
        return json.loads(raw)
    except Exception:
        return None


async def get_session() -> aiohttp.ClientSession:
    """سشن مشترک ماژول برای درخواست‌های HTTP (بهینه‌سازی مصرف منابع)."""
    global _shared_session
    if _shared_session is None or _shared_session.closed:
        _shared_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))
    return _shared_session


async def close_session() -> None:
    global _shared_session
    if _shared_session and not _shared_session.closed:
        await _shared_session.close()
    _shared_session = None


async def _fetch_json(session: aiohttp.ClientSession | None, url: str, timeout: int = 25) -> Any:
    if session is None:
        session = await get_session()
    try:
        async with session.get(url, headers={"User-Agent": "AjorparehBot/1.0 (+https://t.me/Ajorparehbot)"},
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                raise MediaServiceError("http_error", f"سرویس با خطای HTTP {resp.status} پاسخ داد.")
            return await resp.json(content_type=None)
    except asyncio.TimeoutError as exc:
        raise MediaServiceError("timeout", "سرویس پاسخ نداد؛ کمی بعد دوباره تلاش کن.") from exc
    except aiohttp.ClientError as exc:
        raise MediaServiceError("network", "اتصال به سرویس برقرار نشد.") from exc


# ============ آب و هوا ============

async def _openweather_weather(city_name: str) -> dict[str, Any]:
    """آب‌وهوا از OpenWeatherMap (با کلید) — خروجی یکسان با Open-Meteo."""
    if not OPENWEATHER_API_KEY:
        raise MediaServiceError("unconfigured", "کلید OpenWeatherMap تنظیم نشده است.")
    session = await get_session()
    current = await _fetch_json(
        session,
        f"{OWM_URL}/weather?q={quote(city_name)}&appid={OPENWEATHER_API_KEY}&units=metric",
        timeout=20,
    )
    if not current or current.get("cod") != 200:
        raise MediaServiceError("city_not_found", f"شهری به نام «{city_name}» پیدا نشد.")
    # پیش‌بینی ۲۴ ساعت بعدی برای دما/بارش امروز
    daily = []
    today_max = today_min = rain_prob = None
    try:
        forecast = await _fetch_json(
            session,
            f"{OWM_URL}/forecast?q={quote(city_name)}&appid={OPENWEATHER_API_KEY}&units=metric&cnt=8",
            timeout=20,
        )
        temps = [item["main"]["temp"] for item in (forecast or {}).get("list", [])]
        pops = [item.get("pop", 0) for item in (forecast or {}).get("list", [])]
        if temps:
            today_max = max(temps)
            today_min = min(temps)
        if pops:
            rain_prob = int(max(pops) * 100)
        for item in (forecast or {}).get("list", [])[::4][:2]:
            daily.append({
                "date": str(item.get("dt_txt", ""))[:10],
                "max": item["main"].get("temp_max"),
                "min": item["main"].get("temp_min"),
            })
    except Exception:
        pass
    icon_code = str((current.get("weather") or [{}])[0].get("icon") or "")
    icon, label = OWM_ICONS.get(icon_code, ("🌡", str((current.get("weather") or [{}])[0].get("description") or "متغیر")))
    main = current.get("main") or {}
    wind = (current.get("wind") or {}).get("speed")
    return {
        "city": current.get("name") or city_name,
        "country": str((current.get("sys") or {}).get("country") or ""),
        "temp": main.get("temp"),
        "feels": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "wind": wind,
        "code": icon_code,
        "icon": icon,
        "label": label,
        "today_max": today_max,
        "today_min": today_min,
        "rain_prob": rain_prob,
        "daily": daily,
        "provider": "openweathermap",
    }


async def _openmeteo_weather(city: str, name: str) -> dict[str, Any]:
    """آب‌وهوای شهر با Open-Meteo (بدون کلید)."""
    session = await get_session()
    geo = await _fetch_json(session, f"{GEOCODE_URL}?name={quote(name)}&count=1&language=fa")
    results = (geo or {}).get("results") or []
    if not results:
        raise MediaServiceError("city_not_found", f"شهری به نام «{city}» پیدا نشد؛ املای انگلیسی را امتحان کن.")
    lat = results[0]["latitude"]
    lon = results[0]["longitude"]
    found_name = results[0].get("name") or name
    country = (results[0].get("country") or "")
    url = (
        f"{FORECAST_URL}?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=auto&forecast_days=3"
    )
    data = await _fetch_json(session, url)
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(current.get("weather_code") or 0)
    icon, label = WMO_CODES.get(code, ("🌡", "متغیر"))
    return {
        "city": found_name,
        "country": country,
        "temp": current.get("temperature_2m"),
        "feels": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind": current.get("wind_speed_10m"),
        "code": code,
        "icon": icon,
        "label": label,
        "today_max": (daily.get("temperature_2m_max") or [None])[0],
        "today_min": (daily.get("temperature_2m_min") or [None])[0],
        "rain_prob": (daily.get("precipitation_probability_max") or [None])[0],
        "daily": [
            {"date": d, "max": mx, "min": mn}
            for d, mx, mn in zip(
                (daily.get("time") or [])[:3],
                (daily.get("temperature_2m_max") or [])[:3],
                (daily.get("temperature_2m_min") or [])[:3],
                strict=False,
            )
        ],
        "provider": "openmeteo",
    }


async def weather(city: str) -> dict[str, Any]:
    """آب‌وهوا — زنجیره: OpenWeatherMap (اگه کلید باشه) ← Open-Meteo (بدون کلید)."""
    name = normalize_city(city)
    if not name:
        raise MediaServiceError("invalid_city", "نام شهر را بنویس؛ مثلاً /weather تهران")
    cache_key = f"wx:{name.lower()}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    last_error: Exception | None = None
    if OPENWEATHER_API_KEY:
        try:
            result = await _openweather_weather(name)
            await _cache_set(cache_key, result, ttl=600)
            return result
        except MediaServiceError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
    try:
        result = await _openmeteo_weather(city, name)
        await _cache_set(cache_key, result, ttl=600)
        return result
    except MediaServiceError:
        if last_error:
            raise last_error from None
        raise
    except Exception:
        if last_error:
            raise last_error from None
        raise


# ============ نرخ ارز ============

ER_API_URL = "https://open.er-api.com/v6/latest/{base}"


async def _er_rates(base: str) -> dict[str, float]:
    """نرخ‌های روزانه از open.er-api.com — بدون کلید، ۱۶۰+ ارز از جمله ریال."""
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, ER_API_URL.format(base=base), timeout=25)
    return (data or {}).get("rates") or {}


async def exchange_rate(from_code: str, to_code: str) -> dict[str, Any]:
    frm = _parse_currency(from_code)
    to = _parse_currency(to_code)
    if frm == to:
        raise MediaServiceError("same_currency", "دو ارز یکسان را وارد نکن؛ مثلاً /rate usd eur")
    cache_key = f"fx:{frm}:{to}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    rates = await _er_rates(frm)
    if not rates:
        raise MediaServiceError("unavailable", "نرخ ارز در دسترس نیست؛ دوباره تلاش کن.")
    if to not in rates:
        # جستجو با ارز پایه دیگر (بعضی ارزها فقط با USD در دسترس‌اند)
        if frm != "USD":
            usd_rates = await _er_rates("USD")
            if to in usd_rates and "USD" in rates:
                value = rates["USD"] * usd_rates[to]
                return {"from": frm, "to": to, "rate": value, "approx": True, "date": None}
        raise MediaServiceError("bad_currency", "کد ارز نامعتبر است؛ مثلاً /rate usd eur")
    result = {"from": frm, "to": to, "rate": rates.get(to), "date": None, "approx": False}
    await _cache_set(cache_key, result)
    return result


# ============ طلا ============

GOLD_API_URL = "https://api.gold-api.com/price/XAU"
GOLD_GRAM_PER_OZ = 31.1035  # هر اونس تروا چند گرم است


async def gold_price_toman() -> int:
    """قیمت هر گرم طلای ۱۸ عیار به تومان (قیمت جهانی XAU × نرخ دلار)."""
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, GOLD_API_URL, timeout=20)
    price_usd = float((data or {}).get("price") or 0)
    if price_usd <= 0:
        raise MediaServiceError("unavailable", "قیمت طلا در دسترس نیست؛ دوباره تلاش کن.")
    res = await exchange_rate("usd", "irr")
    rial = float(res.get("rate") or 0)
    if rial <= 0:
        raise MediaServiceError("unavailable", "نرخ دلار در دسترس نیست؛ دوباره تلاش کن.")
    per_gram_usd = price_usd / GOLD_GRAM_PER_OZ
    per_gram_toman = per_gram_usd * rial / 10
    return int(round(per_gram_toman * 0.75 / 1000) * 1000)  # عیار ۱۸ + گرد کردن


# ============ کریپتو ============

async def crypto_price(symbols: list[str]) -> list[dict[str, Any]]:
    ids = [_parse_crypto_symbol(s) for s in symbols]
    ids = list(dict.fromkeys(ids))[:6]
    if not ids:
        raise MediaServiceError("invalid_crypto", "نماد ارز دیجیتال را بنویس؛ مثلاً /crypto btc")
    query = ",".join(ids)
    url = f"{COINGECKO_URL}?vs_currency=usd&ids={query}&order=market_cap_desc&per_page=20&page=1&sparkline=false&price_change_percentage=24h"
    async with aiohttp.ClientSession() as session:
        rows = await _fetch_json(session, url, timeout=30)
    if not rows:
        raise MediaServiceError("crypto_not_found", "ارز دیجیتالی با این نماد پیدا نشد.")
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append({
            "name": row.get("name"),
            "symbol": str(row.get("symbol") or "").upper(),
            "price_usd": row.get("current_price"),
            "change_24h": row.get("price_change_percentage_24h"),
            "market_cap": row.get("market_cap"),
            "volume": row.get("total_volume"),
            "image": row.get("image"),
            "ath": row.get("ath"),
        })
    return items


# ============ ویکی‌پدیا ============

async def wiki_summary(query: str, lang: str = "fa") -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        raise MediaServiceError("invalid_query", "موضوع را بنویس؛ مثلاً /wiki نوروز")
    async with aiohttp.ClientSession() as session:
        search = await _fetch_json(
            session,
            f"{WIKIPEDIA_SEARCH_URL.format(lang=lang)}?action=query&list=search&srsearch={quote(q)}&srlimit=1&format=json",
        )
        hits = (search.get("query") or {}).get("search") or []
        if not hits:
            raise MediaServiceError("wiki_not_found", f"صفحه‌ای برای «{q}» پیدا نشد.")
        title = hits[0]["title"]
        summary = await _fetch_json(session, WIKIPEDIA_SUMMARY_URL.format(lang=lang, title=quote(title.replace(" ", "_"))))
    return {
        "title": summary.get("title") or title,
        "extract": summary.get("extract") or "",
        "thumbnail": (summary.get("thumbnail") or {}).get("source"),
        "url": summary.get("content_urls", {}).get("desktop", {}).get("page") if isinstance(summary.get("content_urls"), dict) else "",
    }


# ============ کتاب ============

async def book_search(query: str, limit: int = 4) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        raise MediaServiceError("invalid_query", "نام کتاب را بنویس؛ مثلاً /book شازده کوچولو")
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, f"{OPEN_LIBRARY_URL}?q={quote(q)}&limit={limit}&fields=title,author_name,first_publish_year,cover_i,key")
    docs = (data or {}).get("docs") or []
    items: list[dict[str, Any]] = []
    for doc in docs:
        cover_i = doc.get("cover_i")
        items.append({
            "title": doc.get("title") or "بدون عنوان",
            "authors": (doc.get("author_name") or [])[:3],
            "year": doc.get("first_publish_year"),
            "cover": f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else None,
            "url": f"https://openlibrary.org{doc.get('key')}" if doc.get("key") else "",
        })
    if not items:
        raise MediaServiceError(
            "book_not_found",
            "کتابی پیدا نشد؛ اگه فارسی بود، نام انگلیسی کتاب را هم امتحان کن. 📚",
        )
    return items


# ============ کشور ============

COUNTRY_WIKI_ALIASES = {
    "ایران": "ایران", "iran": "ایران", "persia": "ایران",
    "آمریکا": "ایالات متحده آمریکا", "امریکا": "ایالات متحده آمریکا", "usa": "ایالات متحده آمریکا", "america": "ایالات متحده آمریکا",
    "فرانسه": "فرانسه", "france": "فرانسه",
    "آلمان": "آلمان", "germany": "آلمان",
    "انگلیس": "بریتانیا", "انگلستان": "بریتانیا", "uk": "بریتانیا", "england": "بریتانیا",
    "ترکیه": "ترکیه", "turkey": "ترکیه",
    "امارات": "امارات متحده عربی", "dubai": "امارات متحده عربی", "uae": "امارات متحده عربی",
    "عربستان": "عربستان سعودی", "saudi": "عربستان سعودی",
    "چین": "چین", "china": "چین",
    "ژاپن": "ژاپن", "japan": "ژاپن",
    "روسیه": "روسیه", "russia": "روسیه",
    "هند": "هند", "india": "هند",
    "ایتالیا": "ایتالیا", "italy": "ایتالیا",
    "اسپانیا": "اسپانیا", "spain": "اسپانیا",
    "کانادا": "کانادا", "canada": "کانادا",
    "استرالیا": "استرالیا", "australia": "استرالیا",
    "برزیل": "برزیل", "brazil": "برزیل",
    "مصر": "مصر", "egypt": "مصر",
    "عراق": "عراق", "iraq": "عراق",
    "افغانستان": "افغانستان", "afghanistan": "افغانستان",
    "پاکستان": "پاکستان", "pakistan": "پاکستان",
    "قطر": "قطر", "qatar": "قطر",
    "کویت": "کویت", "kuwait": "کویت",
    "هلند": "هلند", "netherlands": "هلند", "holland": "هلند",
    "سوئد": "سوئد", "sweden": "سوئد",
    "نروژ": "نروژ", "norway": "نروژ",
    "دانمارک": "دانمارک", "denmark": "دانمارک",
    "سوئیس": "سوئیس", "switzerland": "سوئیس",
    "اتریش": "اتریش", "austria": "اتریش",
    "لهستان": "لهستان", "poland": "لهستان",
    "اوکراین": "اوکراین", "ukraine": "اوکراین",
    "ارمنستان": "ارمنستان", "armenia": "ارمنستان",
    "آذربایجان": "جمهوری آذربایجان", "azerbaijan": "جمهوری آذربایجان",
    "گرجستان": "گرجستان", "georgia": "گرجستان",
    "تاجیکستان": "تاجیکستان", "tajikistan": "تاجیکستان",
    "ازبکستان": "ازبکستان", "uzbekistan": "ازبکستان",
    "قزاقستان": "قزاقستان", "kazakhstan": "قزاقستان",
    "ترکمنستان": "ترکمنستان", "turkmenistan": "ترکمنستان",
    "قرقیزستان": "قرقیزستان", "kyrgyzstan": "قرقیزستان",
    "اردن": "اردن", "jordan": "اردن",
    "لبنان": "لبنان", "lebanon": "لبنان",
    "سوریه": "سوریه", "syria": "سوریه",
    "عمان": "عمان", "oman": "عمان",
    "بحرین": "بحرین", "bahrain": "بحرین",
    "مراکش": "مراکش", "morocco": "مراکش",
    "الجزایر": "الجزایر", "algeria": "الجزایر",
    "تونس": "تونس", "tunisia": "تونس",
    "اندونزی": "اندونزی", "indonesia": "اندونزی",
    "مالزی": "مالزی", "malaysia": "مالزی",
    "تایلند": "تایلند", "thailand": "تایلند",
    "کره جنوبی": "کره جنوبی", "south korea": "کره جنوبی",
    "مکزیک": "مکزیک", "mexico": "مکزیک",
    "آرژانتین": "آرژانتین", "argentina": "آرژانتین",
    "چک": "جمهوری چک", "czech": "جمهوری چک",
    "یونان": "یونان", "greece": "یونان",
    "پرتغال": "پرتغال", "portugal": "پرتغال",
    "بلژیک": "بلژیک", "belgium": "بلژیک",
    "فنلاند": "فنلاند", "finland": "فنلاند",
    "آفریقای جنوبی": "آفریقای جنوبی", "south africa": "آفریقای جنوبی",
}

COUNTRY_FLAGS: dict[str, str] = {
    "ایران": "🇮🇷", "ایالات متحده آمریکا": "🇺🇸", "فرانسه": "🇫🇷", "آلمان": "🇩🇪",
    "بریتانیا": "🇬🇧", "ترکیه": "🇹🇷", "امارات متحده عربی": "🇦🇪", "عربستان سعودی": "🇸🇦",
    "چین": "🇨🇳", "ژاپن": "🇯🇵", "روسیه": "🇷🇺", "هند": "🇮🇳", "ایتالیا": "🇮🇹",
    "اسپانیا": "🇪🇸", "کانادا": "🇨🇦", "استرالیا": "🇦🇺", "برزیل": "🇧🇷", "مصر": "🇪🇬",
    "عراق": "🇮🇶", "افغانستان": "🇦🇫", "پاکستان": "🇵🇰", "قطر": "🇶🇦", "کویت": "🇰🇼",
    "هلند": "🇳🇱", "سوئد": "🇸🇪", "نروژ": "🇳🇴", "دانمارک": "🇩🇰", "سوئیس": "🇨🇭",
    "اتریش": "🇦🇹", "لهستان": "🇵🇱", "اوکراین": "🇺🇦", "ارمنستان": "🇦🇲",
    "جمهوری آذربایجان": "🇦🇿", "گرجستان": "🇬🇪", "تاجیکستان": "🇹🇯", "ازبکستان": "🇺🇿",
    "قزاقستان": "🇰🇿", "ترکمنستان": "🇹🇲", "قرقیزستان": "🇰🇬", "اردن": "🇯🇴",
    "لبنان": "🇱🇧", "سوریه": "🇸🇾", "عمان": "🇴🇲", "بحرین": "🇧🇭", "مراکش": "🇲🇦",
    "الجزایر": "🇩🇿", "تونس": "🇹🇳", "اندونزی": "🇮🇩", "مالزی": "🇲🇾", "تایلند": "🇹🇭",
    "کره جنوبی": "🇰🇷", "مکزیک": "🇲🇽", "آرژانتین": "🇦🇷", "جمهوری چک": "🇨🇿",
    "یونان": "🇬🇷", "پرتغال": "🇵🇹", "بلژیک": "🇧🇪", "فنلاند": "🇫🇮", "آفریقای جنوبی": "🇿🇦",
    "سنگاپور": "🇸🇬", "نیوزیلند": "🇳🇿", "کوبا": "🇨🇺", "پاناما": "🇵🇦",
}


async def country_info(name: str) -> dict[str, Any]:
    q = str(name or "").strip()
    if not q:
        raise MediaServiceError("invalid_query", "نام کشور را بنویس؛ مثلاً /country ایران")
    wiki_title = COUNTRY_WIKI_ALIASES.get(q.strip().lower(), q.strip())
    try:
        summary = await wiki_summary(wiki_title, "fa")
    except MediaServiceError:
        raise MediaServiceError("country_not_found", f"کشوری به نام «{name}» پیدا نشد.") from None
    return {
        "name": summary["title"],
        "flag": COUNTRY_FLAGS.get(summary["title"], "🌍"),
        "extract": summary["extract"],
        "thumbnail": summary.get("thumbnail"),
        "url": summary.get("url") or "",
    }


# ============ امنیت رمز (بدون ارسال رمز کامل) ============

def pwned_password_count(password: str) -> int:
    """تعداد دفعات لو‌رفتن رمز با Pwned Passwords range API — فقط ۵ کاراکتر اول هش ارسال می‌شود."""
    sha1 = hashlib.sha1(str(password).encode("utf-8", errors="ignore")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    import urllib.request

    req = urllib.request.Request(
        "PWNED_URL_PLACEHOLDER".replace("PWNED_URL_PLACEHOLDER", PWNED_URL).format(prefix=prefix),
        headers={"User-Agent": "AjorparehBot/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return -1  # خطا در بررسی
    for line in body.splitlines():
        if ":" in line:
            suf, count = line.split(":", 1)
            if suf.strip().upper() == suffix:
                return int(count.strip())
    return 0


# ============ کوئیز ============

async def opentdb_quiz(amount: int = 1) -> list[dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, f"{OPENTDB_URL}?amount={amount}&encode=url3986", timeout=20)
    results = (data or {}).get("results") or []
    from urllib.parse import unquote

    questions: list[dict[str, Any]] = []
    for r in results:
        options = [unquote(x) for x in (r.get("incorrect_answers") or [])]
        options.append(unquote(r.get("correct_answer") or ""))
        questions.append({
            "category": unquote(r.get("category") or ""),
            "difficulty": unquote(r.get("difficulty") or ""),
            "question": unquote(r.get("question") or ""),
            "options": options,
            "correct": unquote(r.get("correct_answer") or ""),
        })
    return questions


# ============ زمان جهانی ============

TIMEZONE_ALIASES = {
    "تهران": "Asia/Tehran", "tehran": "Asia/Tehran", "iran": "Asia/Tehran",
    "لندن": "Europe/London", "london": "Europe/London",
    "نیویورک": "America/New_York", "new york": "America/New_York", "nyc": "America/New_York",
    "دبی": "Asia/Dubai", "dubai": "Asia/Dubai",
    "توکیو": "Asia/Tokyo", "tokyo": "Asia/Tokyo",
    "استانبول": "Europe/Istanbul", "istanbul": "Europe/Istanbul",
    "پاریس": "Europe/Paris", "paris": "Europe/Paris",
    "مسکو": "Europe/Moscow", "moscow": "Europe/Moscow",
    "لوس‌آنجلس": "America/Los_Angeles", "los angeles": "America/Los_Angeles",
    "سیدنی": "Australia/Sydney", "sydney": "Australia/Sydney",
    "برلین": "Europe/Berlin", "berlin": "Europe/Berlin",
}


async def world_time(city_or_zone: str) -> dict[str, Any]:
    zone = TIMEZONE_ALIASES.get(str(city_or_zone or "").strip().lower(), str(city_or_zone or "").strip())
    if "/" not in zone:
        raise MediaServiceError("invalid_zone", "نام شهر یا منطقه زمانی را بنویس؛ مثلاً /time تهران")
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, f"https://timeapi.io/api/Time/current/zone?timeZone={quote(zone)}", timeout=20)
    hour = int(data.get("hour") or 0)
    minute = int(data.get("minute") or 0)
    weekday_raw = str(data.get("dayOfWeek") or "")
    weekday_map = {
        "monday": "دوشنبه", "tuesday": "سه‌شنبه", "wednesday": "چهارشنبه",
        "thursday": "پنجشنبه", "friday": "جمعه", "saturday": "شنبه", "sunday": "یکشنبه",
    }
    day_name = weekday_map.get(weekday_raw.lower(), "—")
    return {
        "zone": zone,
        "time": f"{hour:02d}:{minute:02d}",
        "date": str(data.get("date") or ""),
        "day_name": day_name,
        "datetime": str(data.get("dateTime") or ""),
    }
