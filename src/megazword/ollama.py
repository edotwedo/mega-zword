"""Tiny client for a local Ollama server (stdlib only)."""

from __future__ import annotations

import json
import os
import urllib.request

DEFAULT_URL = os.environ.get("MEGAZWORD_OLLAMA_URL", "http://127.0.0.1:11434")


def generate(prompt: str, model: str, url: str = DEFAULT_URL, *,
             json_format: bool = False, timeout: float = 60) -> str:
    # keep_alive holds the model in memory so later calls skip the slow load.
    body = {"model": model, "prompt": prompt, "stream": False, "keep_alive": "30m"}
    if json_format:
        body["format"] = "json"
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["response"]


def reachable(url: str = DEFAULT_URL, timeout: float = 2) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/version", timeout=timeout):
            return True
    except OSError:
        return False
