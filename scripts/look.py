#!/usr/bin/env python3
"""Describe an image with a vision model, so a text-only seat can "see" it.

Why this exists: the harness only inlines image bytes for vision-capable models.
A seat running a text model (deepseek-v4-flash, for example) gets
"[Binary file: image/jpeg, 3931578 bytes]" from read_file, and the vision tool then
has nothing to look at. This sends the bytes to a vision API instead, so any seat -
and any CLI - can ask "what is in this picture?" without changing its model.

    scripts/look.py <image> [question...]

Env:
  LOOK_MODEL          vision model id (default: the [free.gemini-api] model in config.toml)
  LOOK_PROVIDER       "gemini" (default)
  GOOGLE_AI_API_KEY   required for gemini (already in ~/.agent-env.sh on the Hive box)

Caveat: the free Gemini tier is flagged trains_on_data in this repo. Do not point
this at anything private until it uses a paid or local provider.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_MODEL = "gemini-3.5-flash-lite"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".heic": "image/heic"}


def configured_model() -> str:
    """The free.gemini-api model from ~/.megazword/config.toml, if it is set."""
    home = Path(os.environ.get("MEGAZWORD_HOME", Path.home() / ".megazword"))
    try:
        text = (home / "config.toml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return DEFAULT_MODEL
    section = re.search(r"^\[free\.gemini-api\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not section:
        return DEFAULT_MODEL
    found = re.search(r'^\s*model\s*=\s*"([^"]+)"', section.group(1), re.M)
    return found.group(1) if found else DEFAULT_MODEL


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: look.py <image> [question...]", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser()
    question = " ".join(argv[2:]) or (
        "Describe this image in full detail: the subject, every object and piece of "
        "equipment, all legible text or labels verbatim, the setting and lighting, and "
        "anything unusual. Say nothing you cannot see.")
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"look: cannot read {path}: {exc}", file=sys.stderr)
        return 1

    key = os.environ.get("GOOGLE_AI_API_KEY", "").strip()
    if not key:
        print("look: GOOGLE_AI_API_KEY is not set", file=sys.stderr)
        return 1
    model = os.environ.get("LOOK_MODEL") or configured_model()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    body = {
        "contents": [{"parts": [
            {"text": question},
            {"inline_data": {"mime_type": MIME.get(path.suffix.lower(), "image/jpeg"),
                             "data": base64.b64encode(data).decode("ascii")}},
        ]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read(1 << 20))
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", "replace")
        print(f"look: HTTP {exc.code} from {model}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - one message, no traceback
        print(f"look: request failed: {exc}", file=sys.stderr)
        return 1

    parts = ((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "\n".join(p.get("text", "") for p in parts).strip()
    if not text:
        print(f"look: no text in the response ({json.dumps(payload)[:300]})", file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
