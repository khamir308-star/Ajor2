import asyncio
import hashlib
import io
import hmac
import json
import os
import random
import re
import shutil
import subprocess
import time
import unittest
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from types import MethodType, SimpleNamespace
from urllib.parse import urlencode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from aiogram.types import MessageEntity, Message, Chat
from defusedxml.common import DefusedXmlException
from PIL import Image

os.environ.setdefault("BOT_TOKEN", "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("ADMIN_IDS", "466050034")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("CEREBRAS_API_KEY", "")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("AI_MODEL", "")

import bot
import instagram_comment_service as instagram_comments
from ai_service import AIConfig, AIService, ProviderError
from instagram_comment_service import (
    InstagramCommentError,
    is_instagram_comment_url,
    normalize_comment_id,
    parse_instagram_comment_url,
)
from media_service import (
    MediaServiceError,
    classify_social_download_error,
    extract_instagram_public_media_urls,
    is_instagram_public_url,
    is_social_url,
    looks_like_hls_manifest,
    looks_like_hls_url,
    normalized_host,
    normalize_instagram_url,
    normalize_youtube_url,
    safe_filename,
    social_download_options,
    validate_public_url,
)


class FakeBonusCollection:
    def __init__(self, document):
        self.document = document

    async def find_one(self, *args, **kwargs):
        return dict(self.document)


class FakeControlMessage:
    def __init__(self, user_id: int, text: str):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return SimpleNamespace()


class FakeUpdateCollection:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update, **kwargs):
        self.calls.append((query, update, kwargs))
        return SimpleNamespace(modified_count=1)


class FakeBalanceUsers:
    def __init__(self, document):
        self.document = dict(document)

    async def find_one(self, query, projection=None):
        return dict(self.document) if query.get("_id") == self.document.get("_id") else None

    async def find_one_and_update(self, query, update, **kwargs):
        if query.get("_id") != self.document.get("_id"):
            return None
        for field, condition in query.items():
            if field == "_id":
                continue
            if "$gte" in condition and int(self.document.get(field, 0)) < int(condition["$gte"]):
                return None
        for field, amount in update.get("$inc", {}).items():
            self.document[field] = int(self.document.get(field, 0)) + int(amount)
        self.document.update(update.get("$set", {}))
        return dict(self.document)


class FakeInsertCollection:
    def __init__(self):
        self.documents = []

    async def insert_one(self, document):
        self.documents.append(dict(document))
        return SimpleNamespace(inserted_id=document.get("_id"))


class FakeGreetingCollection:
    def __init__(self):
        self.documents = []

    async def insert_many(self, documents):
        self.documents.extend(dict(item) for item in documents)
        return SimpleNamespace(inserted_ids=[item["_id"] for item in documents])

    async def update_one(self, *args, **kwargs):
        return SimpleNamespace(modified_count=1)


class FakeScheduledPostsCollection:
    def __init__(self, document):
        self.document = dict(document)
        self.calls = []

    async def find_one(self, query):
        if query.get("_id") != self.document.get("_id"):
            return None
        if query.get("status") and query["status"] != self.document.get("status"):
            return None
        return dict(self.document)

    async def update_one(self, query, update):
        self.calls.append((query, update))
        if query.get("_id") != self.document.get("_id"):
            return SimpleNamespace(modified_count=0)
        if query.get("status") and query["status"] != self.document.get("status"):
            return SimpleNamespace(modified_count=0)
        if "items" in query and query["items"] != self.document.get("items"):
            return SimpleNamespace(modified_count=0)
        self.document.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=1)


class FakeMediaPreviewBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, user_id, text, **kwargs):
        self.messages.append((user_id, text, kwargs))
        return SimpleNamespace(message_id=99)


class FakeProfileBot:
    def __init__(self):
        self.names = {}
        self.shorts = {}
        self.descriptions = {}
        self.calls = []

    async def get_my_name(self, language_code=None):
        return SimpleNamespace(name=self.names.get(language_code, ""))

    async def set_my_name(self, name, language_code=None):
        self.names[language_code] = name; self.calls.append(("name", language_code)); return True

    async def get_my_short_description(self, language_code=None):
        return SimpleNamespace(short_description=self.shorts.get(language_code, ""))

    async def set_my_short_description(self, short_description, language_code=None):
        self.shorts[language_code] = short_description; self.calls.append(("short", language_code)); return True

    async def get_my_description(self, language_code=None):
        return SimpleNamespace(description=self.descriptions.get(language_code, ""))

    async def set_my_description(self, description, language_code=None):
        self.descriptions[language_code] = description; self.calls.append(("description", language_code)); return True


class IdAndPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.pages = set()
        self.nav = set()

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if data.get("id"):
            self.ids.append(data["id"])
        if data.get("data-page"):
            self.pages.add(data["data-page"])
        if data.get("data-nav"):
            self.nav.add(data["data-nav"])


class CoreTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        bot.mongo_client.close()

    def test_miniapp_init_data_signature_and_age(self):
        user = {"id": 42, "first_name": "Test"}
        pairs = {
            "auth_date": str(int(time.time())),
            "query_id": "test-query",
            "user": json.dumps(user, separators=(",", ":")),
        }
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", bot.TOKEN.encode(), hashlib.sha256).digest()
        pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(bot.verify_telegram_init_data(urlencode(pairs))["id"], 42)
        pairs["hash"] = "0" * 64
        self.assertIsNone(bot.verify_telegram_init_data(urlencode(pairs)))

    def test_schedule_and_reminder_parsers(self):
        repeat, scheduled, text = bot.parse_recurring_input("فردا 09:00 | تماس با علی")
        self.assertIsNone(repeat)
        self.assertGreater(scheduled, datetime.now(timezone.utc))
        self.assertEqual(text, "تماس با علی")
        tehran_tz = timezone(timedelta(hours=3, minutes=30))
        future = datetime.now(tehran_tz) + timedelta(hours=2)
        parsed = bot.parse_miniapp_datetime(future.strftime("%Y-%m-%dT%H:%M"))
        self.assertGreater(parsed, datetime.now(timezone.utc))
        with self.assertRaises(ValueError):
            bot.parse_recurring_input("فردا 09:00")

    def test_publication_control_detection_and_colloquial_chat(self):
        self.assertTrue(bot.is_publication_control_text("⚙️ پنل مدیریت", 466050034))
        self.assertTrue(bot.is_publication_control_text("📊 آمار و گزارش", 466050034))
        self.assertFalse(bot.is_publication_control_text("این متن واقعی پست کانال است", 466050034))
        normalized = bot.normalize_chat_text("سلاممم رفیق خستم و نمیدونم چیکار کنم")
        self.assertIn("سلام", normalized)
        self.assertIn("خسته ام", normalized)
        self.assertIn("چه کار", normalized)
        self.assertIsNotNone(bot.get_chat_response("گرسنمه چی بخورم"))
        self.assertIsNotNone(bot.get_chat_response("فردا امتحان دارم تمرکز ندارم"))
        self.assertEqual(bot.detect_mood("دلم گرفته و تنهام"), "bad")

    def test_music_menus_and_parsing(self):
        from music_service import _audius_item, _deezer_item, _itunes_item
        # منوهای موزیک در ربات موجودند
        media_menu = bot.media_download_reply_menu()
        texts = [kb.text for row in media_menu.keyboard for kb in row]
        self.assertIn("🎵 موسیقی", texts)
        music_menu = bot.music_reply_menu()
        music_texts = [kb.text for row in music_menu.keyboard for kb in row]
        self.assertIn("🔎 جستجوی آهنگ", music_texts)
        self.assertIn("🔥 آهنگ‌های ترند", music_texts)
        self.assertIn("🎤 تشخیص آهنگ با تکه صدا", music_texts)
        # قالب‌بندی آیتم با برچسب منبع
        line = bot.format_music_item({"source": "audius", "provider": "🎧 آدیوس", "title": "Test Song", "artist": "Artist", "duration": 125})
        self.assertIn("Test Song", line)
        self.assertIn("2:05", line)
        self.assertIn("آدیوس", line)
        # پارس ترک‌های آدیوس از JSON نمونه
        sample = {"id": "abc1", "title": "T1", "duration": 60, "user": {"name": "U1"}, "artwork": {}}
        parsed = _audius_item(sample)
        self.assertEqual(parsed["source"], "audius")
        self.assertEqual(parsed["artist"], "U1")
        self.assertTrue(parsed["downloadable"])
        self.assertEqual(parsed["provider"], "🎧 آدیوس")
        # دیزر — پیش‌نمایش دارد و قابل دانلود نیست
        d = _deezer_item({"id": 1, "title": "D1", "duration": 30, "preview": "https://x/preview.mp3", "artist": {"name": "A"}, "album": {"title": "Al"}})
        self.assertEqual(d["source"], "deezer")
        self.assertTrue(d["preview_url"])
        self.assertFalse(d["downloadable"])
        # اپل
        it = _itunes_item({"trackId": 5, "trackName": "I1", "artistName": "B", "previewUrl": "https://x/p.mp3", "trackTimeMillis": 42000})
        self.assertEqual(it["source"], "itunes")
        self.assertEqual(it["duration"], 42)
        self.assertTrue(it["preview_url"])

    def test_music_search_rejects_empty_query(self):
        import asyncio
        from music_service import search_songs
        from media_service import MediaServiceError
        async def check():
            with self.assertRaises(MediaServiceError):
                await search_songs(None, "   ")
        asyncio.run(check())

    def test_new_games_and_expanded_truth_dare(self):
        # دو بازی جدید در منوها
        menu = bot.game_menu()
        texts = [b.text for row in menu.inline_keyboard for b in row]
        self.assertIn("🧠 جورچین حافظه", texts)
        self.assertIn("🃏 بیست و یک", texts)
        reply = bot.games_reply_menu()
        reply_texts = [b.text for row in reply.keyboard for b in row]
        self.assertIn("🧠 جورچین حافظه", reply_texts)
        self.assertIn("🃏 بیست و یک", reply_texts)
        # منوی جرأت/حقیقت: گزینه کاپلی
        td = bot.truth_dare_menu()
        td_texts = [b.text for row in td.inline_keyboard for b in row]
        self.assertIn("❤️ نسخه کاپلی", td_texts)
        # سوال‌ها زیاد و جذاب شدند
        self.assertGreaterEqual(len(bot.TRUTH_QUESTIONS), 30)
        self.assertGreaterEqual(len(bot.DARE_CHALLENGES), 30)
        self.assertGreaterEqual(len(bot.COUPLE_TRUTH), 15)
        self.assertGreaterEqual(len(bot.COUPLE_DARE), 15)
        # همه سوال‌ها غیرخالی و متنوع
        self.assertEqual(len(set(bot.TRUTH_QUESTIONS)), len(bot.TRUTH_QUESTIONS))
        # حافظه: ساخت بازی و کیبورد ۴x۴
        token, game = bot._new_memory_game(12345, 111, "علی", "solo")
        self.assertEqual(len(game["board"]), 16)
        self.assertEqual(sum(1 for e in game["board"] if e == "🍎"), 2)
        kb = bot._memory_board_keyboard(token, game)
        self.assertEqual(len(kb.inline_keyboard), 5)  # 4 ردیف کارت + 1 ردیف پایان
        # بیست و یک: دو کارت اولیه
        token2, g2 = bot._new_bj_game(12345, 111, "علی", "solo")
        self.assertEqual(len(g2["hands"][1]), 2)
        self.assertTrue(all(1 <= c <= 11 for c in g2["hands"][1]))

    def test_hokm_engine_rules_and_simulations(self):
        import hokm_engine as he
        # ارزش برگ‌ها — حکم
        ace = {"s": "s", "v": 14}; two = {"s": "s", "v": 2}
        self.assertEqual(he.trick_value(ace, "s", "h"), 14)  # آس غیر حکم
        self.assertEqual(he.trick_value({"s": "h", "v": 14}, "s", "h"), 114)  # آس حکم
        self.assertEqual(he.trick_value(ace, "s", None), 14)  # بدون حکم
        self.assertEqual(he.trick_value(two, "s", None), 2)
        self.assertEqual(he.trick_value({"s": "h", "v": 2}, "s", "h"), 102)  # ۲ حکم > ۱۴ غیر حکم
        self.assertEqual(he.trick_value({"s": "d", "v": 14}, "s", "h"), 0)  # غیر زمینه و غیر حکم
        grouped = he.sort_hand([
            {"s": "h", "v": 2}, {"s": "s", "v": 13},
            {"s": "h", "v": 14}, {"s": "s", "v": 14},
        ])
        self.assertEqual(
            [(card["s"], card["v"]) for card in grouped],
            [("s", 14), ("s", 13), ("h", 14), ("h", 2)],
        )
        order_game = he.HokmGame("order", 0, 1, "A", 1, 2, "B")
        order_game.phase = "play"
        order_game.hands = {
            0: [{"s": "s", "v": 14}], 1: [{"s": "d", "v": 2}],
            2: [{"s": "h", "v": 14}], 3: [{"s": "c", "v": 2}],
        }
        order_game.trump_suit = "s"
        order_game.start_trick(2)  # حاکم
        self.assertEqual(order_game.turn, 2)
        self.assertTrue(order_game.play(2, {"s": "h", "v": 14}))
        self.assertEqual(order_game.turn, 3)  # راست حاکم
        self.assertTrue(order_game.play(3, {"s": "c", "v": 2}))
        self.assertEqual(order_game.turn, 0)  # یار حاکم
        self.assertTrue(order_game.play(0, {"s": "s", "v": 14}))
        self.assertEqual(order_game.turn, 1)  # چپ حاکم
        # ساخت بازی و شروع
        game = he.HokmGame("r1", 0, 111, "A", 1, 222, "B", "hard")
        self.assertEqual(game.phase, "waiting")
        game.start()
        self.assertIsNotNone(game.hakem)
        # اگه حاکم انسان باشه، منتظر اعلام حکمه (۲۰ کارت)
        # اگه حاکم ربات باشه، خودش اعلام می‌کنه (۵۲ کارت)
        if game.phase == "bid":
            self.assertEqual(sum(len(v) for v in game.hands.values()), 20)
            game.declare_trump(game.hakem, "h")
        # حالا ۵۲ کارت پخش شده
        self.assertEqual(sum(len(v) for v in game.hands.values()), 52)
        for p in range(4):
            self.assertEqual(len(game.hands[p]), 13)
        # حرکات مجاز: با برگ زمینه فقط هم‌خال
        game.led_suit = "s"
        game.turn = 0
        hand_s = [c for c in game.hands[0] if c["s"] == "s"]
        if hand_s:
            legal = game.legal_moves(0)
            self.assertTrue(all(c["s"] == "s" for c in legal))
        # شبیه‌سازی کامل — AI plays for all
        random.seed(3)
        game2 = he.HokmGame("r2", 0, 111, "A", 1, 222, "B")
        game2.start()
        guard = 0
        while game2.phase != "done" and guard < 500:
            guard += 1
            if game2.phase == "dealing":
                game2.next_hand()
                continue
            if game2.phase == "bid":
                game2._ai_declare_trump()
                continue
            if game2.phase == "play":
                if game2.turn is None:
                    break
                game2.ai_move(game2.turn)
        self.assertEqual(game2.phase, "done")
        # وضعیت عمومی
        st = game2.public_state(0)
        self.assertEqual(len(st["hand"]), len(game2.hands[0]))

    def test_emoji_api_guide_present(self):
        self.assertIn("getCustomEmojiDocuments", bot.EMOJI_API_GUIDE)
        self.assertIn("searchCustomEmoji", bot.EMOJI_API_GUIDE)
        self.assertIn("messageEntityCustomEmoji", bot.EMOJI_API_GUIDE)
        tools = {b.text for row in bot.tools_reply_menu().keyboard for b in row}
        self.assertIn("🧩 API شکلک سفارشی", tools)

    def test_admin_panel_has_new_monitoring_buttons(self):
        menu = bot.admin_menu()
        texts = [b.text for row in menu.inline_keyboard for b in row]
        self.assertIn("📡 رصد زنده فعالیت‌ها", texts)
        self.assertIn("🕵️ فعالیت یک کاربر", texts)
        self.assertIn("🔥 کاربران فعال امروز", texts)
        self.assertIn("📊 آمار رسانه", texts)
        self.assertIn("🧹 پاکسازی صف رسانه", texts)
        self.assertIn("📈 آمار هوش مصنوعی", texts)
        # منوی reply
        reply = bot.admin_reply_menu()
        reply_texts = [b.text for row in reply.keyboard for b in row]
        self.assertIn("📡 رصد فعالیت‌ها", reply_texts)
        self.assertIn("🔥 کاربران فعال", reply_texts)
        # برچسب فعالیت
        self.assertIn("بزن در رو", bot._activity_label("game_hit_run"))
        self.assertEqual(bot._activity_label("چیزی_ناشناس"), "چیزی_ناشناس")
        # راهنمای API شکلک
        self.assertIn("getCustomEmojiDocuments", bot.EMOJI_API_GUIDE)

    def test_info_tools_present(self):
        import tools_service as ts
        # منوی دانش و اطلاعات
        menu = bot.info_reply_menu()
        texts = [b.text for row in menu.keyboard for b in row]
        self.assertIn("☀️ آب‌وهوا", texts)
        self.assertIn("💱 نرخ ارز", texts)
        self.assertIn("🪙 قیمت کریپتو", texts)
        self.assertIn("📚 خلاصه ویکی‌پدیا", texts)
        self.assertIn("🧠 کوئیز جهانی", texts)
        self.assertIn("🔐 بررسی امنیت رمز", texts)
        tools = [b.text for row in bot.tools_reply_menu().keyboard for b in row]
        self.assertIn("🌍 دانش و اطلاعات", tools)
        # الیاس‌ها
        self.assertEqual(ts.normalize_city("تهران"), "Tehran")
        self.assertEqual(ts._parse_crypto_symbol("بیت‌کوین"), "bitcoin")
        self.assertEqual(ts._parse_currency("تومان"), "IRR")
        # بررسی امنیت رمز (محلی — بدون شبکه)
        count = ts.pwned_password_count("this-is-a-unique-test-password-xyz-12345")
        self.assertEqual(count, 0)
        # دکمه پست خودکار در پنل
        admin = bot.admin_menu()
        admin_texts = [b.text for row in admin.inline_keyboard for b in row]
        self.assertTrue(any("پست خودکار نرخ ارز" in t for t in admin_texts))

    def test_persian_calendar(self):
        import calendar_service as cs
        # تبدیل‌های شناخته‌شده
        self.assertEqual(cs.gregorian_to_jalali(2026, 3, 21), (1405, 1, 1))
        self.assertEqual(cs.gregorian_to_jalali(2025, 3, 21), (1404, 1, 1))
        self.assertEqual(cs.gregorian_to_jalali(1986, 2, 25), (1364, 12, 6))
        self.assertEqual(cs.gregorian_to_jalali(2024, 3, 20), (1403, 1, 1))
        # دور برگشت
        self.assertEqual(cs.jalali_to_gregorian(1405, 1, 1), (2026, 3, 21))
        self.assertEqual(cs.jalali_to_gregorian(1405, 5, 11), (2026, 8, 2))
        # طول ماه‌ها
        self.assertEqual(cs.jalali_month_length(1405, 6), 31)
        self.assertEqual(cs.jalali_month_length(1405, 11), 30)
        # مناسبت‌ها
        self.assertIn("نوروز", cs.occasions_for(1405, 1, 1)[0])
        self.assertIn("یلدا", cs.occasions_for(1405, 9, 30)[0])
        self.assertEqual(cs.occasions_for(1405, 4, 21), [])  # بدون مناسبت
        # شبکه ماه
        grid = cs.month_grid(1405, 1)
        self.assertEqual(len(grid["days"]) % 7, 0)
        self.assertEqual(grid["month_name"], "فروردین")
        # اطلاعات امروز
        info = cs.today_info()
        self.assertIn("weekday", info)
        self.assertIn("islamic", info)
        # منوی تقویم در ربات
        tools = [b.text for row in bot.tools_reply_menu().keyboard for b in row]
        self.assertIn("📅 تقویم شمسی", tools)
        # رندر متنی ماه
        text = bot.calendar_month_text(1405, 1)
        self.assertIn("فروردین", text)

    def test_tts_feature_present(self):
        # صداها
        self.assertIn("bella", bot.TTS_VOICES)
        self.assertIn("adam", bot.TTS_VOICES)
        self.assertIn("EXAVITQu4vr4xnSDxMaL", bot.TTS_VOICES["bella"]["id"])
        # دکمه منو
        tools = [b.text for row in bot.tools_reply_menu().keyboard for b in row]
        self.assertIn("🎤 تبدیل متن به صدا", tools)
        # سهمیه روزانه
        self.assertGreater(bot.TTS_DAILY_CHAR_LIMIT, 0)
        self.assertIn("tts", [c.command for c in bot.configured_commands()] if hasattr(bot, "configured_commands") else ["tts"])

    def test_new_engagement_features(self):
        import datetime as _dt
        from datetime import timezone as _tz
        # ۱) یادآور تکراری: parse_recurring_input
        repeat, when, text = bot.parse_recurring_input("هر روز 09:00 | آب بخور")
        self.assertEqual(repeat, "daily")
        self.assertIn("آب", text)
        repeat2, _, _ = bot.parse_recurring_input("شنبه 10:00 | جلسه")
        self.assertEqual(repeat2, "weekly")
        repeat3, _, _ = bot.parse_recurring_input("فردا 09:00 | عادی")
        self.assertIsNone(repeat3)
        # ۲) محاسبه زمان بعدی
        base = _dt.datetime(2026, 8, 2, 5, 0, tzinfo=_tz.utc)
        nxt = bot._next_recurrence(base, "daily")
        self.assertEqual(nxt.day, 3)
        nxt_w = bot._next_recurrence(base, "weekly")
        self.assertEqual(nxt_w.day, 9)
        # ۳) کامندهای جدید ثبت شده‌اند
        self.assertTrue(hasattr(bot, "mystats_command"))
        self.assertTrue(hasattr(bot, "short_command"))
        self.assertTrue(hasattr(bot, "summarize_command"))
        # ۴) منوی اطلاعات و ابزار
        tools = [b.text for row in bot.tools_reply_menu().keyboard for b in row]
        self.assertIn("🎤 تبدیل متن به صدا", tools)

    def test_tools_cache_fallback_without_redis(self):
        import asyncio
        import tools_service as ts
        # بدون متغیر Redis → fallback حافظه
        old_url, old_token = ts.UPSTASH_REST_URL, ts.UPSTASH_REST_TOKEN
        ts.UPSTASH_REST_URL, ts.UPSTASH_REST_TOKEN = "", ""
        try:
            self.assertFalse(ts._redis_available())
            async def run():
                await ts._cache_set("k1", {"x": 1}, ttl=30)
                return await ts._cache_get("k1")
            result = asyncio.run(run())
            self.assertEqual(result, {"x": 1})
        finally:
            ts.UPSTASH_REST_URL, ts.UPSTASH_REST_TOKEN = old_url, old_token
        # با متغیر Redis → available True
        ts.UPSTASH_REST_URL = "https://example.upstash.io"
        ts.UPSTASH_REST_TOKEN = "token"
        try:
            self.assertTrue(ts._redis_available())
        finally:
            ts.UPSTASH_REST_URL, ts.UPSTASH_REST_TOKEN = old_url, old_token

    def test_music_section_in_tools_menu(self):
        # دکمه موسیقی در ابزارها
        tools = bot.tools_reply_menu()
        texts = [b.text for row in tools.keyboard for b in row]
        self.assertIn("🎵 موسیقی", texts)
        # زیرمنوی موسیقی
        music = bot.music_reply_menu()
        music_texts = [b.text for row in music.keyboard for b in row]
        self.assertIn("🔎 جستجوی آهنگ", music_texts)
        self.assertIn("🔥 آهنگ‌های ترند", music_texts)
        self.assertIn("🎤 تشخیص آهنگ با تکه صدا", music_texts)
        self.assertIn("↩️ ابزارهای ربات", music_texts)
        # صفحه موسیقی در مینی اپ
        html = Path("webapp/index.html").read_text()
        self.assertIn('data-page="music"', html)
        self.assertIn('data-mtab="search"', html)
        self.assertIn('data-mtab="trending"', html)
        self.assertIn('data-mtab="listen"', html)
        # جستجوی آهنگ دیگر در مرکز دانلود نباشه
        media_menu = bot.media_download_reply_menu()
        media_texts = [b.text for row in media_menu.keyboard for b in row]
        self.assertNotIn("🎵 جستجو و دانلود آهنگ", media_texts)

    def test_prayer_and_hafez_features(self):
        import prayer_service as ps
        # نام‌های شهر
        self.assertEqual(ps.normalize_prayer_city("تهران"), "Tehran")
        self.assertEqual(ps.normalize_prayer_city("مشهد"), "Mashhad")
        # برچسب‌ها
        self.assertIn("اذان صبح", ps.PRAYER_LABELS["Fajr"])
        self.assertIn("اذان مغرب", ps.PRAYER_LABELS["Maghrib"])
        # خروجی متنی
        text = ps.format_prayer_text({"city": "Tehran", "country": "Iran",
                                      "gregorian": "02 Aug 2026", "hijri": "19 Ṣafar 1448",
                                      "timings": {"Fajr": "03:25", "Maghrib": "19:08"}})
        self.assertIn("03:25", text)
        self.assertIn("19:08", text)
        # دکمه‌های منو
        menu = bot.info_reply_menu()
        texts = [b.text for row in menu.keyboard for b in row]
        self.assertIn("🕌 اوقات شرعی", texts)
        self.assertIn("🍷 فال حافظ", texts)

    def test_stars_payment_present(self):
        # دکمه ستاره در منوی پرداخت (وقتی فعال باشد)
        bot.economy_settings["stars_enabled"] = True
        bot.economy_settings["stars_auto_rate"] = False  # نرخ دستی برای تست قطعی بدون درخواست شبکه
        kb = asyncio.run(bot.service_payment_keyboard("v2ray", 1))
        labels = [b.text for row in kb.inline_keyboard for b in row]
        self.assertTrue(any("⭐" in t for t in labels), labels)
        # وقتی غیرفعال باشد دکمه حذف می‌شود
        bot.economy_settings["stars_enabled"] = False
        kb2 = asyncio.run(bot.service_payment_keyboard("v2ray", 1))
        labels2 = [b.text for row in kb2.inline_keyboard for b in row]
        self.assertFalse(any("⭐" in t for t in labels2), labels2)
        bot.economy_settings["stars_enabled"] = True
        # نرخ پویا
        bot.economy_settings["stars_rate_toman"] = 20000
        kb3 = asyncio.run(bot.service_payment_keyboard("v2ray", 1))
        labels3 = [b.text for row in kb3.inline_keyboard for b in row]
        self.assertTrue(any("⭐" in t for t in labels3))
        bot.economy_settings["stars_rate_toman"] = 10000
        bot.economy_settings["stars_auto_rate"] = True

    def test_media_progress_bar(self):
        bar0 = bot.media_progress_bar(0)
        self.assertIn("0%", bar0)
        bar50 = bot.media_progress_bar(50)
        self.assertIn("50%", bar50)
        self.assertIn("▓", bar50)
        self.assertIn("░", bar50)
        bar100 = bot.media_progress_bar(100)
        self.assertIn("100%", bar100)
        self.assertNotIn("░", bar100)
        # محدوده امن
        self.assertIn("0%", bot.media_progress_bar(-5))
        self.assertIn("100%", bot.media_progress_bar(150))

    def test_daily_fal_features(self):
        self.assertGreaterEqual(len(bot.QUIZ_QUESTIONS), 50)
        self.assertEqual(len({item[0] for item in bot.QUIZ_QUESTIONS}), len(bot.QUIZ_QUESTIONS))
        # دکمه‌های پنل ادمین
        menu = bot.admin_menu()
        texts = [b.text for row in menu.inline_keyboard for b in row]
        self.assertTrue(any("ستاره" in t for t in texts))
        self.assertTrue(any("فال روزانه" in t for t in texts))
        # منوی اطلاعات
        menu = bot.admin_content_reply_menu()
        labels = [btn.text for row in menu.keyboard for btn in row]
        self.assertTrue(any("اذان روزانه" in t for t in labels), labels)
        fin = bot.admin_finance_reply_menu()
        fin_labels = [btn.text for row in fin.keyboard for btn in row]
        self.assertTrue(any("مالی هفتگی" in t for t in fin_labels), fin_labels)
        # اذان‌گوی شخصی
        info = bot.info_reply_menu()
        info_labels = [btn.text for row in info.keyboard for btn in row]
        self.assertTrue(any("اذان‌گوی شخصی" in t for t in info_labels), info_labels)
        self.assertEqual(len(bot.AZAN_LABELS), 5)
        info = bot.info_reply_menu()
        info_texts = [b.text for row in info.keyboard for b in row]
        self.assertIn("🔔 فال روزانه", info_texts)
        # کامند falsub ثبت شده
        self.assertTrue(hasattr(bot, "falsub_command"))
        # کنترل مقصد کانال/گروه فال صبحگاهی
        fal_controls = [button for row in bot.daily_fal_admin_keyboard().inline_keyboard for button in row]
        self.assertTrue(any(button.callback_data == "daily_fal_connect" for button in fal_controls))
        self.assertTrue(hasattr(bot, "daily_fal_worker"))
        self.assertEqual(bot.translate_online_occasion("International Men's Day"), "روز جهانی مردان")

    def test_miniapp_daily_tools_and_persian_occasion_translation(self):
        index = Path("webapp/index.html").read_text()
        app_js = Path("webapp/app.js").read_text()
        self.assertIn('data-open-bot="midnight_greeting"', index)
        self.assertIn('data-open-bot="morning_greeting"', index)
        self.assertIn('data-open-bot="iran_playlist"', index)
        self.assertIn('id="musicIranianTrendBtn"', index)
        self.assertIn("translateOccasionTitle", app_js)
        self.assertIn("روز جهانی مردان", app_js)

    def test_daily_fal_message_is_expanded_and_target_parser_is_safe(self):
        data = {
            "poem": ["بیت اول", "بیت دوم", "بیت سوم"],
            "interpretation": "تفسیر آزمایشی فال",
        }
        text = bot.build_fal_message(data, morning=True, for_channel=True)
        self.assertIn("پیام صبحگاهی", text)
        self.assertIn("تمرکز امروز", text)
        self.assertIn("پیشنهاد عملی", text)
        self.assertIn("پرسش امروز", text)
        self.assertLessEqual(len(text), 4000)
        self.assertEqual(bot.parse_daily_fal_target("https://t.me/my_channel"), "@my_channel")
        self.assertEqual(bot.parse_daily_fal_target("https://t.me/c/123456789/42"), -100123456789)
        with self.assertRaises(ValueError):
            bot.parse_daily_fal_target("https://t.me/+privateInvite")

    def test_scheduled_greeting_defaults_and_sanitization(self):
        self.assertEqual(len(bot.MIDNIGHT_DEFAULT_SENTENCES), 100)
        self.assertEqual(len(bot.MORNING_DEFAULT_SENTENCES), 100)
        self.assertEqual(set(bot.GREETING_CONFIG), {"midnight", "morning"})
        self.assertEqual(bot.SCHEDULED_NO_REPEAT_DAYS, 30)
        cleaned = bot.sanitize_greeting_text("سلام https://t.me/example @example_user -1001234567890")
        self.assertEqual(cleaned, "سلام")
        with self.assertRaises(ValueError):
            bot.sanitize_greeting_text("https://t.me/example")
        self.assertTrue(bot.scheduled_messages_similar("صبح بخیر و روز خوبی داشته باشی", "صبح بخیر؛ روز خوبی داشته باشی"))
        self.assertFalse(bot.scheduled_messages_similar("شب آرام و دلت روشن", "برای شروع امروز یک قدم کوچک بردار"))
        self.assertIn("۰۰:۰۰", bot.render_scheduled_greeting("midnight", "شب آرام"))
        self.assertIn("صبح بخیر", bot.render_scheduled_greeting("morning", "روز خوب"))
        self.assertIn("00:00", bot.scheduled_greeting_text("midnight"))
        self.assertIn("08:00", bot.scheduled_greeting_text("morning"))

    def test_greeting_add_session_accepts_many_lines_without_reopening_menu(self):
        user_id = 991003
        original_collection = bot.scheduled_greetings_col
        original_session = bot.greeting_add_sessions.get(user_id)

        class FakeMessage:
            def __init__(self):
                self.from_user = SimpleNamespace(id=user_id)
                self.answers = []

            async def answer(self, text, **kwargs):
                self.answers.append((text, kwargs))
                return SimpleNamespace()

        fake_collection = FakeGreetingCollection()
        bot.scheduled_greetings_col = fake_collection
        bot.greeting_add_sessions[user_id] = {"kind": "morning", "count": 0}
        try:
            message = FakeMessage()
            asyncio.run(bot.save_greeting_sentence(message, "morning", "اولین جمله\nدومین جمله با https://t.me/example"))
            self.assertEqual(len(fake_collection.documents), 2)
            self.assertEqual(bot.greeting_add_sessions[user_id]["count"], 2)
            self.assertIn("جملهٔ بعدی", message.answers[-1][0])
        finally:
            bot.scheduled_greetings_col = original_collection
            if original_session is None:
                bot.greeting_add_sessions.pop(user_id, None)
            else:
                bot.greeting_add_sessions[user_id] = original_session

    def test_iranian_music_catalog_and_group_upload_sanitization(self):
        from iranian_music_catalog import IRANIAN_MUSIC_CATALOG
        from music_service import is_iranian_music_query

        self.assertGreaterEqual(len(IRANIAN_MUSIC_CATALOG), 100)
        self.assertTrue(is_iranian_music_query("ریمیکس رپ پاپ سنتی"))
        self.assertTrue(is_iranian_music_query("Ebi"))
        self.assertFalse(is_iranian_music_query("Taylor Swift"))
        self.assertGreaterEqual(bot.DAILY_MUSIC_NO_REPEAT_DAYS, 183)

        class FakeAudioMessage:
            audio = SimpleNamespace(file_id="audio-1", title="عنوان https://t.me/example", performer="خواننده")
            document = None
            caption = "عنوان https://t.me/example | @artist_user -1001234567890"

        metadata = asyncio.run(bot._playlist_metadata(FakeAudioMessage()))
        self.assertIsNotNone(metadata)
        self.assertNotIn("https://", metadata[2])
        self.assertNotIn("@", metadata[3])

        class FakePromptMessage:
            def __init__(self):
                self.from_user = SimpleNamespace(id=8985557733)
                self.answers = []

            async def answer(self, text, **kwargs):
                self.answers.append((text, kwargs))
                return SimpleNamespace()

        prompt = FakePromptMessage()
        owner_id = 466050034
        bot.music_playlist_upload_sessions.pop(owner_id, None)
        asyncio.run(bot.start_music_playlist_upload(prompt, owner_id))
        self.assertIn(owner_id, bot.music_playlist_upload_sessions)
        self.assertNotIn(prompt.from_user.id, bot.music_playlist_upload_sessions)
        bot.music_playlist_upload_sessions.pop(owner_id, None)
        music_labels = {button.text for row in bot.music_reply_menu().keyboard for button in row}
        self.assertTrue({"🇮🇷 ترند ایرانی", "🎚 ریمیکس ایرانی", "📅 موزیک امروز", "📚 پلی‌لیست ایرانی", "📤 آپلود گروهی موسیقی"} <= music_labels)

    def test_media_size_label_and_local_api_flag(self):
        from media_service import media_size_label, MAX_MEDIA_BYTES
        self.assertEqual(MAX_MEDIA_BYTES, 49 * 1024 * 1024)
        self.assertEqual(bot.DOWNLOAD_BASE_TOKENS, 10)
        self.assertEqual(bot.DOWNLOAD_TOKENS_PER_REFERRAL, 10)
        self.assertEqual(bot.DOWNLOAD_TOKEN_WINDOW.total_seconds(), 24 * 60 * 60)
        self.assertIn("مگابایت", media_size_label())
        self.assertFalse(bot.LOCAL_BOT_API)
        self.assertFalse(bot.USE_WEBHOOK or False)

    def test_media_url_helpers(self):
        self.assertTrue(is_social_url("https://www.instagram.com/reel/abc/"))
        self.assertTrue(is_social_url("https://youtu.be/test"))
        self.assertFalse(is_social_url("https://example.com/movie.mp4"))
        self.assertEqual(normalized_host("https://WWW.Example.com/a"), "www.example.com")
        self.assertEqual(safe_filename("https://example.com/a%20movie.mp4"), "a movie.mp4")
        self.assertEqual(
            normalize_youtube_url("https://www.youtube.com/shorts/abcDEF_1234?si=share"),
            "https://www.youtube.com/watch?v=abcDEF_1234",
        )
        self.assertEqual(
            normalize_youtube_url("https://youtu.be/abcDEF_1234?t=3"),
            "https://www.youtube.com/watch?v=abcDEF_1234",
        )
        self.assertTrue(looks_like_hls_url("https://stream.example.com/live/master.m3u8?token=x"))
        self.assertTrue(looks_like_hls_manifest(b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n", "application/vnd.apple.mpegurl"))
        self.assertFalse(looks_like_hls_manifest(b"<html>login</html>", "text/html"))
        instagram_url = "https://www.instagram.com/reel/DY2YjrxRJtT/?igsh=MXBodTkzOXYzZzdndQ=="
        self.assertTrue(is_instagram_public_url(instagram_url))
        self.assertEqual(normalize_instagram_url(instagram_url), "https://www.instagram.com/reel/DY2YjrxRJtT/")
        embed_html = '<meta property="og:video" content="https://scontent.example.fbcdn.net/reel.mp4?x=1">'
        self.assertEqual(extract_instagram_public_media_urls(embed_html), ["https://scontent.example.fbcdn.net/reel.mp4?x=1"])
        context = json.dumps({"gql_data": {"shortcode_media": {"video_url": "https://scontent.example.fbcdn.net/reel-2.mp4"}}})
        self.assertTrue(any("reel-2.mp4" in url for url in extract_instagram_public_media_urls(f'"contextJSON":{json.dumps(context)}')))
        self.assertIn("cdn.discordapp.com", bot.SUPPORTED_SOCIAL_DOMAINS)
        self.assertIn("raw.githubusercontent.com", bot.SUPPORTED_SOCIAL_DOMAINS)

    def test_media_download_requires_explicit_mode_and_config_branding_is_safe(self):
        self.assertTrue(bot.contains_media_link("https://www.instagram.com/reel/abc/"))
        self.assertFalse(hasattr(bot, "auto_social_media_download"))
        proxy = "socks5://user:pass@example.com:443?secret=1#old-name"
        sanitized = bot.sanitize_config_text(proxy + "\n@SomeChannel")
        self.assertIn("user:pass@example.com:443?secret=1", sanitized)
        self.assertIn("%40Ajor_pareh", sanitized)
        self.assertNotIn("@SomeChannel", sanitized)

    def test_prompt_library_has_image_examples_and_weekly_trends(self):
        self.assertGreaterEqual(len(bot.PROMPT_CATALOG), 10)
        self.assertTrue(any(item["category"] == "image" for item in bot.PROMPT_CATALOG))
        self.assertTrue(bot._prompt_items("trending"))
        self.assertTrue(all(item["trend"] >= 90 for item in bot._prompt_items("trending")))
        self.assertIn("نمونه", bot.PROMPT_CATALOG[0]["sample"])
        tools = [button.text for row in bot.tools_reply_menu().keyboard for button in row]
        self.assertIn("🧠 پرامپت‌ها", tools)

    def test_prompt_library_contains_exactly_400_new_prompts_and_safe_pagination(self):
        self.assertEqual(bot.PROMPT_NEW_COUNT, 400)
        self.assertGreaterEqual(len(bot.PROMPT_CATALOG), 411)
        self.assertEqual(len({item["id"] for item in bot.PROMPT_CATALOG}), len(bot.PROMPT_CATALOG))
        self.assertEqual(
            {category: len([item for item in bot.EXTENDED_PROMPTS if item["category"] == category]) for category in bot.PROMPT_CATEGORIES},
            {"image": 150, "edit": 80, "content": 80, "utility": 50, "trending": 40},
        )
        for item in bot.PROMPT_CATALOG:
            self.assertLessEqual(len(f"promptview:{item['id']}".encode()), 64)
            self.assertLessEqual(len(item["prompt"]), 4096)
            self.assertIn("نمونه", item["sample"])
        for category in bot.PROMPT_CATEGORIES:
            items = bot._prompt_items(category)
            self.assertTrue(items)
            self.assertEqual(bot._prompt_page_count(category), (len(items) + bot.PROMPTS_PER_PAGE - 1) // bot.PROMPTS_PER_PAGE)
            first_page = bot._prompt_page_keyboard(category, 0)
            prompt_buttons = [
                button for row in first_page.inline_keyboard for button in row
                if button.callback_data and button.callback_data.startswith("promptview:")
            ]
            self.assertLessEqual(len(prompt_buttons), bot.PROMPTS_PER_PAGE)
            self.assertTrue(all(len(button.callback_data.encode()) <= 64 for button in prompt_buttons))

    def test_repost_payload_supports_video_audio_and_text(self):
        class FakeMediaMessage:
            def __init__(self, **media):
                self.photo = None
                self.video = None
                self.animation = None
                self.document = None
                self.audio = None
                self.voice = None
                self.sticker = None
                self.text = None
                self.caption = "کانال @SomeChannel"
                self.entities = []
                self.caption_entities = []
                for key, value in media.items():
                    setattr(self, key, value)

        video = bot.extract_repost_payload(FakeMediaMessage(video=SimpleNamespace(file_id="v1")))
        audio = bot.extract_repost_payload(FakeMediaMessage(audio=SimpleNamespace(file_id="a1", title="Song", performer="Artist")))
        text = FakeMediaMessage()
        text.caption = None
        text.text = "متن پست"
        text_payload = bot.extract_repost_payload(text)
        self.assertEqual(video["type"], "video")
        self.assertEqual(audio["type"], "audio")
        self.assertEqual(text_payload["type"], "text")
        self.assertNotIn("@SomeChannel", video["caption"])

    def test_repost_batch_has_individual_edit_and_delete_controls(self):
        user_id = 991001
        original_batch = bot.repost_batches.get(user_id)
        batch = {
            "admin_id": user_id,
            "items": [
                {"payload": {"type": "text", "text": "پست اول"}, "published": False},
                {"payload": {"type": "photo", "file_id": "photo-1", "caption": "پست دوم"}, "published": False},
            ],
            "publishing": False,
            "created_at": 0,
        }
        bot.repost_batches[user_id] = batch
        try:
            markup = bot.repost_batch_manage_keyboard(batch)
            callbacks = [
                button.callback_data
                for row in markup.inline_keyboard
                for button in row
                if button.callback_data
            ]
            self.assertIn("repost_edit:0", callbacks)
            self.assertIn("repost_delete:0", callbacks)
            self.assertIn("repost_edit:1", callbacks)
            self.assertIn("repost_delete:1", callbacks)
            self.assertEqual(bot.repost_payload_preview({"type": "text", "text": "a\nb"}), "متن · a b")
        finally:
            if original_batch is None:
                bot.repost_batches.pop(user_id, None)
            else:
                bot.repost_batches[user_id] = original_batch
            bot.repost_edit_sessions.pop(user_id, None)

    def test_repost_item_edit_and_scheduled_item_add_edit_are_atomic(self):
        user_id = 991002

        class FakeMessage:
            def __init__(self, uid):
                self.from_user = SimpleNamespace(id=uid)
                self.answers = []

            async def answer(self, text, **kwargs):
                self.answers.append((text, kwargs))
                return SimpleNamespace()

        original_batch = bot.repost_batches.get(user_id)
        original_collection = bot.scheduled_posts_col
        batch = {
            "admin_id": user_id,
            "items": [{"payload": {"type": "text", "text": "قدیمی"}, "published": False}],
            "publishing": False,
            "created_at": 0,
        }
        bot.repost_batches[user_id] = batch
        bot.repost_edit_sessions[user_id] = 0
        try:
            message = FakeMessage(user_id)
            asyncio.run(bot.replace_repost_item(message, {"type": "text", "text": "اصلاح‌شده"}))
            self.assertEqual(batch["items"][0]["payload"]["text"], "اصلاح‌شده")
            self.assertNotIn(user_id, bot.repost_edit_sessions)

            scheduled = {
                "_id": "job-atomic",
                "status": "pending",
                "items": [{"type": "text", "text": "زمان‌بندی اول"}],
            }
            fake_collection = FakeScheduledPostsCollection(scheduled)
            bot.scheduled_posts_col = fake_collection
            bot.scheduled_add_sessions[user_id] = "job-atomic"
            asyncio.run(bot.append_scheduled_payload(message, {"type": "text", "text": "زمان‌بندی دوم"}))
            self.assertEqual(len(fake_collection.document["items"]), 2)

            bot.scheduled_edit_sessions[user_id] = ("job-atomic", 0)
            asyncio.run(bot.replace_scheduled_payload(message, {"type": "text", "text": "زمان‌بندی اصلاح‌شده"}))
            self.assertEqual(fake_collection.document["items"][0]["text"], "زمان‌بندی اصلاح‌شده")
            self.assertFalse(bot.scheduled_add_sessions.get(user_id))
            self.assertNotIn(user_id, bot.scheduled_edit_sessions)
        finally:
            bot.scheduled_posts_col = original_collection
            if original_batch is None:
                bot.repost_batches.pop(user_id, None)
            else:
                bot.repost_batches[user_id] = original_batch
            bot.repost_edit_sessions.pop(user_id, None)
            bot.scheduled_add_sessions.pop(user_id, None)
            bot.scheduled_edit_sessions.pop(user_id, None)

    def test_exact_keyword_router_is_deterministic_before_ai(self):
        class FakeMessage:
            def __init__(self, text):
                self.text = text
                self.from_user = SimpleNamespace(id=999001, full_name="Test")
                self.answers = []

            async def answer(self, text, **kwargs):
                self.answers.append((text, kwargs))
                return SimpleNamespace()

        message = FakeMessage("کلیدواژه")
        handled = asyncio.run(bot.handle_keyword_command(message))
        self.assertTrue(handled)
        self.assertTrue(message.answers)
        self.assertIn("انتشار", bot.KEYWORD_HELP_TEXT)
        self.assertTrue(asyncio.run(bot.handle_keyword_command(FakeMessage("ربات جوک بگو"))))
        self.assertTrue(asyncio.run(bot.handle_keyword_command(FakeMessage("گزینه های انتشار"))))

    def test_miniapp_comment_tool_is_wired(self):
        html = Path("webapp/index.html").read_text()
        js = Path("webapp/app.js").read_text()
        self.assertIn('id="instagramCommentForm"', html)
        self.assertIn('id="instagramCommentResult"', html)
        self.assertIn('/api/instagram/comment', js)
        self.assertIn('async def miniapp_instagram_comment_api', Path("bot.py").read_text())

    def test_instagram_comment_link_extraction_helpers(self):
        path_link = "https://www.instagram.com/p/Chunk8-jurw/c/18102822571970750/"
        query_link = "https://www.instagram.com/reel/Chunk8-jurw/?comment_id=18102822571970750"
        reply_link = "https://www.instagram.com/reel/Chunk8-jurw/?comment_id=18102822571970750&reply_comment_id=18123394012620235"
        parsed = parse_instagram_comment_url(path_link)
        self.assertEqual(parsed.shortcode, "Chunk8-jurw")
        self.assertEqual(parsed.comment_id, "18102822571970750")
        self.assertEqual(parsed.post_url, "https://www.instagram.com/p/Chunk8-jurw/")
        self.assertEqual(parse_instagram_comment_url(query_link).comment_id, "18102822571970750")
        reply = parse_instagram_comment_url(reply_link)
        self.assertEqual(reply.comment_id, "18123394012620235")
        self.assertTrue(reply.is_reply)
        self.assertTrue(is_instagram_comment_url(path_link))
        self.assertFalse(is_instagram_comment_url("https://www.instagram.com/p/Chunk8-jurw/"))
        with self.assertRaises(InstagramCommentError):
            parse_instagram_comment_url("https://example.com/p/Chunk8-jurw/c/18102822571970750/")
        self.assertEqual(normalize_comment_id("18102822571970750"), "18102822571970750")
        self.assertEqual(normalize_comment_id("not-a-comment"), "")
        media_menu = bot.media_download_reply_menu()
        media_texts = [button.text for row in media_menu.keyboard for button in row]
        self.assertIn("💬 کپی متن کامنت اینستاگرام", media_texts)
        self.assertIn("💬 کپی متن کامنت اینستاگرام", bot.REPLY_BUTTON_LABELS)
        self.assertTrue(bot.contains_media_link("https://www.instagram.com/reel/abc/"))
        self.assertTrue(bot.contains_media_link("https://cdn.example.com/video.mp4"))
        self.assertFalse(bot.contains_media_link("https://example.com/article"))
        self.assertFalse(hasattr(bot, "auto_social_media_download"))
        self.assertFalse(hasattr(bot, "auto_direct_media_download"))

    def test_instagram_graphql_pagination_finds_older_comment(self):
        class FakeResponse:
            status_code = 200

            def __init__(self, body):
                self.body = body

            def json(self):
                return self.body

        class FakeSession:
            def __init__(self):
                self.calls = []

            def post(self, _url, data, headers, timeout):
                variables = json.loads(data["variables"])
                self.calls.append(variables)
                if len(self.calls) == 1:
                    node = {"pk": "10000000000000001", "text": "اول", "user": {"username": "a"}}
                    connection = {
                        "edges": [{"node": node}],
                        "page_info": {"has_next_page": True, "end_cursor": "cursor-1"},
                    }
                else:
                    node = {"pk": "10000000000000002", "text": "کامنت قدیمی", "user": {"username": "b"}}
                    connection = {
                        "edges": [{"node": node}],
                        "page_info": {"has_next_page": False, "end_cursor": None},
                    }
                return FakeResponse({"data": {instagram_comments.COMMENT_GRAPHQL_CONNECTION: connection}})

            def close(self):
                return None

        session = FakeSession()

        class FakeCurl:
            @staticmethod
            def Session(**_kwargs):
                return session

        old_curl, old_id = instagram_comments.curl_requests, instagram_comments._id_to_pk
        instagram_comments.curl_requests = FakeCurl
        instagram_comments._id_to_pk = lambda _shortcode: 123
        try:
            link = parse_instagram_comment_url(
                "https://www.instagram.com/p/Chunk8-jurw/c/10000000000000002/"
            )
            result = instagram_comments._extract_comment_graphql_sync(link)
        finally:
            instagram_comments.curl_requests = old_curl
            instagram_comments._id_to_pk = old_id
        self.assertEqual(result.text, "کامنت قدیمی")
        self.assertEqual(session.calls[1]["after"], "cursor-1")

    def test_instagram_comment_error_path_uses_inline_keyboard(self):
        class Waiting:
            def __init__(self):
                self.edit_kwargs = None

            async def edit_text(self, text, **kwargs):
                self.edit_kwargs = {"text": text, **kwargs}
                return self

        class FakeMessage:
            def __init__(self):
                self.from_user = SimpleNamespace(id=123456)
                self.text = "https://www.instagram.com/p/Chunk8-jurw/c/18102822571970750/"
                self.waiting = Waiting()

            async def answer(self, text, **kwargs):
                self.waiting.answer = (text, kwargs)
                return self.waiting

        async def failing_extractor(_url):
            raise InstagramCommentError("platform_blocked", "اینستاگرام موقتاً محدود کرده")

        original = bot.extract_instagram_comment
        # edit_text only accepts InlineKeyboardMarkup; ReplyKeyboardMarkup here
        # used to crash the handler and leave the «در حال جستجو» message forever.
        message = FakeMessage()
        message.waiting.edit_kwargs = None
        bot.extract_instagram_comment = failing_extractor
        try:
            asyncio.run(bot.copy_instagram_comment_from_message(message))
        finally:
            bot.extract_instagram_comment = original
        self.assertEqual(
            message.waiting.edit_kwargs["reply_markup"].__class__.__name__,
            "InlineKeyboardMarkup",
        )

    def test_direct_upload_supports_many_formats(self):
        from media_service import is_direct_upload_allowed
        allowed = [
            ("application/vnd.android.package-archive", "app.apk"),
            ("application/x-msdownload", "setup.exe"),
            ("application/octet-stream", "installer.msi"),
            ("application/octet-stream", "setup.apk"),
            ("application/octet-stream", "book.epub"),
            ("application/octet-stream", "archive.7z"),
            ("application/octet-stream", "package.deb"),
            ("application/octet-stream", "font.ttf"),
            ("application/octet-stream", "video.mkv"),
            ("audio/mpeg", "song.mp3"),
            ("audio/flac", "song.flac"),
            ("video/mp4", "movie.mp4"),
            ("application/pdf", "doc.pdf"),
            ("application/msword", "doc.doc"),
            ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "doc.docx"),
            ("application/vnd.ms-excel", "sheet.xls"),
            ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "sheet.xlsx"),
            ("application/zip", "files.zip"),
            ("application/x-rar-compressed", "files.rar"),
            ("text/vtt", "sub.vtt"),
            ("font/woff2", "font.woff2"),
            ("text/plain", "notes.txt"),
            ("application/octet-stream", "data.json"),
        ]
        for mime, name in allowed:
            self.assertTrue(is_direct_upload_allowed(mime, name), f"{mime} / {name}")
        blocked = [
            ("text/html", "page.html"),
            ("text/html", "evil.exe"),
            ("text/html", "app.apk"),
            ("application/octet-stream", "file.unknownext"),
            ("text/html", ""),
        ]
        for mime, name in blocked:
            self.assertFalse(is_direct_upload_allowed(mime, name), f"{mime} / {name}")

    def test_social_url_supports_many_platforms(self):
        from media_service import is_social_url, looks_like_direct_media_url
        for url in [
            "https://www.dailymotion.com/video/x8abc",
            "https://www.twitch.tv/videos/1234567890",
            "https://soundcloud.com/artist/track",
            "https://drive.google.com/file/d/abc/view",
            "https://www.dropbox.com/s/xyz/file.mp4",
            "https://archive.org/details/some-movie",
            "https://vk.com/video-123_456",
            "https://ok.ru/video/12345",
            "https://rutube.ru/video/abc/",
            "https://bilibili.com/video/BV1xx/",
            "https://streamable.com/abcde",
            "https://rumble.com/vabcdef/",
            "https://odysee.com/@channel/video",
            "https://www.instagram.com/reel/abc/",
            "https://youtu.be/test",
            "https://vm.tiktok.com/xyz/",
        ]:
            self.assertTrue(is_social_url(url), url)
        self.assertFalse(is_social_url("https://example.com/random"))
        self.assertTrue(looks_like_direct_media_url("https://cdn.example.com/video.mp4?token=1"))
        self.assertTrue(looks_like_direct_media_url("https://cdn.example.com/app.apk"))
        self.assertFalse(looks_like_direct_media_url("https://example.com/page.html"))

    def test_html_sniffer_blocks_pages_and_allows_binary(self):
        from media_service import looks_like_html
        pages = [
            b"<!DOCTYPE html><html>...",
            b"<!doctype html>",
            b"<html lang=\"fa\">",
            b"<HTML><head><title>x</title></head>",
            b"\n\n  <head>meta",
        ]
        for raw in pages:
            self.assertTrue(looks_like_html(raw), raw[:40])
        binaries = [
            b"%PDF-1.7",
            b"PK\x03\x04archive",
            b"\x1f\x8b\x08compressed",
            b"\x00\x00\x00\x18ftypmp42",
            b"ID3\x03\x00mp3",
            b"\x89PNG\r\n\x1a\n",
            b"\x7fELF binary",
            b"{\"key\": \"json\"}",
            b"",
        ]
        for raw in binaries:
            self.assertFalse(looks_like_html(raw), raw[:40])

    def test_auto_media_patterns_match_expanded_sources(self):
        self.assertTrue(bot.SOCIAL_MEDIA_URL_RE.match("https://www.dailymotion.com/video/x8"))
        self.assertTrue(bot.SOCIAL_MEDIA_URL_RE.match("https://drive.google.com/file/d/abc/view"))
        self.assertTrue(bot.SOCIAL_MEDIA_URL_RE.match("https://twitter.com/user/status/1"))
        self.assertTrue(bot.SOCIAL_MEDIA_URL_RE.match("https://www.dropbox.com/s/abc/file.zip"))
        self.assertIsNone(bot.SOCIAL_MEDIA_URL_RE.match("https://example.com/plain"))
        self.assertTrue(bot.DIRECT_MEDIA_URL_RE.match("https://cdn.site.com/clip.mp4?x=1"))
        self.assertTrue(bot.DIRECT_MEDIA_URL_RE.match("https://cdn.site.com/app.apk"))
        self.assertIsNone(bot.DIRECT_MEDIA_URL_RE.match("https://site.com/watch?v=abc"))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is installed in the Railway Docker image")
    def test_compress_video_to_fit_and_audio_extraction(self):
        from media_service import compress_video_to_fit
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "src.mp4"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                 "-i", "color=c=red:s=640x360:d=3", "-f", "lavfi",
                 "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
                 "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "64k", str(source)],
                capture_output=True, timeout=120,
            )
            self.assertEqual(proc.returncode, 0)
            target = Path(folder) / "fit.mp4"
            ok = compress_video_to_fit(str(source), str(target), 150 * 1024)
            self.assertTrue(ok)
            self.assertLessEqual(target.stat().st_size, 150 * 1024)
            mp3 = Path(folder) / "out.mp3"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                 "-vn", "-c:a", "libmp3lame", "-q:a", "5", str(mp3)],
                capture_output=True, timeout=120,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertGreater(mp3.stat().st_size, 0)

    def test_social_downloader_impersonation_and_error_classification(self):
        options = social_download_options("/tmp/ajor-test", 48 * 1024 * 1024)
        self.assertEqual(options["impersonate"].client, "chrome")
        self.assertTrue(options["noprogress"])
        blocked = classify_social_download_error(Exception("Sign in to confirm you're not a bot"))
        self.assertEqual(blocked.reason, "platform_blocked")
        empty = classify_social_download_error(Exception("Instagram sent an empty media response"))
        self.assertEqual(empty.reason, "platform_blocked")
        rate = classify_social_download_error(Exception("HTTP Error 429: Too Many Requests"))
        self.assertEqual(rate.reason, "platform_blocked")
        private = classify_social_download_error(Exception("This private video requires authentication"))
        self.assertEqual(private.reason, "private_or_restricted")
        # صفحه رسانه و بخش موسیقی در مینی اپ
        html = Path("webapp/index.html").read_text()
        self.assertIn('data-page="media"', html)
        self.assertIn('data-page="music"', html)
        # پنل تاریخچه رسانه برای حریم خصوصی حذف شده
        self.assertNotIn("mediaJobsList", html)

    def test_admin_balance_panel_exposes_all_three_balances(self):
        finance = {button.text for row in bot.admin_finance_reply_menu().keyboard for button in row}
        self.assertIn("💰 افزایش موجودی کاربر", finance)
        self.assertEqual(set(bot.ADMIN_BALANCE_FIELDS), {"xp", "coins", "wallet_toman"})
        self.assertGreaterEqual(bot.MAX_ADMIN_BALANCE_ADJUSTMENT, 100_000_000_000)

    def test_menus_keep_existing_and_new_features(self):
        ai = {button.text for row in bot.ai_reply_menu().keyboard for button in row}
        tools = {button.text for row in bot.tools_reply_menu().keyboard for button in row}
        self.assertTrue({"💬 چت هوشمند", "🎨 ساخت تصویر", "👁 تحلیل تصویر", "🎙 ویس به متن"} <= ai)
        self.assertTrue({"📥 مرکز دانلود و آپلود", "📱 QR ساز", "🎨 گیف و استیکرساز", "⏰ یادآور هوشمند", "🛡 بررسی امنیت لینک", "🕛 00:00", "🌅 صبح بخیر"} <= tools)
        main_reply = {button.text for row in bot.chat_reply_menu().keyboard for button in row}
        self.assertNotIn("📱 QR ساز", main_reply)
        support = {button.text for row in bot.support_reply_menu().keyboard for button in row}
        self.assertIn("👤 پروفایل من", support)
        download = {button.text for row in bot.media_download_reply_menu().keyboard for button in row}
        self.assertTrue({"📸 دانلود اینستاگرام", "🎵 دانلود تیک‌تاک", "🔗 آپلود فایل از URL", "📋 دانلودهای اخیر"} <= download)
        media = {button.text for row in bot.media_maker_reply_menu().keyboard for button in row}
        self.assertTrue({"🪄 ساخت استیکر", "🎞 ساخت گیف", "📦 پک استیکرهای من"} <= media)
        news = {button.text for row in bot.news_reply_menu().keyboard for button in row}
        self.assertTrue({"📰 اخبار زنده", "🧠 دانستنی عجیب", "🧩 معمای فوری", "🎭 این یا اون", "⚡ چالش ۳۰ ثانیه", "🤡 میم متنی"} <= news)

    def test_hokm_miniapp_uses_hakem_order_and_grouped_hand(self):
        js = Path("webapp/hokm.js").read_text()
        css = Path("webapp/hokm.css").read_text()
        self.assertIn("function sortHand(hand)", js)
        self.assertIn("const firstLeader = S.caller", js)
        self.assertIn("suit-break", js)
        self.assertIn(".hokm-card.suit-break", css)

    def test_miniapp_has_matching_pages_and_unique_ids(self):
        parser = IdAndPageParser()
        parser.feed(Path("webapp/index.html").read_text())
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        # «حکم»، «تقویم»، «بازی‌های رومیزی»، «موسیقی» و «فروشگاه» صفحه‌های داخلی هستند نه تب ناوبری
        self.assertEqual(parser.pages - {"hokm", "calendar", "boardgames", "ajorchin", "snake", "music", "shop"}, parser.nav)
        self.assertIn("ai", parser.pages)
        self.assertIn("hokm", parser.pages)
        self.assertIn("calendar", parser.pages)
        self.assertIn("boardgames", parser.pages)
        self.assertIn("music", parser.pages)
        self.assertIn("shop", parser.pages)

    def test_rss_parser_returns_safe_live_item(self):
        payload = b'<rss><channel><item><title>Test headline</title><link>https://example.com/news</link><description>Short summary</description><pubDate>Wed, 30 Jul 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        items = bot.parse_rss_items(payload, "Example", "world", "x")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://example.com/news")

    def test_rss_parser_rejects_xml_entities(self):
        payload = b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss><channel><item><title>&x;</title></item></channel></rss>'
        with self.assertRaises(DefusedXmlException):
            bot.parse_rss_items(payload, "test", "world", "x")

    def test_allowed_domain_matching_is_host_based(self):
        self.assertTrue(bot.is_allowed_url("https://news.example.com/post", ["example.com"]))
        self.assertFalse(bot.is_allowed_url("https://example.com.evil.test/post", ["example.com"]))
        self.assertFalse(bot.is_allowed_url("https://evil-example.com", ["example.com"]))

    def test_repost_brand_and_hidden_proxy_links(self):
        text = "Click proxy now"
        proxy_url = "https://t.me/proxy?server=1.2.3.4&port=443&secret=abc"
        entity = MessageEntity(type="text_link", offset=6, length=5, url=proxy_url)
        message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=1, type="private"),
            text=text,
            entities=[entity],
        )
        payload = bot.extract_repost_payload(message)
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn('<a href="https://t.me/proxy?', payload["text"])
        self.assertIn(">proxy</a>", payload["text"])
        self.assertNotIn("🔗 پروکسی:", payload["text"])
        self.assertIn("@Ajor_pareh", payload["text"])
        no_id = bot.build_branded_caption("یک پست بدون آیدی", 4096)
        self.assertIn("@Ajor_pareh", no_id)

    def test_sticker_pack_name_and_webp_are_valid(self):
        name = bot.user_sticker_pack_name(466050034, 2, "Ajorparehbot")
        self.assertRegex(name, r"^[a-z0-9_]+_by_ajorparehbot$")
        self.assertLessEqual(len(name), 64)
        source = io.BytesIO()
        Image.new("RGB", (900, 500), "#8a3ffc").save(source, format="PNG")
        result = bot.make_sticker_webp(source.getvalue())
        self.assertLessEqual(len(result), 512 * 1024)
        with Image.open(io.BytesIO(result)) as sticker:
            self.assertEqual(sticker.format, "WEBP")
            self.assertEqual(sticker.size, (512, 512))

    def test_service_prices_and_discount(self):
        original_settings = dict(bot.service_shop_settings)
        try:
            bot.service_shop_settings.update({"offer_active": False, "offer_percent": 0, "offer_expires_at": None})
            self.assertEqual(bot.service_plan_price(1)[:2], (60_000, 60_000))
            self.assertEqual(bot.service_plan_price(12)[:2], (500_000, 500_000))
            bot.service_shop_settings.update({"offer_active": True, "offer_percent": 50, "offer_title": "آخرشب", "offer_expires_at": datetime.now(timezone.utc) + timedelta(hours=1)})
            self.assertEqual(bot.service_plan_price(3)[1], 75_000)
        finally:
            bot.service_shop_settings.clear(); bot.service_shop_settings.update(original_settings)

    def test_flexible_gift_reward_parser(self):
        self.assertEqual(bot.parse_promo_rewards("100"), {"xp": 100})
        rewards = bot.parse_promo_rewards("xp=50,coins=20,ai_text=5,ai_image=1,badge=badge_neon")
        self.assertEqual(rewards["xp"], 50)
        self.assertEqual(rewards["coins"], 20)
        self.assertEqual(rewards["badge"], "badge_neon")
        self.assertIn("20 سکه", bot.promo_reward_summary(rewards))
        with self.assertRaises(ValueError):
            bot.parse_promo_rewards("sticker,gif")

    def test_builtin_reward_missions_cover_real_events(self):
        self.assertGreaterEqual(len(bot.BUILTIN_MISSIONS), 7)
        mission_types = {item["type"] for item in bot.BUILTIN_MISSIONS}
        self.assertTrue({"referrals", "reactions", "reviews", "games", "ai_requests", "voice_transcriptions"} <= mission_types)
        self.assertEqual(bot.mission_progress({"channel_reaction_count": 5}, {"type": "reactions"}), 5)
        html = Path("webapp/index.html").read_text()
        self.assertIn('id="missionList"', html)

    def test_demo_reviews_are_explicitly_labeled(self):
        self.assertEqual(len(bot.DEMO_REVIEWS), 20)
        self.assertTrue(all(item.get("demo") is True for item in bot.DEMO_REVIEWS))
        rating, text = bot.parse_review_input("4 | چالش‌ها خیلی خوب بودن")
        self.assertEqual(rating, 4)
        self.assertIn("چالش", text)

    def test_referral_ai_economy_bounds(self):
        self.assertIsNone(bot.validate_economy_setting_value("referral_ai_text_bonus", 1))
        self.assertIsNotNone(bot.validate_economy_setting_value("referral_ai_text_bonus", 6))
        self.assertIsNone(bot.validate_economy_setting_value("referral_ai_bonus_cap", 10))
        self.assertIsNotNone(bot.validate_economy_setting_value("referral_ai_bonus_cap", 51))

    def test_public_landing_seo_and_bot_profile_limits(self):
        landing = Path("webapp/landing.html").read_text()
        self.assertEqual(landing.count("<h1"), 1)
        self.assertIn('<link rel="canonical" href="https://ajor2-production.up.railway.app/"', landing)
        self.assertIn("https://t.me/Ajorparehbot?start=website", landing)
        structured = re.search(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', landing, flags=re.S
        )
        self.assertIsNotNone(structured)
        graph = json.loads(structured.group(1))["@graph"]
        self.assertTrue({"WebSite", "SoftwareApplication", "FAQPage"} <= {item["@type"] for item in graph})
        self.assertEqual({item["language_code"] for item in bot.TELEGRAM_PROFILE_LOCALIZATIONS}, {None, "fa", "en"})
        for profile in bot.TELEGRAM_PROFILE_LOCALIZATIONS:
            self.assertLessEqual(len(profile["name"]), 64)
            self.assertLessEqual(len(profile["short_description"]), 120)
            self.assertLessEqual(len(profile["description"]), 512)

    def test_provider_defaults(self):
        config = AIConfig()
        self.assertEqual(config.gemini_model, "gemini-3.6-flash")
        self.assertEqual(config.groq_model, "openai/gpt-oss-120b")
        self.assertEqual(config.openrouter_model, "openrouter/free")
        self.assertEqual(config.groq_transcription_model, "whisper-large-v3-turbo")


class AsyncCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_wallet_adjustment_is_audited_and_never_goes_negative(self):
        original_users = bot.users_col
        original_transactions = bot.wallet_transactions_col
        original_bot = bot.bot
        original_audit = bot.audit_admin_action
        fake_users = FakeBalanceUsers({"_id": 42, "name": "Test", "wallet_toman": 1_000})
        fake_transactions = FakeInsertCollection()
        fake_bot = FakeMediaPreviewBot()
        audits = []

        async def fake_audit(*args):
            audits.append(args)

        bot.users_col = fake_users
        bot.wallet_transactions_col = fake_transactions
        bot.bot = fake_bot
        bot.audit_admin_action = fake_audit
        try:
            added = await bot.apply_admin_balance_adjustment(1, 42, "wallet_toman", 100_000_000_000)
            rejected = await bot.apply_admin_balance_adjustment(1, 42, "wallet_toman", -200_000_000_000)
        finally:
            bot.users_col = original_users
            bot.wallet_transactions_col = original_transactions
            bot.bot = original_bot
            bot.audit_admin_action = original_audit
        self.assertTrue(added["ok"])
        self.assertEqual(added["before"], 1_000)
        self.assertEqual(added["after"], 100_000_001_000)
        self.assertEqual(rejected["reason"], "insufficient")
        self.assertEqual(len(fake_transactions.documents), 1)
        self.assertTrue(audits)
        self.assertIn("بروزرسانی شد", fake_bot.messages[0][1])

    async def test_telegram_profile_metadata_sync_is_idempotent(self):
        original_bot = bot.bot
        original_synced = bot.telegram_profile_synced
        fake = FakeProfileBot()
        bot.bot = fake
        bot.telegram_profile_synced = False
        try:
            await bot.configure_telegram_profile()
            self.assertTrue(bot.telegram_profile_synced)
            self.assertEqual(len(fake.calls), 9)
            await bot.configure_telegram_profile()
            self.assertEqual(len(fake.calls), 9)
            self.assertEqual(fake.names[None], "🧱 آجُرپاره | هوش مصنوعی و ابزار تلگرام")
            self.assertIn("Persian Telegram super bot", fake.descriptions["en"])
        finally:
            bot.bot = original_bot
            bot.telegram_profile_synced = original_synced

    async def test_platform_block_sends_watchable_preview_instead_of_failure(self):
        original_bot = bot.bot
        original_jobs = bot.media_jobs_col
        original_log = bot.log_activity
        fake_bot = FakeMediaPreviewBot()
        fake_jobs = FakeUpdateCollection()
        logged = []

        async def fake_log_activity(*args):
            logged.append(args)

        bot.bot = fake_bot
        bot.media_jobs_col = fake_jobs
        bot.log_activity = fake_log_activity
        try:
            result = await bot.send_media_preview_fallback(
                {"_id": "testjob", "user_id": 42, "mode": "social", "url": "https://youtu.be/public"},
                MediaServiceError("platform_blocked", "blocked"),
            )
            private_result = await bot.send_media_preview_fallback(
                {"_id": "instagram-job", "user_id": 42, "mode": "social", "url": "https://www.instagram.com/reel/example/"},
                MediaServiceError("private_or_restricted", "restricted"),
            )
        finally:
            bot.bot = original_bot
            bot.media_jobs_col = original_jobs
            bot.log_activity = original_log
        self.assertTrue(result)
        # برای یوتیوب متن «آنلاین تماشا کن» می‌آید
        self.assertIn("آنلاین تماشا کنی", fake_bot.messages[0][1])
        self.assertTrue(private_result)
        self.assertIn("Instagram", fake_bot.messages[-1][1])
        self.assertEqual(fake_jobs.calls[0][1]["$set"]["status"], "preview")
        self.assertTrue(logged)

    async def test_publication_menu_command_is_not_published(self):
        uid = 466050034
        message = FakeControlMessage(uid, "⚙️ پنل مدیریت")
        bot.instant_repost_sessions[uid] = []
        try:
            handled = await bot.pause_publication_for_control(message)
        finally:
            bot.instant_repost_sessions.pop(uid, None)
        self.assertTrue(handled)
        self.assertNotIn(uid, bot.instant_repost_sessions)
        self.assertIn("منتشر نشد", message.answers[0][0])

    async def test_maintenance_waiter_is_recorded(self):
        original = bot.users_col
        fake = FakeUpdateCollection()
        bot.users_col = fake
        try:
            await bot.mark_maintenance_waiter(SimpleNamespace(id=42, full_name="Test User", username="test"))
        finally:
            bot.users_col = original
        self.assertEqual(fake.calls[0][0], {"_id": 42})
        self.assertTrue(fake.calls[0][1]["$set"]["maintenance_notify_pending"])
        self.assertTrue(fake.calls[0][2]["upsert"])

    async def test_per_user_and_referral_quota_bonuses(self):
        bonus_col = FakeBonusCollection({
            "ai_admin_text_bonus": 15,
            "ai_admin_image_bonus": 3,
            "ai_referral_text_bonus": 7,
            "ai_gift_text_bonus": 4,
            "ai_gift_image_bonus": 1,
        })
        service = AIService(
            AIConfig(daily_text_limit=25, daily_image_limit=2),
            bonus_col=bonus_col,
        )
        quota = await service.quota_snapshot(42)
        self.assertEqual(quota["text_bonus"], 26)
        self.assertEqual(quota["image_bonus"], 4)
        self.assertEqual(quota["text_limit"], 51)
        self.assertEqual(quota["image_limit"], 6)
        self.assertEqual(quota["referral_text_bonus"], 7)
        self.assertEqual(quota["gift_text_bonus"], 4)

    async def test_text_fallback_order(self):
        service = AIService(AIConfig(gemini_api_key="g", groq_api_key="q", openrouter_api_key="o"))
        service.session = SimpleNamespace(closed=False)
        calls = []

        async def gemini_fail(self, *args):
            calls.append("gemini")
            raise ProviderError(status=429, retryable=True)

        async def openai_call(self, provider, *args):
            calls.append(provider)
            if provider == "groq":
                raise ProviderError(status=503, retryable=True)
            return "ok"

        service._gemini_text = MethodType(gemini_fail, service)
        service._openai_text = MethodType(openai_call, service)
        result = await service.ask_text("test", system_prompt="test", unlimited=True, enforce_quota=False)
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "openrouter")
        self.assertEqual(calls, ["gemini", "groq", "openrouter"])

    async def test_root_serves_landing_to_browsers_and_health_to_monitors(self):
        app = web.Application(middlewares=[bot.security_headers_middleware])
        app.router.add_get("/", bot.root_landing)
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            browser = await client.get("/", headers={"Accept": "text/html"})
            self.assertEqual(browser.status, 200)
            self.assertIn("ربات آجُرپاره", await browser.text())
            self.assertEqual(browser.headers.get("Cache-Control"), "no-cache")
            generic = await client.get("/")
            self.assertEqual(generic.status, 200)
            self.assertIn("ربات آجُرپاره", await generic.text())
            monitor = await client.get("/", headers={"Accept": "application/json"})
            self.assertEqual(monitor.status, 200)
            self.assertTrue((await monitor.json())["ok"])
        finally:
            await client.close()

    async def test_unauthenticated_ai_api_has_security_headers(self):
        app = web.Application(middlewares=[bot.security_headers_middleware])
        app.router.add_get("/api/ai/status", bot.miniapp_ai_status_api)
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            response = await client.get("/api/ai/status")
            self.assertEqual(response.status, 401)
            self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))
        finally:
            await client.close()

    async def test_private_url_is_rejected(self):
        with self.assertRaises(MediaServiceError):
            await validate_public_url("http://127.0.0.1/private.mp4")
        with self.assertRaises(MediaServiceError):
            await validate_public_url("http://localhost/file.zip")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is installed in the Railway Docker image")
    async def test_photo_to_telegram_animation(self):
        source = io.BytesIO()
        Image.new("RGB", (640, 420), "#22e6e2").save(source, format="PNG")
        result = await bot.make_telegram_animation(source.getvalue(), ".png", from_photo=True)
        self.assertLess(len(result), 19 * 1024 * 1024)
        self.assertIn(b"ftyp", result[:64])

    async def test_audio_falls_back_from_groq_to_gemini(self):
        service = AIService(AIConfig(groq_api_key="q", gemini_api_key="g"))
        service.session = SimpleNamespace(closed=False)
        calls = []

        async def groq_fail(self, *args):
            calls.append("groq")
            raise ProviderError(status=429, retryable=True)

        async def gemini_ok(self, *args):
            calls.append("gemini")
            return "متن آزمایشی"

        service._groq_transcribe = MethodType(groq_fail, service)
        service._gemini_transcribe = MethodType(gemini_ok, service)
        result = await service.transcribe_audio(
            b"fake-audio", "audio/ogg", "voice.ogg", user_id=42, unlimited=True
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(calls, ["groq", "gemini"])


    def test_ajorchin_game_reward(self):
        """🧱 آجرچین reward scales with score."""
        self.assertEqual(bot.calculate_game_reward("ajorchin", 0), 20)
        r = bot.calculate_game_reward("ajorchin", 5000)
        self.assertGreaterEqual(r, 50)
        self.assertLessEqual(r, 200)
        self.assertEqual(bot.calculate_game_reward("ajorchin", 100000), 200)
        self.assertEqual(bot.calculate_game_reward("unknown_game", 100), 0)

    def test_snake_game_reward(self):
        """🐍 مار غذایی reward scales with score."""
        self.assertEqual(bot.calculate_game_reward("snake", 0), 20)
        r = bot.calculate_game_reward("snake", 2000)
        self.assertGreaterEqual(r, 30)
        self.assertLessEqual(r, 200)
        self.assertEqual(bot.calculate_game_reward("snake", 100000), 200)

    def test_duel_room_creation(self):
        """⚔️ Duel rooms can be created."""
        room = {
            "room_id": "test1234", "type": "tap", "phase": "waiting",
            "players": {"123": {"name": "Player1", "score": 0, "submitted": False}},
            "round": 1, "max_rounds": 3, "questions": [{"type": "tap", "instruction": "tap!"}],
            "updated_at": 0,
        }
        bot.duel_rooms["test1234"] = room
        self.assertIn("test1234", bot.duel_rooms)
        self.assertEqual(bot.duel_rooms["test1234"]["phase"], "waiting")
        bot.duel_rooms.pop("test1234", None)

    def test_wheel_table_has_vip_items(self):
        """🎡 Wheel has VIP items (XP, AI quota, badge)."""
        has_xp = any(item.get("xp") for item in bot.WHEEL_TABLE)
        has_ai = any(item.get("ai_quota") for item in bot.WHEEL_TABLE)
        has_badge = any(item.get("badge") for item in bot.WHEEL_TABLE)
        self.assertTrue(has_xp, "Wheel should have XP reward")
        self.assertTrue(has_ai, "Wheel should have AI quota reward")
        self.assertTrue(has_badge, "Wheel should have badge reward")

    def test_wheel_weights_sum_positive(self):
        """🎡 Wheel weights are all positive."""
        for item in bot.WHEEL_TABLE:
            self.assertGreater(item["weight"], 0, f"Wheel item '{item['label']}' has non-positive weight")

    def test_supported_social_domains_count(self):
        """📡 Supported social domains > 100."""
        from media_service import SUPPORTED_SOCIAL_DOMAINS
        self.assertGreater(len(SUPPORTED_SOCIAL_DOMAINS), 100, "Should support 100+ domains")

    def test_calculate_game_reward_all_games(self):
        """🎮 All game types return valid rewards."""
        games = ["reflex", "emoji", "fact", "memory", "tap", "reverse", "laugh", "ajorchin", "snake"]
        for game in games:
            r = bot.calculate_game_reward(game, 500)
            self.assertGreater(r, 0, f"{game} should have positive reward")
            self.assertLessEqual(r, 200, f"{game} reward should be <= 200")
        # Unknown game should return 0
        self.assertEqual(bot.calculate_game_reward("unknown", 500), 0)

    def test_normalize_chat_text(self):
        """🔤 Chat text normalization works."""
        result = bot.normalize_chat_text("سلاممم رفیق خستم")
        self.assertIn("سلام", result)
        self.assertIn("خسته ام", result)

    def test_detect_profanity(self):
        """🔤 Profanity detection works."""
        matches = bot.detect_profanity("کیر")
        self.assertTrue(len(matches) > 0)
        clean = bot.detect_profanity("سلام رفیق")
        self.assertEqual(len(clean), 0)

    def test_safe_eval_basic(self):
        """🧮 Calculator safety."""
        self.assertEqual(bot.safe_eval("2+3"), 5)
        self.assertEqual(bot.safe_eval("10*5"), 50)
        with self.assertRaises(ValueError):
            bot.safe_eval("__import__('os')")

    def test_is_valid_card_number(self):
        """💳 Card number validation."""
        self.assertTrue(bot.is_valid_card_number("4111111111111111"))  # Visa test number
        self.assertFalse(bot.is_valid_card_number("1111-1111-1111-1111"))
        self.assertFalse(bot.is_valid_card_number("123"))


if __name__ == "__main__":
    unittest.main()
