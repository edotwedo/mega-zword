"""Markdown project reports. Only selected memory/answer fields and run totals leave here."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import html
import os
from pathlib import Path
import re
import sys

from . import answers, config, memory, runlog
from .filelock import locked


def cutoff(value: str, now: datetime) -> datetime:
    """Relative days or a calendar date at midnight UTC, inclusive."""
    try:
        if re.fullmatch(r"[1-9][0-9]*d", value):
            start = now - timedelta(days=int(value[:-1]))
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            start = datetime.combine(date.fromisoformat(value), datetime.min.time(), timezone.utc)
        else:
            raise ValueError
        if start > now:
            raise ValueError
        return start
    except (ValueError, OverflowError):
        raise ValueError("--since must be positive days (e.g. 7d) or YYYY-MM-DD, not in the future") from None


def redact(value: object) -> str:
    text = str(value)
    # Known environment keys plus common provider key formats, including keys
    # accidentally pasted into a saved prompt. Never read or export config values.
    for name, secret in os.environ.items():
        if name.upper().endswith("API_KEY") and secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"\b(?:sk-|gsk_|xai-|AIza)[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
    return re.sub(r"(?i)(\b[a-z0-9_-]*api[_-]?key\b[\"']?\s*[:=]\s*)[^\s,;]+",
                  r"\1[REDACTED]", text)


def escaped(value: object) -> str:
    text = html.escape(redact(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text)


def quote(value: object) -> str:
    return "\n".join("> " + line for line in escaped(value).splitlines()) or ">"


def fenced(value: object) -> str:
    text = redact(value).replace("\r\n", "\n").replace("\r", "\n")
    fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", text)), default=0))
    return f"{fence}\n{text}\n{fence}"


def render(project: str, log_path: Path, since: str = "7d",
           now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    start = cutoff(since, now)
    memory.check_project(config.HOME, project, allowed={memory.project_name()})

    def in_window(stamp):
        parsed = runlog._time(stamp)
        return parsed is not None and start <= parsed <= now

    mem = memory.Memory(config.HOME, project)
    if mem.path.exists():
        with locked(mem.path):
            entries = mem.entries()
    else:
        entries = []
    lines = [f"# Project report: {escaped(project)}", "",
             f"Window (UTC, inclusive): {start.isoformat()} to {now.isoformat()}", "",
             "Decisions include all saved history. Other sections cover the window.",
             "Only retained records are available; older answers and runs may have been trimmed.", ""]
    for heading, kind in (("Decisions", "decision"), ("Notes", "note"), ("Done", "done")):
        lines += [f"## {heading}", ""]
        selected = [e for e in entries if e.kind == kind and (kind == "decision" or in_window(e.time))]
        for e in selected:
            lines += [f"{escaped(e.time)} — {escaped(e.by)}".replace("\n", " "), "", quote(e.text), ""]
        if not selected:
            lines += ["None.", ""]
    lines += ["## Past answers", ""]
    saved = [r for r in answers.recent(n=sys.maxsize, project=project) if in_window(r.get("time"))]
    for r in reversed(saved):
        lines += [f"AI: {escaped(r.get('backend', 'unknown'))} — {escaped(r['time'])}".replace("\n", " "),
                  "", quote(r.get("prompt", "")), "", fenced(r.get("answer", "")), ""]
    if not saved:
        lines += ["None.", ""]
    lines += ["## Per-AI run summary", "",
              "| AI | Runs | OK | Rejected | Failed | Seconds | Estimated tokens |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    totals = runlog.summarize(log_path, now - start, now, project=project)
    for name, s in sorted(totals.items()):
        label = escaped(name).replace("\n", " ").replace("\r", " ")
        lines.append(f"| {label} | {s.runs} | {s.ok} | {s.rejected} | {s.failed} | {s.seconds:.1f} | {s.est_tokens} |")
    if not totals:
        lines += ["", "No runs in this window."]
    lines += ["", "Tokens are rough estimates from saved run counts.", ""]
    return "\n".join(lines)


def command(args, cfg: config.Config | None = None) -> int:
    try:
        project = args.project if args.project is not None else memory.project_name()
        memory.check_project(config.HOME, project, allowed={memory.project_name()})
        cutoff(args.since, datetime.now(timezone.utc))
        cfg = cfg if cfg is not None else config.load()
        report = render(project, cfg.log_path, args.since)
        if args.out is None:
            print(report, end="")
        else:
            # Exclusive creation makes overwrite refusal safe against a race.
            with args.out.open("w" if args.force else "x", encoding="utf-8", newline="\n") as f:
                f.write(report)
        return 0
    except FileExistsError:
        print("[megazword] output already exists (use --force to replace)", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError):
        # Config parse errors can contain secrets: don't echo their contents.
        print("[megazword] export failed: check project name, --since, config and output path", file=sys.stderr)
        return 2
