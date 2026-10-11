"""The `megazword` command."""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from . import __version__, config, log
from .memory import Memory, project_name, with_context
from .backends import Backend, default_backends
from .escalate import escalate
from .rater import Rating, rate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="megazword",
        description="Run your AI CLIs from one place.",
    )
    parser.add_argument("--version", action="version", version=f"megazword {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a prompt; picks an AI unless -m is given")
    run.add_argument("prompt", nargs="?", help="the prompt (reads stdin if left out)")
    run.add_argument("-m", "--model", help="force a specific AI, e.g. claude")
    run.add_argument("-c", "--context", action="store_true",
                     help="include this project's memory (decisions, recent activity)")
    run.add_argument("-p", "--project", help="project name (default: current repo/folder)")

    for name, help_text in (("note", "save a note to project memory"),
                            ("decide", "record a decision every AI must follow")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("text")
        cmd.add_argument("-p", "--project")
        cmd.add_argument("--by", default="phil", help="who is adding it")

    imp = sub.add_parser("import-hive",
                         help="copy decisions and open handoffs from an old Hive repo clone")
    imp.add_argument("repo", help="path to a local clone of the workshop repo")
    imp.add_argument("-p", "--project", default="hive")

    hist = sub.add_parser("history", help="show project memory")
    hist.add_argument("-n", type=int, default=20)
    hist.add_argument("-p", "--project")

    sub.add_parser("backends", help="list AIs and whether they're installed")
    sub.add_parser("usage", help="show each AI plan's current usage")
    return parser


def show_usage() -> int:
    from .usage_sources import all_usage
    for plan in all_usage():
        if not plan.windows:
            print(f"{plan.service:7} -  {plan.note}")
            continue
        parts = []
        for w in plan.windows:
            reset = f", resets {w.resets_at.astimezone():%a %I:%M %p}" if w.resets_at else ""
            parts.append(f"{w.name} {w.used_percent:.0f}%{reset}")
        note = f"  ({plan.note})" if plan.note else ""
        print(f"{plan.service:7} {' | '.join(parts)}{note}")
    return 0


def plan_statuses() -> dict:
    """Current pacing status per AI; empty if the meters can't be read."""
    from .pacing import status
    from .usage_sources import all_usage
    try:
        return {u.service: status(u) for u in all_usage()}
    except Exception:
        return {}


LEVELS = ("easy", "medium", "hard")


def candidates(rating: Rating, route: dict[str, list[str]],
               backends: dict[str, Backend], statuses: dict | None = None) -> list[Backend]:
    """Installed AIs to try, in order: this difficulty's route (ranked by
    pacing when statuses are given), then stronger routes as fallbacks."""
    from .pacing import rank
    names: list[str] = []
    for level in LEVELS[LEVELS.index(rating.level):]:
        level_names = route.get(level, [])
        if statuses is not None:
            level_names = rank(statuses, level_names, rating.level)
        names += [n for n in level_names if n not in names]
    return [backends[n] for n in names if n in backends and backends[n].available()]


def main(argv: list[str] | None = None,
         backends: dict[str, Backend] | None = None,
         cfg: config.Config | None = None,
         rater: Callable[[str], Rating] | None = None,
         statuses: Callable[[], dict] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backends = backends if backends is not None else default_backends()
    cfg = cfg if cfg is not None else config.load()
    rater = rater if rater is not None else (lambda p: rate(p, cfg.rater_model))

    if args.command == "backends":
        for name, b in backends.items():
            print(f"{name:10} {'installed' if b.available() else 'not found'}")
        return 0

    if args.command == "usage":
        return show_usage()

    if args.command == "import-hive":
        from pathlib import Path
        from .hive_import import import_hive
        repo = Path(args.repo)
        if not (repo / "DECISIONS.md").exists() and not (repo / "handoffs").is_dir():
            print(f"[megazword] {repo} doesn't look like a Hive repo "
                  "(no DECISIONS.md or handoffs/)", file=sys.stderr)
            return 2
        memory = Memory(config.HOME, args.project)
        decisions, handoffs = import_hive(repo, memory)
        print(f"[megazword] imported {decisions} decisions and {handoffs} open handoffs "
              f"into '{memory.project}' memory (old repo not changed)", file=sys.stderr)
        return 0

    if args.command in ("note", "decide", "history"):
        memory = Memory(config.HOME, args.project or project_name())
        if args.command == "history":
            for e in memory.recent(args.n):
                print(f"{e.time[:16]}  {e.by:8} {e.kind:8} {e.text}")
            return 0
        memory.add("decision" if args.command == "decide" else "note", args.text, args.by)
        print(f"[megazword] saved to {memory.project} memory", file=sys.stderr)
        return 0

    # command == "run"
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        print("No prompt given.", file=sys.stderr)
        return 2

    rating: Rating | None = None
    if args.model:
        backend = backends.get(args.model)
        if backend is None:
            print(f"Unknown AI '{args.model}'. Choose from: {', '.join(backends)}",
                  file=sys.stderr)
            return 2
        chain = [backend]
        print(f"[megazword] using {backend.name} (you chose it)", file=sys.stderr)
    else:
        rating = rater(prompt)
        chain = candidates(rating, cfg.route, backends, (statuses or plan_statuses)())
        if not chain:
            print(f"[megazword] no installed AI for a {rating.level} task; "
                  f"check the route in {config.HOME / 'config.toml'}", file=sys.stderr)
            return 1
        print(f"[megazword] rated {rating.level} ({rating.reason}) -> using {chain[0].name}",
              file=sys.stderr)

    memory = Memory(config.HOME, args.project or project_name())
    first_line = prompt.strip().splitlines()[0][:80]

    def on_attempt(name, result, reason):
        log.append(cfg.log_path, backend=name, forced=bool(args.model),
                   rating=rating.level if rating else None,
                   rater=rating.source if rating else None,
                   seconds=round(result.seconds, 2), ok=result.ok and not reason,
                   rejected=reason, prompt_chars=len(prompt), answer_chars=len(result.text))
        memory.add("done", f"{'REJECTED (' + reason + ')' if reason else 'ok'}: {first_line}",
                   by=name)
        if reason:
            print(f"[megazword] {name} rejected after {result.seconds:.1f}s: {reason}",
                  file=sys.stderr)

    # A forced AI (-m) never escalates; otherwise move up the chain on failure.
    sent = with_context(prompt, memory.context_block()) if args.context else prompt
    outcome = escalate(sent, chain, on_attempt=on_attempt)
    if outcome.result is None:
        print("[megazword] no AI gave a usable answer", file=sys.stderr)
        return 1
    result = outcome.result
    print(result.text)
    print(f"[megazword] {result.backend} answered in {result.seconds:.1f}s"
          + (" (after escalating)" if outcome.escalated else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
