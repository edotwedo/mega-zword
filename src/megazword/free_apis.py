"""Opt-in chat APIs. Credentials stay in the environment and HTTP headers."""

from __future__ import annotations

import json
import os
import re
import math
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .backends import Backend


class ToolsUnsupported(RuntimeError):
    """Backend rejected the native tool schema; retry using text JSON."""


class APIHTTPError(RuntimeError):
    """HTTP status for retries, optionally with a sanitized validation reason."""

    def __init__(self, code, headers=None, reason=""):
        self.code = code
        self.retry_after = retry_seconds(headers) if code == 429 else None
        super().__init__(http_error_message(code, headers) + (": " + reason if reason else ""))


def _cloudflare_daily_quota_exhausted(raw: bytes) -> bool:
    """Recognize Workers AI's daily free-allocation error, not capacity 429s."""
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
        errors = payload.get("errors", [])
        return any(
            isinstance(error, dict)
            and str(error.get("code", "")) in {"3036", "4006"}
            and "daily free allocation" in str(error.get("message", "")).lower()
            for error in errors
        )
    except (ValueError, TypeError, AttributeError):
        return False


def _cloudflare_daily_reset_seconds(now: datetime | None = None) -> int:
    """Workers AI's free allocation resets at midnight UTC."""
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, math.ceil((reset - now).total_seconds()))


def _mistral_rate_limited(raw: bytes) -> bool:
    """Recognize Mistral's documented structured 429 response without echoing it."""
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
        return (payload.get("type") == "rate_limited"
                and str(payload.get("code", "")) == "1300")
    except (ValueError, TypeError, AttributeError):
        return False


def _safe_reason(exc):
    """Only structured validation messages, bounded and stripped of credentials."""
    from .guard import scrub
    try:
        payload = json.loads(exc.read(16384))
        error = payload.get("error", {})
        reason = error.get("message", "") if isinstance(error, dict) else ""
        if not reason and isinstance(payload.get("errors"), list) and payload["errors"]:
            reason = payload["errors"][0].get("message", "")
        if not isinstance(reason, str):
            return ""
        for name, value in sorted(os.environ.items(), key=lambda item: -len(item[1])):
            if value and (re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I)
                          or name == "CLOUDFLARE_ACCOUNT_ID"):
                reason = reason.replace(value, "[REDACTED]")
        reason = re.sub(r"https?://\S+|Bearer\s+\S+", "[REDACTED]", reason, flags=re.I)
        return " ".join(scrub(reason).split())[:240]
    except (ValueError, AttributeError, TypeError, IndexError, OSError):
        return ""


@dataclass
class OpenAICompatibleBackend(Backend):
    base_url: str = ""
    model: str = ""
    key_env: str = ""
    extra_env: tuple[str, ...] = ()
    extra_headers: dict[str, str] = field(default_factory=dict)

    def _env_ok(self) -> bool:
        return bool(os.environ.get(self.key_env)) and all(os.environ.get(n) for n in self.extra_env)

    def available(self) -> bool:
        return self._env_ok()

    def _endpoint(self) -> str:
        url = self.base_url
        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        if "{account}" in url:
            url = url.replace("{account}", account)
        return url.rstrip("/") + "/chat/completions"

    def _run(self, prompt: str) -> str:
        message = self.chat([{"role": "user", "content": prompt}])
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("API returned an invalid or empty chat response")
        return content

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             timeout: float | None = None) -> dict:
        """One OpenAI chat turn, preserving native tool calls."""
        key = os.environ.get(self.key_env)
        if not key or not self._env_ok():
            raise RuntimeError("API key not set")
        try:
            headers = {"Authorization": f"Bearer {key}",
                       "Content-Type": "application/json", **self.extra_headers}
            body = {"model": self.model, "messages": messages, "stream": False}
            if self.name == "cloudflare":
                body.pop("stream")  # The default is a non-streaming response.
            if tools is not None:
                body["tools"] = tools
                # OpenAI-compatible providers do not all default to automatic
                # selection when tools are present. Google documents this field
                # for its compatibility endpoint; be explicit for each API.
                body["tool_choice"] = "auto"
            request = urllib.request.Request(
                self._endpoint(),
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            message = payload["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("missing answer")
            return json.loads(json.dumps(message).replace(key, "[REDACTED]"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and self.name in {"cloudflare", "mistral"}:
                try:
                    raw = exc.read(16384)
                except OSError:
                    raw = b""
                reason = ""
                headers = exc.headers
                if self.name == "cloudflare" and _cloudflare_daily_quota_exhausted(raw):
                    headers = dict(exc.headers or {})
                    headers["Retry-After"] = str(_cloudflare_daily_reset_seconds())
                    reason = "daily free allocation exhausted; resets at 00:00 UTC"
                elif self.name == "mistral" and _mistral_rate_limited(raw):
                    reason = "Mistral rate limit exceeded (code 1300)"
                raise APIHTTPError(exc.code, headers, reason) from None
            reason = _safe_reason(exc) if exc.code in (400, 422) else ""
            if tools is not None and exc.code in (400, 422):
                raise ToolsUnsupported("API rejected native tools" + (": " + reason if reason else "")) from None
            # Auth and rate-limit bodies stay private. Only sanitized validation
            # messages reach Result.error (which the CLI prints/logs).
            raise APIHTTPError(exc.code, exc.headers, reason) from None
        except TimeoutError:
            raise RuntimeError("API request timed out") from None
        except urllib.error.URLError as exc:
            # Worded so failures.classify() sees a network problem (and can
            # stop the chain) rather than an unknown error.
            message = ("API request timed out" if isinstance(exc.reason, TimeoutError)
                       else "API connection failed: unable to connect (network or DNS)")
            raise RuntimeError(message) from None
        except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
            raise RuntimeError("API returned an invalid or empty chat response") from None
        except Exception:
            raise RuntimeError("API request failed") from None


def retry_seconds(headers=None) -> float:
    """Keep Retry-After precision for numeric seconds or an HTTP-date."""
    retry = (headers.get("Retry-After") if headers is not None else None) or ""
    try:
        seconds = float(str(retry).strip())
        return max(0, seconds) if math.isfinite(seconds) else 120
    except ValueError:
        try:
            reset = parsedate_to_datetime(retry)
            if reset.tzinfo is None:
                reset = reset.replace(tzinfo=timezone.utc)
            return max(0, (reset - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 120


def http_error_message(code: int, headers=None) -> str:
    """Safe one-line error (no body/URL). A 429 carries the server's
    Retry-After so limits.detect() marks the AI out for that long, not for
    its 1-hour guess: free-tier rate limits usually clear in seconds."""
    if code == 429:
        minutes = max(1, math.ceil(retry_seconds(headers) / 60))
        return f"API HTTP error 429: rate limited, try again in {minutes} minutes"
    # Worded so failures.classify() sees an auth problem. Never echo the body.
    if code == 401:
        return "API HTTP error 401: unauthorized (auth failed, check the API key)"
    if code == 403:
        return "API HTTP error 403: forbidden (auth rejected, check the API key or model access)"
    return f"API HTTP error {code}"


# Free API backends available to automatic routes when credentials are present.
FREE_KEYS = (
    ("kimi", "OPENROUTER_API_KEY"),
    ("deepseek", "OPENROUTER_API_KEY"),
    ("qwen-coder", "OPENROUTER_API_KEY"),
    ("openrouter", "OPENROUTER_API_KEY"),
    ("groq", "GROQ_API_KEY"),
    ("cloudflare", "CLOUDFLARE_API_TOKEN"),
    ("zai", "ZAI_API_KEY"),
    ("gemini-api", "GOOGLE_AI_API_KEY"),
    ("nvidia", "NVIDIA_API_KEY"),
    ("mistral", "MISTRAL_API_KEY"),
)


def free_backends(models: dict[str, str]) -> list[Backend]:
    m = {**{k: v for k, v in models.items()}}
    return [
        OpenAICompatibleBackend("openrouter", base_url="https://openrouter.ai/api/v1",
                                model=m.get("openrouter", "openrouter/free"),
                                key_env="OPENROUTER_API_KEY", trains_on_data=True),
        OpenAICompatibleBackend("groq", base_url="https://api.groq.com/openai/v1",
                                model=m.get("groq", "llama-3.3-70b-versatile"),
                                key_env="GROQ_API_KEY"),
        OpenAICompatibleBackend(
            "cloudflare",
            base_url="https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
            model=m.get("cloudflare", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
            key_env="CLOUDFLARE_API_TOKEN",
            extra_env=("CLOUDFLARE_ACCOUNT_ID",),
        ),
        OpenAICompatibleBackend(
            "zai", base_url="https://api.z.ai/api/paas/v4",
            model=m.get("zai", "glm-4.5-flash"),
            key_env="ZAI_API_KEY",  # Developer API terms say no training unless we opt in.
        ),
        OpenAICompatibleBackend(
            "gemini-api", base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            # Stable free-tier model with function calling; verified in the edit loop (2026-10-14).
            model=m.get("gemini-api", "gemini-3.5-flash-lite"),
            key_env="GOOGLE_AI_API_KEY", trains_on_data=True,
        ),
        OpenAICompatibleBackend(
            "nvidia", base_url="https://integrate.api.nvidia.com/v1",
            model=m.get("nvidia", "meta/llama-3.1-8b-instruct"),
            key_env="NVIDIA_API_KEY",
        ),
        OpenAICompatibleBackend(
            "mistral", base_url="https://api.mistral.ai/v1",
            model=m.get("mistral", "ministral-3b-2512"),
            key_env="MISTRAL_API_KEY", trains_on_data=True,
        ),
        # OpenRouter chooses the serving provider. Its training policy can
        # vary by endpoint (and configured model); unknown means scrub prompts.
        *[OpenAICompatibleBackend(name, base_url="https://openrouter.ai/api/v1",
                                  model=m.get(name, default),
                                  key_env="OPENROUTER_API_KEY", trains_on_data=True)
          for name, default in (
              ("kimi", "moonshotai/kimi-k2.6:free"),
              ("deepseek", "deepseek/deepseek-chat-v3.1:free"),
              ("qwen-coder", "qwen/qwen3-coder:free"))],
    ]
