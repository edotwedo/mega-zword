"""Opt-in chat APIs. Credentials stay in the environment and HTTP headers."""

from __future__ import annotations

import json
import os
import re
import math
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .backends import Backend
from .filelock import locked, write_atomic


def _near_request_limit(remaining: int | None, limit: int | None) -> bool:
    return bool(remaining is not None and limit
                and remaining <= max(5, int(limit * 0.05)))


def _request_reset_seconds(value: str | None) -> float:
    """Parse provider duration headers (for example, ``1h2m3.4s``)."""
    if not value:
        return 3600
    try:
        number = float(value)
        return max(1, number)
    except (ValueError, TypeError):
        pass
    match = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?"
        r"(?:(\d+(?:\.\d+)?)s)?", value.strip(), re.I)
    if not match or not any(match.groups()):
        return 3600
    hours, minutes, seconds = (float(part or 0) for part in match.groups())
    return max(1, hours * 3600 + minutes * 60 + seconds)


def request_quota_low(name: str) -> bool:
    """Whether a recent response marked this identity low until its reset."""
    from . import config
    path = config.HOME / "request-quota.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data.get(name, {})
        return float(record.get("until", 0)) > time.time()
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _record_request_quota(name: str, remaining: int | None,
                          limit: int | None, reset: str | None) -> None:
    """Persist only low-water marks; remove them when a fresh header recovers."""
    from . import config
    path = config.HOME / "request-quota.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked(path, timeout=2) as got:
            if not got:
                return
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            if _near_request_limit(remaining, limit):
                data[name] = {"remaining": remaining, "limit": limit,
                              "until": time.time() + _request_reset_seconds(reset)}
            else:
                data.pop(name, None)
            write_atomic(path, json.dumps(data, sort_keys=True))
    except (OSError, TimeoutError, ValueError):
        # A cache failure must not block an otherwise usable free API.
        return


class ToolsUnsupported(RuntimeError):
    """Backend rejected the native tool schema; retry using text JSON."""


class APIHTTPError(RuntimeError):
    """HTTP status for retries, optionally with a sanitized validation reason."""

    def __init__(self, code, headers=None, reason="", blocked=False):
        self.code = code
        self.retry_after = retry_seconds(headers) if code == 429 else None
        if blocked:
            message = "API HTTP error 403: Cloudflare blocked this HTTP client (error 1010)"
        else:
            message = http_error_message(code, headers) + (": " + reason if reason else "")
        super().__init__(message)


class _BytesBody:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self, n=16384):
        return self._raw[:n]


def _curl_bin() -> str | None:
    return shutil.which("curl.exe") or shutil.which("curl")


def _use_curl(name: str, url: str | None = None) -> bool:
    # This PC's Python TLS fingerprint is blocked by Cloudflare on Groq.
    # curl reads the authorization header from a temporary file, not argv.
    return (name == "groq" and bool(_curl_bin()) and url is not None
            and urllib.parse.urlsplit(url).hostname == "api.groq.com")


def _cloudflare_1010(body: bytes) -> bool:
    text = body.decode("utf-8", "replace").lower()
    return "1010" in text or "access denied" in text


def _parse_curl_headers(text: str) -> tuple[int, dict[str, str]]:
    status = 0
    headers: dict[str, str] = {}
    for line in text.splitlines():
        if line.upper().startswith("HTTP/"):
            fields = line.split()
            status = int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else 0
            headers = {}
        elif ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    return status, headers


def _header(headers, name: str):
    if headers is None:
        return None
    direct = headers.get(name)
    if direct is not None:
        return direct
    target = name.lower()
    return next((value for key, value in headers.items()
                 if str(key).lower() == target), None)


def _curl_json_post(url: str, headers: dict[str, str], body: dict,
                    timeout: float, tools: list[dict] | None = None
                    ) -> tuple[dict, dict[str, str]]:
    """POST JSON through curl without exposing credentials in process args."""
    curl = _curl_bin()
    if not curl:
        raise RuntimeError("API connection failed: curl is unavailable")
    seconds = max(1, int(timeout or 1))
    with tempfile.TemporaryDirectory() as folder:
        header_file = os.path.join(folder, "headers.txt")
        response_headers_file = os.path.join(folder, "response-headers.txt")
        with open(header_file, "w", encoding="utf-8", newline="\n") as handle:
            for name, value in headers.items():
                if any(char in name or char in value for char in "\r\n"):
                    raise RuntimeError("invalid API request header")
                handle.write(f"{name}: {value}\n")
        try:
            result = subprocess.run(
                [curl, "-sS", "--http1.1", "--max-time", str(seconds),
                 "-X", "POST", url, "-D", response_headers_file,
                 "-H", f"@{header_file}", "--data-binary", "@-"],
                input=json.dumps(body).encode("utf-8"),
                capture_output=True, timeout=seconds + 5,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("API request timed out") from None
        raw = result.stdout or b""
        header_text = ""
        if os.path.exists(response_headers_file):
            with open(response_headers_file, encoding="utf-8", errors="replace") as handle:
                header_text = handle.read()
        code, response_headers = _parse_curl_headers(header_text)
        if code >= 400:
            _raise_http(code, response_headers, raw, tools)
        if result.returncode != 0 or code == 0:
            raise RuntimeError("API connection failed: unable to connect (network or DNS)")
        try:
            return json.loads(raw.decode("utf-8")), response_headers
        except (ValueError, UnicodeError):
            raise RuntimeError("API returned an invalid or empty chat response") from None


def _raise_http(code, headers, raw: bytes, tools):
    if code == 403 and _cloudflare_1010(raw):
        raise APIHTTPError(code, headers, blocked=True)
    reason = _safe_reason(_BytesBody(raw)) if code in (400, 403, 422) else ""
    if tools is not None and code in (400, 422):
        raise ToolsUnsupported("API rejected native tools" + (": " + reason if reason else ""))
    raise APIHTTPError(code, headers, reason)


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
    remaining_requests: int | None = field(default=None, init=False)
    limit_requests: int | None = field(default=None, init=False)

    @property
    def quota_near_limit(self) -> bool:
        return (_near_request_limit(self.remaining_requests, self.limit_requests)
                or request_quota_low(self.name))

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

    def _record_rate_limit_headers(self, headers) -> None:
        try:
            remaining = _header(headers, "x-ratelimit-remaining-requests")
            limit = _header(headers, "x-ratelimit-limit-requests")
            self.remaining_requests = int(remaining) if remaining is not None else None
            self.limit_requests = int(limit) if limit is not None else None
            if self.remaining_requests is not None and self.limit_requests is not None:
                _record_request_quota(
                    self.name, self.remaining_requests, self.limit_requests,
                    _header(headers, "x-ratelimit-reset-requests"))
        except (TypeError, ValueError):
            self.remaining_requests = self.limit_requests = None

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
            from . import __version__
            headers = {"Authorization": f"Bearer {key}",
                       "Content-Type": "application/json",
                       "User-Agent": f"megazword/{__version__}", **self.extra_headers}
            body = {"model": self.model, "messages": messages, "stream": False}
            if self.name == "cloudflare":
                body.pop("stream")  # The default is a non-streaming response.
            if tools is not None:
                body["tools"] = tools
                # OpenAI-compatible providers do not all default to automatic
                # selection when tools are present. Google documents this field
                # for its compatibility endpoint; be explicit for each API.
                body["tool_choice"] = "auto"
                # Groq requires parsed/hidden reasoning for GPT-OSS tool calls;
                # its default raw format can reject an otherwise valid call.
                if (self.name.startswith("groq") and self.model.startswith("openai/gpt-oss-")):
                    body["reasoning_format"] = "parsed"
            if _use_curl(self.name, self._endpoint()):
                payload, response_headers = _curl_json_post(
                    self._endpoint(), headers, body, timeout or self.timeout, tools)
                self._record_rate_limit_headers(response_headers)
            else:
                request = urllib.request.Request(
                    self._endpoint(),
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                    response_headers = getattr(response, "headers", {})
                    self._record_rate_limit_headers(response_headers)
                    payload = json.loads(response.read().decode("utf-8"))
            message = payload["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("missing answer")
            return json.loads(json.dumps(message).replace(key, "[REDACTED]"))
        except (APIHTTPError, ToolsUnsupported):
            raise
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
            reason = _safe_reason(exc) if exc.code in (400, 403, 422) else ""
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
    retry = _header(headers, "Retry-After") or ""
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
    ("openrouter-dots", "OPENROUTER_API_KEY"),
    ("openrouter-nemotron-nano", "OPENROUTER_API_KEY"),
    ("openrouter-nemotron-lightning", "OPENROUTER_API_KEY"),
    ("openrouter-laguna-s", "OPENROUTER_API_KEY"),
    ("openrouter-laguna-xs", "OPENROUTER_API_KEY"),
    ("groq", "GROQ_API_KEY"),
    ("groq-120b", "GROQ_API_KEY"),
    ("groq-qwen", "GROQ_API_KEY"),
    ("groq-allam", "GROQ_API_KEY"),
    ("cloudflare", "CLOUDFLARE_API_TOKEN"),
    ("zai", "ZAI_API_KEY"),
    ("gemini-api", "GOOGLE_AI_API_KEY"),
    ("gemini-api-31-lite", "GOOGLE_AI_API_KEY"),
    ("cerebras", "CEREBRAS_API_KEY"),
    ("nvidia", "NVIDIA_API_KEY"),
    ("nvidia-lightning", "NVIDIA_API_KEY"),
    ("tencent", "TENCENT_TOKENHUB_API_KEY"),
    ("tencent-glm-5.3-flash", "TENCENT_TOKENHUB_API_KEY"),
    ("tencent-glm-5.3", "TENCENT_TOKENHUB_API_KEY"),
    ("tencent-kimi-k2.7-code", "TENCENT_TOKENHUB_API_KEY"),
    ("tencent-kimi-k3", "TENCENT_TOKENHUB_API_KEY"),
    ("tencent-deepseek-v4-pro", "TENCENT_TOKENHUB_API_KEY"),
    ("tencent-deepseek-v4-flash-vision-exp", "TENCENT_TOKENHUB_API_KEY"),
    ("mistral", "MISTRAL_API_KEY"),
)


def free_backends(models: dict[str, str]) -> list[Backend]:
    m = {**{k: v for k, v in models.items()}}
    return [
        OpenAICompatibleBackend("openrouter", base_url="https://openrouter.ai/api/v1",
                                model=m.get("openrouter", "openrouter/free"),
                                key_env="OPENROUTER_API_KEY", trains_on_data=True),
        OpenAICompatibleBackend("groq", base_url="https://api.groq.com/openai/v1",
                                model=m.get("groq", "openai/gpt-oss-20b"),
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
            "nvidia-lightning", base_url="https://integrate.api.nvidia.com/v1",
            model=m.get("nvidia-lightning", "nvidia/nemotron-3.5-lightning-30b-a3b"),
            key_env="NVIDIA_API_KEY",
        ),
        OpenAICompatibleBackend(
            "cerebras", base_url="https://api.cerebras.ai/v1",
            model=m.get("cerebras", "qwen-3.8-27b"),
            key_env="CEREBRAS_API_KEY",
        ),
        OpenAICompatibleBackend(
            "mistral", base_url="https://api.mistral.ai/v1",
            model=m.get("mistral", "ministral-3b-2512"),
            key_env="MISTRAL_API_KEY", trains_on_data=True,
        ),
        # The International Singapore site uses a separate key space from
        # Tencent's China site, despite both consoles offering Singapore.
        OpenAICompatibleBackend(
            "tencent", base_url="https://tokenhub-intl.tencentcloudmaas.com/v1",
            model=m.get("tencent", "hy3"), key_env="TENCENT_TOKENHUB_API_KEY",
        ),
        *[OpenAICompatibleBackend(
            name, base_url="https://tokenhub-intl.tencentcloudmaas.com/v1",
            model=m.get(name, model), key_env="TENCENT_TOKENHUB_API_KEY",
        ) for name, model in (
            ("tencent-glm-5.3-flash", "glm-5.3-flash"),
            ("tencent-glm-5.3", "glm-5.3"),
            ("tencent-kimi-k2.7-code", "kimi-k2.7-code"),
            ("tencent-kimi-k3", "kimi-k3"),
            ("tencent-deepseek-v4-pro", "deepseek-v4-pro"),
            ("tencent-deepseek-v4-flash-vision-exp",
             "deepseek/deepseek-v4-flash-vision-exp"),
        )],
        # OpenRouter chooses the serving provider. Its training policy can
        # vary by endpoint (and configured model); unknown means scrub prompts.
        *[OpenAICompatibleBackend(name, base_url="https://openrouter.ai/api/v1",
                                  model=m.get(name, default),
                                  key_env="OPENROUTER_API_KEY", trains_on_data=True)
          for name, default in (
              ("kimi", "moonshotai/kimi-k2.6:free"),
              ("deepseek", "deepseek/deepseek-chat-v3.1:free"),
              ("qwen-coder", "qwen/qwen3-coder:free"))],
        *[OpenAICompatibleBackend(name, base_url=base,
                                  model=m.get(name, model), key_env=key,
                                  trains_on_data=trains)
          for name, base, model, key, trains in (
              ("groq-120b", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "GROQ_API_KEY", False),
              ("groq-qwen", "https://api.groq.com/openai/v1", "qwen/qwen3.8-27b", "GROQ_API_KEY", False),
              ("groq-allam", "https://api.groq.com/openai/v1", "allam-2-7b", "GROQ_API_KEY", False),
              ("gemini-api-31-lite", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.1-flash-lite", "GOOGLE_AI_API_KEY", True),
              ("openrouter-dots", "https://openrouter.ai/api/v1", "dots-studio/dots-3-note-preview:free", "OPENROUTER_API_KEY", True),
              ("openrouter-nemotron-nano", "https://openrouter.ai/api/v1", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "OPENROUTER_API_KEY", True),
              ("openrouter-nemotron-lightning", "https://openrouter.ai/api/v1", "nvidia/nemotron-3.5-lightning:free", "OPENROUTER_API_KEY", True),
              ("openrouter-laguna-s", "https://openrouter.ai/api/v1", "poolside/laguna-s-2.1:free", "OPENROUTER_API_KEY", True),
              ("openrouter-laguna-xs", "https://openrouter.ai/api/v1", "poolside/laguna-xs-2.1:free", "OPENROUTER_API_KEY", True))],
    ]
