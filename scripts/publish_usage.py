"""Publish every AI's plan usage as one GitHub comment that is edited in place, so
sessions that can't run Mega Zword (cloud chats, other bots) can read it.

    python scripts/publish_usage.py --repo OWNER/REPO --issue N

Creates the comment once, then edits the same one each run (an edit sends no
notifications). Needs the GitHub CLI (`gh`) logged in. Never calls a model.
The comment id is kept in ~/.megazword/usage_comment_<repo>_<issue>.txt.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

from megazword import config, usage_sources

NAMES = {"claude": "Claude", "codex": "Codex", "grok": "Grok", "gemini": "Gemini"}


def cell(windows, name):
    w = next((w for w in windows if w.name == name), None)
    if w is None:
        return "-"
    reset = f" (resets {w.resets_at.astimezone():%a %b %d %I:%M %p})" if w.resets_at else ""
    return f"**{w.used_percent:.0f}%**{reset}"


def body() -> str:
    now = datetime.now(timezone.utc)
    out = config.load().out_until
    rows = []
    for plan in usage_sources.all_usage():
        name = NAMES.get(plan.service, plan.service)
        until = out.get(plan.service)
        if until and until > now:
            rows.append(f"| {name} | marked out until {until.astimezone():%a %I:%M %p} | | |")
            continue
        src = plan.source if plan.source != "error" else "unreadable"
        rows.append(f"| {name} | {cell(plan.windows, '5-hour')} | {cell(plan.windows, 'weekly')} | {src} |")
    stamp = datetime.now().astimezone().strftime("%a %b %d %I:%M %p %Z")
    return "\n".join([
        "## Usage board (live, edited in place)",
        "",
        f"Updated **{stamp}** from Phil's PC by Mega Zword. Percent **used**. "
        "If this is more than 30 minutes old, the PC is off or asleep.",
        "",
        "| AI | 5-hour window | Week | Source |",
        "|---|---|---|---|",
        *rows,
        "",
        "_Read this before planning work: send work to whoever has the most room. "
        "On the PC, `megazword usage` gives the same numbers instantly._",
    ])


def gh(*args, payload=None) -> str:
    r = subprocess.run(["gh", "api", *args, "--input", "-"] if payload is not None else ["gh", "api", *args],
                       input=json.dumps(payload) if payload is not None else None,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue", required=True, type=int)
    ap.add_argument("--print", action="store_true", help="print the text, post nothing")
    a = ap.parse_args()
    text = body()
    if a.print:
        print(text)
        return 0
    store = config.HOME / f"usage_comment_{a.repo.replace('/', '_')}_{a.issue}.txt"
    store.parent.mkdir(parents=True, exist_ok=True)
    cid = store.read_text().strip() if store.exists() else ""
    if cid:
        try:
            gh("-X", "PATCH", f"repos/{a.repo}/issues/comments/{cid}", payload={"body": text})
            return 0
        except RuntimeError as exc:
            if "Not Found" not in str(exc):
                raise
    made = json.loads(gh("-X", "POST", f"repos/{a.repo}/issues/{a.issue}/comments", payload={"body": text}))
    store.write_text(str(made["id"]))
    print(made.get("html_url", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
