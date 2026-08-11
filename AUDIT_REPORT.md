# Ajorpareh Final Audit — 2026-07-30

## Scope

- Telegram bot handlers, middleware, webhook, group moderation, economy, wallet, publishing, scheduler, AI gateway and MongoDB indexes.
- Mini App HTML/CSS/JavaScript, authenticated APIs, Telegram WebApp integration, accessibility, security headers and responsive behavior.
- Python dependencies, static syntax, automated tests and secret scanning.

## Bugs and risks fixed

- Replaced substring-based allowed-domain checks with exact/subdomain hostname validation to prevent lookalike-domain bypasses.
- Hardened RSS XML parsing with `defusedxml` against XML entity attacks.
- Replaced a security scanner warning caused by MD5 with SHA-256.
- Hardened Telegram Mini App `initData` timestamp validation against future/stale sessions.
- Added CSP, nosniff, no-referrer, permissions policy and correct API/static cache policies.
- Corrected stale GitHub Pages canonical/OpenGraph URLs to the active Railway Mini App URL.
- Replaced fake profile statistics and static leaderboard data with real MongoDB-backed values.
- Persisted the haptic setting safely and protected local-storage use when storage is unavailable.
- Added network timeouts and safe, text-only rendering for AI output.
- Added safe-area support for Telegram fullscreen/mobile layouts.
- Fixed group allow-list hostname matching (`example.com.evil.test` no longer matches `example.com`).

## New capabilities

### Bot

- Voice/audio transcription up to 19 MB with Groq Whisper and automatic Gemini fallback.
- Personal reminders via `/remind`, `/reminders` and persistent Reply Keyboard.
- Per-user daily AI quota bonuses controlled by the owner, plus a small capped text-quota bonus for each verified referral.
- Automatic post-maintenance recovery notifications for users who tried the bot while it was offline.
- Moderated real-user reviews plus 20 clearly labeled demo cards for the Mini App layout (never presented as genuine testimonials).
- Seeded, database-backed reward missions tied to verified referrals, five recent channel reactions, reviews, games, AI usage, voice transcription and streaks.
- Replaced the bot's placeholder news button with live categorized RSS headlines and expanded entertainment using current Telegram patterns: trivia/riddles, would-you-rather polls, short social challenges, text memes and deterministic daily fun.
- Added idempotent multi-reward gift codes for XP, coins, daily AI bonuses, badges, Telegram stickers and GIF animations, redeemable in chat and Mini App.
- Added a manually fulfilled V2Ray/NPV service shop with fixed-duration plans, wallet/card payments, receipt review, renewals, configurable payment details and timed discounts.
- Hardened repost branding so all publishing paths add `@Ajor_pareh` when absent and preserve Telegram HTML entities in place; hidden proxy words stay clickable without appending extracted URLs.
- Added a publication-mode command guard: persistent-menu labels and administrative controls are never sent to the channel and pause the active ingest mode before normal routing.
- Expanded conversational Persian normalization and casual intents, with short-term AI dialogue memory and an energetic informal persona inspired by open informal-Persian resources.
- Sticker conversion now creates/extends a real per-user Telegram Sticker Set with an Add Stickers link, sends the pack-backed sticker, and returns a forced-download WEBP document. Photo/video/GIF inputs can also become muted Telegram Animation MP4s that support Save GIF.
- Added a durable MongoDB-backed public-media queue for social downloads and direct URL uploads, with 48 MB limits, private-network/SSRF blocking, private-content refusal and automatic cleanup.
- Added a Mini App media center, structural link-risk inspection, robots.txt, sitemap.xml and first-start menu onboarding.
- Durable MongoDB reminder worker with retry/recovery and user-owned cancellation.
- Existing AI provider chain remains: Gemini → Groq → Cerebras (when configured) → OpenRouter.

### Mini App

- Authenticated Persian AI center: chat, rewrite, translation, summarization, study, coding, content, ideas and image generation.
- Live AI provider and quota status.
- Real personal reminder create/list/delete UI.
- Telegram fullscreen and Add to Home Screen controls.
- Real wallet/profile stats and live leaderboard.
- Updated manifest and SEO metadata for AI and productivity features.

## Verification

- `python -m py_compile`: passed.
- `node --check webapp/app.js`: passed.
- JSON manifest validation: passed.
- 25 automated unit/integration tests: passed (the FFmpeg test runs in the Railway image).
- Ruff fatal/undefined-name checks: passed.
- `pip check`: passed.
- `pip-audit`: no known dependency vulnerabilities.
- Bandit medium/high scan: passed after intentional Railway bind exemption.
- Secret scan: no Gemini, Groq or OpenRouter key found in source/workspace.

## Deployment checks required after release

- Railway build/deploy status `SUCCESS`.
- `/health` reports webhook mode and active AI providers.
- Mini App `/app/` returns HTTP 200 with CSP/security headers.
- Telegram webhook has no last error and zero stuck updates.
- Live Gemini, Groq, OpenRouter, image generation and voice transcription smoke tests.
- Telegram `/ai`, `/voice`, `/remind`, `/reminders` commands and Mini App menu button are installed.

## Super-Bot hardening pass — 2026-08-05

### Deterministic keyword router

- Added exact, normalized keyword commands that run before casual chat and AI sessions.
- `پنل`, `انتشار`, `جوک`, `دانلود`, `موسیقی`, `بازی`, `پروفایل`, `کیف پول`, `پروکسی`, `کانفیگ`, `کامنت`, `راهنما` and `کلیدواژه` route to their existing menus/features without substring matching.
- `کلیدواژه` returns the user-facing quick-command guide.

### Media and download reliability

- YouTube Shorts and `youtu.be` links are normalized to stable `watch?v=` URLs before the downloader/fallback chain.
- Public media fallback chain now preserves the original methods and adds `curl`, `wget` and `aria2c`; incomplete files and HTML pages are rejected between attempts.
- Added direct CDN/file-host coverage for Discord, GitHub/GitLab, Google/Cloud storage, Cloudflare R2, CloudFront, DigitalOcean Spaces, Wikimedia, Giphy, Tenor, X CDN and other public hosts.
- Failed media jobs now expose a user-owned retry button; extracted post captions are persisted and can be copied again.
- URL extraction strips surrounding punctuation without reclassifying arbitrary chat text as a download.

### Proxy/config safety

- Uploading a proxy/config clears stale media/comment sessions first.
- Config branding no longer rewrites `user:password@host` inside SOCKS/VLESS/SS-style URIs; only the remark or ordinary text is branded.

### Mini App and lifecycle

- Added authenticated Mini App form/API for extracting public Instagram comment text.
- Bumped service-worker cache and added the core app assets to the static cache list.
- All four media queue workers are now tracked and cancelled during shutdown instead of becoming orphan tasks.
- Removed invalid ReplyKeyboard instances from `editMessageText` paths; edit operations now use no keyboard or an InlineKeyboard only.

### Current verification

- `69 passed, 2 skipped` automated tests.
- Python compileall and JavaScript `node --check` passed.
- AST inventory: 324 Telegram handlers, 49 HTTP/static routes, no duplicate callback-prefix registrations detected.
- Latest deployed commit: `03d4246` (includes the previous media fallback commit `8350dc2`).
