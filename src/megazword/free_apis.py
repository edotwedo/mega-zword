"""Opt-in chat APIs. Credentials stay in the environment and HTTP headers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .backends import Backend


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
        key = os.environ.get(self.key_env)
        if not key or not self._env_ok():
            raise RuntimeError("API key not set")
        try:
            headers = {"Authorization": f"Bearer {key}",
                       "Content-Type": "application/json", **self.extra_headers}
            request = urllib.request.Request(
                self._endpoint(),
                data=json.dumps({"model": self.model,
                                 "messages": [{"role": "user", "content": prompt}],
                                 "stream": False}).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("missing answer")
            return content.replace(key, "[REDACTED]")
        except urllib.error.HTTPError as exc:
            # Response bodies, reasons and URLs can echo credentials. Never
            # propagate them into Result.error (which the CLI prints/logs).
            raise RuntimeError(http_error_message(exc.code, exc.headers)) from None
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


def http_error_message(code: int, headers=None) -> str:
    """Safe one-line error (no body/URL). A 429 carries the server's
    Retry-After so limits.detect() marks the AI out for that long, not for
    its 1-hour guess: free-tier rate limits usually clear in seconds."""
    if code == 429:
        retry = (headers.get("Retry-After") if headers is not None else None) or ""
        if retry.strip().isdigit():
            minutes = max(1, -(-int(retry.strip()) // 60))  # round up
            return f"API HTTP error 429: rate limited, try again in {minutes} minutes"
        return "API HTTP error 429: rate limited"
    return f"API HTTP error {code}"


# Names shown in `megazword backends` / doctor. Never put these on DEFAULT_ROUTE.
FREE_KEYS = (
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
                                model=m.get("openrouter", "qwen/qwen3-4b:free"),
                                key_env="OPENROUTER_API_KEY"),
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
            model=m.get("gemini-api", "gemini-2.0-flash"),
            key_env="GOOGLE_AI_API_KEY", trains_on_data=True,
        ),
        OpenAICompatibleBackend(
            "nvidia", base_url="https://integrate.api.nvidia.com/v1",
            model=m.get("nvidia", "meta/llama-3.1-8b-instruct"),
            key_env="NVIDIA_API_KEY",
        ),
        OpenAICompatibleBackend(
            "mistral", base_url="https://api.mistral.ai/v1",
            model=m.get("mistral", "mistral-small-latest"),
            key_env="MISTRAL_API_KEY", trains_on_data=True,
        ),
    ]
