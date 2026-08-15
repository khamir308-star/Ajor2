"""Super music center for Ajorpareh — multi-provider search & download.

Provider chain (fallback until one answers):
  search:    Audius → Deezer → iTunes → Piped(YouTube)
  trending:  Audius → Deezer chart → iTunes top
  download:  Audius (full MP3) with quality re-encode options;
             Deezer/iTunes give official 30s previews (listen);
             YouTube/Piped give watch link fallback.

Public content only: no cookies, no credentials, no DRM bypass.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

from media_service import DownloadedMedia, MediaServiceError, safe_filename
from iranian_music_catalog import IRANIAN_ARTIST_ALIASES, IRANIAN_MUSIC_CATALOG, IRANIAN_SEARCH_MARKERS

try:
    import yt_dlp
    from yt_dlp.networking.impersonate import ImpersonateTarget
except ImportError:  # pragma: no cover
    yt_dlp = None
    ImpersonateTarget = None

AUDIUS_DISCOVERY_URL = "https://api.audius.co"
DEEZER_API = "https://api.deezer.com"
ITUNES_API = "https://itunes.apple.com"
AUDD_API_URL = "https://api.audd.io/"
AUDD_API_KEY = os.getenv("AUDD_API_KEY", "").strip()
MUSIC_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
# سرویس‌های Cobalt برای دانلود یوتیوب (زمانی که yt-dlp از IP سرور بلاک باشد).
# اولی بدون Turnstile است؛ بقیه گاهی باز می‌شوند.
COBALT_INSTANCES = [
    "https://rue-cobalt.xenon.zone",
    "https://api.cobalt.liubquanti.click",
    "https://cobaltapi.cjs.nz",
]
PIPED_INSTANCES = [
    "https://api.piped.private.coffee",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.ducks.party",
    "https://pipedapi.reallyaweso.me",
    "https://api.piped.yt",
]
_audius_host_cache: str | None = None
_piped_ok_cache: str | None = None

PROVIDER_LABELS = {
    "iranian_catalog": "🇮🇷 کاتالوگ ایرانی",
    "audius": "🎧 آدیوس",
    "deezer": "🎵 دیزر",
    "itunes": "🍎 اپل موزیک",
    "youtube": "▶️ یوتیوب",
    "piped": "▶️ یوتیوب",
}


def mimetypes_guess(name: str) -> str | None:
    try:
        return mimetypes.guess_type(name)[0]
    except Exception:
        return None


def _headers() -> dict[str, str]:
    return {"User-Agent": MUSIC_UA, "Accept": "application/json, */*"}


async def _http_json(session: aiohttp.ClientSession, url: str, timeout: int = 25) -> Any:
    try:
        async with session.get(url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                raise MediaServiceError("http_error", f"سرویس موسیقی با خطای HTTP {resp.status} پاسخ داد.")
            return await resp.json(content_type=None)
    except asyncio.TimeoutError as exc:
        raise MediaServiceError("timeout", "سرویس موسیقی پاسخ نداد؛ کمی بعد دوباره تلاش کن.") from exc
    except aiohttp.ClientError as exc:
        raise MediaServiceError("network", "اتصال به سرویس موسیقی برقرار نشد.") from exc


async def _http_bytes(session: aiohttp.ClientSession, url: str, timeout: int = 120) -> bytes:
    try:
        async with session.get(url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                raise MediaServiceError("http_error", f"دریافت فایل با خطای HTTP {resp.status} پاسخ داد.")
            return await resp.read()
    except asyncio.TimeoutError as exc:
        raise MediaServiceError("timeout", "دریافت فایل طول کشید؛ دوباره تلاش کن.") from exc
    except aiohttp.ClientError as exc:
        raise MediaServiceError("network", "اتصال به سرور فایل برقرار نشد.") from exc


# ============ Audius ============

async def audius_host(session: aiohttp.ClientSession) -> str:
    global _audius_host_cache
    if _audius_host_cache:
        return _audius_host_cache
    try:
        raw = await _http_json(session, AUDIUS_DISCOVERY_URL, timeout=12)
        data = raw.get("data") or []
        host = next((h for h in data if str(h).startswith("https://")), None)
        if not host:
            raise MediaServiceError("unavailable", "سرویس آدیوس در دسترس نیست.")
        _audius_host_cache = host
        return host
    except MediaServiceError:
        raise
    except Exception as exc:  # pragma: no cover
        raise MediaServiceError("unavailable", "سرویس آدیوس در دسترس نیست.") from exc


def _audius_item(item: dict) -> dict[str, Any]:
    user = item.get("user") or {}
    return {
        "source": "audius",
        "provider": PROVIDER_LABELS["audius"],
        "id": str(item.get("id", "")),
        "title": str(item.get("title") or "بدون عنوان")[:180],
        "artist": str(user.get("name") or "ناشناس")[:120],
        "album": "",
        "duration": int(item.get("duration") or 0),
        "artwork": (item.get("artwork") or {}).get("150x150") if isinstance(item.get("artwork"), dict) else None,
        "preview_url": None,
        "downloadable": True,
        "watch_url": None,
        "permalink": str(item.get("permalink") or "")[:300],
    }


async def audius_search(session: aiohttp.ClientSession, query: str, limit: int = 6) -> list[dict[str, Any]]:
    host = await audius_host(session)
    url = f"{host}/v1/tracks/search?query={quote(str(query)[:120])}&limit={limit}&app_name=Ajorpareh"
    data = await _http_json(session, url)
    return [_audius_item(t) for t in (data.get("data") or [])]


async def audius_trending(session: aiohttp.ClientSession, time: str = "week", limit: int = 8) -> list[dict[str, Any]]:
    host = await audius_host(session)
    url = f"{host}/v1/tracks/trending?time={time}&limit={limit}&app_name=Ajorpareh"
    data = await _http_json(session, url)
    return [_audius_item(t) for t in (data.get("data") or [])]


# ============ Deezer ============

def _deezer_item(item: dict) -> dict[str, Any]:
    artist = (item.get("artist") or {})
    return {
        "source": "deezer",
        "provider": PROVIDER_LABELS["deezer"],
        "id": str(item.get("id", "")),
        "title": str(item.get("title") or "بدون عنوان")[:180],
        "artist": str(artist.get("name") or "ناشناس")[:120],
        "album": str((item.get("album") or {}).get("title") or "")[:120],
        "duration": int(item.get("duration") or 0),
        "artwork": item.get("album", {}).get("cover_small") if isinstance(item.get("album"), dict) else None,
        "preview_url": str(item.get("preview") or "")[:300] or None,
        "downloadable": False,
        "watch_url": None,
        "permalink": str(item.get("link") or "")[:300],
    }


async def deezer_search(session: aiohttp.ClientSession, query: str, limit: int = 6) -> list[dict[str, Any]]:
    data = await _http_json(session, f"{DEEZER_API}/search?q={quote(str(query)[:120])}&limit={limit}")
    return [_deezer_item(t) for t in (data.get("data") or [])]


async def deezer_trending(session: aiohttp.ClientSession, limit: int = 8) -> list[dict[str, Any]]:
    data = await _http_json(session, f"{DEEZER_API}/chart/0/tracks?limit={limit}")
    return [_deezer_item(t) for t in (data.get("data") or [])]


# ============ iTunes ============

def _itunes_item(item: dict) -> dict[str, Any]:
    return {
        "source": "itunes",
        "provider": PROVIDER_LABELS["itunes"],
        "id": str(item.get("trackId", "")),
        "title": str(item.get("trackName") or "بدون عنوان")[:180],
        "artist": str(item.get("artistName") or "ناشناس")[:120],
        "album": str(item.get("collectionName") or "")[:120],
        "duration": int(item.get("trackTimeMillis", 0) or 0) // 1000,
        "artwork": item.get("artworkUrl60") or item.get("artworkUrl100"),
        "preview_url": str(item.get("previewUrl") or "")[:300] or None,
        "downloadable": False,
        "watch_url": None,
        "permalink": str(item.get("trackViewUrl") or "")[:300],
    }


async def itunes_search(session: aiohttp.ClientSession, query: str, limit: int = 6) -> list[dict[str, Any]]:
    data = await _http_json(session, f"{ITUNES_API}/search?term={quote(str(query)[:120])}&media=music&limit={limit}")
    return [_itunes_item(t) for t in (data.get("results") or [])]


async def itunes_trending(session: aiohttp.ClientSession, limit: int = 8) -> list[dict[str, Any]]:
    # آهنگ‌های پرفروش اپل موزیک (جهانی)
    data = await _http_json(session, f"{ITUNES_API}/us/rss/topsongs/limit={limit}/json")
    feed = data.get("feed") or {}
    entries = feed.get("entry") or []
    items: list[dict[str, Any]] = []
    for entry in entries:
        name = (entry.get("im:name") or {}).get("label", "")
        artist = (entry.get("im:artist") or {}).get("label", "ناشناس")
        image = None
        images = entry.get("im:image") or []
        if images:
            image = images[0].get("label")
        items.append({
            "source": "itunes",
            "provider": PROVIDER_LABELS["itunes"],
            "id": (entry.get("id") or {}).get("label", ""),
            "title": str(name)[:180],
            "artist": str(artist)[:120],
            "album": "",
            "duration": 0,
            "artwork": image,
            "preview_url": None,
            "downloadable": False,
            "watch_url": None,
            "permalink": (entry.get("link") or [{}])[0].get("href", "")[:300] if isinstance(entry.get("link"), list) else "",
        })
    return items[:limit]


# ============ Piped (YouTube search proxy) ============

def _piped_search_sync(query: str, limit: int) -> list[dict[str, Any]]:
    """جستجوی یوتیوب از طریق instance های Piped (به‌صورت هم‌زمان در thread جدا)."""
    global _piped_ok_cache
    import urllib.request

    candidates = [c for c in PIPED_INSTANCES if c != _piped_ok_cache] if _piped_ok_cache else PIPED_INSTANCES
    candidates = ([_piped_ok_cache] + candidates) if _piped_ok_cache else candidates
    for inst in candidates:
        try:
            req = urllib.request.Request(
                f"{inst}/search?q={quote(str(query)[:120])}&filter=music_songs",
                headers={"User-Agent": MUSIC_UA},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    continue
                raw = resp.read()
            data = json.loads(raw)
            items = []
            for entry in (data.get("items") or [])[:limit]:
                video_id = str(entry.get("url") or "").split("v=")[-1]
                if not video_id or video_id == entry.get("url"):
                    continue
                items.append({
                    "source": "youtube",
                    "provider": PROVIDER_LABELS["youtube"],
                    "id": video_id,
                    "title": str(entry.get("title") or "بدون عنوان")[:180],
                    "artist": str(entry.get("uploaderName") or "ناشناس")[:120],
                    "album": "",
                    "duration": int(entry.get("duration") or 0),
                    "artwork": entry.get("thumbnail") or None,
                    "preview_url": None,
                    "downloadable": False,
                    "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                    "permalink": f"https://www.youtube.com/watch?v={video_id}",
                })
            if items:
                _piped_ok_cache = inst
                return items
        except Exception:
            continue
    return []


async def piped_search(session: aiohttp.ClientSession, query: str, limit: int = 6) -> list[dict[str, Any]]:
    try:
        return await asyncio.to_thread(_piped_search_sync, query, limit)
    except Exception:
        return []


# ============ Merge & search ============

def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("title") or "").strip().lower()[:50], str(item.get("artist") or "").strip().lower()[:30])
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def is_iranian_music_query(query: str) -> bool:
    value = str(query or "").strip().lower()
    if any("\u0600" <= char <= "\u06ff" for char in value):
        return True
    if any(marker in value for marker in IRANIAN_SEARCH_MARKERS):
        return True
    return any(alias in value for alias in IRANIAN_ARTIST_ALIASES)


def _iranian_catalog_search(query: str, limit: int = 12) -> list[dict[str, Any]]:
    value = str(query or "").strip().lower()
    tokens = [token for token in value.split() if len(token) > 1]
    remix_query = any(word in value for word in ("ریمیکس", "میکس", "remix", "mix", "تلفیقی"))
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for position, item in enumerate(IRANIAN_MUSIC_CATALOG):
        haystack = " ".join([
            str(item.get("artist") or ""),
            str(item.get("title") or ""),
            str(item.get("genre") or ""),
            str(item.get("tags") or ""),
        ]).lower()
        score = sum(4 if token in haystack else 0 for token in tokens)
        if remix_query and "remix" in str(item.get("tags") or ""):
            score += 12
        if not tokens or value in {"ایرانی", "ایران", "فارسی", "ترند ایرانی", "موزیک ایرانی"}:
            score += max(0, 10 - position // 20)
        if score:
            enriched = dict(item)
            enriched["region"] = "iranian"
            scored.append((score, -position, enriched))
    scored.sort(reverse=True, key=lambda entry: (entry[0], entry[1]))
    return [item for _score, _position, item in scored[:limit]]


async def search_iranian_songs(session: aiohttp.ClientSession, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """ایندکس ایرانی + دیتابیس‌های عمومی زنده برای پاپ، رپ، سنتی و ریمیکس."""
    query = str(query or "").strip()
    catalog = _iranian_catalog_search(query, max(limit, 12))
    remote_query = query
    if "ریمیکس" in query or "میکس" in query or "remix" in query.lower():
        remote_query = f"{query} ایرانی رپ پاپ سنتی remix"
    elif not any("\u0600" <= char <= "\u06ff" for char in query):
        remote_query = f"{query} Iranian Persian music"
    remote_results = await asyncio.gather(
        deezer_search(session, remote_query, 8),
        itunes_search(session, remote_query, 8),
        piped_search(session, remote_query, 10),
        return_exceptions=True,
    )
    results = list(catalog)
    for result in remote_results:
        if isinstance(result, list):
            for item in result:
                enriched = dict(item)
                enriched["region"] = "iranian"
                results.append(enriched)
    results = _dedupe(results)
    if not results:
        raise MediaServiceError("no_results", "آهنگ ایرانی پیدا نشد؛ اسم خواننده یا عبارت ریمیکس را دقیق‌تر امتحان کن.")
    return results[:limit]


async def trending_iranian_songs(session: aiohttp.ClientSession, limit: int = 10) -> list[dict[str, Any]]:
    """ترند ایرانی و ریمیکس‌های پاپ/رپ/سنتی از ایندکس محلی و منابع عمومی."""
    catalog = _iranian_catalog_search("ترند ایرانی", max(limit, 12))
    remote_results = await asyncio.gather(
        piped_search(session, "موزیک ایرانی جدید ترند", 8),
        piped_search(session, "ریمیکس ایرانی رپ پاپ سنتی جدید", 8),
        deezer_search(session, "Iranian Persian music", 6),
        return_exceptions=True,
    )
    results = list(catalog)
    for result in remote_results:
        if isinstance(result, list):
            for item in result:
                enriched = dict(item)
                enriched["region"] = "iranian"
                results.append(enriched)
    results = _dedupe(results)
    if not results:
        raise MediaServiceError("no_results", "ترند ایرانی در حال حاضر در دسترس نیست؛ دوباره تلاش کن.")
    return results[:limit]


async def search_songs(session: aiohttp.ClientSession, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """جستجوی یکپارچه با زنجیرهٔ سرویس‌ها: آدیوس → دیزر → اپل → یوتیوب."""
    query = str(query or "").strip()
    if not query:
        raise MediaServiceError("invalid_query", "نام آهنگ یا خواننده را بنویس.")
    if is_iranian_music_query(query):
        return await search_iranian_songs(session, query, limit)
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    # ۱) آدیوس — قابل دانلود
    try:
        results.extend(await audius_search(session, query, 6))
    except MediaServiceError as exc:
        errors.append(f"audius:{exc.reason}")
    except Exception as exc:  # pragma: no cover
        errors.append(f"audius:{type(exc).__name__}")
    # ۲) دیزر — پیش‌نمایش رسمی
    if len(results) < limit:
        try:
            results.extend(await deezer_search(session, query, 6))
        except Exception as exc:
            errors.append(f"deezer:{type(exc).__name__}")
    # ۳) اپل موزیک — پیش‌نمایش رسمی
    if len(results) < limit:
        try:
            results.extend(await itunes_search(session, query, 6))
        except Exception as exc:
            errors.append(f"itunes:{type(exc).__name__}")
    # ۴) یوتیوب (Piped) — لینک تماشا
    if len(results) < limit:
        try:
            results.extend(await piped_search(session, query, 6))
        except Exception as exc:
            errors.append(f"youtube:{type(exc).__name__}")
    results = _dedupe(results)[:limit]
    if not results:
        if errors:
            raise MediaServiceError("no_results", "آهنگی با این نام پیدا نشد؛ نام یا املای دیگری را امتحان کن.")
        raise MediaServiceError("no_results", "آهنگی با این نام پیدا نشد؛ نام یا املای دیگری را امتحان کن.")
    return results


async def trending_songs(session: aiohttp.ClientSession, limit: int = 10) -> list[dict[str, Any]]:
    """ترندها: آدیوس → دیزر چارت → اپل تاپ."""
    results: list[dict[str, Any]] = []
    try:
        results.extend(await audius_trending(session, "week", 6))
    except Exception:
        pass
    if len(results) < limit:
        try:
            results.extend(await deezer_trending(session, 6))
        except Exception:
            pass
    if len(results) < limit:
        try:
            results.extend(await itunes_trending(session, 6))
        except Exception:
            pass
    results = _dedupe(results)[:limit]
    if not results:
        raise MediaServiceError("no_results", "دریافت آهنگ‌های ترند ناموفق بود؛ کمی بعد دوباره تلاش کن.")
    return results


# ============ Download (Audius full + quality) ============

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "original": {"label": "🎧 کیفیت اصلی", "bitrate": None},
    "high": {"label": "🔉 معمولی (۱۲۸k)", "bitrate": 128},
    "low": {"label": "🔈 کم‌حجم (۶۴k)", "bitrate": 64},
}


def _make_audio_file(raw: bytes, folder: Path, stem: str, bitrate: int | None, title: str) -> DownloadedMedia:
    """فایل صوتی را می‌سازد؛ اگر bitrate مشخص باشد با ffmpeg دوباره کدگذاری می‌شود."""
    raw_path = folder / f"{stem}.src"
    raw_path.write_bytes(raw)
    if bitrate and shutil.which("ffmpeg"):
        mp3_path = folder / f"{stem}.mp3"
        try:
            process = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_path),
                 "-vn", "-c:a", "libmp3lame", "-b:a", f"{bitrate}k", str(mp3_path)],
                capture_output=True, timeout=600,
            )
            if process.returncode == 0 and mp3_path.stat().st_size > 0:
                raw_path.unlink(missing_ok=True)
                return DownloadedMedia(
                    path=str(mp3_path), filename=mp3_path.name, mime_type="audio/mpeg",
                    size=mp3_path.stat().st_size, title=title, kind="audio",
                )
        except Exception:
            pass
    # بدون تبدیل، همان بایت‌ها
    probe = raw[:12].lower()
    ext = ".mp3" if (b"id3" in probe or b"\xff\xfb" in probe or b"\xff\xf3" in probe) else ".m4a"
    final = folder / f"{stem}{ext}"
    raw_path.replace(final)
    return DownloadedMedia(
        path=str(final), filename=final.name,
        mime_type="audio/mpeg" if ext == ".mp3" else "audio/mp4",
        size=final.stat().st_size, title=title, kind="audio",
    )


async def download_audius_track(
    session: aiohttp.ClientSession,
    track: dict[str, Any],
    output_dir: str,
    max_bytes: int = 300 * 1024 * 1024,
    quality: str = "original",
) -> DownloadedMedia:
    track_id = str(track.get("id") or "")
    if not track_id:
        raise MediaServiceError("invalid_track", "شناسهٔ آهنگ نامعتبر است.")
    preset = QUALITY_PRESETS.get(quality or "original", QUALITY_PRESETS["original"])
    host = await audius_host(session)
    url = f"{host}/v1/tracks/{track_id}/stream?app_name=Ajorpareh"
    raw = await _http_bytes(session, url, timeout=180)
    if not raw or len(raw) < 2048:
        raise MediaServiceError("empty", "فایل صوتی خالی یا در دسترس نیست.")
    if len(raw) > max_bytes:
        raise MediaServiceError("too_large", "حجم فایل صوتی بیش از حد مجاز است.")
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    base = safe_filename(f"{track.get('artist') or 'artist'} - {track.get('title') or 'track'}", "ajorpareh-song")
    stem = Path(base).stem[:70] or "ajorpareh-song"
    title = f"{track.get('title') or 'آهنگ'} - {track.get('artist') or ''}"
    return _make_audio_file(raw, folder, stem, preset["bitrate"], title)


async def download_preview(session: aiohttp.ClientSession, preview_url: str, output_dir: str, title: str) -> DownloadedMedia:
    """دانلود پیش‌نمایش رسمی ۳۰ ثانیه‌ای (دیزر/اپل)."""
    raw = await _http_bytes(session, str(preview_url), timeout=60)
    if not raw or len(raw) < 2048:
        raise MediaServiceError("empty", "پیش‌نمایش در دسترس نیست.")
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    base = safe_filename(title or "ajorpareh-preview", "ajorpareh-preview")
    stem = Path(base).stem[:70] or "ajorpareh-preview"
    return _make_audio_file(raw, folder, stem, None, title)


# ============ YouTube via Cobalt (public download API) ============

async def _cobalt_request(session: aiohttp.ClientSession, inst: str, url: str, mode: str, quality: str | None = None) -> dict[str, Any]:
    # در نسخه‌های جدید Cobalt مقدار "video" معتبر نیست؛ "auto" ویدیو/صوت را برمی‌گرداند
    # و videoQuality کیفیت را کنترل می‌کند. برای "audio" هم "auto" + audioFormat جواب می‌دهد.
    api_mode = "auto" if mode in ("video", "audio") else mode
    payload: dict[str, Any] = {"url": str(url).strip()[:1000], "downloadMode": api_mode}
    if mode == "audio":
        payload["audioFormat"] = "mp3"
    if quality:
        payload["videoQuality"] = quality
    headers = {
        "User-Agent": "AjorparehBot/1.0 (+https://t.me/Ajorparehbot)",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": inst,
    }
    async with session.post(inst.rstrip("/") + "/", json=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=45)) as resp:
        if resp.status == 429:
            raise MediaServiceError("rate_limited", "سرویس دانلود یوتیوب موقتاً محدود شده؛ دوباره تلاش کن.")
        if resp.status != 200:
            raise MediaServiceError("http_error", f"سرویس دانلود یوتیوب با خطای HTTP {resp.status} پاسخ داد.")
        return await resp.json(content_type=None)


async def _cobalt_download(session: aiohttp.ClientSession, url: str, output_dir: str,
                           mode: str, max_bytes: int, quality: str | None = None) -> DownloadedMedia:
    """دانلود از یوتیوب از طریق زنجیرهٔ instance های Cobalt؛ فقط محتوای عمومی."""
    last_error: Exception | None = None
    for inst in COBALT_INSTANCES:
        try:
            data = await _cobalt_request(session, inst, url, mode, quality)
        except (asyncio.TimeoutError, aiohttp.ClientError, MediaServiceError) as exc:
            last_error = exc
            continue
        status = data.get("status") if isinstance(data, dict) else None
        if status == "error":
            error = (data.get("error") or {})
            code = str(error.get("code") or "") if isinstance(error, dict) else ""
            if "youtube.login" in code:
                raise MediaServiceError("platform_blocked", "یوتیوب دانلود را برای این سرویس موقتاً محدود کرده.")
            last_error = MediaServiceError("download_failed", "دانلود یوتیوب ناموفق بود.")
            continue
        if status not in {"tunnel", "redirect", "stream"}:
            last_error = MediaServiceError("download_failed", "پاسخ نامعتبر از سرویس دانلود.")
            continue
        download_url = str(data.get("url") or "").strip()
        filename = str(data.get("filename") or "")[:200]
        if not download_url.startswith("http"):
            last_error = MediaServiceError("download_failed", "لینک دانلود نامعتبر است.")
            continue
        try:
            async with session.get(download_url, headers={"User-Agent": MUSIC_UA},
                                   timeout=aiohttp.ClientTimeout(total=300)) as resp:
                if resp.status != 200:
                    last_error = MediaServiceError("http_error", f"دریافت فایل با خطای HTTP {resp.status} پاسخ داد.")
                    continue
                folder = Path(output_dir)
                folder.mkdir(parents=True, exist_ok=True)
                safe = safe_filename(filename or "ajorpareh-youtube", "ajorpareh-youtube.mp3")
                target = folder / safe
                received = 0
                with target.open("wb") as out:
                    async for chunk in resp.content.iter_chunked(512 * 1024):
                        received += len(chunk)
                        if received > max_bytes:
                            raise MediaServiceError("too_large", "حجم فایل بیشتر از حد مجاز است.")
                        out.write(chunk)
                if received < 2048:
                    target.unlink(missing_ok=True)
                    last_error = MediaServiceError("empty", "فایل صوتی خالی دریافت شد.")
                    continue
                mime = mimetypes_guess(str(target.name)) or ("video/mp4" if mode == "video" else "audio/mpeg")
                return DownloadedMedia(
                    path=str(target), filename=target.name, mime_type=mime,
                    size=received, title=filename[:200],
                    kind="video" if mode == "video" else "audio",
                )
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            last_error = exc
            continue
    if isinstance(last_error, MediaServiceError):
        raise last_error
    raise MediaServiceError("download_failed", "هیچ سرویس دانلود یوتیوب در دسترس نبود؛ کمی بعد دوباره تلاش کن.")


async def download_youtube_audio_cobalt(session: aiohttp.ClientSession, url: str, output_dir: str,
                                        max_bytes: int = 200 * 1024 * 1024) -> DownloadedMedia:
    return await _cobalt_download(session, url, output_dir, "audio", max_bytes)


async def list_youtube_formats(url: str) -> list[dict]:
    """لیست کیفیت‌های قابل دانلود یوتیوب با حجم تقریبی (فقط metadata — سریع).

    با yt-dlp فرمت‌های ویدئویی را استخراج می‌کند (بدون دانلود) و برمی‌گرداند:
    [{height, ext, filesize_mb, format_note}]. اگر yt-dlp جواب ندهد [] برمی‌گرداند.
    """
    try:
        import yt_dlp
    except ImportError:
        return []
    try:
        with yt_dlp.YoutubeDL({
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 15,
            "noplaylist": True,
        }) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return []
    formats: list[dict] = []
    seen: set[tuple] = set()
    entries = info.get("entries") or [info]
    for entry in entries:
        if not entry:
            continue
        for f in entry.get("formats") or []:
            height = int(f.get("height") or 0)
            ext = str(f.get("ext") or "mp4")
            if height < 144 or "video" not in str(f.get("vcodec") or ""):
                continue
            filesize = int(f.get("filesize") or f.get("filesize_approx") or 0)
            if filesize <= 0:
                # تخمین: ویدئو 1 دقیقه‌ای 720p تقریباً 10MB
                duration = float(entry.get("duration") or 0)
                filesize = int(duration * height * 0.014 * 1024 * 1024)
            key = (height, ext)
            if key in seen:
                continue
            seen.add(key)
            formats.append({
                "height": height,
                "ext": ext,
                "filesize_mb": round(filesize / 1024 / 1024, 1),
                "format_note": str(f.get("format_note") or f"{height}p"),
            })
    # مرتب‌سازی: بالاترین کیفیت اول
    formats.sort(key=lambda x: -x["height"])
    return formats[:8]


async def download_youtube_video_cobalt(session: aiohttp.ClientSession, url: str, output_dir: str,
                                        max_bytes: int = 300 * 1024 * 1024, quality: str = "360") -> DownloadedMedia:
    return await _cobalt_download(session, url, output_dir, "video", max_bytes, quality)


# ============ Audio recognition (audd.io) ============

async def recognize_audio(session: aiohttp.ClientSession, file_path: str, api_key: str | None = None) -> dict[str, Any] | None:
    key = (api_key or AUDD_API_KEY or "").strip()
    if not key:
        return None
    path = Path(file_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise MediaServiceError("empty_audio", "فایل صوتی برای تشخیص معتبر نیست.")
    if path.stat().st_size > 25 * 1024 * 1024:
        raise MediaServiceError("too_large", "تکهٔ صدا برای تشخیص نباید بیشتر از ۲۵ مگابایت باشد.")
    data = aiohttp.FormData()
    data.add_field("api_token", key)
    data.add_field("return", "timecode,lyrics,spotify,apple_music,deezer")
    data.add_field("file", open(path, "rb"), filename=path.name, content_type="application/octet-stream")
    try:
        async with session.post(AUDD_API_URL, data=data, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                raise MediaServiceError("http_error", f"سرویس تشخیص با خطای HTTP {resp.status} پاسخ داد.")
            payload = await resp.json(content_type=None)
    except asyncio.TimeoutError as exc:
        raise MediaServiceError("timeout", "تشخیص صدا طول کشید؛ دوباره تلاش کن.") from exc
    except aiohttp.ClientError as exc:
        raise MediaServiceError("network", "اتصال به سرویس تشخیص برقرار نشد.") from exc
    result = payload.get("result") if isinstance(payload, dict) else None
    if not result:
        return None
    title = str(result.get("title") or "").strip()
    artist = str(result.get("artist") or "").strip()
    if not title:
        return None
    return {
        "title": title[:180],
        "artist": artist[:120],
        "album": str(result.get("album") or "")[:120],
        "song_link": result.get("song_link") or "",
        "spotify": (result.get("spotify") or {}).get("external_urls", {}).get("spotify", "")
        if isinstance(result.get("spotify"), dict) else "",
    }
