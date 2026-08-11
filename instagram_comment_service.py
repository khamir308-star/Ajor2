"""Public Instagram comment-link extraction helpers.

The bot intentionally reads public comments only.  It never accepts Instagram
cookies, passwords, session IDs, or private-account credentials.  Instagram's
public web response is obtained through the already-pinned yt-dlp extractor;
that keeps the transport and anti-bot handling in one maintained dependency.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse

try:  # yt-dlp is a production dependency, but keep imports test-friendly.
    import yt_dlp
    from yt_dlp.extractor.instagram import _id_to_pk
    from yt_dlp.networking.impersonate import ImpersonateTarget
except ImportError:  # pragma: no cover - deployment installs yt-dlp
    yt_dlp = None
    _id_to_pk = None
    ImpersonateTarget = None

try:  # Installed through yt-dlp[curl-cffi]; keep a safe fallback for tests.
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - deployment installs the extra
    curl_requests = None


INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
INSTAGRAM_POST_TYPES = {"p", "reel", "reels", "tv"}
_COMMENT_ID_RE = re.compile(r"^\d{8,30}(?:_\d{8,30})?$")
_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,120}$")
_TRAILING_URL_PUNCTUATION = "\u200c\u200d.,!?;:)]}>،؛؟"
COMMENT_GRAPHQL_URL = "https://www.instagram.com/graphql/query/"
COMMENT_GRAPHQL_DOC_ID = "6974885689225067"
COMMENT_GRAPHQL_CONNECTION = "xdt_api__v1__media__media_id__comments__connection"
COMMENT_GRAPHQL_MAX_PAGES = 40  # 40 × the public 15-comment pages ≈ 600 comments


class InstagramCommentError(Exception):
    """A safe, user-facing error while reading a public comment."""

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class InstagramCommentLink:
    """The useful parts of a copied Instagram comment permalink."""

    original_url: str
    post_url: str
    shortcode: str
    comment_id: str
    is_reply: bool = False


@dataclass(frozen=True, slots=True)
class InstagramComment:
    """A public comment returned by Instagram/yt-dlp."""

    comment_id: str
    text: str
    author: str
    post_url: str
    source_url: str


def _strip_url_noise(value: str) -> str:
    value = str(value or "").strip()
    # Telegram users sometimes paste a URL followed by a Persian full stop or
    # a closing parenthesis.  Do not remove URL-significant query characters.
    return value.rstrip(_TRAILING_URL_PUNCTUATION)


def normalize_comment_id(value: Any) -> str:
    """Return a canonical numeric Instagram comment id, or ``""``."""

    raw = unquote(str(value or "")).strip()
    raw = raw.removeprefix("comment:").removeprefix("comment_")
    return raw if _COMMENT_ID_RE.fullmatch(raw) else ""


def _query_value(query: dict[str, list[str]], *names: str) -> tuple[str, bool]:
    for name in names:
        for value in query.get(name, []):
            comment_id = normalize_comment_id(value)
            if comment_id:
                return comment_id, True
    return "", False


def parse_instagram_comment_url(url: str) -> InstagramCommentLink:
    """Parse a post/reel comment permalink.

    Supported public formats include Instagram's ``/c/<id>/`` path and the
    ``?comment_id=<id>``/``?reply_comment_id=<id>`` query format used by the
    Instagram share sheet.
    """

    original = _strip_url_noise(url)
    try:
        parsed = urlparse(original)
    except ValueError as exc:
        raise InstagramCommentError(
            "invalid_url", "لینک کامنت قابل شناسایی نیست."
        ) from exc
    host = (parsed.hostname or "").lower().strip(".")
    if parsed.scheme.lower() not in {"http", "https"} or host not in INSTAGRAM_HOSTS:
        raise InstagramCommentError(
            "invalid_host", "این لینک، لینک معتبر اینستاگرام نیست."
        )

    segments = [unquote(part) for part in parsed.path.split("/") if part]
    post_index = next(
        (
            index
            for index, segment in enumerate(segments[:-1])
            if segment.lower() in INSTAGRAM_POST_TYPES
        ),
        None,
    )
    if post_index is None:
        raise InstagramCommentError(
            "not_comment_url",
            "لینک باید مربوط به خودِ کامنت باشد؛ مثل لینک‌های پست/.../c/... "
            "یا لینک دارای comment_id.",
        )
    shortcode = segments[post_index + 1]
    if not _SHORTCODE_RE.fullmatch(shortcode):
        raise InstagramCommentError(
            "invalid_post", "شناسه پست اینستاگرام در لینک معتبر نیست."
        )

    query = {}
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query.setdefault(key, []).append(value)

    # A reply permalink commonly carries both values.  The reply id is the
    # text the user actually selected, so it must win over its parent id.
    comment_id, is_reply = _query_value(
        query,
        "reply_comment_id",
        "replyCommentId",
        "reply_comment",
        "reply_id",
    )
    if not comment_id:
        comment_id, _ = _query_value(query, "comment_id", "commentId", "comment", "cid")

    if not comment_id:
        for index in range(post_index + 2, len(segments) - 1):
            if segments[index].lower() in {"c", "comment", "comments"}:
                comment_id = normalize_comment_id(segments[index + 1])
                is_reply = False
                break
    if not comment_id:
        # A few older share links put the id directly after /c/ without a
        # stable marker; accepting only a strict numeric id avoids false hits.
        for segment in segments[post_index + 2 :]:
            comment_id = normalize_comment_id(segment)
            if comment_id:
                break

    if not comment_id:
        fragment_query = dict(
            parse_qsl(parsed.fragment.lstrip("?"), keep_blank_values=True)
        )
        comment_id = normalize_comment_id(
            fragment_query.get("comment_id")
            or fragment_query.get("reply_comment_id")
            or ""
        )

    if not comment_id:
        raise InstagramCommentError(
            "missing_comment_id",
            "این لینک فقط لینک پست است؛ از منوی اینستاگرام روی همان کامنت بزن و "
            "«Copy link» را انتخاب کن.",
        )

    post_type = segments[post_index].lower()
    post_url = f"https://www.instagram.com/{post_type}/{shortcode}/"
    return InstagramCommentLink(
        original_url=original,
        post_url=post_url,
        shortcode=shortcode,
        comment_id=comment_id,
        is_reply=is_reply,
    )


def is_instagram_comment_url(url: str) -> bool:
    """Whether ``url`` is a valid Instagram comment permalink."""

    try:
        parse_instagram_comment_url(url)
    except InstagramCommentError:
        return False
    return True


def _comment_ids_match(left: str, right: str) -> bool:
    if left == right:
        return True
    # Some old Instagram links represented a compound id as ``media_comment``
    # while the public response exposed only the comment part.
    left_parts, right_parts = set(left.split("_")), set(right.split("_"))
    return (
        len(left_parts) > 1
        and right in left_parts
        or len(right_parts) > 1
        and left in right_parts
    )


def _iter_info_dicts(info: dict[str, Any] | None):
    if not isinstance(info, dict):
        return
    yield info
    entries = info.get("entries")
    if isinstance(entries, (list, tuple)):
        for entry in entries:
            yield from _iter_info_dicts(entry if isinstance(entry, dict) else None)


def _comment_from_mapping(
    raw_comment: Any, link: InstagramCommentLink
) -> InstagramComment | None:
    """Convert either GraphQL or yt-dlp's comment shape to one result."""
    if not isinstance(raw_comment, dict):
        return None
    candidate_id = normalize_comment_id(raw_comment.get("id") or raw_comment.get("pk"))
    if not candidate_id or not _comment_ids_match(candidate_id, link.comment_id):
        return None
    text = str(raw_comment.get("text") or raw_comment.get("comment") or "").strip()
    if not text:
        return None
    user = raw_comment.get("user") or raw_comment.get("owner") or {}
    if not isinstance(user, dict):
        user = {}
    author = str(
        raw_comment.get("author")
        or raw_comment.get("username")
        or user.get("username")
        or "کاربر اینستاگرام"
    ).strip()
    return InstagramComment(
        comment_id=candidate_id,
        text=text[:4000],
        author=author[:120],
        post_url=link.post_url,
        source_url=link.original_url,
    )


def _extract_comment_graphql_sync(
    link: InstagramCommentLink,
) -> InstagramComment | None:
    """Search public comment pages until the linked comment is found.

    yt-dlp intentionally returns only Instagram's first public comment page.
    The web GraphQL comments connection exposes a cursor, so a copied link to
    an older comment can be resolved instead of being incorrectly reported as
    deleted.
    """
    if curl_requests is None or _id_to_pk is None:
        raise InstagramCommentError(
            "graphql_unavailable",
            "موتور جست‌وجوی کامل کامنت روی سرور فعال نیست.",
        )
    try:
        media_id = str(_id_to_pk(link.shortcode))
    except Exception as exc:
        raise InstagramCommentError(
            "graphql_unavailable", "شناسهٔ پست اینستاگرام قابل تبدیل نیست."
        ) from exc

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": link.post_url,
        "User-Agent": (
            "Instagram 273.0.0.16.70 (iPhone15,2; iOS 17_5_1; en_US; en-US; "
            "scale=3.00; 1290x2796; 470085518)"
        ),
    }
    try:
        session = curl_requests.Session(impersonate="chrome136")
    except TypeError:  # pragma: no cover - older curl-cffi releases
        session = curl_requests.Session()

    after: str | None = None
    seen_cursors: set[str] = set()
    try:
        for _page in range(COMMENT_GRAPHQL_MAX_PAGES):
            variables = {
                "after": after,
                "before": None,
                "first": 50,
                "last": None,
                "media_id": media_id,
                "sort_order": "recent",
            }
            payload = {
                "variables": json.dumps(variables, separators=(",", ":")),
                "doc_id": COMMENT_GRAPHQL_DOC_ID,
                "server_timestamps": "true",
            }
            try:
                response = session.post(
                    COMMENT_GRAPHQL_URL,
                    data=payload,
                    headers=headers,
                    timeout=25,
                )
            except Exception as exc:
                raise InstagramCommentError(
                    "graphql_network", "اتصال به بخش کامنت‌های اینستاگرام ناموفق شد."
                ) from exc
            if response.status_code in {401, 403, 429}:
                raise InstagramCommentError(
                    "graphql_blocked",
                    "اینستاگرام فعلاً جست‌وجوی کامنت‌ها را محدود کرده؛ "
                    "چند دقیقه بعد دوباره امتحان کن.",
                )
            if response.status_code != 200:
                raise InstagramCommentError(
                    "graphql_http",
                    f"اینستاگرام با خطای HTTP {response.status_code} پاسخ داد.",
                )
            try:
                body = response.json()
            except Exception as exc:
                raise InstagramCommentError(
                    "graphql_response", "پاسخ کامنت‌های اینستاگرام قابل خواندن نیست."
                ) from exc
            connection = (body.get("data") or {}).get(COMMENT_GRAPHQL_CONNECTION) or {}
            if not connection:
                errors = body.get("errors") or []
                detail = str(errors[0].get("message") if errors else "")
                raise InstagramCommentError(
                    "graphql_response",
                    f"دادهٔ کامنت‌ها دریافت نشد. {detail}".strip(),
                )
            for edge in connection.get("edges") or []:
                result = _comment_from_mapping(edge.get("node"), link)
                if result:
                    return result
            page_info = connection.get("page_info") or {}
            if not page_info.get("has_next_page"):
                break
            cursor = str(page_info.get("end_cursor") or "")
            if not cursor or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            after = cursor
    finally:
        try:
            session.close()
        except Exception:
            pass
    return None


def _extract_comment_sync(link: InstagramCommentLink) -> InstagramComment:
    if yt_dlp is None:
        raise InstagramCommentError(
            "unavailable",
            "موتور دریافت کامنت روی سرور فعال نیست؛ بعداً دوباره امتحان کن.",
        )

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": False,
        "getcomments": True,
        "ignoreerrors": False,
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
        "continuedl": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.7",
            "Referer": link.post_url,
        },
    }
    if ImpersonateTarget is not None:
        options["impersonate"] = ImpersonateTarget(client="chrome")

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(link.post_url, download=False)
    except Exception as exc:
        message = str(exc).lower()
        if any(
            term in message
            for term in (
                "login",
                "private",
                "authentication",
                "registered users",
                "follow this account",
            )
        ):
            raise InstagramCommentError(
                "private_or_restricted",
                "این پست عمومی نیست یا اینستاگرام برای دیدن کامنت‌ها ورود می‌خواهد؛ "
                "فقط کامنت‌های عمومی قابل دریافت‌اند.",
            ) from exc
        if any(
            term in message
            for term in (
                "rate",
                "429",
                "too many requests",
                "blocked",
                "not a bot",
                "empty media",
                "temporarily",
            )
        ):
            raise InstagramCommentError(
                "platform_blocked",
                "اینستاگرام فعلاً درخواست را محدود کرده؛ "
                "چند دقیقه بعد دوباره امتحان کن.",
            ) from exc
        raise InstagramCommentError(
            "fetch_failed",
            "دریافت کامنت ناموفق شد؛ مطمئن شو لینک کامل و مربوط به یک پست عمومی است.",
        ) from exc

    for item in _iter_info_dicts(info):
        for raw_comment in item.get("comments") or []:
            result = _comment_from_mapping(raw_comment, link)
            if result:
                return result

    raise InstagramCommentError(
        "comment_not_found",
        "متن این کامنت در داده عمومی اینستاگرام پیدا نشد؛ شاید کامنت حذف شده، "
        "خصوصی باشد یا لینک قدیمی/ناقص باشد.",
    )


async def _extract_instagram_comment_async(
    link: InstagramCommentLink,
) -> InstagramComment:
    """GraphQL first, with yt-dlp as a compatibility fallback."""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_extract_comment_graphql_sync, link), timeout=45
        )
        if result:
            return result
        raise InstagramCommentError(
            "comment_not_found",
            "متن این کامنت در داده عمومی اینستاگرام پیدا نشد؛ شاید کامنت حذف شده، "
            "خصوصی باشد یا لینک قدیمی/ناقص باشد.",
        )
    except InstagramCommentError as graphql_error:
        if graphql_error.reason == "comment_not_found":
            raise
        # The GraphQL doc id can rotate.  yt-dlp remains a useful fallback for
        # the first public page and older Instagram deployments.
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_extract_comment_sync, link), timeout=20
            )
        except asyncio.TimeoutError as exc:
            raise graphql_error from exc
        except InstagramCommentError:
            raise graphql_error from None
    except asyncio.TimeoutError as exc:
        raise InstagramCommentError(
            "timeout", "اینستاگرام دیر پاسخ داد؛ چند لحظه بعد دوباره امتحان کن."
        ) from exc


async def extract_instagram_comment(url: str) -> InstagramComment:
    """Extract one public comment without blocking the bot event loop."""

    link = parse_instagram_comment_url(url)
    try:
        return await asyncio.wait_for(
            _extract_instagram_comment_async(link), timeout=65
        )
    except asyncio.TimeoutError as exc:
        raise InstagramCommentError(
            "timeout", "اینستاگرام دیر پاسخ داد؛ چند لحظه بعد دوباره امتحان کن."
        ) from exc
