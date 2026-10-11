"""Opt-in chat APIs. Credentials stay in the environment and HTTP headers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from .backends import Backend


@dataclass
class OpenAICompatibleBackend(Backend):
    base_url: str = ""
    model: str = ""
    key_env: str = ""

    def available(self) -> bool:
        return bool(os.environ.get(self.key_env))

    def _run(self, prompt: str) -> str:
        key = os.environ.get(self.key_env)
        if not key:
            raise RuntimeError("API key not set")
        try:
            request = urllib.request.Request(
                self.base_url.rstrip("/") + "/chat/completions",
                data=json.dumps({"model": self.model,
                                 "messages": [{"role": "user", "content": prompt}],
                                 "stream": False}).encode("utf-8"),
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
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


def free_backends(models: dict[str, str]) -> list[Backend]:
    return [
        OpenAICompatibleBackend("openrouter", base_url="https://openrouter.ai/api/v1",
                                model=models["openrouter"], key_env="OPENROUTER_API_KEY"),
        OpenAICompatibleBackend("groq", base_url="https://api.groq.com/openai/v1",
                                model=models["groq"], key_env="GROQ_API_KEY"),
    ]
