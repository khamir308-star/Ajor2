"""Resilient multi-provider AI gateway for Ajorpareh.

Secrets are read only from environment variables. This module never logs API
keys, request headers, full prompts, or provider response bodies.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import aiohttp
from pymongo.errors import DuplicateKeyError

log = logging.getLogger("bot.ai")
TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,120}$")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _clean_model(value: str, default: str) -> str:
    model = (value or default).strip()
    model = model.removeprefix("models/")
    return model if MODEL_PATTERN.fullmatch(model) else default


@dataclass(slots=True)
class AIConfig:
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    pollinations_image_enabled: bool = True
    pollinations_image_model: str = "flux"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_transcription_model: str = "whisper-large-v3-turbo"
    cerebras_api_key: str = ""
    cerebras_model: str = "gpt-oss-120b"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    daily_text_limit: int = 25
    daily_image_limit: int = 2
    max_user_text_bonus: int = 200
    max_user_image_bonus: int = 20
    max_referral_text_bonus: int = 50
    provider_timeout_seconds: int = 18
    total_timeout_seconds: int = 45
    image_timeout_seconds: int = 90
    max_input_chars: int = 6000
    max_output_tokens: int = 900

    @classmethod
    def from_env(cls) -> AIConfig:
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=_clean_model(os.getenv("GEMINI_MODEL", ""), "gemini-3.6-flash"),
            gemini_image_model=_clean_model(
                os.getenv("GEMINI_IMAGE_MODEL", ""), "gemini-3.1-flash-image"
            ),
            pollinations_image_enabled=_env_bool("POLLINATIONS_IMAGE_ENABLED", True),
            pollinations_image_model=_clean_model(
                os.getenv("POLLINATIONS_IMAGE_MODEL", ""), "flux"
            ),
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=_clean_model(os.getenv("GROQ_MODEL", ""), "openai/gpt-oss-120b"),
            groq_transcription_model=_clean_model(
                os.getenv("GROQ_TRANSCRIPTION_MODEL", ""), "whisper-large-v3-turbo"
            ),
            cerebras_api_key=os.getenv("CEREBRAS_API_KEY", "").strip(),
            cerebras_model=_clean_model(os.getenv("CEREBRAS_MODEL", ""), "gpt-oss-120b"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            openrouter_model=_clean_model(
                os.getenv("AI_MODEL", os.getenv("OPENROUTER_MODEL", "")),
                "openrouter/free",
            ),
            daily_text_limit=_env_int("AI_DAILY_TEXT_LIMIT", 25, 1, 500),
            daily_image_limit=_env_int("AI_DAILY_IMAGE_LIMIT", 2, 1, 50),
            max_user_text_bonus=_env_int("AI_MAX_USER_TEXT_BONUS", 200, 0, 1000),
            max_user_image_bonus=_env_int("AI_MAX_USER_IMAGE_BONUS", 20, 0, 100),
            max_referral_text_bonus=_env_int("AI_MAX_REFERRAL_TEXT_BONUS", 50, 0, 500),
            provider_timeout_seconds=_env_int("AI_PROVIDER_TIMEOUT_SECONDS", 18, 5, 60),
            total_timeout_seconds=_env_int("AI_TOTAL_TIMEOUT_SECONDS", 45, 10, 180),
            image_timeout_seconds=_env_int("AI_IMAGE_TIMEOUT_SECONDS", 90, 20, 240),
            max_input_chars=_env_int("AI_MAX_INPUT_CHARS", 6000, 500, 20000),
            max_output_tokens=_env_int("AI_MAX_OUTPUT_TOKENS", 900, 100, 4000),
        )


@dataclass(slots=True)
class AIResult:
    ok: bool
    text: str | None = None
    provider: str | None = None
    model: str | None = None
    reason: str | None = None
    latency_ms: int = 0


@dataclass(slots=True)
class AIImageResult:
    ok: bool
    image: bytes | None = None
    mime_type: str = "image/png"
    caption: str | None = None
    provider: str | None = None
    model: str | None = None
    reason: str | None = None
    latency_ms: int = 0


class ProviderError(Exception):
    def __init__(self, status: int | None = None, retryable: bool = False, reason: str = "provider_error"):
        super().__init__(reason)
        self.status = status
        self.retryable = retryable
        self.reason = reason


class AIService:
    """Provider fallback, quotas, circuit breakers, and usage metrics."""

    def __init__(
        self,
        config: AIConfig,
        usage_col: Any = None,
        metrics_col: Any = None,
        bonus_col: Any = None,
    ):
        self.config = config
        self.usage_col = usage_col
        self.metrics_col = metrics_col
        self.bonus_col = bonus_col
        self.session: aiohttp.ClientSession | None = None
        self._provider_state: dict[str, dict[str, float | int]] = {}
        self._quota_locks: dict[int, asyncio.Lock] = {}
        self._pollinations_lock = asyncio.Lock()
        self._pollinations_last_call = 0.0

    def set_session(self, session: aiohttp.ClientSession | None) -> None:
        self.session = session

    def configured_text_providers(self) -> list[str]:
        providers: list[str] = []
        if self.config.gemini_api_key:
            providers.append("gemini")
        if self.config.groq_api_key:
            providers.append("groq")
        if self.config.cerebras_api_key:
            providers.append("cerebras")
        if self.config.openrouter_api_key:
            providers.append("openrouter")
        return providers

    def public_status(self) -> dict[str, Any]:
        now = time.monotonic()
        text = self.configured_text_providers()
        image_providers: list[str] = []
        if self.config.gemini_api_key:
            image_providers.append("gemini")
        if self.config.pollinations_image_enabled:
            image_providers.append("pollinations")
        return {
            "configured": bool(text),
            "text_providers": text,
            "image_generation": bool(image_providers),
            "image_editing": bool(self.config.gemini_api_key),
            "image_providers": image_providers,
            "circuits": {
                provider: "open" if float(state.get("open_until", 0)) > now else "closed"
                for provider, state in self._provider_state.items()
            },
        }

    @staticmethod
    def _day() -> str:
        return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")

    @staticmethod
    def _expires_at() -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=90)

    def _quota_lock(self, user_id: int) -> asyncio.Lock:
        lock = self._quota_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._quota_locks[user_id] = lock
        return lock

    async def _quota_bonuses(self, user_id: int | None) -> dict[str, int]:
        empty = {"admin_text": 0, "admin_image": 0, "referral_text": 0, "gift_text": 0, "gift_image": 0, "text": 0, "image": 0}
        if user_id is None or self.bonus_col is None:
            return empty
        try:
            user = await self.bonus_col.find_one(
                {"_id": user_id},
                {"ai_admin_text_bonus": 1, "ai_admin_image_bonus": 1, "ai_referral_text_bonus": 1, "ai_gift_text_bonus": 1, "ai_gift_image_bonus": 1},
            ) or {}
        except Exception:
            log.warning("AI bonus quota unavailable for user_id=%s", user_id)
            return empty
        def bounded(field: str, maximum: int) -> int:
            try:
                return max(0, min(maximum, int(user.get(field, 0) or 0)))
            except (TypeError, ValueError):
                return 0

        admin_text = bounded("ai_admin_text_bonus", self.config.max_user_text_bonus)
        admin_image = bounded("ai_admin_image_bonus", self.config.max_user_image_bonus)
        referral_text = bounded("ai_referral_text_bonus", self.config.max_referral_text_bonus)
        gift_text = bounded("ai_gift_text_bonus", self.config.max_user_text_bonus)
        gift_image = bounded("ai_gift_image_bonus", self.config.max_user_image_bonus)
        return {
            "admin_text": admin_text,
            "admin_image": admin_image,
            "referral_text": referral_text,
            "gift_text": gift_text,
            "gift_image": gift_image,
            "text": admin_text + referral_text + gift_text,
            "image": admin_image + gift_image,
        }

    async def quota_snapshot(self, user_id: int, unlimited: bool = False) -> dict[str, int | bool]:
        text_used = 0
        image_used = 0
        bonuses = await self._quota_bonuses(user_id)
        if self.usage_col is not None:
            try:
                doc = await self.usage_col.find_one({"_id": f"{self._day()}:{user_id}"}) or {}
                text_used = max(0, int(doc.get("text_requests", 0)))
                image_used = max(0, int(doc.get("image_requests", 0)))
            except Exception:
                log.warning("AI quota snapshot unavailable for user_id=%s", user_id)
        text_limit = self.config.daily_text_limit + bonuses["text"]
        image_limit = self.config.daily_image_limit + bonuses["image"]
        return {
            "unlimited": unlimited,
            "text_used": text_used,
            "text_limit": text_limit,
            "text_remaining": max(0, text_limit - text_used),
            "image_used": image_used,
            "image_limit": image_limit,
            "image_remaining": max(0, image_limit - image_used),
            "text_bonus": bonuses["text"],
            "image_bonus": bonuses["image"],
            "admin_text_bonus": bonuses["admin_text"],
            "admin_image_bonus": bonuses["admin_image"],
            "referral_text_bonus": bonuses["referral_text"],
            "gift_text_bonus": bonuses["gift_text"],
            "gift_image_bonus": bonuses["gift_image"],
        }

    async def _reserve_quota(self, user_id: int | None, kind: str, unlimited: bool) -> bool:
        if user_id is None or unlimited:
            return True
        if self.usage_col is None:
            # Fail closed if a quota cannot be enforced in production.
            return False
        field = "image_requests" if kind == "image" else "text_requests"
        bonuses = await self._quota_bonuses(user_id)
        limit = (
            self.config.daily_image_limit + bonuses["image"]
            if kind == "image"
            else self.config.daily_text_limit + bonuses["text"]
        )
        doc_id = f"{self._day()}:{user_id}"
        async with self._quota_lock(user_id):
            try:
                result = await self.usage_col.update_one(
                    {
                        "_id": doc_id,
                        "$or": [{field: {"$exists": False}}, {field: {"$lt": limit}}],
                    },
                    {
                        "$inc": {field: 1},
                        "$set": {"updated_at": datetime.now(timezone.utc)},
                        "$setOnInsert": {
                            "user_id": user_id,
                            "day": self._day(),
                            "created_at": datetime.now(timezone.utc),
                            "expires_at": self._expires_at(),
                        },
                    },
                    upsert=True,
                )
                return bool(result.modified_count or result.upserted_id is not None)
            except DuplicateKeyError:
                return False
            except Exception:
                log.warning("AI quota reservation unavailable for user_id=%s", user_id)
                return False

    async def _rollback_quota(self, user_id: int | None, kind: str, unlimited: bool) -> None:
        if user_id is None or unlimited or self.usage_col is None:
            return
        field = "image_requests" if kind == "image" else "text_requests"
        try:
            await self.usage_col.update_one(
                {"_id": f"{self._day()}:{user_id}", field: {"$gt": 0}},
                {"$inc": {field: -1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
            )
        except Exception:
            log.warning("AI quota rollback unavailable for user_id=%s", user_id)

    def _circuit_available(self, provider: str) -> bool:
        state = self._provider_state.get(provider) or {}
        return float(state.get("open_until", 0)) <= time.monotonic()

    def _provider_success(self, provider: str) -> None:
        self._provider_state[provider] = {"failures": 0, "open_until": 0.0}

    def _provider_failure(self, provider: str, status: int | None) -> None:
        state = self._provider_state.setdefault(provider, {"failures": 0, "open_until": 0.0})
        failures = int(state.get("failures", 0)) + 1
        state["failures"] = failures
        if status in {401, 403}:
            state["open_until"] = time.monotonic() + 600
        elif failures >= 3:
            state["open_until"] = time.monotonic() + 120

    async def _metric(
        self,
        provider: str,
        success: bool,
        latency_ms: int,
        status: int | None = None,
        feature: str = "general",
    ) -> None:
        if self.metrics_col is None:
            return
        increments: dict[str, int] = {
            "calls": 1,
            "successes" if success else "failures": 1,
            "latency_ms_total": max(0, latency_ms),
            f"features.{re.sub(r'[^a-z0-9_]', '_', feature.lower())[:40] or 'general'}": 1,
        }
        if status == 429:
            increments["rate_limited"] = 1
        try:
            await self.metrics_col.update_one(
                {"_id": f"{provider}:{self._day()}"},
                {
                    "$inc": increments,
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                    "$setOnInsert": {
                        "provider": provider,
                        "day": self._day(),
                        "created_at": datetime.now(timezone.utc),
                        "expires_at": self._expires_at(),
                    },
                },
                upsert=True,
            )
        except Exception:
            # Metrics must never break a user request.
            pass

    async def _post_json(
        self,
        provider: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> tuple[dict[str, Any], int]:
        if self.session is None or self.session.closed:
            raise ProviderError(reason="session_unavailable")

        last_error: ProviderError | None = None
        for attempt in range(2):
            try:
                timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=min(8, timeout_seconds))
                async with self.session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                    status = response.status
                    if status == 200:
                        try:
                            body = await response.json(content_type=None)
                        except (ValueError, aiohttp.ContentTypeError) as exc:
                            raise ProviderError(status=200, reason="invalid_json") from exc
                        if not isinstance(body, dict):
                            raise ProviderError(status=200, reason="invalid_payload")
                        return body, status
                    # Never log response bodies: providers can echo part of a prompt.
                    retryable = status == 429 or status >= 500
                    last_error = ProviderError(status=status, retryable=retryable)
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                last_error = ProviderError(retryable=True, reason=type(exc).__name__)
            if not last_error.retryable or attempt == 1:
                break
            await asyncio.sleep((0.45 * (2**attempt)) + random.uniform(0.05, 0.25))
        raise last_error or ProviderError()

    @staticmethod
    def _normalize_history(history: list[dict[str, str]] | None, max_chars: int = 12000) -> list[dict[str, str]]:
        newest_first: list[dict[str, str]] = []
        used = 0
        for item in reversed((history or [])[-10:]):
            role = item.get("role", "")
            content = str(item.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            content = content[:3000]
            if used + len(content) > max_chars:
                break
            used += len(content)
            newest_first.append({"role": role, "content": content})
        return list(reversed(newest_first))

    async def _gemini_text(
        self,
        system_prompt: str,
        query: str,
        history: list[dict[str, str]],
    ) -> str:
        model = self.config.gemini_model
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(model, safe='-._')}:generateContent"
        )
        contents = [
            {
                "role": "model" if item["role"] == "assistant" else "user",
                "parts": [{"text": item["content"]}],
            }
            for item in history
        ]
        contents.append({"role": "user", "parts": [{"text": query}]})
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.72,
                "maxOutputTokens": self.config.max_output_tokens,
            },
        }
        body, _ = await self._post_json(
            "gemini",
            url,
            {"x-goog-api-key": self.config.gemini_api_key, "Content-Type": "application/json"},
            payload,
            self.config.provider_timeout_seconds,
        )
        parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()
        if not text:
            raise ProviderError(reason="empty_response")
        return text

    async def _openai_text(
        self,
        provider: str,
        api_key: str,
        model: str,
        url: str,
        system_prompt: str,
        query: str,
        history: list[dict[str, str]],
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": query}]
        token_key = "max_tokens" if provider == "openrouter" else "max_completion_tokens"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.72,
            token_key: self.config.max_output_tokens,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers.update({"HTTP-Referer": "https://ajor2-production.up.railway.app", "X-Title": "Ajorpareh"})
        body, _ = await self._post_json(
            provider, url, headers, payload, self.config.provider_timeout_seconds
        )
        choices = body.get("choices") or []
        text = str(((choices[0].get("message") or {}).get("content") if choices else "") or "").strip()
        if not text:
            raise ProviderError(reason="empty_response")
        return text

    async def ask_text(
        self,
        query: str,
        *,
        user_id: int | None = None,
        feature: str = "general",
        system_prompt: str,
        history: list[dict[str, str]] | None = None,
        unlimited: bool = False,
        enforce_quota: bool = True,
    ) -> AIResult:
        query = (query or "").strip()[: self.config.max_input_chars]
        if not query:
            return AIResult(ok=False, reason="empty_input")
        providers = self.configured_text_providers()
        if not providers or self.session is None or self.session.closed:
            return AIResult(ok=False, reason="unconfigured")
        if enforce_quota and not await self._reserve_quota(user_id, "text", unlimited):
            return AIResult(ok=False, reason="quota")

        history_clean = self._normalize_history(history)
        started_total = time.monotonic()
        deadline = started_total + self.config.total_timeout_seconds
        attempted = False
        succeeded = False
        try:
            for provider in providers:
                if not self._circuit_available(provider):
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 1:
                    break
                attempted = True
                started = time.monotonic()
                status: int | None = None
                model = ""
                try:
                    if provider == "gemini":
                        model = self.config.gemini_model
                        task = self._gemini_text(system_prompt, query, history_clean)
                    elif provider == "groq":
                        model = self.config.groq_model
                        task = self._openai_text(
                            provider,
                            self.config.groq_api_key,
                            model,
                            "https://api.groq.com/openai/v1/chat/completions",
                            system_prompt,
                            query,
                            history_clean,
                        )
                    elif provider == "cerebras":
                        model = self.config.cerebras_model
                        task = self._openai_text(
                            provider,
                            self.config.cerebras_api_key,
                            model,
                            "https://api.cerebras.ai/v1/chat/completions",
                            system_prompt,
                            query,
                            history_clean,
                        )
                    else:
                        model = self.config.openrouter_model
                        task = self._openai_text(
                            provider,
                            self.config.openrouter_api_key,
                            model,
                            "https://openrouter.ai/api/v1/chat/completions",
                            system_prompt,
                            query,
                            history_clean,
                        )
                    text = await asyncio.wait_for(task, timeout=max(1, remaining))
                    latency = int((time.monotonic() - started) * 1000)
                    self._provider_success(provider)
                    await self._metric(provider, True, latency, feature=feature)
                    succeeded = True
                    return AIResult(
                        ok=True,
                        text=text,
                        provider=provider,
                        model=model,
                        latency_ms=int((time.monotonic() - started_total) * 1000),
                    )
                except ProviderError as exc:
                    status = exc.status
                    self._provider_failure(provider, status)
                except asyncio.TimeoutError:
                    self._provider_failure(provider, None)
                except Exception:
                    self._provider_failure(provider, None)
                latency = int((time.monotonic() - started) * 1000)
                await self._metric(provider, False, latency, status=status, feature=feature)
                log.warning("AI provider failed provider=%s status=%s", provider, status or "network")
            reason = "timeout" if attempted and time.monotonic() >= deadline else "providers_failed"
            return AIResult(
                ok=False,
                reason=reason,
                latency_ms=int((time.monotonic() - started_total) * 1000),
            )
        finally:
            # Failed and cancelled requests must not consume the daily allowance.
            if enforce_quota and not succeeded:
                await asyncio.shield(self._rollback_quota(user_id, "text", unlimited))

    async def _groq_transcribe(self, audio: bytes, mime_type: str, filename: str) -> str:
        if self.session is None or self.session.closed:
            raise ProviderError(reason="session_unavailable")
        form = aiohttp.FormData()
        form.add_field(
            "file",
            audio,
            filename=filename,
            content_type=mime_type or "audio/ogg",
        )
        form.add_field("model", self.config.groq_transcription_model)
        form.add_field("response_format", "json")
        form.add_field("temperature", "0")
        timeout = aiohttp.ClientTimeout(total=max(45, self.config.provider_timeout_seconds + 30), connect=10)
        try:
            async with self.session.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.config.groq_api_key}"},
                data=form,
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    raise ProviderError(
                        status=response.status,
                        retryable=response.status == 429 or response.status >= 500,
                    )
                body = await response.json(content_type=None)
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            raise ProviderError(retryable=True, reason=type(exc).__name__) from exc
        text = str(body.get("text") or "").strip()
        if not text:
            raise ProviderError(reason="empty_transcription")
        return text

    async def _gemini_transcribe(self, audio: bytes, mime_type: str) -> str:
        model = self.config.gemini_model
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(model, safe='-._')}:generateContent"
        )
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": "این فایل صوتی را دقیق و بدون توضیح اضافه به متن تبدیل کن. زبان را خودکار تشخیص بده."},
                    {"inlineData": {
                        "mimeType": mime_type or "audio/ogg",
                        "data": base64.b64encode(audio).decode("ascii"),
                    }},
                ],
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": self.config.max_output_tokens},
        }
        body, _ = await self._post_json(
            "gemini_audio",
            url,
            {"x-goog-api-key": self.config.gemini_api_key, "Content-Type": "application/json"},
            payload,
            max(45, self.config.provider_timeout_seconds + 30),
        )
        parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()
        if not text:
            raise ProviderError(reason="empty_transcription")
        return text

    async def transcribe_audio(
        self,
        audio: bytes,
        mime_type: str,
        filename: str,
        *,
        user_id: int,
        unlimited: bool = False,
    ) -> AIResult:
        if not audio or len(audio) > 19 * 1024 * 1024:
            return AIResult(ok=False, reason="invalid_audio")
        if self.session is None or self.session.closed:
            return AIResult(ok=False, reason="unconfigured")
        providers = []
        if self.config.groq_api_key:
            providers.append("groq_audio")
        if self.config.gemini_api_key:
            providers.append("gemini_audio")
        if not providers:
            return AIResult(ok=False, reason="unconfigured")
        if not await self._reserve_quota(user_id, "text", unlimited):
            return AIResult(ok=False, reason="quota")

        started_total = time.monotonic()
        for provider in providers:
            if not self._circuit_available(provider):
                continue
            started = time.monotonic()
            status: int | None = None
            try:
                if provider == "groq_audio":
                    text = await self._groq_transcribe(audio, mime_type, filename)
                    model = self.config.groq_transcription_model
                else:
                    text = await self._gemini_transcribe(audio, mime_type)
                    model = self.config.gemini_model
                latency = int((time.monotonic() - started) * 1000)
                self._provider_success(provider)
                await self._metric(provider, True, latency, feature="voice_transcription")
                return AIResult(
                    ok=True,
                    text=text,
                    provider=provider.removesuffix("_audio"),
                    model=model,
                    latency_ms=int((time.monotonic() - started_total) * 1000),
                )
            except ProviderError as exc:
                status = exc.status
            except Exception:
                status = None
            latency = int((time.monotonic() - started) * 1000)
            self._provider_failure(provider, status)
            await self._metric(provider, False, latency, status=status, feature="voice_transcription")
            log.warning("AI provider failed provider=%s status=%s", provider, status or "network")
        await self._rollback_quota(user_id, "text", unlimited)
        return AIResult(
            ok=False,
            reason="providers_failed",
            latency_ms=int((time.monotonic() - started_total) * 1000),
        )

    async def analyze_image(
        self,
        image: bytes,
        mime_type: str,
        prompt: str,
        *,
        user_id: int,
        system_prompt: str,
        unlimited: bool = False,
    ) -> AIResult:
        if not self.config.gemini_api_key or self.session is None or self.session.closed:
            return AIResult(ok=False, reason="image_understanding_unavailable")
        if not image or len(image) > 8 * 1024 * 1024:
            return AIResult(ok=False, reason="invalid_image")
        if not await self._reserve_quota(user_id, "text", unlimited):
            return AIResult(ok=False, reason="quota")
        provider = "gemini_vision"
        if not self._circuit_available(provider):
            await self._rollback_quota(user_id, "text", unlimited)
            return AIResult(ok=False, reason="providers_failed")
        model = self.config.gemini_model
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(model, safe='-._')}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": (prompt or "این تصویر را دقیق و کاربردی تحلیل کن.")[: self.config.max_input_chars]},
                    {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image).decode("ascii")}},
                ],
            }],
            "generationConfig": {"temperature": 0.45, "maxOutputTokens": self.config.max_output_tokens},
        }
        started = time.monotonic()
        status: int | None = None
        try:
            body, _ = await self._post_json(
                provider,
                url,
                {"x-goog-api-key": self.config.gemini_api_key, "Content-Type": "application/json"},
                payload,
                self.config.provider_timeout_seconds + 10,
            )
            parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            text = "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()
            if not text:
                raise ProviderError(reason="empty_response")
            latency = int((time.monotonic() - started) * 1000)
            self._provider_success(provider)
            await self._metric(provider, True, latency, feature="image_analysis")
            return AIResult(ok=True, text=text, provider="gemini", model=model, latency_ms=latency)
        except ProviderError as exc:
            status = exc.status
        except Exception:
            status = None
        latency = int((time.monotonic() - started) * 1000)
        self._provider_failure(provider, status)
        await self._metric(provider, False, latency, status=status, feature="image_analysis")
        await self._rollback_quota(user_id, "text", unlimited)
        log.warning("AI provider failed provider=%s status=%s", provider, status or "network")
        return AIResult(ok=False, reason="providers_failed", latency_ms=latency)

    async def _pollinations_image(self, prompt: str) -> tuple[bytes, str]:
        """Generate a free Flux image through the anonymous Pollinations endpoint.

        Anonymous traffic is deliberately serialized and spaced out to respect
        the public endpoint's rate limit. No API key or user identifier is sent.
        """
        if self.session is None or self.session.closed:
            raise ProviderError(reason="session_unavailable")
        safe_prompt = quote(prompt[:1200], safe="")
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
        params = {
            "model": self.config.pollinations_image_model,
            "width": "1024",
            "height": "1024",
            "nologo": "true",
            "enhance": "true",
            "seed": str(random.randint(1, 2_147_483_647)),
        }
        async with self._pollinations_lock:
            wait_for = 15.2 - (time.monotonic() - self._pollinations_last_call)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._pollinations_last_call = time.monotonic()
            last_error: ProviderError | None = None
            for attempt in range(2):
                try:
                    timeout = aiohttp.ClientTimeout(total=self.config.image_timeout_seconds, connect=12)
                    async with self.session.get(
                        url,
                        params=params,
                        headers={"Accept": "image/*", "User-Agent": "AjorparehBot/1.0"},
                        timeout=timeout,
                    ) as response:
                        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                        if response.status == 200 and content_type.startswith("image/"):
                            content_length = int(response.headers.get("Content-Length", "0") or 0)
                            if content_length > 18 * 1024 * 1024:
                                raise ProviderError(status=200, reason="image_too_large")
                            image = await response.read()
                            if not image or len(image) > 18 * 1024 * 1024:
                                raise ProviderError(status=200, reason="empty_or_large_image")
                            return image, content_type
                        retryable = response.status == 429 or response.status >= 500
                        last_error = ProviderError(status=response.status, retryable=retryable)
                except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                    last_error = ProviderError(retryable=True, reason=type(exc).__name__)
                if not last_error.retryable or attempt == 1:
                    break
                await asyncio.sleep(15.5 + random.uniform(0.1, 0.8))
                self._pollinations_last_call = time.monotonic()
            raise last_error or ProviderError()

    async def generate_image(
        self,
        prompt: str,
        *,
        user_id: int,
        unlimited: bool = False,
        source_image: bytes | None = None,
        source_mime_type: str = "image/jpeg",
    ) -> AIImageResult:
        prompt = (prompt or "").strip()[: self.config.max_input_chars]
        if not prompt:
            return AIImageResult(ok=False, reason="empty_input")
        if self.session is None or self.session.closed:
            return AIImageResult(ok=False, reason="image_generation_unavailable")
        if source_image and len(source_image) > 8 * 1024 * 1024:
            return AIImageResult(ok=False, reason="invalid_image")

        gemini_available = bool(self.config.gemini_api_key)
        pollinations_available = self.config.pollinations_image_enabled and source_image is None
        if source_image and not gemini_available:
            return AIImageResult(ok=False, reason="image_generation_unavailable")
        if not gemini_available and not pollinations_available:
            return AIImageResult(ok=False, reason="image_generation_unavailable")
        if not await self._reserve_quota(user_id, "image", unlimited):
            return AIImageResult(ok=False, reason="quota")

        overall_started = time.monotonic()
        feature = "image_edit" if source_image else "image_generation"

        # First choice: Gemini native image generation/editing.
        gemini_provider = "gemini_image"
        if gemini_available and self._circuit_available(gemini_provider):
            model = self.config.gemini_image_model
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{quote(model, safe='-._')}:generateContent"
            )
            parts: list[dict[str, Any]] = [{"text": prompt}]
            if source_image:
                parts.append({
                    "inlineData": {
                        "mimeType": source_mime_type,
                        "data": base64.b64encode(source_image).decode("ascii"),
                    }
                })
            payload = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            }
            started = time.monotonic()
            status: int | None = None
            try:
                body, _ = await self._post_json(
                    gemini_provider,
                    url,
                    {"x-goog-api-key": self.config.gemini_api_key, "Content-Type": "application/json"},
                    payload,
                    self.config.image_timeout_seconds,
                )
                response_parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
                image_bytes: bytes | None = None
                mime_type = "image/png"
                captions: list[str] = []
                for part in response_parts:
                    if part.get("text"):
                        captions.append(str(part["text"]).strip())
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data") and image_bytes is None:
                        image_bytes = base64.b64decode(inline["data"], validate=True)
                        mime_type = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
                if not image_bytes or len(image_bytes) > 18 * 1024 * 1024:
                    raise ProviderError(reason="empty_or_large_image")
                latency = int((time.monotonic() - started) * 1000)
                self._provider_success(gemini_provider)
                await self._metric(gemini_provider, True, latency, feature=feature)
                return AIImageResult(
                    ok=True,
                    image=image_bytes,
                    mime_type=mime_type,
                    caption="\n".join(filter(None, captions))[:900] or None,
                    provider="gemini",
                    model=model,
                    latency_ms=int((time.monotonic() - overall_started) * 1000),
                )
            except ProviderError as exc:
                status = exc.status
            except (ValueError, TypeError):
                status = None
            except Exception:
                status = None
            latency = int((time.monotonic() - started) * 1000)
            self._provider_failure(gemini_provider, status)
            await self._metric(gemini_provider, False, latency, status=status, feature=feature)
            log.warning("AI provider failed provider=%s status=%s", gemini_provider, status or "network")

        # Free text-to-image fallback. Editing stays Gemini-only because the
        # anonymous endpoint has no private source-image upload flow.
        pollinations_provider = "pollinations_image"
        if pollinations_available and self._circuit_available(pollinations_provider):
            started = time.monotonic()
            status = None
            try:
                image_bytes, mime_type = await self._pollinations_image(prompt)
                latency = int((time.monotonic() - started) * 1000)
                self._provider_success(pollinations_provider)
                await self._metric(pollinations_provider, True, latency, feature=feature)
                return AIImageResult(
                    ok=True,
                    image=image_bytes,
                    mime_type=mime_type,
                    provider="pollinations",
                    model=self.config.pollinations_image_model,
                    latency_ms=int((time.monotonic() - overall_started) * 1000),
                )
            except ProviderError as exc:
                status = exc.status
            except Exception:
                status = None
            latency = int((time.monotonic() - started) * 1000)
            self._provider_failure(pollinations_provider, status)
            await self._metric(
                pollinations_provider,
                False,
                latency,
                status=status,
                feature=feature,
            )
            log.warning(
                "AI provider failed provider=%s status=%s",
                pollinations_provider,
                status or "network",
            )

        await self._rollback_quota(user_id, "image", unlimited)
        return AIImageResult(
            ok=False,
            reason="providers_failed",
            latency_ms=int((time.monotonic() - overall_started) * 1000),
        )
