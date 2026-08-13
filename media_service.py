"""Safe public-media downloading and direct URL upload helpers for Ajorpareh.

The module intentionally supports public URLs only. It does not accept cookies,
credentials, private-network destinations, DRM bypasses, or private profiles.
"""

from __future__ import annotations

import asyncio
import ipaddress
import html as html_lib
import json
import logging
import mimetypes
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import aiohttp

log = logging.getLogger("media_service")

try:
    import yt_dlp
    from yt_dlp.networking.impersonate import ImpersonateTarget
except ImportError:  # pragma: no cover - deployment installs yt-dlp
    yt_dlp = None
    ImpersonateTarget = None


# سقف حجم فایل: به‌صورت پیش‌فرض ۵۰ مگابایت (سقف API معمولی تلگرام).
# وقتی سرور لوکال Bot API فعال باشد (MAX_MEDIA_BYTES_MB=1950)، تا ~۲ گیگابایت.
MAX_MEDIA_BYTES = max(49, min(int(os.environ.get("MAX_MEDIA_BYTES_MB", "49") or 49), 1950)) * 1024 * 1024
MAX_MEDIA_ITEMS = 10
INSTAGRAM_HIKER_TOKEN = os.getenv("HIKERAPI_TOKEN", "").strip()
INSTAGRAM_MANAGED_PROVIDER = os.getenv(
    "INSTAGRAM_MANAGED_PROVIDER",
    "hiker" if INSTAGRAM_HIKER_TOKEN else "apify",
).strip().lower()
INSTAGRAM_APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
INSTAGRAM_APIFY_ACTOR = os.getenv(
    "INSTAGRAM_APIFY_ACTOR",
    "apify~instagram-scraper",
).strip()
INSTAGRAM_RESOLVER_API_URL = os.getenv("INSTAGRAM_RESOLVER_API_URL", "").strip()
INSTAGRAM_RESOLVER_API_KEY = os.getenv("INSTAGRAM_RESOLVER_API_KEY", "").strip()


def media_size_label() -> str:
    mb = MAX_MEDIA_BYTES // (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.1f} گیگابایت"
    return f"{mb} مگابایت"
SUPPORTED_SOCIAL_DOMAINS = {
    # شبکه‌های اجتماعی و ویدئو
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    "vxtwitter.com", "fxtwitter.com", "nitter.net",
    "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch",
    "reddit.com", "www.reddit.com", "old.reddit.com", "v.redd.it",
    "pinterest.com", "www.pinterest.com", "pin.it",
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com",
    "threads.net", "www.threads.net",
    "vimeo.com", "www.vimeo.com", "player.vimeo.com",
    "dailymotion.com", "www.dailymotion.com", "dai.ly",
    "twitch.tv", "www.twitch.tv", "clips.twitch.tv", "m.twitch.tv",
    "soundcloud.com", "www.soundcloud.com", "on.soundcloud.com",
    "bandcamp.com", "www.bandcamp.com",
    "mixcloud.com", "www.mixcloud.com",
    "audiomack.com", "www.audiomack.com",
    "vk.com", "www.vk.com", "m.vk.com", "vkvideo.ru",
    "ok.ru", "www.ok.ru", "m.ok.ru",
    "rutube.ru", "www.rutube.ru",
    "bilibili.com", "www.bilibili.com", "b23.tv",
    "streamable.com", "www.streamable.com",
    "coub.com", "www.coub.com",
    "9gag.com", "www.9gag.com",
    "imgur.com", "www.imgur.com", "i.imgur.com",
    "tumblr.com", "www.tumblr.com",
    "flickr.com", "www.flickr.com",
    "archive.org", "www.archive.org",
    "rumble.com", "www.rumble.com",
    "odysee.com", "www.odysee.com", "lbry.tv",
    "kick.com", "www.kick.com",
    "bitchute.com", "www.bitchute.com",
    "douyin.com", "www.douyin.com",
    "weibo.com", "www.weibo.com",
    "kuaishou.com", "www.kuaishou.com",
    "t.me", "telegram.me", "telegram.dog",
    # ویدئو و استریم اضافی
    "loom.com", "www.loom.com",
    "gfycat.com", "www.gfycat.com",
    "vlive.tv", "www.vlive.tv",
    "nicovideo.jp", "www.nicovideo.jp", "sp.nicovideo.jp",
    "iwara.tv", "www.iwara.tv",
    # موسیقی
    "spotify.com", "open.spotify.com",
    "deezer.com", "www.deezer.com",
    "music.apple.com",
    "podcasts.apple.com",
    "anchor.fm", "www.anchor.fm",
    "hearthis.at", "www.hearthis.at",
    "reverbnation.com", "www.reverbnation.com",
    # تصویر
    "unsplash.com", "www.unsplash.com",
    "pexels.com", "www.pexels.com",
    "pixabay.com", "www.pixabay.com",
    "500px.com", "www.500px.com",
    "deviantart.com", "www.deviantart.com",
    "artstation.com", "www.artstation.com",
    "imgbb.com", "www.imgbb.com", "i.imgbb.com",
    "postimages.org", "www.postimages.org",
    # شبکه‌های اجتماعی اضافی
    "mastodon.social", "www.mastodon.social",
    "truthsocial.com", "www.truthsocial.com",
    "minds.com", "www.minds.com",
    "gettr.com", "www.gettr.com",
    "bsky.app",
    # آموزشی
    "coursera.org", "www.coursera.org",
    "udemy.com", "www.udemy.com",
    "khanacademy.org", "www.khanacademy.org",
    "ted.com", "www.ted.com",
    "academia.edu", "www.academia.edu",
    "slideshare.net", "www.slideshare.net",
    # اشتراک‌گذاری عمومی فایل
    "drive.google.com", "docs.google.com", "dropbox.com", "www.dropbox.com",
    "dl.dropbox.com", "dl.dropboxusercontent.com", "mediafire.com",
    "www.mediafire.com", "1drv.ms", "onedrive.live.com",
    "mega.nz", "mega.co.nz",
    "wetransfer.com", "www.wetransfer.com",
    "sendspace.com", "www.sendspace.com",
    "cdn.discordapp.com", "media.discordapp.net",
    "raw.githubusercontent.com", "github.com", "gist.githubusercontent.com",
    "gitlab.com", "raw.gitlab.com", "cdn.jsdelivr.net", "unpkg.com",
    "storage.googleapis.com", "storage.cloud.google.com", "blob.core.windows.net",
    "r2.dev", "pages.dev", "cloudfront.net", "digitaloceanspaces.com",
    "upload.wikimedia.org", "images.unsplash.com", "images.pexels.com",
    "media.tenor.com", "media.giphy.com", "i.giphy.com",
    "video.twimg.com", "pbs.twimg.com",
    # CDNهای عمومی و سرویس‌های استریم HLS/DASH
    "stream.mux.com", "cdn.jwplayer.com", "content.jwplatform.com",
    "videos.cdn.mozilla.net", "akamaized.net", "fastly.net",
    "videodelivery.net", "cloudflarestream.com",
    "pixeldrain.com", "www.pixeldrain.com",
    "gofile.io", "www.gofile.io",
    "catbox.moe", "files.catbox.moe",
    "krakenfiles.com", "www.krakenfiles.com",
    # ایرانی
    "aparat.com", "www.aparat.com",
    "tamasha.com", "www.tamasha.com",
    "filimo.com", "www.filimo.com",
    "namasha.com", "www.namasha.com",
    "telewebion.com", "www.telewebion.com",
}
SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "cutt.ly", "shorturl.at", "rebrand.ly",
    "is.gd", "buff.ly", "ow.ly", "rb.gy", "goo.su",
}
SUSPICIOUS_TERMS = {
    "login", "signin", "verify", "verification", "wallet", "seed", "password",
    "gift", "bonus", "airdrop", "support", "telegram-premium", "recover", "secure",
    "ورود", "تایید", "کیف پول", "رمز", "جایزه", "هدیه",
}
DIRECT_ALLOWED_MIME_PREFIXES = ("video/", "audio/", "image/")
DIRECT_ALLOWED_MIME_TYPES = {
    # اسناد
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/rtf", "text/rtf",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "application/epub+zip", "application/x-mobipocket-ebook",
    "application/vnd.amazon.ebook", "application/oxps",
    "application/vnd.ms-xpsdocument", "application/x-djvu", "image/vnd.djvu",
    # بایگانی و تصویر دیسک
    "application/zip", "application/x-zip-compressed",
    "application/vnd.rar", "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/x-tar", "application/gzip", "application/x-gzip",
    "application/x-bzip2", "application/x-xz", "application/zstd",
    "application/x-iso9660-image", "application/x-cd-image",
    # برنامه‌ها و اجرایی
    "application/vnd.android.package-archive",
    "application/x-msdownload", "application/vnd.microsoft.portable-executable",
    "application/x-msi", "application/x-msinstaller",
    "application/x-deb", "application/vnd.debian.binary-package",
    "application/x-rpm", "application/x-iso9660-appimage",
    "application/vnd.apple.installer+xml", "application/x-apple-diskimage",
    "application/java-archive", "application/x-java-archive",
    "application/x-pkcs12", "application/x-chrome-extension",
    "application/x-xpinstall",
    # کد و داده
    "application/json", "application/xml", "text/xml",
    "application/javascript", "text/javascript", "text/css",
    "application/x-sql", "application/vnd.sqlite3", "application/x-sqlite3",
    "application/x-httpd-php", "text/x-php",
    "text/markdown", "text/x-markdown",
    "text/yaml", "application/yaml", "application/x-yaml",
    "text/x-sh", "application/x-sh", "application/x-bat",
    "text/x-python", "application/x-python-code",
    "text/x-java-source", "text/x-c", "text/x-c++", "text/x-ruby",
    "application/x-ipynb+json",
    # فونت
    "font/ttf", "font/otf", "font/woff", "font/woff2",
    "application/font-ttf", "application/font-woff",
    "application/x-font-ttf", "application/x-font-otf",
    "application/vnd.ms-fontobject",
    # زیرنویس و متن‌های خاص
    "text/vtt", "application/x-subrip", "text/x-srt",
    "text/vcard", "text/x-vcard", "text/calendar",
    "text/csv", "text/x-csv", "text/tab-separated-values",
    "text/plain",
}
# اگر سرور برای پسوندِ شناخته‌شده، نوع MIME درست نفرستد
# (مثلاً APK یا EXE را به‌صورت application/octet-stream بدهد)،
# با پسوند فایل هم اجازه می‌دهیم؛ فقط صفحات HTML همیشه رد می‌شوند.
DIRECT_ALLOWED_SUFFIXES = {
    # رسانه (وقتی سرور MIME درست نفرستد)
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv", ".wmv", ".m4v", ".3gp",
    ".mpg", ".mpeg", ".ts", ".m2ts",
    ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".flac", ".aac", ".amr", ".mid",
    ".midi", ".wma", ".aiff",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic",
    ".heif", ".tiff", ".ico", ".avif", ".raw",
    # اجرایی و نصاب
    ".apk", ".aab", ".exe", ".msi", ".bat", ".cmd", ".com", ".jar", ".deb",
    ".rpm", ".appimage", ".ipa", ".dmg", ".iso", ".xpi", ".crx", ".apks",
    ".xapk", ".msix", ".ps1", ".run",
    # اسناد
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf",
    ".odt", ".ods", ".odp", ".txt", ".csv", ".tsv", ".md", ".epub", ".mobi",
    ".azw3", ".djvu", ".xps", ".tex", ".ps", ".pages", ".key", ".numbers",
    # بایگانی
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2",
    ".zst", ".lz4", ".cab", ".ace", ".arj",
    # کد و داده
    ".json", ".xml", ".yaml", ".yml", ".sql", ".db", ".sqlite", ".sqlite3",
    ".log", ".ini", ".cfg", ".conf", ".env", ".py", ".js", ".mjs",
    ".css", ".php", ".sh", ".ipynb", ".java", ".c", ".cpp", ".rb", ".go",
    ".rs", ".cs", ".swift", ".kt",
    # فونت
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # زیرنویس
    ".srt", ".vtt", ".ass", ".ssa",
    # تماس، تقویم، نقشه
    ".vcf", ".ics", ".kml", ".gpx", ".kmz",
    # سه‌بعدی و طراحی
    ".stl", ".obj", ".glb", ".gltf", ".blend", ".fbx", ".psd", ".ai", ".xcf",
}
# پسوند پیشنهادی برای فایل‌هایی که سرور پسوند نگوید (نام فایل بی‌پسوند)
MIME_EXTENSION_FALLBACK = {
    "application/vnd.android.package-archive": ".apk",
    "application/x-msdownload": ".exe",
    "application/vnd.microsoft.portable-executable": ".exe",
    "application/x-msi": ".msi",
    "application/x-deb": ".deb",
    "application/x-rpm": ".rpm",
    "application/java-archive": ".jar",
    "application/epub+zip": ".epub",
    "application/x-mobipocket-ebook": ".mobi",
    "application/x-7z-compressed": ".7z",
    "application/x-tar": ".tar",
    "application/gzip": ".gz",
    "application/x-bzip2": ".bz2",
    "application/x-xz": ".xz",
    "application/vnd.rar": ".rar",
    "application/x-rar-compressed": ".rar",
    "application/rtf": ".rtf",
    "application/x-iso9660-image": ".iso",
    "application/x-apple-diskimage": ".dmg",
    "application/x-iso9660-appimage": ".appimage",
    "font/ttf": ".ttf", "font/otf": ".otf", "font/woff": ".woff",
    "font/woff2": ".woff2",
    "application/x-subrip": ".srt", "text/vtt": ".vtt",
    "text/vcard": ".vcf", "text/calendar": ".ics",
    "application/x-chrome-extension": ".crx", "application/x-xpinstall": ".xpi",
}


def is_direct_upload_allowed(content_type: str, filename: str) -> bool:
    """آیا MIME/پسوند از قبل شناخته‌شده و مجاز است؟ صفحات HTML همیشه رد می‌شوند.

    فایل‌های ناشناخته با MIME عمومی مثل octet-stream این‌جا رد می‌شوند اما
    گیت نهایی فقط بایت‌های اول فایل را بررسی می‌کند (نه HTML بودن)؛ یعنی هر
    فایل عمومیِ واقعی حتی با پسوند ناشناخته هم پذیرفته می‌شود.
    """
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime == "text/html":
        return False
    if mime.startswith(DIRECT_ALLOWED_MIME_PREFIXES):
        return True
    if mime in DIRECT_ALLOWED_MIME_TYPES:
        return True
    return Path(filename).suffix.lower() in DIRECT_ALLOWED_SUFFIXES


def looks_like_html(raw: bytes) -> bool:
    """تشخیص صفحهٔ وب از روی بایت‌های اول؛ برای جلوگیری از آپلود صفحات HTML."""
    head = raw.lstrip()[:512].lower()
    if head.startswith((b"<!doctype html", b"<html", b"<head", b"<!html")):
        return True
    return False


class MediaServiceError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(slots=True)
class DownloadedMedia:
    path: str
    filename: str
    mime_type: str
    size: int
    title: str
    kind: str
    caption: str = ""  # متن/کپشن پست
    description: str = ""  # توضیحات اضافی


def normalized_host(url: str) -> str:
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.strip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    return host if re.fullmatch(r"[a-z0-9.-]{1,253}", host) and ".." not in host else ""


def host_matches(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def normalize_youtube_url(url: str) -> str:
    """تبدیل Shorts/Shorts share URL به watch URL پایدار برای yt-dlp/Cobalt."""
    value = str(url or "").strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        return value
    parts = [part for part in parsed.path.split("/") if part]
    video_id = ""
    if host == "youtu.be" and parts:
        video_id = parts[0]
    elif parts and parts[0].lower() in {"shorts", "embed", "live"} and len(parts) > 1:
        video_id = parts[1]
    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
        return f"https://www.youtube.com/watch?v={video_id}"
    return value


def normalize_instagram_url(url: str) -> str:
    """حذف پارامترهای اشتراک‌گذاری Instagram برای fallbackهای عمومی."""
    value = str(url or "").strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host not in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
        return value
    path = "/" + "/".join(part for part in parsed.path.split("/") if part) + "/"
    if not re.match(r"^/(?:reel|p|tv)/[A-Za-z0-9_-]{3,}/$", path, flags=re.I):
        return value
    return f"https://www.instagram.com{path}"


def is_instagram_public_url(url: str) -> bool:
    host = normalized_host(url)
    return host in {"instagram.com", "www.instagram.com", "m.instagram.com"} and bool(
        re.search(r"/(?:reel|p|tv)/[A-Za-z0-9_-]{3,}", url, flags=re.I)
    )


# مسیرهای سیستمی اینستاگرام که نام کاربری نیستند
INSTAGRAM_RESERVED_PATHS = {
    "p", "reel", "reels", "tv", "stories", "accounts", "explore", "about",
    "developer", "directory", "legal", "privacy", "terms", "help", "challenge",
    "two_factor", "create", "web", "api", "graphql", "download", "embed",
}

INSTAGRAM_PROFILE_RE = re.compile(
    r"^/(?:([A-Za-z0-9._]{1,30}))/?(?:[?#].*)?$"
)


def is_instagram_profile_url(url: str) -> bool:
    """لینک صفحهٔ پروفایل عمومی اینستاگرام مثل instagram.com/username/"""
    host = normalized_host(url)
    if host not in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
        return False
    try:
        path = urlparse(str(url or "").strip()).path or "/"
    except ValueError:
        return False
    match = INSTAGRAM_PROFILE_RE.match(path)
    if not match:
        return False
    username = match.group(1).lower()
    if username in INSTAGRAM_RESERVED_PATHS:
        return False
    # نام کاربری معتبر اینستاگرام: حداقل ۲ کاراکتر و شروع/پایان با نقطه ممنوع
    return len(username) >= 2 and not username.startswith(".") and not username.endswith(".")


def instagram_username_from_url(url: str) -> str:
    try:
        path = urlparse(str(url or "").strip()).path or "/"
    except ValueError:
        return ""
    match = INSTAGRAM_PROFILE_RE.match(path)
    return match.group(1) if match else ""


def is_social_url(url: str) -> bool:
    host = normalized_host(normalize_youtube_url(url))
    return bool(host and host_matches(host, SUPPORTED_SOCIAL_DOMAINS))


def is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not any((
        address.is_private,
        address.is_loopback,
        address.is_link_local,
        address.is_multicast,
        address.is_reserved,
        address.is_unspecified,
    ))


async def resolve_public_host(host: str) -> list[str]:
    def resolve() -> list[str]:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return sorted({record[4][0] for record in records})

    try:
        addresses = await asyncio.wait_for(asyncio.to_thread(resolve), timeout=8)
    except (socket.gaierror, asyncio.TimeoutError, OSError) as exc:
        raise MediaServiceError("dns", "دامنه پیدا نشد یا DNS پاسخ نداد.") from exc
    if not addresses or any(not is_public_ip(address) for address in addresses):
        raise MediaServiceError("private_host", "آدرس‌های داخلی، محلی یا خصوصی قابل دریافت نیستند.")
    return addresses


async def validate_public_url(url: str, *, social_only: bool = False, allow_generic: bool = False) -> str:
    value = str(url or "").strip()
    host = normalized_host(value)
    if not host:
        raise MediaServiceError("invalid_url", "لینک باید کامل و با http یا https شروع شود.")
    # allow_generic یعنی هر دامنهٔ عمومی می‌تواند رسانه داشته باشد
    # (موتور yt-dlp روی سایت‌های ناشناخته هم تلاش می‌کند)؛ باز هم SSRF محافظت می‌شود.
    if social_only and not allow_generic and not host_matches(host, SUPPORTED_SOCIAL_DOMAINS):
        raise MediaServiceError("unsupported_site", "این شبکه فعلاً پشتیبانی نمی‌شود.")
    await resolve_public_host(host)
    return value


HLS_MIME_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
    "video/mp2t",
}


def looks_like_hls_url(url: str) -> bool:
    """تشخیص لینک m3u8/m3u یا manifestهای شناخته‌شده بدون دانلود آن."""
    value = str(url or "").lower()
    path = urlparse(value).path.lower()
    return path.endswith((".m3u8", ".m3u")) or "m3u8" in value or "manifest" in path or "playlist" in path


def looks_like_hls_manifest(raw: bytes, content_type: str = "") -> bool:
    head = raw.lstrip()[:4096].upper()
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    return mime in HLS_MIME_TYPES or head.startswith(b"#EXTM3U") or b"#EXT-X-" in head


def looks_like_direct_media_url(url: str) -> bool:
    """آیا لینک مستقیم به یک فایل رسانه/بایگانی با پسوند شناخته‌شده است؟"""
    suffix = Path(urlparse(str(url or "").strip()).path).suffix.lower()
    return bool(suffix) and suffix in DIRECT_ALLOWED_SUFFIXES


def safe_filename(value: str, fallback: str = "ajorpareh-file") -> str:
    name = Path(unquote(str(value or ""))).name
    name = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]", "_", name).strip(" ._")
    if not name:
        name = fallback
    stem = Path(name).stem[:80] or fallback
    suffix = Path(name).suffix.lower()[:10]
    return f"{stem}{suffix}"


def infer_kind(path: Path, mime_type: str = "") -> str:
    suffix = path.suffix.lower()
    mime = (mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream").lower()
    if mime.startswith("image/") and suffix not in {".gif"}:
        return "photo"
    if mime.startswith("video/") or suffix in {".mp4", ".mov", ".mkv", ".webm"}:
        return "video"
    if mime.startswith("audio/") or suffix in {".mp3", ".m4a", ".ogg", ".opus", ".wav"}:
        return "audio"
    if suffix == ".gif" or mime == "image/gif":
        return "animation"
    return "document"


def _make_ytdlp_progress_hook(callback):
    """ساخت progress hook برای yt-dlp با callback خارجی."""
    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = min(99, int(downloaded * 100 / total))
            else:
                pct = 0
            if callback:
                callback(pct, downloaded, total)
        elif d.get("status") == "finished":
            if callback:
                callback(100, 0, 0)
    return hook


def social_download_options(output_dir: str, max_bytes: int, progress_hook=None) -> dict[str, Any]:
    folder = Path(output_dir)
    options: dict[str, Any] = {
        "format": (
            "best[height<=1080][ext=mp4][vcodec!=none][acodec!=none]/"
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
            "best[height<=1080]/"
            "bestvideo[height<=720]+bestaudio/"
            "best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(folder / "%(playlist_index|00)s-%(id)s-%(title).60B.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": False,
        "playlistend": MAX_MEDIA_ITEMS,
        "socket_timeout": 25,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "continuedl": False,
        "restrictfilenames": True,
        "overwrites": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr", "web", "mweb"]}},
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.google.com/",
        },
        "geo_bypass": True,
        "geo_bypass_country": "US",
        "compat_opts": [],
    }
    if progress_hook:
        options["progress_hooks"] = [progress_hook]
    if ImpersonateTarget is not None:
        options["impersonate"] = ImpersonateTarget(client="chrome")
    return options


def probe_duration_seconds(path: str) -> float | None:
    try:
        process = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60,
        )
        value = float(process.stdout.strip())
        return value if value > 0 else None
    except Exception:
        return None


def compress_video_to_fit(src: str, dst: str, max_bytes: int) -> bool:
    """ویدئو را با ffmpeg تا زیر سقف حجم فشرده می‌کند (کیفیت تا جای ممکن حفظ می‌شود)."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        return False
    target = max(max_bytes - 1024 * 1024, 2 * 1024 * 1024)
    duration = probe_duration_seconds(src)
    # اول با رزولوشن پایین‌تر (خیلی سریع‌تر) تلاش کن؛ آخر سراغ bitrate با رزولوشن کامل برو
    attempts: list[tuple[int | None, int | None]] = [(720, None), (480, None)]
    if duration and duration > 1:
        bitrate_kbps = int(target * 8 / duration / 1000 * 0.9)
        if bitrate_kbps > 100:
            attempts.append((None, bitrate_kbps))
    for scale, bitrate_kbps in attempts:
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-threads", "0", "-i", src,
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-c:a", "aac", "-b:a", "96k",
        ]
        if scale is not None:
            command += ["-vf", f"scale=min({scale}\\,iw):-2", "-crf", "23"]
        else:
            command += [
                "-b:v", f"{bitrate_kbps}k",
                "-maxrate", f"{int(bitrate_kbps * 1.2)}k",
                "-bufsize", f"{int(bitrate_kbps * 2)}k",
            ]
        command.append(dst)
        try:
            process = subprocess.run(command, capture_output=True, timeout=900)
        except Exception:
            continue
        if process.returncode != 0:
            continue
        if Path(dst).stat().st_size <= max_bytes:
            return True
    return False


def classify_social_download_error(exc: Exception) -> MediaServiceError:
    message = str(exc).lower()
    platform_block_terms = (
        "not a bot", "bot check", "ip address is blocked", "empty media response",
        "rate-limit reached", "http error 403", "http error 429", "too many requests",
        "sign in to confirm", "unable to extract webpage video data",
        "unable to extract universal data", "temporarily blocked",
    )
    if any(term in message for term in platform_block_terms):
        return MediaServiceError(
            "platform_blocked",
            "پلتفرم درخواست سرور را موقتاً محدود کرده؛ اگر لینک عمومی باشد نسخه قابل‌تماشا فرستاده می‌شود.",
        )
    private_terms = (
        "private", "members-only", "login required", "requires authentication",
        "requested content is not available", "age-restricted", "not available in your country",
    )
    if any(term in message for term in private_terms):
        return MediaServiceError(
            "private_or_restricted",
            "این محتوا خصوصی، حذف‌شده، محدود یا نیازمند ورود است؛ فقط محتوای عمومی قابل دریافت است.",
        )
    no_media_terms = (
        "unsupported url", "no video", "no media", "nothing to download",
        "no video formats found", "unable to find", "does not contain any video",
        "no supported url", "is not a valid url",
    )
    if any(term in message for term in no_media_terms):
        return MediaServiceError(
            "no_media",
            "در این صفحه رسانهٔ قابل دریافت پیدا نشد؛ مطمئن شو لینک به ویدئو/پست است نه فقط صفحهٔ سایت.",
        )
    return MediaServiceError(
        "download_failed",
        "دریافت رسانه ناموفق بود؛ لینک عمومی و در دسترس را بررسی کن.",
    )


def _social_download_sync(url: str, output_dir: str, max_bytes: int, progress_callback=None) -> tuple[str, list[DownloadedMedia]]:
    if yt_dlp is None:
        raise MediaServiceError("unavailable", "موتور دانلود روی سرور نصب نیست.")
    folder = Path(output_dir)
    title = "رسانه"
    caption = ""
    description = ""
    ytdlp_hook = _make_ytdlp_progress_hook(progress_callback)

    # ===== روش ۱: yt-dlp stable (اصلی) =====
    ytdlp_error = None
    try:
        opts = social_download_options(output_dir, max_bytes, progress_hook=ytdlp_hook)
        with yt_dlp.YoutubeDL(opts) as downloader:
            info = downloader.extract_info(url, download=True)
        title = str((info or {}).get("title") or (info or {}).get("description") or "رسانه")[:200]
        caption = str((info or {}).get("description") or (info or {}).get("title") or "")[:1000]
        description = str((info or {}).get("description") or "")[:2000]
        if progress_callback: progress_callback(100, 0, 0)
        return _collect_files(folder, max_bytes, title, caption, description)
    except Exception as exc:
        ytdlp_error = classify_social_download_error(exc)
        if ytdlp_error.reason not in {"no_media", "download_failed", "platform_blocked"}:
            raise ytdlp_error from None

    # ===== روش ۲: yt-dlp مستقیم (بدون extractor — برای لینک‌های مستقیم) =====
    try:
        if progress_callback: progress_callback(5, 0, 0)
        output_path = str(folder / "%(title).60B.%(ext)s")
        cmd = [
            "yt-dlp", "--no-warnings", "--no-check-certificates",
            "-o", output_path,
            "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--add-header", "Referer:https://www.google.com/",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            if progress_callback: progress_callback(100, 0, 0)
            collected = _collect_files(folder, max_bytes, title or "رسانه")
            if collected[1]:
                return collected
    except Exception:
        pass

    # ===== روش ۳: ffmpeg برای لینک‌های m3u8/HLS =====
    if shutil.which("ffmpeg") and (".m3u8" in url or "hls" in url.lower() or ".mpd" in url):
        try:
            if progress_callback: progress_callback(10, 0, 0)
            output_path = str(folder / "stream_download.mp4")
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\n",
                "-i", url,
                "-c", "copy",
                "-movflags", "+faststart",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if result.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
                if progress_callback: progress_callback(100, 0, 0)
                return _collect_files(folder, max_bytes, title or "ویدئو")
        except Exception:
            pass

    # ===== روش ۴: دانلود مستقیم HTTP (آخرین راه) =====
    if progress_callback: progress_callback(5, 0, 0)
    try:
        import urllib.request
        output_path = str(folder / "direct_download.mp4")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.google.com/",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(output_path, "wb") as f:
                while True:
                    chunk = resp.read(512 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(min(99, int(downloaded * 100 / total)), downloaded, total)
                    if downloaded > max_bytes:
                        break
        if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            if progress_callback: progress_callback(100, 0, 0)
            return _collect_files(folder, max_bytes, title or "رسانه")
    except Exception:
        pass

    def clear_fallback_artifacts() -> None:
        """فایل‌های ناقص روش قبلی را قبل از ابزار بعدی پاک می‌کند."""
        for artifact in folder.iterdir():
            if artifact.is_file():
                try:
                    artifact.unlink()
                except OSError:
                    pass

    def external_download(method: str) -> tuple[str, list[DownloadedMedia]] | None:
        """روش‌های باینری سبک برای CDNها و لینک‌های مستقیم عمومی."""
        executable = shutil.which(method)
        if not executable:
            return None
        clear_fallback_artifacts()
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in DIRECT_ALLOWED_SUFFIXES:
            suffix = ".mp4"
        output_path = folder / f"{method}_download{suffix}"
        user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
        if method == "curl":
            command = [
                executable, "-L", "--fail", "--silent", "--show-error",
                "--max-time", "300", "--connect-timeout", "20",
                "--retry", "2", "--max-filesize", str(max_bytes),
                "-A", user_agent, "-e", "https://www.google.com/",
                "-o", str(output_path), url,
            ]
        elif method == "wget":
            # wget has no portable per-file byte cap; only use it for URLs that
            # already look like a direct file, then enforce the cap in collector.
            if not looks_like_direct_media_url(url):
                return None
            command = [
                executable, "--quiet", "--max-redirect=8", "--timeout=25",
                "--tries=2", "--user-agent", user_agent,
                "-O", str(output_path), url,
            ]
        else:  # aria2c
            output_path.unlink(missing_ok=True)
            command = [
                executable, "--allow-overwrite=true", "--auto-file-renaming=false",
                "--file-allocation=none", "--max-tries=3", "--retry-wait=2",
                "--max-connection-per-server=4", "--timeout=25", "--summary-interval=0",
                f"--max-file-size={max_bytes}", f"--dir={folder}", f"--out={output_path.name}", url,
            ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=330)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
            return None
        try:
            return _collect_files(folder, max_bytes, title or "رسانه", caption, description)
        except MediaServiceError:
            return None

    # ===== روش ۵: curl با redirect/retry و سقف حجم =====
    for binary in ("curl", "wget", "aria2c"):
        collected = external_download(binary)
        if collected:
            if progress_callback:
                progress_callback(100, 0, 0)
            return collected

    # همه روش‌ها ناموفق بود
    if ytdlp_error:
        raise ytdlp_error
    raise MediaServiceError("download_failed", "دریافت رسانه از همه روش‌ها ناموفق بود. لینک رو بررسی کن.")


def _collect_files(folder: Path, max_bytes: int, title: str, caption: str = "", description: str = "") -> tuple[str, list[DownloadedMedia]]:
    """فایل‌های دانلودشده در پوشه رو جمع‌آوری می‌کنه."""
    files: list[DownloadedMedia] = []
    ignored_suffixes = {".part", ".ytdl", ".json", ".description", ".vtt", ".srt"}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() in ignored_suffixes:
            continue
        size = path.stat().st_size
        try:
            with path.open("rb") as sample:
                if looks_like_html(sample.read(4096)):
                    continue
        except OSError:
            continue
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        kind = infer_kind(path, mime)
        if size > max_bytes and (kind == "video" or mime.startswith("video/")):
            fitted = folder / f"{path.stem}.fit.mp4"
            if compress_video_to_fit(str(path), str(fitted), max_bytes):
                os.replace(fitted, path)
                path = Path(path)
                size = path.stat().st_size
                mime = "video/mp4"
                kind = "video"
        if size <= 0 or size > max_bytes:
            continue
        files.append(DownloadedMedia(
            path=str(path), filename=safe_filename(path.name, "ajorpareh-media"),
            mime_type=mime, size=size, title=title, kind=kind,
            caption=caption, description=description,
        ))
        if len(files) >= MAX_MEDIA_ITEMS:
            break
    if not files:
        raise MediaServiceError(
            "too_large_or_empty",
            f"فایل پیدا نشد یا حتی پس از فشرده‌سازی حجمش از محدودیت {media_size_label()} تلگرام بیشتر بود.",
        )
    return title, files


def _audio_download_sync(url: str, output_dir: str, max_bytes: int) -> tuple[str, list[DownloadedMedia]]:
    if yt_dlp is None:
        raise MediaServiceError("unavailable", "موتور دانلود روی سرور نصب نیست.")
    folder = Path(output_dir)
    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(folder / "%(id)s-audio.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 20,
        "retries": 2,
        "concurrent_fragment_downloads": 4,
        "continuedl": False,
        "restrictfilenames": True,
        "overwrites": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
    }
    if ImpersonateTarget is not None:
        options["impersonate"] = ImpersonateTarget(client="chrome")
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
    except Exception as exc:
        raise classify_social_download_error(exc) from exc
    title = str((info or {}).get("title") or (info or {}).get("description") or "صوت")[:200]
    files: list[DownloadedMedia] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() in {".part", ".ytdl", ".json"}:
            continue
        if path.suffix.lower() not in {".mp3", ".m4a", ".opus", ".ogg", ".wav", ".aac"}:
            continue
        size = path.stat().st_size
        if size <= 0 or size > max_bytes:
            continue
        mime = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
        files.append(DownloadedMedia(
            path=str(path),
            filename=safe_filename(path.name, "ajorpareh-audio"),
            mime_type=mime,
            size=size,
            title=title,
            kind="audio",
        ))
        break
    if not files:
        raise MediaServiceError(
            "too_large_or_empty",
            "استخراج صوت ناموفق بود یا حجم آن از محدودیت ۵۰ مگابایت بیشتر است.",
        )
    return title, files


async def download_audio_track(url: str, output_dir: str, max_bytes: int = MAX_MEDIA_BYTES) -> tuple[str, list[DownloadedMedia]]:
    safe_url = normalize_youtube_url(await validate_public_url(url, social_only=True, allow_generic=True))
    return await asyncio.to_thread(_audio_download_sync, safe_url, output_dir, max_bytes)


def _instagram_embed_candidates(url: str) -> list[str]:
    base = normalize_instagram_url(url).rstrip("/")
    shortcode = base.rsplit("/", 1)[-1]
    return list(dict.fromkeys([
        f"{base}/embed/",
        f"{base}/embed/captioned/",
        f"https://www.instagram.com/p/{shortcode}/embed/",
        f"https://www.instagram.com/p/{shortcode}/embed/captioned/",
        f"{base}/?__a=1&__d=dis",
    ]))


def extract_instagram_public_media_urls(body: str) -> list[str]:
    """استخراج URL عمومی ویدئوی embed/metadata بدون کوکی یا ورود."""
    text = html_lib.unescape(str(body or ""))
    patterns = [
        r"<meta[^>]+(?:property|name)=[\"'](?:og:video|og:video:secure_url)[\"'][^>]+content=[\"']([^\"']+)",
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name)=[\"'](?:og:video|og:video:secure_url)[\"']",
        r"[\"'](?:video_url|videoUrl|playback_url|playbackUrl)[\"']\s*:\s*[\"']([^\"']+)",
    ]
    urls: list[str] = []
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.I):
            candidate = html_lib.unescape(str(raw)).replace("\\/", "/").replace("\\u0026", "&")
            if candidate.startswith("http") and candidate not in urls:
                urls.append(candidate)
    # Some logged-out embed versions put the GraphQL payload inside a JSON
    # string named contextJSON. Decode it when present, without requiring login.
    context_key = '"contextJSON":'
    context_index = text.find(context_key)
    if context_index >= 0:
        try:
            decoded, _ = json.JSONDecoder().raw_decode(text, context_index + len(context_key))
            if isinstance(decoded, str):
                decoded = json.loads(decoded)
            context_text = json.dumps(decoded, ensure_ascii=False) if isinstance(decoded, (dict, list)) else ""
            for raw in re.findall(
                r'''["'](?:video_url|videoUrl|playback_url|playbackUrl)["']\s*:\s*["']([^"']+)''',
                context_text,
                flags=re.I,
            ):
                candidate = html_lib.unescape(str(raw)).replace("\\/", "/").replace("\\u0026", "&")
                if candidate.startswith("http") and candidate not in urls:
                    urls.append(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return urls[:12]


def _clean_instagram_count(value: str) -> str:
    """اعداد مثل 1,234 یا 12.5K را به‌صورت متن مرتب برمی‌گرداند."""
    return re.sub(r"\s+", "", str(value or "")).strip()


def extract_instagram_post_metadata(body: str) -> dict:
    """استخراج کپشن/لایک/کامنت/ویو/نام کاربری از صفحهٔ embed یا پست عمومی اینستاگرام (بدون ورود)."""
    text = html_lib.unescape(str(body or ""))
    meta: dict = {"caption": "", "likes": "", "comments": "", "views": "", "username": ""}
    if not text:
        return meta

    # og:description معمولاً این قالب را دارد: "1,234 likes, 45 comments - متن کپشن..."
    og_desc = ""
    desc_match = re.search(
        r"<meta[^>]+(?:property|name)=[\"']og:description[\"'][^>]+content=[\"']([^\"']*)",
        text, flags=re.I,
    ) or re.search(
        r"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]+(?:property|name)=[\"']og:description[\"']",
        text, flags=re.I,
    )
    if desc_match:
        og_desc = html_lib.unescape(desc_match.group(1)).strip()

    likes_match = re.search(r"([\d][\d,.]*[KkMm]?)\s+likes?", og_desc or text, flags=re.I)
    if likes_match:
        meta["likes"] = _clean_instagram_count(likes_match.group(1))
    comments_match = re.search(r"([\d][\d,.]*[KkMm]?)\s+comments?", og_desc or text, flags=re.I)
    if comments_match:
        meta["comments"] = _clean_instagram_count(comments_match.group(1))
    views_match = (
        re.search(r"\"(?:video_view_count|view_count|viewCount)\"\s*:\s*(\d+)", text)
        or re.search(r"([\d][\d,.]*[KkMm]?)\s+views?", text, flags=re.I)
    )
    if views_match:
        meta["views"] = _clean_instagram_count(views_match.group(1))

    if og_desc:
        caption_part = re.split(r"\s+-\s+", og_desc, maxsplit=1)
        if len(caption_part) == 2 and likes_match:
            meta["caption"] = caption_part[1].strip()
        elif not likes_match:
            meta["caption"] = og_desc

    # کپشن داخل embed captioned
    if not meta["caption"]:
        caption_block = re.search(
            r"<div[^>]+class=\"Caption\"[^>]*>(.*?)</div>", text, flags=re.I | re.S,
        )
        if caption_block:
            cleaned = re.sub(r"<[^>]+>", "", caption_block.group(1))
            cleaned = html_lib.unescape(cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            meta["caption"] = cleaned

    user_match = (
        re.search(r"class=\"CaptionUsername\"[^>]*>([^<]+)<", text, flags=re.I)
        or re.search(r"\"username\"\s*:\s*\"([A-Za-z0-9._]{1,30})\"", text)
        or re.search(r"<meta[^>]+(?:property|name)=[\"']og:title[\"'][^>]+content=[\"']@?([A-Za-z0-9._]{1,30})\s+on", text, flags=re.I)
    )
    if user_match:
        meta["username"] = user_match.group(1).strip().lstrip("@")
    return meta


async def fetch_instagram_metadata(session: aiohttp.ClientSession, url: str) -> dict:
    """دریافت متادیتای پست/ریلز اینستاگرام از مسیرهای عمومی؛ در صورت شکست dict خالی برمی‌گرداند."""
    safe_url = normalize_instagram_url(url)
    base = safe_url.rstrip("/")
    # شورت‌کد برای imginn
    shortcode = ""
    short_match = re.search(r"/(?:p|reel|tv|stories)/([A-Za-z0-9_-]+)", safe_url)
    if short_match:
        shortcode = short_match.group(1)
    candidates = list(dict.fromkeys([
        f"{base}/embed/captioned/",
        f"{base}/embed/",
        f"{base}/?__a=1&__d=dis",
        safe_url,
        *([f"https://imginn.com/p/{shortcode}/", f"https://imginn.com/{shortcode}/"] if shortcode else []),
    ]))
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Referer": "https://www.instagram.com/",
    }
    best: dict = {}
    for candidate in candidates:
        try:
            async with session.get(candidate, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status != 200:
                    continue
                body = await response.text(errors="ignore")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            continue
        parsed = extract_instagram_post_metadata(body)
        # برای imginn فیلدهای icon-likes/icon-comments را جدا استخراج می‌کنیم
        if "imginn.com" in candidate and shortcode:
            likes_m = re.search(r'icon-likes"></i>\s*<span>([\d][\d,.]*[KkMm]?)</span>', body)
            comments_m = re.search(r'icon-comments"></i>\s*<span>([\d][\d,.]*[KkMm]?)</span>', body)
            if likes_m:
                parsed["likes"] = _clean_instagram_count(likes_m.group(1))
            if comments_m:
                parsed["comments"] = _clean_instagram_count(comments_m.group(1))
            if not parsed.get("caption"):
                desc_m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', body, flags=re.I)
                if desc_m:
                    parsed["caption"] = html_lib.unescape(desc_m.group(1))[:300]
            # views از imginn فقط اگر الگوی مشخص view-count باشد (در غیر این صورت حذف)
            views_m = re.search(r'class="view-count"[^>]*>\s*([\d][\d,.]*[KkMm]?)', body)
            if views_m:
                parsed["views"] = _clean_instagram_count(views_m.group(1))
            elif parsed.get("views") and not re.match(r"^[\d][\d,.]*[KkMm]?$", str(parsed.get("views"))):
                parsed.pop("views", None)
        score = sum(1 for key in ("caption", "likes", "comments", "views", "username") if parsed.get(key))
        best_score = sum(1 for key in ("caption", "likes", "comments", "views", "username") if best.get(key))
        if score > best_score:
            best = parsed
        if best.get("caption") and best.get("likes"):
            break
    return best


# میزبان‌های CDN عمومی مجاز برای عکس پروفایل اینستاگرام (جلوگیری از SSRF از طریق og:image جعلی)
INSTAGRAM_CDN_HOST_SUFFIXES = (
    ".cdninstagram.com", ".fbcdn.net", ".fbsbx.com", ".instagram.com",
)


def extract_instagram_profile_image_url(body: str) -> str:
    """URL عکس پروفایل را از og:image/meta صفحهٔ عمومی استخراج می‌کند."""
    text = html_lib.unescape(str(body or ""))
    patterns = [
        r"<meta[^>]+(?:property|name)=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)",
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name)=[\"']og:image[\"']",
        # imginn: کلاس avatar
        r"<img[^>]+class=\"[^\"]*avatar[^\"]*\"[^>]+src=\"([^\"]+)\"",
        r"<img[^>]+src=\"([^\"]+)\"[^>]+class=\"[^\"]*avatar[^\"]*\"",
        # imginn: اولین تصویر CDN اینستاگرام
        r"https://scontent[^\"\s\\']+?\.(?:jpg|webp|png)(?:\?[^\"\s\\']*)?",
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.I):
            candidate = html_lib.unescape(str(raw)).replace("\\/", "/").replace("\\u0026", "&")
            if not candidate.lower().startswith("https://"):
                continue
            host = (urlparse(candidate).hostname or "").lower()
            if host and any(host == suffix[1:] or host.endswith(suffix) for suffix in INSTAGRAM_CDN_HOST_SUFFIXES):
                return candidate
    return ""


async def download_instagram_profile(
    session: aiohttp.ClientSession,
    url: str,
    output_dir: str,
    max_bytes: int = 25 * 1024 * 1024,
) -> tuple[str, list["DownloadedMedia"]]:
    """دانلود عکس پروفایل اینستاگرام از مسیر کاملاً عمومی (og:image) — بدون کوکی یا ورود."""
    safe_url = str(url or "").strip()
    if not is_instagram_profile_url(safe_url):
        raise MediaServiceError("invalid_url", "این لینک پروفایل عمومی اینستاگرام نیست.")
    username = instagram_username_from_url(safe_url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Referer": "https://www.instagram.com/",
    }
    image_url = ""
    page_candidates = list(dict.fromkeys([
        f"https://www.instagram.com/{username}/",
        f"https://m.instagram.com/{username}/",
        f"https://imginn.com/{username}/",
    ]))
    for page in page_candidates:
        try:
            async with session.get(page, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as response:
                if response.status != 200:
                    continue
                body = await response.text(errors="ignore")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            continue
        image_url = extract_instagram_profile_image_url(body)
        if image_url:
            break
    if not image_url:
        raise MediaServiceError(
            "private_or_restricted",
            "عکس پروفایل این کاربر از مسیر عمومی قابل دریافت نیست؛ احتمالاً پیج خصوصی است یا اینستاگرام صفحه را بدون ورود نشان نمی‌دهد.",
        )
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    output_path = folder / f"instagram_profile_{safe_filename(username, 'profile')}.jpg"
    downloaded = 0
    try:
        async with session.get(image_url, headers={"User-Agent": headers["User-Agent"], "Referer": "https://www.instagram.com/"}, timeout=aiohttp.ClientTimeout(total=60)) as response:
            if response.status != 200:
                raise MediaServiceError("download_failed", "CDN اینستاگرام عکس پروفایل را نفرستاد.")
            with open(output_path, "wb") as handle:
                async for chunk in response.content.iter_chunked(256 * 1024):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise MediaServiceError("too_large_or_empty", "عکس پروفایل غیرعادی بزرگ است.")
                    handle.write(chunk)
    except aiohttp.ClientError as exc:
        raise MediaServiceError("download_failed", "دریافت عکس پروفایل از CDN اینستاگرام ناموفق بود.") from exc
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise MediaServiceError("too_large_or_empty", "عکس پروفایل خالی دریافت شد.")
    size = output_path.stat().st_size
    title = f"پروفایل اینستاگرام @{username}"
    item = DownloadedMedia(
        path=str(output_path),
        filename=output_path.name,
        mime_type="image/jpeg",
        size=size,
        title=title,
        kind="photo",
        caption="",
        description=f"instagram_profile:{username}",
    )
    return title, [item]


async def _download_instagram_public_fallback(
    session: aiohttp.ClientSession,
    url: str,
    output_dir: str,
    max_bytes: int,
    progress_callback=None,
) -> tuple[str, list[DownloadedMedia]]:
    """آخرین fallback عمومی Instagram: embed/og:video و CDN عمومی."""
    safe_url = normalize_instagram_url(url)
    if not is_instagram_public_url(safe_url):
        raise MediaServiceError("invalid_url", "این لینک Instagram عمومی و قابل شناسایی نیست.")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Referer": "https://www.instagram.com/",
    }
    media_urls: list[str] = []
    for candidate in _instagram_embed_candidates(safe_url):
        try:
            async with session.get(candidate, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    continue
                body = await response.text(errors="ignore")
                media_urls.extend(extract_instagram_public_media_urls(body))
                if media_urls:
                    break
        except (aiohttp.ClientError, asyncio.TimeoutError):
            continue
    unique_urls = list(dict.fromkeys(media_urls))
    if not unique_urls:
        raise MediaServiceError(
            "private_or_restricted",
            "Instagram برای این Reel از مسیرهای عمومی URL ویدئو ارائه نکرد؛ محتوا احتمالاً خصوصی، سنی/منطقه‌ای محدود یا فقط برای کاربران واردشده است.",
        )
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    shortcode = safe_url.rstrip("/").split("/")[-1] or "reel"
    output_path = folder / f"instagram_{safe_filename(shortcode, 'reel')}.mp4"
    for media_url in unique_urls:
        try:
            await validate_public_url(media_url, allow_generic=True)
            if looks_like_hls_url(media_url):
                item = await download_hls_ffmpeg(session, media_url, output_dir, max_bytes, progress_callback)
                return "Instagram public reel", [item]
            async with session.get(
                media_url,
                headers={"User-Agent": headers["User-Agent"], "Referer": safe_url},
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as response:
                if response.status != 200:
                    continue
                await validate_public_url(str(response.url), allow_generic=True)
                content_type = response.headers.get("Content-Type", "video/mp4").split(";", 1)[0].lower()
                length = int(response.headers.get("Content-Length", "0") or 0)
                if length > max_bytes:
                    continue
                first = await response.content.read(65536)
                if looks_like_html(first):
                    continue
                received = len(first)
                if received < 128:
                    continue
                if progress_callback:
                    await progress_callback(10, received, length)
                with output_path.open("wb") as output:
                    output.write(first)
                    async for chunk in response.content.iter_chunked(512 * 1024):
                        received += len(chunk)
                        if received > max_bytes:
                            raise MediaServiceError("too_large", f"حجم ویدئو بیشتر از {media_size_label()} است.")
                        output.write(chunk)
                        if progress_callback and length:
                            await progress_callback(min(99, int(received * 100 // length)), received, length)
                if received <= 0:
                    output_path.unlink(missing_ok=True)
                    continue
                if progress_callback:
                    await progress_callback(100, received, length or received)
                return "Instagram public reel", [DownloadedMedia(
                    path=str(output_path),
                    filename=output_path.name,
                    mime_type=content_type if content_type.startswith("video/") else "video/mp4",
                    size=received,
                    title="Instagram public reel",
                    kind="video",
                )]
        except MediaServiceError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            output_path.unlink(missing_ok=True)
            continue
    raise MediaServiceError("platform_blocked", "CDN عمومی Instagram قابل دریافت نبود.")


def _extract_managed_instagram_urls(payload: Any) -> list[str]:
    """استخراج لینک‌های media/download از پاسخ Provider بدون اعتماد به کلید ثابت."""
    media_keys = {
        "video_url", "videourl", "video_download_url", "videodownloadurl",
        "download_url", "downloadurl", "media_url", "mediaurl", "direct_url",
        "directurl", "url", "src",
    }
    found: list[str] = []

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                walk(child_value, str(child_key).lower().replace("-", "").replace("_", ""))
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str) and value.startswith(("http://", "https://")):
            if key in media_keys and not is_instagram_public_url(value) and value not in found:
                found.append(value)

    walk(payload)
    return found[:20]


async def _download_managed_instagram_media(
    session: aiohttp.ClientSession,
    media_url: str,
    source_url: str,
    output_dir: str,
    max_bytes: int,
    progress_callback=None,
) -> tuple[str, list[DownloadedMedia]]:
    await validate_public_url(media_url, allow_generic=True)
    if looks_like_hls_url(media_url):
        item = await download_hls_ffmpeg(session, media_url, output_dir, max_bytes, progress_callback)
        return "Instagram managed public reel", [item]
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    shortcode = source_url.rstrip("/").split("/")[-1] or "reel"
    output_path = folder / f"instagram_managed_{safe_filename(shortcode, 'reel')}.mp4"
    try:
        async with session.get(
            media_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": source_url},
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as response:
            if response.status != 200:
                raise MediaServiceError("provider_media", f"Provider media URL با HTTP {response.status} پاسخ داد.")
            await validate_public_url(str(response.url), allow_generic=True)
            content_type = response.headers.get("Content-Type", "video/mp4").split(";", 1)[0].lower()
            length = int(response.headers.get("Content-Length", "0") or 0)
            if length > max_bytes:
                raise MediaServiceError("too_large", f"حجم ویدئو بیشتر از {media_size_label()} است.")
            first = await response.content.read(65536)
            if looks_like_html(first):
                raise MediaServiceError("provider_media", "Provider به‌جای فایل، صفحهٔ HTML برگرداند.")
            received = len(first)
            with output_path.open("wb") as output:
                output.write(first)
                async for chunk in response.content.iter_chunked(512 * 1024):
                    received += len(chunk)
                    if received > max_bytes:
                        raise MediaServiceError("too_large", f"حجم ویدئو بیشتر از {media_size_label()} است.")
                    output.write(chunk)
                    if progress_callback and length:
                        await progress_callback(min(99, int(received * 100 // length)), received, length)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        output_path.unlink(missing_ok=True)
        raise MediaServiceError("provider_media", "دریافت فایل از Provider ناموفق بود.") from exc
    if received <= 0:
        output_path.unlink(missing_ok=True)
        raise MediaServiceError("provider_media", "Provider فایل ویدئو برنگرداند.")
    if progress_callback:
        await progress_callback(100, received, length or received)
    return "Instagram managed public reel", [DownloadedMedia(
        path=str(output_path), filename=output_path.name,
        mime_type=content_type if content_type.startswith("video/") else "video/mp4",
        size=received, title="Instagram managed public reel", kind="video",
    )]


def instagram_provider_order() -> list[str]:
    """فهرست Providerهای قابل استفاده را بدون لو دادن کلیدها برمی‌گرداند."""
    order = []
    if INSTAGRAM_HIKER_TOKEN:
        order.append("hiker")
    if INSTAGRAM_APIFY_TOKEN:
        order.append("apify")
    if INSTAGRAM_RESOLVER_API_URL and INSTAGRAM_RESOLVER_API_KEY:
        order.append("custom")
    return order


async def _managed_instagram_provider(
    session: aiohttp.ClientSession,
    source_url: str,
    output_dir: str,
    max_bytes: int,
    progress_callback=None,
    provider: str | None = None,
) -> tuple[str, list[DownloadedMedia]]:
    """اجرای یک Provider مدیریت‌شده؛ بدون API key هرگز فعال نمی‌شود."""
    provider = (provider or INSTAGRAM_MANAGED_PROVIDER).lower()
    if provider == "hiker":
        if not INSTAGRAM_HIKER_TOKEN:
            raise MediaServiceError("provider_unconfigured", "HikerAPI provider is not configured.")
        shortcode = source_url.rstrip("/").split("/")[-1]
        endpoint = "https://api.hikerapi.com/v1/media/by/code"
        try:
            async with session.get(
                endpoint,
                params={"code": shortcode},
                headers={"x-access-key": INSTAGRAM_HIKER_TOKEN, "accept": "application/json", "User-Agent": "AjorparehBot/1.0"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status in {401, 403}:
                    raise MediaServiceError("provider_auth", "HikerAPI authentication failed.")
                if response.status == 404:
                    raise MediaServiceError("private_or_restricted", "HikerAPI این مدیا را عمومی پیدا نکرد.")
                if response.status >= 400:
                    raise MediaServiceError("provider_http", f"HikerAPI HTTP {response.status}.")
                data = await response.json(content_type=None)
        except MediaServiceError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise MediaServiceError("provider_network", "HikerAPI در دسترس نیست.") from exc
    elif provider == "apify":
        if not INSTAGRAM_APIFY_TOKEN:
            raise MediaServiceError("provider_unconfigured", "Instagram managed provider is not configured.")
        endpoint = (
            f"https://api.apify.com/v2/acts/{INSTAGRAM_APIFY_ACTOR}/runs"
            f"?token={INSTAGRAM_APIFY_TOKEN}"
        )
        payload = {
            "directUrls": [source_url],
            "resultsLimit": 1,
            "proxyConfiguration": {"useApifyProxy": True},
        }
        headers = {"User-Agent": "AjorparehBot/1.0", "Content-Type": "application/json"}
        try:
            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status in {401, 403}:
                    raise MediaServiceError("provider_auth", "Instagram managed provider authentication failed.")
                if response.status >= 400:
                    raise MediaServiceError("provider_http", f"Instagram managed provider HTTP {response.status}.")
                run = await response.json(content_type=None)
            run_data = run.get("data") if isinstance(run, dict) else None
            run_id = str((run_data or {}).get("id") or "")
            dataset_id = str((run_data or {}).get("defaultDatasetId") or "")
            if not run_id or not dataset_id:
                raise MediaServiceError("provider_run", "Instagram managed provider returned no run ID.")
            status = str((run_data or {}).get("status") or "READY")
            for _ in range(90):
                if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                    break
                await asyncio.sleep(2)
                status_endpoint = f"https://api.apify.com/v2/actor-runs/{run_id}?token={INSTAGRAM_APIFY_TOKEN}"
                async with session.get(status_endpoint, headers={"User-Agent": "AjorparehBot/1.0"}, timeout=aiohttp.ClientTimeout(total=30)) as status_response:
                    if status_response.status in {401, 403}:
                        raise MediaServiceError("provider_auth", "Instagram managed provider authentication failed.")
                    if status_response.status >= 400:
                        raise MediaServiceError("provider_http", f"Instagram managed provider HTTP {status_response.status}.")
                    status_payload = await status_response.json(content_type=None)
                    status = str((status_payload.get("data") or {}).get("status") or status)
            if status != "SUCCEEDED":
                raise MediaServiceError("provider_run", f"Instagram managed provider run ended with {status}.")
            dataset_endpoint = (
                f"https://api.apify.com/v2/datasets/{dataset_id}/items"
                f"?token={INSTAGRAM_APIFY_TOKEN}&clean=true&format=json"
            )
            async with session.get(dataset_endpoint, headers={"User-Agent": "AjorparehBot/1.0"}, timeout=aiohttp.ClientTimeout(total=60)) as dataset_response:
                if dataset_response.status in {401, 403}:
                    raise MediaServiceError("provider_auth", "Instagram managed provider dataset access was denied.")
                if dataset_response.status >= 400:
                    raise MediaServiceError("provider_http", f"Instagram managed provider dataset HTTP {dataset_response.status}.")
                data = await dataset_response.json(content_type=None)
        except MediaServiceError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise MediaServiceError("provider_network", "Instagram managed provider is unavailable.") from exc
    else:
        if not INSTAGRAM_RESOLVER_API_URL or not INSTAGRAM_RESOLVER_API_KEY:
            raise MediaServiceError("provider_unconfigured", "Instagram managed provider is not configured.")
        payload = {"url": source_url, "format": "mp4"}
        headers = {
            "User-Agent": "AjorparehBot/1.0",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {INSTAGRAM_RESOLVER_API_KEY}",
        }
        try:
            async with session.post(INSTAGRAM_RESOLVER_API_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as response:
                if response.status in {401, 403}:
                    raise MediaServiceError("provider_auth", "Instagram managed provider authentication failed.")
                if response.status >= 400:
                    raise MediaServiceError("provider_http", f"Instagram managed provider HTTP {response.status}.")
                data = await response.json(content_type=None)
        except MediaServiceError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise MediaServiceError("provider_network", "Instagram managed provider is unavailable.") from exc
    urls = _extract_managed_instagram_urls(data)
    if not urls:
        payload_text = json.dumps(data, ensure_ascii=False).lower() if isinstance(data, (dict, list)) else ""
        if "restricted" in payload_text or "login" in payload_text or "private" in payload_text:
            raise MediaServiceError("private_or_restricted", "Managed Instagram provider also reported restricted or login-only media.")
        raise MediaServiceError("provider_no_media", "Instagram managed provider returned no public media URL.")
    last_error: MediaServiceError | None = None
    for media_url in urls:
        try:
            return await _download_managed_instagram_media(
                session, media_url, source_url, output_dir, max_bytes, progress_callback
            )
        except MediaServiceError as exc:
            last_error = exc
    raise last_error or MediaServiceError("provider_media", "Instagram managed provider media download failed.")


async def download_social_media(url: str, output_dir: str, max_bytes: int = MAX_MEDIA_BYTES, progress_callback=None) -> tuple[str, list[DownloadedMedia]]:
    # allow_generic: هر دامنهٔ عمومی که ویدئو داشته باشد تلاش می‌شود (نه فقط شبکه‌های معروف)
    safe_url = normalize_instagram_url(normalize_youtube_url(await validate_public_url(url, social_only=True, allow_generic=True)))
    # عکس پروفایل اینستاگرام مسیر اختصاصی خودش را دارد (og:image عمومی؛ بدون ورود به موتور ویدئو)
    if is_instagram_profile_url(safe_url):
        profile_session = aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar(),
            timeout=aiohttp.ClientTimeout(total=90),
        )
        try:
            return await download_instagram_profile(profile_session, safe_url, output_dir, min(max_bytes, 25 * 1024 * 1024))
        finally:
            await profile_session.close()
    try:
        return await asyncio.to_thread(_social_download_sync, safe_url, output_dir, max_bytes, progress_callback)
    except MediaServiceError as exc:
        if is_instagram_public_url(safe_url):
            fallback_session = aiohttp.ClientSession(
                cookie_jar=aiohttp.DummyCookieJar(),
                timeout=aiohttp.ClientTimeout(total=45),
            )
            try:
                # این مسیر فقط embed عمومی/CDN عمومی است؛ هیچ کوکی یا احراز هویتی استفاده نمی‌کند.
                return await _download_instagram_public_fallback(
                    fallback_session,
                    safe_url,
                    output_dir,
                    max_bytes,
                    progress_callback,
                )
            except MediaServiceError as fallback_exc:
                public_error = fallback_exc if fallback_exc.reason == "private_or_restricted" else exc
                provider_errors = []
                for provider_name in instagram_provider_order():
                    try:
                        return await _managed_instagram_provider(
                            fallback_session,
                            safe_url,
                            output_dir,
                            max_bytes,
                            progress_callback,
                            provider=provider_name,
                        )
                    except MediaServiceError as provider_exc:
                        provider_errors.append(f"{provider_name}:{provider_exc.reason}")
                        log.warning("managed Instagram provider %s failed: %s", provider_name, provider_exc.message)
                if provider_errors:
                    log.warning("all managed Instagram providers failed: %s", ",".join(provider_errors))
                raise public_error from None
            finally:
                await fallback_session.close()
        raise


def filename_from_headers(url: str, headers: aiohttp.typedefs.LooseHeaders) -> str:
    disposition = str(headers.get("Content-Disposition", ""))
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, flags=re.I)
    if match:
        return safe_filename(match.group(1))
    return safe_filename(urlparse(url).path, "ajorpareh-upload")


async def _validate_hls_manifest(session: aiohttp.ClientSession, url: str) -> None:
    """پلی‌لیست HLS را برای جلوگیری از ریدایرکت به مقصد خصوصی بررسی می‌کند."""
    try:
        async with session.get(
            url,
            allow_redirects=False,
            headers={"User-Agent": "Ajorpareh-HLS/1.0", "Accept": "application/vnd.apple.mpegurl,*/*"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status != 200:
                raise MediaServiceError("hls_manifest", f"مانیفست HLS با خطای HTTP {response.status} پاسخ داد.")
            content_type = response.headers.get("Content-Type", "")
            body = await response.content.read(2 * 1024 * 1024)
    except MediaServiceError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise MediaServiceError("hls_manifest", "دریافت مانیفست m3u8 ناموفق بود.") from exc
    if not looks_like_hls_manifest(body, content_type):
        raise MediaServiceError("not_a_file", "این لینک مانیفست معتبر m3u8 نیست.")
    checked_hosts: set[str] = set()
    for raw_line in body.decode("utf-8", errors="ignore").splitlines():
        line = raw_line.strip().strip('"')
        candidates = []
        if line and not line.startswith("#"):
            candidates.append(line)
        candidates.extend(re.findall(r"URI=\"([^\"]+)\"", line, flags=re.I))
        for child in candidates:
            child_url = urljoin(url, child)
            child_host = normalized_host(child_url)
            if child_host and child_host not in checked_hosts:
                await validate_public_url(child_url, allow_generic=True)
                checked_hosts.add(child_host)
                if len(checked_hosts) >= 32:
                    break
        if len(checked_hosts) >= 32:
            break


def _ffmpeg_hls_sync(url: str, output_path: str, max_bytes: int) -> None:
    if shutil.which("ffmpeg") is None:
        raise MediaServiceError("unavailable", "ffmpeg روی سرور نصب نیست.")
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}/"
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
        "-headers", f"User-Agent: Mozilla/5.0\r\nReferer: {origin}\r\n",
        "-i", url,
        "-map", "0:v:0?", "-map", "0:a:0?",
        "-c", "copy", "-movflags", "+faststart", "-fs", str(max_bytes),
        output_path,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise MediaServiceError("timeout", "دریافت مانیفست ویدئو طول کشید؛ دوباره تلاش کن.") from exc
    except OSError as exc:
        raise MediaServiceError("unavailable", "اجرای ffmpeg روی سرور ممکن نیست.") from exc
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[-500:]
        raise MediaServiceError("hls_download_failed", f"دریافت m3u8 با ffmpeg ناموفق بود. {detail}")
    if not Path(output_path).is_file() or Path(output_path).stat().st_size <= 0:
        raise MediaServiceError("hls_download_failed", "ffmpeg فایل خروجی معتبری نساخت.")


async def download_hls_ffmpeg(
    session: aiohttp.ClientSession,
    url: str,
    output_dir: str,
    max_bytes: int = MAX_MEDIA_BYTES,
    progress_callback=None,
) -> DownloadedMedia:
    """آخرین fallback لینک مستقیم: دریافت m3u8/m3u با ffmpeg و خروجی MP4."""
    await _validate_hls_manifest(session, url)
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stem = safe_filename(Path(urlparse(url).path).stem or "hls-stream", "hls-stream")
    output_path = folder / f"{Path(stem).stem[:70]}.mp4"
    if progress_callback:
        await progress_callback(10, 0, 0)
    await asyncio.to_thread(_ffmpeg_hls_sync, url, str(output_path), max_bytes)
    size = output_path.stat().st_size
    if size > max_bytes:
        output_path.unlink(missing_ok=True)
        raise MediaServiceError("too_large", f"حجم خروجی m3u8 بیشتر از {media_size_label()} است.")
    if progress_callback:
        await progress_callback(100, size, size)
    return DownloadedMedia(
        path=str(output_path), filename=output_path.name, mime_type="video/mp4",
        size=size, title=output_path.stem, kind="video",
    )


async def download_direct_file(
    session: aiohttp.ClientSession,
    url: str,
    output_dir: str,
    max_bytes: int = MAX_MEDIA_BYTES,
    progress_callback=None,
) -> DownloadedMedia:
    """دانلود فایل مستقیم. اگر progress_callback داده شود، به‌صورت
    `await progress_callback(percent: int, received: int, total: int)`
    بعد از هر chunk صدا زده می‌شود (total می‌تواند ۰ باشد = نامشخص)."""
    current = await validate_public_url(url)
    folder = Path(output_dir)
    for _ in range(5):
        await validate_public_url(current)
        try:
            response = await session.get(
                current,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=120, connect=12, sock_read=35),
                headers={"User-Agent": "Ajorpareh-URL-Uploader/1.0", "Accept": "*/*"},
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise MediaServiceError("network", "اتصال به لینک فایل ناموفق بود.") from exc
        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.release()
            if not location:
                raise MediaServiceError("redirect", "مسیر انتقال لینک نامعتبر است.")
            current = urljoin(current, location)
            continue
        if response.status != 200:
            response.release()
            raise MediaServiceError("http_error", f"سرور فایل با خطای HTTP {response.status} پاسخ داد.")
        content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].lower()
        initial_bytes = await response.content.read(65536)
        if looks_like_hls_url(current) or looks_like_hls_manifest(initial_bytes, content_type):
            response.release()
            return await download_hls_ffmpeg(
                session, current, output_dir, max_bytes, progress_callback
            )
        filename = filename_from_headers(current, response.headers)
        if content_type == "text/html":
            response.release()
            raise MediaServiceError("not_a_file", "این آدرس صفحه وب است، نه لینک مستقیم فایل یا فیلم.")
        length = int(response.headers.get("Content-Length", "0") or 0)
        if length > max_bytes:
            response.release()
            raise MediaServiceError("too_large", f"حجم فایل بیشتر از {media_size_label()} است.")
        if not Path(filename).suffix:
            extension = MIME_EXTENSION_FALLBACK.get(content_type) or mimetypes.guess_extension(content_type) or ".bin"
            filename += extension
        path = folder / filename
        received = 0
        try:
            # بایت‌های اول از قبل برای تشخیص HLS خوانده شده‌اند.
            first = initial_bytes
            if looks_like_html(first):
                raise MediaServiceError("not_a_file", "این آدرس صفحه وب است، نه لینک مستقیم فایل یا فیلم.")
            received += len(first)
            if received > max_bytes:
                raise MediaServiceError("too_large", f"حجم فایل بیشتر از {media_size_label()} است.")
            if progress_callback is not None:
                await progress_callback(int(received * 100 // length) if length else 0, received, length)
            with path.open("wb") as output:
                output.write(first)
                async for chunk in response.content.iter_chunked(512 * 1024):
                    received += len(chunk)
                    if received > max_bytes:
                        raise MediaServiceError("too_large", f"حجم فایل بیشتر از {media_size_label()} است.")
                    output.write(chunk)
                    if progress_callback is not None:
                        await progress_callback(int(received * 100 // length) if length else 0, received, length)
        finally:
            response.release()
        return DownloadedMedia(
            path=str(path), filename=filename, mime_type=content_type,
            size=received, title=filename, kind=infer_kind(path, content_type),
        )
    raise MediaServiceError("redirect_loop", "تعداد انتقال‌های لینک بیش از حد بود.")


async def inspect_link(url: str) -> dict[str, Any]:
    value = str(url or "").strip()
    host = normalized_host(value)
    if not host:
        raise MediaServiceError("invalid_url", "لینک معتبر نیست.")
    addresses = await resolve_public_host(host)
    parsed = urlparse(value)
    decoded = unquote(value).lower()
    score = 0
    signals: list[str] = []
    if parsed.scheme.lower() != "https":
        score += 25
        signals.append("ارتباط HTTPS ندارد")
    if host in SHORTENER_DOMAINS:
        score += 20
        signals.append("لینک کوتاه‌شده است و مقصد را پنهان می‌کند")
    if host.startswith("xn--") or ".xn--" in host:
        score += 20
        signals.append("دامنه بین‌المللی/Punycode است؛ املای آن را بررسی کن")
    suspicious = sorted(term for term in SUSPICIOUS_TERMS if term in decoded)
    if suspicious:
        score += min(30, len(suspicious) * 8)
        signals.append("واژه‌های حساس در لینک: " + "، ".join(suspicious[:4]))
    labels = host.split(".")
    if len(labels) > 4:
        score += 10
        signals.append("زیر‌دامنه‌های غیرعادی زیادی دارد")
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        score += 25
        signals.append("به‌جای دامنه از IP مستقیم استفاده شده")
    score = min(score, 100)
    level = "بالا" if score >= 55 else "متوسط" if score >= 25 else "کم"
    return {
        "url": value,
        "host": host,
        "scheme": parsed.scheme.lower(),
        "addresses": addresses,
        "risk_score": score,
        "risk_level": level,
        "signals": signals or ["نشانه واضحی از جعل در ساختار لینک دیده نشد"],
        "social_supported": is_social_url(value) or looks_like_direct_media_url(value),
    }
