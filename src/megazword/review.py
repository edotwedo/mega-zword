"""`megazword review`: several reviewers look at one change; findings are merged.

Free models from different families review the diff at the same time (fair
share via routing.spread). With --greptile, the branch also goes to GitHub as a
temporary PR so Greptile (50 free credits a month) can review it; its comments
come back into the same report and the PR is closed. A finding that two or more
reviewers flag independently goes to the top.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config, log
from .backends import Backend, Result

REVIEWERS = 1          # routine change; the heartbeat uses 2 before merging (Phil, 2026-10-16)
SPARES = 2             # backups from other families when a reviewer fails
MAX_DIFF_CHARS = 24_000
GREPTILE_MONTHLY = 50
SEVERITY = {"high": 0, "medium": 1, "med": 1, "low": 2}

PROMPT = """You are one of {n} independent code reviewers. Other reviewers from
different AI families see the same change; findings that several of you report
independently will be trusted most, so report only real problems you can point to.

Review this git diff for bugs only: wrong logic, crashes, security holes, data
loss, secrets, money-spending risks, broken tests. No style comments, no praise,
no summary. One finding per line, exactly in this form:
- [high|medium|low] path/to/file.py:LINE - what is wrong and why
If you find nothing, reply exactly: no bugs found

{note}```diff
{diff}
```"""

FINDING = re.compile(r"^\s*[-*]\s*\[(high|medium|med|low)\]\s*([^\s:]+):(\d+)\s*[-:–—]+\s*(.+)$",
                     re.I | re.M)


@dataclass
class Finding:
    severity: str
    path: str
    line: int
    text: str
    by: list[str] = field(default_factory=list)


def git(repo: Path, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def change(repo: Path, base: str | None = None) -> tuple[str, str]:
    """The diff to review and a one-line label. Default: this branch against
    origin/main; on main itself (nothing ahead), the last commit."""
    if base:
        out = git(repo, "diff", f"{base}...HEAD")
        return out.stdout, f"{base}...HEAD"
    ahead = git(repo, "diff", "origin/main...HEAD").stdout
    if ahead.strip():
        return ahead, "origin/main...HEAD"
    return git(repo, "show", "--format=", "HEAD").stdout, "last commit"


def clip(diff: str, limit: int = MAX_DIFF_CHARS) -> tuple[str, str]:
    """Keep whole files until the limit; name the files left out."""
    files = re.split(r"(?m)^(?=diff --git )", diff)
    kept, dropped, size = [], [], 0
    for part in files:
        if not part.strip():
            continue
        if size + len(part) <= limit:
            kept.append(part)
            size += len(part)
        else:
            dropped.append(part.split("\n", 1)[0].split(" b/")[-1])
    note = f"(Diff shortened; not shown: {', '.join(dropped)})\n\n" if dropped else ""
    return "".join(kept), note


def pick_reviewers(backends: dict[str, Backend], count: int = REVIEWERS,
                   log_path: Path | None = None) -> list[Backend]:
    """Least-used free sources first, at most one per provider family.

    Tiny models (routing.WEAK_BACKENDS) are left out: they fail on long diffs.
    """
    from .request_mode import free_backend
    from .routing import WEAK_BACKENDS, spread
    names = [n for n in config.DEFAULT_FREE_FAILOVER if n in backends]
    order = spread(names, "medium", log_path)
    chosen, families = [], set()
    for name in order:
        b = backends[name]
        family = name.split("-")[0]
        # Tencent's one-time grants are kept for coding, never spent on reviews.
        if (family in families or family == "tencent" or name in WEAK_BACKENDS
                or not free_backend(b) or not b.available()):
            continue
        chosen.append(b)
        families.add(family)
        if len(chosen) == count:
            break
    return chosen


def parse(text: str, by: str) -> list[Finding]:
    return [Finding("medium" if m.group(1).lower() == "med" else m.group(1).lower(),
                    m.group(2).strip("`"), int(m.group(3)), m.group(4).strip(), [by])
            for m in FINDING.finditer(text or "")]


def merge(findings: list[Finding], near: int = 3) -> list[Finding]:
    """Same file and a line within `near` = same finding, reported by several."""
    merged: list[Finding] = []
    for f in findings:
        same = next((m for m in merged if m.path.endswith(f.path) or f.path.endswith(m.path)
                     if abs(m.line - f.line) <= near), None)
        if same and not set(f.by) & set(same.by):
            same.by += f.by
            if SEVERITY.get(f.severity, 2) < SEVERITY.get(same.severity, 2):
                same.severity = f.severity
        elif not same:
            merged.append(Finding(f.severity, f.path, f.line, f.text, list(f.by)))
    return sorted(merged, key=lambda m: (-len(m.by), SEVERITY.get(m.severity, 2), m.path, m.line))


def report(merged: list[Finding], raw: dict[str, str]) -> str:
    lines = []
    if not merged:
        lines.append("No findings in the expected format.")
    for f in merged:
        agree = f" ({len(f.by)} reviewers agree)" if len(f.by) > 1 else ""
        lines.append(f"[{f.severity}] {f.path}:{f.line}{agree} - {f.text}  <{', '.join(f.by)}>")
    quiet = [name for name, text in raw.items() if "no bugs found" in (text or "").lower()]
    if quiet:
        lines.append(f"\nNo bugs found by: {', '.join(quiet)}")
    found_by = {name for f in merged for name in f.by}
    for name, text in raw.items():
        if name not in found_by and name not in quiet and (text or "").strip():
            lines.append(f"\n{name} answered outside the finding format:\n{text.strip()[:1200]}")
    return "\n".join(lines)


# --- Greptile through a temporary GitHub PR ---------------------------------

def reviews_path() -> Path:
    return config.HOME / "reviews.jsonl"


def greptile_used_this_month(path: Path | None = None, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    used = 0
    try:
        lines = (path or reviews_path()).read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("reviewer") == "greptile" and str(row.get("time", "")).startswith(now.strftime("%Y-%m")):
            used += int(row.get("credits", 1))
    return used


def _gh(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def greptile(repo: Path, label: str, wait_minutes: float = 15, poll: float = 30,
             sleep=time.sleep) -> tuple[list[Finding], str]:
    """Push HEAD to a review branch on GitHub, open a PR, collect Greptile's
    comments, close the PR and delete the branch. Returns findings and a status line."""
    used = greptile_used_this_month()
    if used >= GREPTILE_MONTHLY:
        return [], f"greptile skipped: {used}/{GREPTILE_MONTHLY} credits used this month"
    sha = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    branch = f"review/{sha}"
    pushed = git(repo, "push", "github", f"HEAD:refs/heads/{branch}", timeout=300)
    if pushed.returncode != 0:
        return [], f"greptile skipped: push to GitHub failed: {pushed.stderr.strip()[:200]}"
    made = _gh("pr", "create", "--repo", "edotwedo/mega-zword", "--base", "main", "--head", branch,
               "--title", f"[review] {label} {sha}",
               "--body", "Temporary review PR opened by `megazword review`; closed automatically.")
    url = made.stdout.strip().splitlines()[-1] if made.returncode == 0 and made.stdout.strip() else ""
    if not url:
        git(repo, "push", "github", "--delete", branch)
        return [], f"greptile skipped: PR not created: {made.stderr.strip()[:200]}"
    number = url.rstrip("/").rsplit("/", 1)[-1]
    with reviews_path().open("a", encoding="utf-8") as out:
        out.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "reviewer": "greptile",
                              "credits": 1, "pr": url, "sha": sha}) + "\n")
    texts: list[str] = []
    deadline = time.monotonic() + wait_minutes * 60
    try:
        while True:
            texts = _greptile_comments(number)
            if texts or time.monotonic() >= deadline:
                break
            sleep(poll)
    finally:
        _gh("pr", "close", number, "--repo", "edotwedo/mega-zword", "--delete-branch")
    if not texts:
        return [], f"greptile: no review within {wait_minutes:g} min ({url}, closed)"
    findings = []
    for text in texts:
        findings += parse(text, "greptile") or _loose(text)
    return findings, f"greptile: {len(texts)} comment(s) from {url} (closed)"


BADGE = re.compile(r"!\[P(?P<p>[0-9]) Badge\]\([^)]*\)")
BADGE_SEVERITY = {"0": "high", "1": "high", "2": "medium", "3": "low"}


def _badge(body: str) -> tuple[str, str]:
    """Greptile/Codex inline comments start with a P1/P2/P3 badge and a bold title.

    Returns (severity, "Title: first sentence") with the HTML stripped.
    """
    m = BADGE.search(body)
    severity = BADGE_SEVERITY.get(m["p"], "medium") if m else "medium"
    text = re.sub(r"<[^>]+>", "", BADGE.sub("", body)).strip()
    title, _, rest = text.partition("\n")
    title = title.strip().strip("*").strip()
    rest = " ".join(rest.split())
    sentence = re.split(r"(?<=[.!?])\s", rest, maxsplit=1)[0] if rest else ""
    return severity, (f"{title}: {sentence}" if title and sentence else title or sentence)[:300]


def _greptile_comments(number: str) -> list[str]:
    texts = []
    for path in (f"repos/edotwedo/mega-zword/pulls/{number}/comments",
                 f"repos/edotwedo/mega-zword/issues/{number}/comments",
                 f"repos/edotwedo/mega-zword/pulls/{number}/reviews"):
        res = _gh("api", path)
        try:
            rows = json.loads(res.stdout or "[]")
        except ValueError:
            continue
        for row in rows if isinstance(rows, list) else []:
            login = ((row.get("user") or {}).get("login") or "").lower()
            body = row.get("body") or ""
            if "greptile" in login and body.strip():
                where = f"{row['path']}:{row.get('line') or row.get('original_line') or 0}" if row.get("path") else ""
                if where:
                    severity, text = _badge(body)
                    texts.append(f"- [{severity}] {where} - {text}")
                else:
                    texts.append(body)
    return texts


def _loose(text: str) -> list[Finding]:
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return [Finding("medium", "(summary)", 0, first[:300], ["greptile"])] if first else []


# --- command ----------------------------------------------------------------

def run(repo: Path, backends: dict[str, Backend], cfg: config.Config, base: str | None = None,
        use_greptile: bool = False, count: int = REVIEWERS, write=print) -> int:
    merged, raw, status = collect(repo, backends, cfg, base, use_greptile, count, write)
    if merged is None:
        return 1
    write(report(merged, raw))
    if status:
        write(f"\n[megazword] {status}")
    return 0 if raw or merged else 1


def blocking(merged: list[Finding]) -> list[Finding]:
    """High-severity findings that at least two reviewers reported independently."""
    return [f for f in merged if f.severity == "high" and len(f.by) >= 2]


def collect(repo: Path, backends: dict[str, Backend], cfg: config.Config, base: str | None = None,
            use_greptile: bool = False, count: int = REVIEWERS, write=print):
    """(merged findings, raw answers, status line); merged is None if nothing ran."""
    diff, label = change(repo, base)
    if not diff.strip():
        write("[megazword] nothing to review")
        return None, {}, ""
    shown, note = clip(diff)
    # Pick spares too: a reviewer that fails is replaced by one from another family.
    picked = pick_reviewers(backends, count + SPARES, cfg.log_path)
    reviewers, spares = picked[:count], picked[count:]
    if not reviewers and not use_greptile:
        write("[megazword] no free reviewers available (check keys with `megazword free test`)")
        return None, {}, ""
    prompt = PROMPT.format(n=len(reviewers) + use_greptile, note=note, diff=shown)
    print(f"[megazword] reviewing {label} ({len(diff):,} chars) with "
          f"{', '.join(b.name for b in reviewers) or 'no free models'}"
          f"{' + greptile' if use_greptile else ''}", file=sys.stderr)
    for b in picked:
        b.timeout = cfg.timeouts.get(b.name, b.timeout)
    with ThreadPoolExecutor(max_workers=max(1, len(reviewers) + 1)) as pool:
        futures = [pool.submit(b.run, prompt) for b in reviewers]
        side = pool.submit(greptile, repo, label) if use_greptile else None
        results: list[Result] = [f.result() for f in futures]
        missing = sum(1 for r in results if not r.ok)
        if missing and spares:
            backup = spares[:missing]
            write(f"[megazword] {missing} reviewer(s) failed; asking {', '.join(b.name for b in backup)}")
            results += [f.result() for f in [pool.submit(b.run, prompt) for b in backup]]
        extra, status = side.result() if side else ([], "")
    findings, raw = [], {}
    for r in results:
        log.append(cfg.log_path, cfg.log_lines, backend=r.backend, forced=True, review=True,
                   seconds=round(r.seconds, 2), ok=r.ok,
                   rejected=None if r.ok else f"failed: {r.error}"[:200],
                   prompt_chars=len(prompt), answer_chars=len(r.text),
                   est_tokens=(len(prompt) + len(r.text)) // 4)
        if r.ok:
            raw[r.backend] = r.text
            findings += parse(r.text, r.backend)
        else:
            write(f"[megazword] {r.backend} failed: {r.error[:160]}")
    findings += extra
    return merge(findings), raw, status


def add_parser(sub) -> None:
    p = sub.add_parser("review", help="free AIs (+ Greptile) review your change")
    p.add_argument("--base", help="compare against this ref (default: origin/main, or the last commit)")
    p.add_argument("--greptile", action="store_true",
                   help=f"also send it to Greptile via a temporary GitHub PR ({GREPTILE_MONTHLY} free/month)")
    p.add_argument("-n", type=int, default=REVIEWERS, help="how many free reviewers (default 1)")


def command(args, backends: dict[str, Backend], cfg: config.Config) -> int:
    return run(Path.cwd(), backends, cfg, args.base, args.greptile, max(1, args.n))
