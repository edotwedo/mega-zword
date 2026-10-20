"""Live check with REAL AIs. Costs a little usage, so it's opt-in.

    python scripts/live_check.py --yes-spend

What it does, in order:
1. Runs `megazword doctor` and stops if anything is FAIL.
2. Sends ONE tiny prompt ("Reply with exactly: pong") to each installed AI
   that isn't marked out, through the normal path (`megazword run -m <ai>`),
   so every call is logged like any other run.
3. Sends the same prompt once with auto-pick, to show which AI it chose.
4. Prints a table: AI, ok, seconds, answer length.

Each call is a few dozen tokens. Without --yes-spend it only explains itself.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMPT = "Reply with exactly: pong"


def megazword(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(REPO / "src"))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run([sys.executable, "-m", "megazword.cli", *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env,
                          timeout=timeout)


def ready_ais() -> tuple[list[str], list[str]]:
    """(installed and not marked out, skipped with reason)."""
    r = megazword("backends")
    installed = [line.split()[0] for line in r.stdout.splitlines()
                 if line.strip() and "not found" not in line and "installed" in line]
    out = megazword("out").stdout
    marked = {line.split()[0] for line in out.splitlines() if "out until" in line}
    ready = [n for n in installed if n not in marked]
    skipped = [f"{n} (marked out)" for n in installed if n in marked]
    return ready, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes-spend", action="store_true",
                        help="I understand this sends real prompts to my paid AIs")
    args = parser.parse_args(argv)
    if not args.yes_spend:
        print(__doc__.strip())
        print("\nNot run. Add --yes-spend to send the real prompts.")
        return 2

    doc = megazword("doctor")
    print(doc.stdout.rstrip())
    fails = [l for l in doc.stdout.splitlines() if l.startswith("FAIL")]
    if fails:
        print(f"\nStopped: doctor reported {len(fails)} FAIL line(s). Fix those first.")
        return 1

    ready, skipped = ready_ais()
    if skipped:
        print("\nSkipping: " + ", ".join(skipped))
    if not ready:
        print("\nNo installed AI is available (all missing or marked out).")
        return 1

    rows = []
    for name in ready:
        start = time.monotonic()
        r = megazword("run", PROMPT, "-m", name)
        secs = time.monotonic() - start
        answer = r.stdout.strip()
        rows.append((name, r.returncode == 0 and "pong" in answer.lower(), secs, len(answer),
                     "" if r.returncode == 0 else r.stderr.strip().splitlines()[-1:][0][:60]
                     if r.stderr.strip() else f"exit {r.returncode}"))

    start = time.monotonic()
    auto = megazword("run", PROMPT)
    auto_secs = time.monotonic() - start
    picked = re.search(r"-> using (\S+)", auto.stderr)
    picked_name = picked.group(1) if picked else "?"

    print("\nAI       ok    secs  answer chars  note")
    for name, ok, secs, length, note in rows:
        print(f"{name:8} {'yes' if ok else 'NO ':5} {secs:5.1f}  {length:12}  {note}")
    auto_ok = auto.returncode == 0 and "pong" in auto.stdout.lower()
    print(f"\nauto-pick chose {picked_name}: {'ok' if auto_ok else 'FAILED'} in {auto_secs:.1f}s")
    good = sum(ok for _, ok, *_ in rows)
    print(f"{good}/{len(rows)} AIs answered pong. Runs are in `megazword stats`.")
    return 0 if good == len(rows) and auto_ok else 1


if __name__ == "__main__":
    sys.exit(main())
