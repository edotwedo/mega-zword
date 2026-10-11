"""The `megazword` command."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable

from . import __version__, config, log
from .memory import Memory, project_name, with_context
from .backends import Backend, apply_grok_effort, default_backends, grok_label
from .escalate import escalate, looks_failed
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
    run.add_argument("-e", "--edit", action="store_true",
                     help="let the AI change files in the current folder")

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

    out = sub.add_parser("out", help="mark an AI out of usage (auto-pick skips it)")
    out.add_argument("ai", nargs="?", help="which AI; leave out to list current marks")
    group = out.add_mutually_exclusive_group()
    group.add_argument("--until", help="when it's back: 7d, 5h, 2026-10-17 or 2026-10-17T23:30")
    group.add_argument("--clear", action="store_true", help="it's back now")
    sub.add_parser("doctor", help="check local setup without running an AI prompt")
    dash = sub.add_parser("dashboard", help="open a local web page with meters, runs and a run box")
    dash.add_argument("--port", type=int, default=8765)
    dash.add_argument("-p", "--project")
    dash.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    dash.add_argument("--host", default="127.0.0.1",
                      help="address to listen on; use your Tailscale IP for phone access")
    init = sub.add_parser("init", help="write a default config file")
    init.add_argument("--force", action="store_true", help="replace an existing config")

    retry = sub.add_parser("retry", help="last answer not good enough: ask a stronger AI")
    retry.add_argument("-m", "--model", help="force which AI tries next")
    sub.add_parser("chat", help="start an interactive conversation")
    return parser


def show_usage() -> int:
    from datetime import timedelta
    from .runlog import summarize
    from .usage_sources import all_usage
    for plan in all_usage(config.HOME / "log.jsonl"):
        if not plan.windows:
            print(f"{plan.service:7} -  {plan.note}")
            continue
        parts = []
        for w in plan.windows:
            reset = f", resets {w.resets_at.astimezone():%a %I:%M %p}" if w.resets_at else ""
            parts.append(f"{w.name} {w.used_percent:.0f}%{reset}")
        note = f"  ({plan.note})" if plan.note else ""
        print(f"{plan.service:7} {' | '.join(parts)}{note}")
    print("\nMega Zword runs (last 24h)")
    runs = summarize(config.HOME / "log.jsonl", timedelta(hours=24))
    print("AI      runs ok rej/bad sec chars")
    for name in ("claude", "codex", "grok"):
        item = runs.get(name)
        if item:
            chars = item.prompt_chars + item.answer_chars
            print(f"{name:7} {item.runs:4} {item.ok:2} "
                  f"{item.rejected}/{item.failed:<3} {item.seconds:3.0f} {chars:5}")
        else:
            print(f"{name:7}    0  0   0   0     0")
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
               backends: dict[str, Backend], statuses: dict | None = None,
               out: set[str] = frozenset()) -> list[Backend]:
    """Installed AIs to try, in order: this difficulty's route (ranked by
    pacing when statuses are given), then stronger routes as fallbacks.
    AIs in `out` (marked out of usage in config) are skipped."""
    from .pacing import rank
    names: list[str] = []
    for level in LEVELS[LEVELS.index(rating.level):]:
        level_names = route.get(level, [])
        if statuses is not None:
            level_names = rank(statuses, level_names, rating.level)
        names += [n for n in level_names if n not in names]
    return [backends[n] for n in names
            if n in backends and n not in out and backends[n].available()]


def main(argv: list[str] | None = None,
         backends: dict[str, Backend] | None = None,
         cfg: config.Config | None = None,
         rater: Callable[[str], Rating] | None = None,
         statuses: Callable[[], dict] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        from .doctor import run
        return run()
    if backends is None:
        backends = default_backends(edit=getattr(args, "edit", False))
    cfg = cfg if cfg is not None else config.load()
    rater = rater if rater is not None else (lambda p: rate(p, cfg.rater_model))

    if args.command == "backends":
        for name, b in backends.items():
            print(f"{name:10} {'installed' if b.available() else 'not found'}")
        return 0

    if args.command == "init":
        installed = [name for name, backend in backends.items() if backend.available()]
        path = config.HOME / "config.toml"
        try:
            config.write_default(path, installed, args.force)
        except FileExistsError:
            print(f"[megazword] config already exists: {path} (use --force to replace)",
                  file=sys.stderr)
            return 1
        from . import ollama
        print(f"[megazword] wrote {path}")
        print(f"[megazword] installed AIs: {', '.join(installed) if installed else 'none'}")
        print(f"[megazword] Ollama: {'reachable' if ollama.reachable() else 'not reachable'}")
        return 0

    if args.command == "usage":
        return show_usage()

    if args.command == "out":
        return out_command(args, cfg)

    if args.command == "dashboard":
        from .dashboard import serve
        return serve(args.port, args.project, not args.no_browser and args.host == "127.0.0.1",
                     args.host)

    if args.command == "import-hive":
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

    if args.command == "retry":
        return retry_last(args, backends, cfg)

    if args.command == "chat":
        from .chat import run
        return run(backends, cfg, rater, statuses or plan_statuses)

    # command == "run"
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        print("No prompt given.", file=sys.stderr)
        return 2

    rating: Rating | None = None
    if args.model:
        apply_grok_effort(backends, "medium", cfg.grok)
        backend = backends.get(args.model)
        if backend is None and args.edit and args.model == "grok":
            print("[megazword] Grok can't edit files safely on Windows (no sandbox); "
                  "use claude or codex for --edit", file=sys.stderr)
            return 2
        if backend is None:
            print(f"Unknown AI '{args.model}'. Choose from: {', '.join(backends)}",
                  file=sys.stderr)
            return 2
        chain = [backend]
        print(f"[megazword] using {grok_label(backend)} (you chose it)", file=sys.stderr)
    else:
        rating = rater(prompt)
        apply_grok_effort(backends, rating.level, cfg.grok)
        out = cfg.out_now()
        chain = candidates(rating, cfg.route, backends, (statuses or plan_statuses)(), out)
        if not chain:
            print(f"[megazword] no installed AI for a {rating.level} task; "
                  f"check the route in {config.HOME / 'config.toml'}", file=sys.stderr)
            return 1
        print(f"[megazword] rated {rating.level} ({rating.reason}) -> using {grok_label(chain[0])}",
              file=sys.stderr)
        if out:
            print(f"[megazword] skipped (marked out in config): {', '.join(sorted(out))}",
                  file=sys.stderr)
    if getattr(args, "edit", False):
        print(f"[megazword] edit mode: AIs may change files in {Path.cwd()}", file=sys.stderr)

    memory = Memory(config.HOME, args.project or project_name())
    sent = with_context(prompt, memory.context_block()) if args.context else prompt
    # A forced AI (-m) never escalates; otherwise move up the chain on failure.
    return execute(sent, prompt, chain, cfg, memory, rating, forced=bool(args.model))


# The CLIs load their users' global startup rules (e.g. "read the team board
# first"). For a routed one-shot that wastes time and usage, so say so up front.
ONE_SHOT_NOTE = ("[Sent by Mega Zword as a one-shot task. Answer it directly. Skip "
                 "session startup, coordination and check-in routines.]\n\n")


def execute(sent: str, prompt: str, chain: list[Backend], cfg: config.Config,
            memory: Memory, rating: Rating | None, forced: bool,
            start_after: str | None = None, prior_answer: str | None = None,
            on_answer: Callable[[str], None] | None = None) -> int:
    """Run the chain with escalation, log every attempt, print the answer,
    and remember the run so `megazword retry` can pick it up."""
    first_line = prompt.strip().splitlines()[0][:80]
    for b in chain:  # per-AI timeouts from config ([timeouts] claude = 600)
        b.timeout = cfg.timeouts.get(b.name, b.timeout)

    def on_attempt(name, result, reason):
        log.append(cfg.log_path, backend=name, forced=forced,
                   rating=rating.level if rating else None,
                   rater=rating.source if rating else None,
                   seconds=round(result.seconds, 2), ok=result.ok and not reason,
                   rejected=reason, prompt_chars=len(prompt), answer_chars=len(result.text))
        memory.add("done", f"{'REJECTED (' + reason + ')' if reason else 'ok'}: {first_line}",
                   by=name)
        if reason:
            print(f"[megazword] {name} rejected after {result.seconds:.1f}s: {reason}",
                  file=sys.stderr)

    judge = looks_failed
    if cfg.quality_check and not forced:
        # Only auto-picked runs: if Phil chose the AI, don't second-guess it.
        from .quality import judge_for
        judge = judge_for(prompt, cfg.rater_model, looks_failed)
    outcome = escalate(ONE_SHOT_NOTE + sent, chain, judge=judge, on_attempt=on_attempt,
                       start_after=start_after, prior_answer=prior_answer)
    if outcome.result is None:
        print("[megazword] no AI gave a usable answer", file=sys.stderr)
        return 1
    result = outcome.result
    save_last_run(sent, prompt, [b.name for b in chain], result.backend, result.text,
                  memory.project, rating.level if rating else None)
    if on_answer is None:
        print(result.text)
    else:
        on_answer(result.text)
    print(f"[megazword] {result.backend} answered in {result.seconds:.1f}s"
          + (" (after escalating)" if outcome.escalated else ""), file=sys.stderr)
    return 0


def out_command(args, cfg: config.Config) -> int:
    path = config.HOME / "config.toml"
    if not args.ai:
        marks = cfg.out_now()
        if not marks:
            print("[megazword] no AI is marked out")
        for name in sorted(marks):
            print(f"{name:7} out until {cfg.out_until[name].astimezone():%a %b %d %I:%M %p}")
        return 0
    if not args.until and not args.clear:
        print("[megazword] say when it's back (--until 7d) or --clear", file=sys.stderr)
        return 2
    try:
        until = None if args.clear else config.parse_until(args.until)
        config.set_out(path, args.ai, until)
    except ValueError as exc:
        print(f"[megazword] {exc}", file=sys.stderr)
        return 2
    if until:
        print(f"[megazword] {args.ai} marked out until {until.astimezone():%a %b %d %I:%M %p}")
    else:
        print(f"[megazword] {args.ai} is back in the rotation")
    return 0


def last_run_path():
    return config.HOME / "last_run.json"


def save_last_run(sent, prompt, chain, backend, answer, project, level) -> None:
    import json
    path = last_run_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sent": sent, "prompt": prompt, "chain": chain,
                                "backend": backend, "answer": answer,
                                "project": project, "rating": level}), encoding="utf-8")
    from . import answers
    answers.add(prompt, answer, backend, project, level)


def retry_last(args, backends: dict[str, Backend], cfg: config.Config,
               on_answer: Callable[[str], None] | None = None) -> int:
    import json
    path = last_run_path()
    if not path.exists():
        print("[megazword] nothing to retry yet; run something first", file=sys.stderr)
        return 2
    last = json.loads(path.read_text(encoding="utf-8"))
    memory = Memory(config.HOME, last["project"])
    level = last.get("rating") or "medium"
    if level == "easy":
        level = "medium"  # a retry is real work, not a status pass
    apply_grok_effort(backends, level, cfg.grok)
    rating = Rating(level, "retry", "retry") if last.get("rating") else None
    if args.model:
        if args.model not in backends:
            print(f"Unknown AI '{args.model}'. Choose from: {', '.join(backends)}",
                  file=sys.stderr)
            return 2
        names = [last["backend"], args.model]
    else:
        # Strongest first: the hard-task route, then anything else from the
        # original chain. The AI that answered last goes first so escalate()
        # can skip it.
        names = list(dict.fromkeys([last["backend"], *cfg.route.get("hard", []),
                                    *last["chain"]]))
    chain = [backends[n] for n in names
             if n in backends and (n == last["backend"]
                                   or (n not in cfg.out_now() and backends[n].available()))]
    if not any(b.name != last["backend"] for b in chain):
        print(f"[megazword] no AI left to try after {last['backend']}", file=sys.stderr)
        return 1
    print(f"[megazword] {last['backend']}'s answer rejected; trying a stronger AI",
          file=sys.stderr)
    return execute(last["sent"], last["prompt"], chain, cfg, memory, rating,
                   forced=bool(args.model), start_after=last["backend"],
                   prior_answer=last["answer"], on_answer=on_answer)


if __name__ == "__main__":
    sys.exit(main())
