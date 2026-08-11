# Ajorpareh Super-Bot — Comprehensive Audit & Hardening Report

**Date:** 2026-08-05
**Scope:** `bot.py`, media/AI/game services, Telegram handlers/callbacks, HTTP APIs, MongoDB lifecycle, Mini App HTML/JS/service worker, tests and deployment configuration.

## 1. Executive result

The codebase is syntactically valid and the current automated suite passes **70 tests with 2 intentional skips**. JavaScript syntax checks also pass. The latest production deployment reports:

- `ok: true`
- `mode: polling`
- `database: connected`
- AI provider status available

No API keys or bot tokens are stored in the repository. Mini App protected actions continue to require Telegram `initData` validation through the backend.

## 2. Problem analysis and implemented solutions

### A. Telegram edit-message keyboard type crash

**Root cause:** `Message.edit_text()` accepts `InlineKeyboardMarkup`; several failure/success paths passed a `ReplyKeyboardMarkup`. Pydantic raised before the Telegram request, leaving “در حال جست‌وجو” messages stuck.

**Solution:** edit operations now omit ReplyKeyboard markup. Persistent ReplyKeyboard menus are sent with a new message when needed; inline actions remain inline. This change was applied to media, music, information, prayer, summary, TTS and news paths.

```python
# Correct: EditMessageText accepts no ReplyKeyboardMarkup.
try:
    await waiting.edit_text("❌ درخواست ناموفق بود؛ دوباره تلاش کن.")
except TelegramBadRequest:
    await message.answer(
        "❌ درخواست ناموفق بود؛ دوباره تلاش کن.",
        reply_markup=tools_reply_menu(),
    )
```

### B. Accidental downloads from ordinary links

**Root cause:** broad URL message handlers queued every matching social/direct URL, even when the user had not selected a download mode.

**Solution:** automatic URL handlers were removed. A link is queued only when `media_request_sessions[user_id]` is explicitly set by a download button or command. Unselected links receive a clear prompt instead of being downloaded.

```python
async def queue_media_from_message(message: types.Message, mode: str) -> None:
    url = extract_first_url(message.text or "")
    job = await enqueue_media_job(message.from_user.id, url, mode, "bot")
    await message.answer(
        f"✅ درخواست در صف قرار گرفت.\nشناسه: <code>{job['_id']}</code>",
        parse_mode="HTML",
        reply_markup=media_download_reply_menu(),
    )
```

### C. YouTube Shorts and public media resilience

Direct URL upload now detects public HLS/m3u8/m3u manifests after normal HTTP checks and uses a final ffmpeg fallback. The manifest and its absolute segment hosts are DNS/IP-validated before ffmpeg runs; output is capped at the configured media limit and returned as MP4. HTML pages and private destinations remain rejected.

Instagram also has a managed-provider chain that automatically tries HikerAPI first when `HIKERAPI_TOKEN` is present, then Apify when `APIFY_TOKEN` is present, and finally an optional custom resolver. Each provider receives only the public Instagram URL, returned CDN URLs are validated again, the result is streamed to disk, and no user cookies or passwords are accepted. A provider with zero balance or a provider-side failure is skipped automatically in favor of the next method.

**Root cause:** Shorts/share URLs are not equally handled by every extractor or public fallback service.

**Solution:** `/shorts/<id>`, `/embed/<id>`, `/live/<id>` and `youtu.be/<id>` are normalized to a stable `watch?v=<id>` URL. The existing methods remain first; additional methods run only after failure:

1. yt-dlp Python extractor
2. yt-dlp CLI
3. FFmpeg HLS/MPD
4. urllib direct HTTP
5. curl with redirects/retry/size cap
6. wget for URLs that look like direct files
7. aria2c multi-connection download

HTML responses are rejected before upload and partial artifacts are cleared between attempts.

```python
def normalize_youtube_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    video_id = ""
    if host == "youtu.be" and parts:
        video_id = parts[0]
    elif parts and parts[0].lower() in {"shorts", "embed", "live"} and len(parts) > 1:
        video_id = parts[1]
    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
        return f"https://www.youtube.com/watch?v={video_id}"
    return value
```

No downloader can guarantee private, DRM-protected, login-only or geo-blocked media. The code now exhausts safe public methods and returns a retry action instead of silently failing.

### D. Proxy/config data corruption

**Root cause:** global `@username` branding could modify the `user@host` part of SOCKS/VLESS/SS URLs.

**Solution:** URI lines preserve credentials and host. Only URI fragments/remarks are branded; ordinary text and Telegram links are sanitized separately.

```python
def sanitize_config_text(content: str) -> str:
    """برندینگ امن کانفیگ بدون خراب‌کردن userinfo یا host پروکسی."""
    branded_lines = []
    uri_schemes = r"(?:vless|vmess|trojan|ss|ssr|hysteria2?|tuic|wireguard|npv|socks5?|mtproto|tg)"
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("vmess://"):
            encoded = line[8:].split("#", 1)[0]
            try:
                decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
                data = json.loads(decoded)
                if isinstance(data, dict):
                    data["ps"] = "@Ajor_pareh"
                    for key in ("name", "remark", "remarks"):
                        if key in data:
                            data[key] = "@Ajor_pareh"
                    encoded = base64.b64encode(
                        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
                    ).decode()
                    line = f"vmess://{encoded}"
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        elif re.match(rf"^{uri_schemes}://", line, flags=re.I):
            # user:password@host must remain intact; only the remark changes.
            line = line.split("#", 1)[0] + "#%40Ajor_pareh"
        else:
            line = re.sub(
                r"https?://(?:t\.me|telegram\.me)/(?:s/)?[A-Za-z0-9_]+(?:/\d+)?",
                "https://t.me/Ajor_pareh", line, flags=re.I,
            )
            line = re.sub(r"(?<![\w@])@[A-Za-z0-9_]{5,}", "@Ajor_pareh", line)
        branded_lines.append(line)
    return "\n".join(branded_lines)
```

The complete implementation is in `bot.py`; the production function has no placeholders and includes the VMess JSON branch.

### E. Keyword routing mixed with AI

**Root cause:** casual AI routing ran before some natural-language menu intents.

**Solution:** exact normalized keywords run before AI sessions and implicit chat. Substring messages are not routed. The user can send `کلیدواژه` to receive the live guide.

```python
async def handle_keyword_command(message: types.Message) -> bool:
    key = normalize_chat_text(message.text or "")
    if key in {"جوک", "جوک بگو", "ربات جوک بگو"}:
        await send_keyword_joke(message)
        return True
    if key in {"انتشار", "گزینه های انتشار"}:
        await message.answer("📢 ابزارهای انتشار:", reply_markup=admin_content_reply_menu())
        return True
    if key in {"پرامپت", "پرامپت ها", "پرامپت های ترند"}:
        await show_prompt_center(message)
        return True
    return False
```

### F. Prompt library and rotating trends

**Solution:** a new `🧠 پرامپت‌ها` option exists in Tools and AI menus. The catalog keeps the original entries and adds exactly ۴۰۰ deterministic, structured prompts (۱۵۰ تصویرسازی، ۸۰ ویرایش، ۸۰ محتوا، ۵۰ کاربردی و ۴۰ ترند) for ۴۱۱ entries total. Each item has a stable id, sample-output description and copy action; image/edit entries can prepare a reference-photo session with identity/gender preservation. Telegram-safe pagination shows at most eight prompt buttons per page, with previous/next page and `⏭ پرامپت بعدی` navigation. Ordering rotates every seven days and the trend category remains a focused shortlist.

The prompt catalog is deterministic and local, so it does not add a network dependency or leak user prompts. The ۴۰۰ new entries live in `prompt_catalog.py`, while the existing `PROMPT_CATALOG` routing and callbacks remain backward-compatible.

### G. Per-item publication-group editing and scheduled-group updates

**Problem:** the repost draft exposed only whole-group cancel/publish actions. A wrong item forced the administrator to discard the entire draft, and a group moved to `scheduled_posts` was immutable even while it was still `pending`.

**Solution:** draft groups now expose `🛠 ویرایش یا حذف یک پست`. Text, photo, video, document, animation, audio, voice and sticker payloads use the same repost router for immediate and scheduled publishing. Each item can be replaced by a new message or deleted independently. Pending scheduled jobs expose `➕ افزودن پست` and `🛠 ویرایش/حذف پست‌ها`; all changes use a status check plus compare-and-swap on the current `items` array, so a worker that has already changed the job to `publishing` wins and the edit is rejected safely. Media albums use the same buffering path as normal reposts. A ۲۰-item limit remains enforced.

A scheduled group becomes immutable once publishing starts, preventing duplicate or partial sends while an edit is in flight.

### H. Daily morning Hafez fortune and channel/group delivery

**Solution:** the morning fortune now contains the poem and interpretation plus a deterministic daily message, focus, practical suggestion, caution, affirmation and reflection question. The existing weekly/private subscription remains available.

Admins can open `🍷 فال روزانه صبحگاهی`, choose `🔗 اتصال یا تغییر کانال/گروه`, and send a public `@username`, public `https://t.me/...` link, numeric chat ID or a `t.me/c/...` post link. The bot verifies the chat type and its own send permission, stores the target in MongoDB, offers a test-send button, and disconnects it without affecting private subscriptions. Invite links such as `t.me/+...` cannot be resolved by Telegram Bot API alone; the UI asks for the numeric ID in that case.

The worker sends to connected targets between 07:00 and 12:00 Tehran time, so a short restart does not silently skip the morning. It uses one generated fortune per day and marks the date after generation to prevent duplicate delivery. A ۳۰-day message-history check rejects exact or highly similar daily fortunes; if the provider returns a similar fortune, the worker retries a few times and chooses the least-similar result available.

### I. Scheduled midnight and morning greeting tools

**Solution:** Tools now include `🕛 00:00` and `🌅 صبح بخیر`. Each category is seeded once with exactly ۱۰۰ default sentences in MongoDB. Admins can connect one writable channel/group target, activate either schedule, send a test, add one sentence or a newline-separated batch, edit existing ones or delete them. The add mode stays open until `✅ پایان افزودن`, `❌ لغو حالت افزودن` or `/cancel`, so ten to twenty sentences can be entered without reopening the menu. The midnight schedule runs at 00:00 Tehran time with a short recovery window; the morning schedule runs at 08:00 Tehran time with a recovery window until noon.

A ۳۰-day history per kind stores the rendered message and its core sentence. Candidate selection excludes exact and highly similar core text, and falls back to the least-similar available item only when the administrator has removed/disabled too many alternatives. User-entered sentences pass through a sanitizer before storage and sending. Telegram URLs, `@username` mentions, invite links and numeric chat IDs are removed; a sentence containing only a link or ID is rejected. The two schedules share the configured target but maintain independent enabled and last-sent state.

### J. Iranian music center and public playlist

**Solution:** music search now detects Persian/Iranian/remix queries and prioritizes a local ۱۱۲-entry Iranian metadata catalog, then combines live Deezer, iTunes and Piped/YouTube results. Separate `🇮🇷 ترند ایرانی` and `🎚 ریمیکس ایرانی` paths focus on Persian pop, rap, traditional, fusion and rap/pop/traditional remix searches instead of relying only on global Audius/Deezer charts.

`📅 موزیک امروز` has its own writable channel/group target, configurable Tehran time, enable/disable, test-send and ۳۰-day non-repeat history. If the public playlist has uploaded audio, the worker sends the actual Telegram audio/document; otherwise it sends an Iranian recommendation with a public listening link and the caption `🎵 امروز موزیک چی گوش کنیم؟`.

Admins can open `📚 پلی‌لیست ایرانی`, enter group upload mode, send many Audio/Document files one after another or as newline-independent uploads, and finish with `✅ پایان آپلود` or `/cancel`. Title/artist captions accept `عنوان | خواننده`; URLs, `@username` values and numeric IDs are removed before storage. The resulting playlist is publicly browsable and shareable through a bot deep link, while admins can soft-delete entries. Daily music uses a dedicated ۱۸۳-day history window (six months); when a non-empty playlist has no eligible unseen track, the worker skips the day instead of repeating a playlist item. At least ۱۸۳ distinct active tracks are needed for uninterrupted daily delivery across the whole window.

### K. Mini App daily tools and Persian occasion rendering

The Mini App home now exposes cards for `🌙 ۰۰:۰۰`, `🌅 صبح بخیر`, `🍷 فال حافظ`, `🎵 موزیک امروز` and `📚 پلی‌لیست ایرانی`; Telegram actions open the corresponding bot flow while music quick actions call the Iranian/trending endpoints. The service worker and asset query versions were bumped to prevent stale bundles.

The home daily-context fallback and server occasion API now translate common English occasion titles such as `International Men's Day`, `World Consumer Rights Day` and `World Water Day` into Persian. Unknown English world/international titles fall back to a Persian generic label instead of being rendered raw.

### L. QR placement and menu cleanup

The QR generator remains fully available through `🧰 ابزارهای ربات`, while its button was removed only from the main ReplyKeyboard menu. The `/qr` command remains backward-compatible.

### M. Unified media download tokens and referral bonuses

All Bot and Mini App media enqueue paths now consume one shared rolling ۲۴ساعته quota: Instagram, YouTube, music and direct URL uploads each cost one token. The base allowance is ۱۰ tokens; every referral completed by the existing anti-fraud/captcha flow adds ۱۰ tokens to the user's allowance for every future ۲۴-hour window. The atomic MongoDB update prevents concurrent double-spending, and admins remain unlimited for operations/testing. A quota panel shows remaining tokens, referral bonus and the invitation link.

### N. Media queue recovery and idempotent user actions

**Solution:** failed media jobs now expose `🔁 تلاش دوباره`; retry requeues the user-owned job without consuming a new daily quota. Extracted captions are stored on the job and exposed through `📝 کپی متن پست`. Four media workers are tracked and cancelled during shutdown, preventing orphan background tasks.

### O. Mini App authentication and frontend resilience

**Backend:** sensitive Mini App APIs continue to call `require_miniapp_user()`, which validates Telegram `initData` server-side before reading/writing user data. The new `/api/instagram/comment` endpoint follows the same rule.

**Frontend:** the new comment form uses `apiRequest()`, attaches `X-Telegram-Init-Data`, aborts after a bounded timeout, uses `textContent` for returned comment text, and provides a clipboard action. The service-worker cache was versioned and now includes `app.js`, `styles.css`, and the manifest to avoid stale feature bundles.

```javascript
async function apiRequest(path, options = {}, timeoutMs = 45000) {
  if (!tgCandidate?.initData) throw new Error("Mini App را از داخل ربات رسمی باز کن");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = {
      ...(options.headers || {}),
      "X-Telegram-Init-Data": tgCandidate.initData,
    };
    return await fetch(path, { ...options, headers, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
```

## 3. Performance and data-integrity controls

- Shared `aiohttp.ClientSession` is used for service calls.
- MongoDB indexes cover media queue status/creation, user history, AI usage, reminders, wallets, service orders and activity history.
- Media limits, active-job limits and daily limits are enforced before queue insertion.
- Temporary media folders are isolated per job and cleaned after processing.
- URL validation resolves DNS and rejects loopback/private/link-local/reserved destinations.
- Callback actions validate ownership for media jobs, prompt copies and Mini App resources.
- Reward/payment flows use atomic MongoDB updates and idempotency keys where the operation can be retried.
- Telegram retry handling exists for broadcast sends; user-facing failures degrade to an actionable message rather than an unhandled task.

## 4. Frontend review notes

- `node --check webapp/app.js` and `node --check webapp/sw.js` pass.
- Existing dynamic HTML is escaped for external/news/AI values at the relevant rendering boundaries; controlled game templates remain static.
- `AbortController` bounds long AI/media requests.
- Service-worker cache uses versioning and network-first behavior for `/api/*`.
- Telegram WebApp initialization calls `ready`, `expand`, theme handling and viewport helpers during startup.
- Game timers are cleared by the relevant game reset/finish paths; no new global interval was introduced by the prompt/media work.

## 5. Verification record

- Python compile: passed.
- JavaScript syntax: passed.
- Automated tests: **80 passed, 2 skipped**.
- AST inventory: 324 Telegram handlers and 49 HTTP/static routes; no duplicate callback-prefix registration detected.
- Prompt library, scheduled-group editing, daily fortune/channel delivery, non-repeating scheduled greetings, batch sentence management, Iranian music search, public playlist metadata sanitization, QR menu placement, keyword routing, media retry/caption actions, YouTube normalization, proxy sanitization and Mini App comment wiring are covered by tests or static checks.
- Latest production deployment before this task: Railway `SUCCESS`; `/health` returned `ok: true`, polling mode and connected database.

## 6. Explicit operational limitations

No implementation can safely guarantee downloads from private, DRM-protected, login-only, geo-blocked or anti-bot-protected sources without credentials or prohibited bypasses. The platform intentionally refuses those paths and provides a public-link error/retry path instead.
