"""The `megazword` command."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

from . import __version__, config, failures, log
from .memory import Memory, project_name, with_context
from .backends import Backend, apply_levels, default_backends, grok_label
from .escalate import escalate, looks_failed
from .rater import Rating, rate


COMMAND_GROUPS = {
    "Ask": ("run", "chat", "retry", "room"),
    "See": ("start", "usage", "plan", "stats", "advise", "dashboard", "projects", "history", "export",
            "sentinel", "floor", "mcp"),
    "Set up": ("init", "doctor", "out", "backends", "app"),
    "Memory": ("note", "decide", "import-hive"),
}


class CLIParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f"{self.prog}: error: {' '.join(message.split())}\n")

    def format_help(self):
        sub = next((a for a in self._actions
                    if isinstance(a, argparse._SubParsersAction)), None)
        if sub is None or self.prog != "megazword":
            return super().format_help()
        formatter = self._get_formatter()
        formatter.add_usage(self.usage, self._actions, self._mutually_exclusive_groups)
        formatter.add_text(self.description)
        for group in self._action_groups:
            actions = [a for a in group._group_actions if a is not sub]
            if actions:
                formatter.start_section(group.title)
                formatter.add_arguments(actions)
                formatter.end_section()
        commands = {a.dest: a for a in sub._choices_actions}
        for title, names in COMMAND_GROUPS.items():
            formatter.start_section(title)
            formatter.add_arguments([commands[n] for n in names])
            formatter.end_section()
        formatter.add_text(self.epilog)
        return formatter.format_help()


def build_parser() -> argparse.ArgumentParser:
    parser = CLIParser(
        prog="megazword",
        description="Run your AI CLIs from one place.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n  megazword run "Explain this code"\n'
               '  megazword run -m claude "Review my plan"\n'
               '  megazword chat\n  megazword out grok --until 7d',
    )
    parser.add_argument("--version", action="version", version=f"megazword {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")  # none: start screen

    run = sub.add_parser("run", help="run a prompt; picks an AI unless -m is given")
    run.add_argument("prompt", nargs="?", help="the prompt (reads stdin if left out)")
    run.add_argument("-m", "--model", help="force a specific AI, e.g. claude")
    run.add_argument("-c", "--context", action="store_true",
                     help="include this project's memory (decisions, recent activity)")
    run.add_argument("-p", "--project", help="project name (default: current repo/folder)")
    run.add_argument("-e", "--edit", action="store_true",
                     help="let the AI change files in the current folder")
    run.add_argument("--compare", metavar="AIS",
                     help="same prompt on 2-3 AIs at once, e.g. claude,codex")

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

    exp = sub.add_parser("export", help="export project memory, answers and run totals as Markdown")
    exp.add_argument("-p", "--project", help="project name (default: current repo/folder)")
    exp.add_argument("--since", default="7d", help="window start: Nd or YYYY-MM-DD (UTC; default: 7d)")
    exp.add_argument("--out", type=Path, help="output file (default: stdout)")
    exp.add_argument("--force", action="store_true", help="replace an existing output file")

    sub.add_parser("backends", help="list AIs and whether they're installed")
    sub.add_parser("usage", help="show each AI plan's current usage")
    sub.add_parser("plan", help="rank the AIs for new work by live spare usage")
    sub.add_parser("start", help="text start screen (plain `megazword` opens the app window)")
    sub.add_parser("projects", help="list projects with memory entries and last activity")
    sub.add_parser("advise", help="suggest a route order from stats and votes (changes nothing)")
    st = sub.add_parser("stats", help="per-day, per-AI table from the run log")
    st.add_argument("--days", type=int, default=7)
    sent = sub.add_parser("sentinel", help="uptime and security log (reboots, logins, network)")
    sent.add_argument("action", nargs="?", choices=("status", "log", "check", "install"),
                      default="status")
    sent.add_argument("-n", type=int, default=20, help="how many events to show for log")
    sent.add_argument("--yes", action="store_true",
                      help="for install: actually create the scheduled task")
    floor = sub.add_parser("floor", help="Hive floor: seats, introduce, peek/wait; suggest picks a seat")
    floor.add_argument("action", nargs="?",
                       choices=("status", "introduce", "peek", "wait", "suggest"),
                       default="status")
    floor.add_argument("kind", nargs="?", choices=("bulk", "edit", "decide", "review"),
                       help="suggest: which seated model should take this kind of job")
    floor.add_argument("--room", default="hive", help="hive room name (default: hive)")
    floor.add_argument("-n", type=int, default=10, help="peek: how many messages")
    floor.add_argument("--timeout", type=int, default=120, help="wait: seconds to block")
    floor.add_argument("--after", type=int, default=None,
                       help="wait: message count from peek's (after=N); returns anything newer")
    sub.add_parser("mcp", help="Hive MCP server on stdio (for AI CLIs to connect to)")

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
    dash.add_argument("--app", action="store_true",
                      help="open in its own desktop window (pywebview; else Edge/Chrome app mode)")
    appc = sub.add_parser("app", help="Start menu shortcut for the Mega Zword desktop window")
    appc.add_argument("action", choices=["install", "remove"])
    connection = dash.add_mutually_exclusive_group()
    connection.add_argument("--host", default="127.0.0.1",
                      help="address to listen on; use your Tailscale IP for phone access")
    connection.add_argument("--phone", action="store_true",
                            help="check Tailscale and listen on this PC's private phone address")
    init = sub.add_parser("init", help="write a default config file")
    init.add_argument("--force", action="store_true", help="replace an existing config")

    retry = sub.add_parser("retry", help="last answer not good enough: ask a stronger AI")
    retry.add_argument("-m", "--model", help="force which AI tries next")
    sub.add_parser("chat", help="start an interactive conversation")

    room = sub.add_parser("room", help="Hive bot room: group chat between Phil and the bots")
    room_sub = room.add_subparsers(dest="action", metavar="ACTION")

    room_start = room_sub.add_parser("start", help="start or resume a room session")
    room_start.add_argument("--room", default="hive", help="room name (default: hive)")
    room_start.add_argument("--turns", type=int, help="max turns to run (default: 12)")
    room_start.add_argument("-p", "--project", help="primary project override")

    room_stop = room_sub.add_parser("stop", help="stop active room session")
    room_stop.add_argument("--room", default="hive", help="room name (default: hive)")

    room_say = room_sub.add_parser("say", help="post a message into the room")
    room_say.add_argument("text", help="message to post")
    room_say.add_argument("--room", default="hive", help="room name (default: hive)")
    room_say.add_argument("--by", default="phil", help="author name (default: phil)")

    room_show = room_sub.add_parser("show", help="show recent room messages")
    room_show.add_argument("--room", default="hive", help="room name (default: hive)")
    room_show.add_argument("-n", type=int, default=20, help="number of messages to show")

    room_post = room_sub.add_parser("post-summary", help="show the room summary; --post sends it to Q (PR #33)")
    room_post.add_argument("--room", default="hive", help="room name (default: hive)")
    room_post.add_argument("--post", action="store_true", help="actually post it to Q with gh")

    for action in sub._choices_actions:
        sub.choices[action.dest].description = action.help
    return parser


def show_plan() -> int:
    """Labor plan from live usage. Re-run before each piece of work (Phil)."""
    from .meters import labor_order, summarize_all
    from .usage_sources import all_usage
    try:
        out_until = config.load().out_until
    except (ValueError, TypeError, OSError):
        out_until = {}
    order = labor_order(summarize_all(all_usage(config.HOME / "log.jsonl"), out_until))
    print("Labor plan from live usage (most room first). A reading, not a rule:")
    for i, (name, reason) in enumerate(order, 1):
        print(f"  {i}. {name:7} {reason}")
    if order and "left in its" in order[0][1]:
        print(f"New work goes to {order[0][0]} first; keep work already in progress where it is.")
    else:
        print("No live meter readings; check usage by hand before assigning work.")
    return 0


def show_usage() -> int:
    from datetime import timedelta
    from .runlog import summarize
    from .meters import summarize_all
    from .usage_sources import all_usage
    plans = all_usage(config.HOME / "log.jsonl")
    by_name = {p.service: p for p in plans}
    try:
        out_until = config.load().out_until
    except (ValueError, TypeError, OSError):
        out_until = {}
    # Same one-line summary as the start screen and dashboard, then details.
    for summary in summarize_all(plans, out_until):
        print(summary.line())
        plan = by_name.get(summary.service)
        if plan and plan.windows:
            parts = []
            for w in plan.windows:
                reset = f", resets {w.resets_at.astimezone():%a %I:%M %p}" if w.resets_at else ""
                parts.append(f"{w.name} {w.used_percent:.0f}%{reset}")
            print(f"{'':8}{' | '.join(parts)}")
    print("\nMega Zword runs (last 24h)")
    runs = summarize(config.HOME / "log.jsonl", timedelta(hours=24))
    print("AI      runs ok rej/bad sec chars est_tokens")
    for name in ("claude", "codex", "grok", "gemini"):
        item = runs.get(name)
        if item:
            chars = item.prompt_chars + item.answer_chars
            print(f"{name:7} {item.runs:4} {item.ok:2} "
                  f"{item.rejected}/{item.failed:<3} {item.seconds:3.0f} {chars:5} {item.est_tokens:10}")
        else:
            print(f"{name:7}    0  0 0/0     0     0          0")
    print("est_tokens: rough (prompt + answer chars) // 4; old runs count as 0.")
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
    chain = [backends[n] for n in names
             if n in backends and n not in out and backends[n].available()]
    if rating.level == "easy":
        # B15 (Phil): AIs that train on prompts go first for small repetitive jobs.
        chain.sort(key=lambda b: not getattr(b, "trains_on_data", False))
    return chain


def opens_app() -> bool:
    """B13: plain `megazword` opens the app, but only for a person at a terminal. Scripts,
    tests and pipes (stdout not a terminal) or MEGAZWORD_NO_APP=1 keep the text start screen."""
    if os.environ.get("MEGAZWORD_NO_APP", "").strip() not in ("", "0"):
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def launch_app() -> None:
    """Start `megazword dashboard --app` detached, so closing this terminal leaves it running."""
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    python = str(windowless if windowless.exists() else exe)
    cmd = [python, "-c", "import sys; from megazword.cli import main; "
           "sys.exit(main(['dashboard', '--app']))"]
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags,
                     start_new_session=os.name != "nt", close_fds=True)


def main(argv: list[str] | None = None,
         backends: dict[str, Backend] | None = None,
         cfg: config.Config | None = None,
         rater: Callable[[str], Rating] | None = None,
         statuses: Callable[[], dict] | None = None) -> int:
    if argv is None:  # real CLI run, not a test calling main([...])
        config.load_user_env()
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        from .doctor import run
        return run()
    if args.command == "export":
        from .export import command
        return command(args, cfg)
    if args.command == "mcp":
        from .mcp_hive import serve
        # Anything that prints by accident must not corrupt the JSON-RPC stream.
        out, saved = sys.stdout.buffer, sys.stdout
        sys.stdout = sys.stderr
        try:
            return serve(sys.stdin.buffer, out)
        finally:
            sys.stdout = saved
    if cfg is None:
        try:
            cfg = config.load()
        except (ValueError, TypeError, OSError) as exc:  # TOMLDecodeError is a ValueError
            print(f"[megazword] can't read {config.HOME / 'config.toml'}: {exc}\n"
                  "[megazword] fix that line (or rename the file to start fresh), "
                  "then run `megazword doctor`", file=sys.stderr)
            return 2
    if args.command is None and opens_app():
        launch_app()
        print("[megazword] opening the Mega Zword app window "
              "(`megazword start` shows the text start screen)")
        return 0
    if args.command in (None, "start"):
        from .start import render
        print(render(cfg))
        return 0
    if backends is None:
        backends = default_backends(edit=getattr(args, "edit", False), free_models=cfg.free,
                                    lean=cfg.lean)
    rater = rater if rater is not None else (lambda p: rate(p, cfg.rater_model))

    if args.command == "backends":
        for name, b in backends.items():
            mark = "installed" if b.available() else "not found"
            trains = "  (trains on prompts)" if getattr(b, "trains_on_data", False) else ""
            print(f"{name:12} {mark}{trains}")
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

    if args.command == "projects":
        from .memory import list_projects
        found = list_projects(config.HOME)
        if not found:
            print("[megazword] no projects yet; they appear after a run, note or decision")
            return 0
        print("project              entries  decisions  last activity")
        for p in found:
            last = p.last[:16].replace("T", " ") if p.last else "-"
            print(f"{p.name[:20]:20} {p.entries:7}  {p.decisions:9}  {last}")
        return 0

    if args.command == "plan":
        return show_plan()

    if args.command == "advise":
        from . import advise
        print(advise.text(advise.advise(cfg)))
        return 0

    if args.command == "stats":
        from .stats import daily, table
        print(table(daily(cfg.log_path, max(1, args.days))))
        return 0

    if args.command == "sentinel":
        from . import sentinel
        return sentinel.command(args)

    if args.command == "floor":
        from . import floor
        return floor.command(args, backends, cfg)

    if args.command == "out":
        return out_command(args, cfg)

    if args.command == "dashboard":
        from .dashboard import serve
        if args.phone:
            from .phone import address
            try:
                args.host = address()
            except ValueError as exc:
                print(f"[megazword] {exc}", file=sys.stderr)
                return 2
            print("[megazword] Connect Tailscale on your phone and open the full link below. "
                  "Keep this terminal and the PC awake while using it.", file=sys.stderr)
        return serve(args.port, args.project, not args.no_browser and args.host == "127.0.0.1",
                     args.host, app_window=args.app)

    if args.command == "app":
        from . import desktop
        if args.action == "remove":
            gone = desktop.remove_shortcut()
            print("[megazword] Start menu shortcut removed" if gone
                  else "[megazword] no Start menu shortcut to remove", file=sys.stderr)
            return 0
        if os.name != "nt":
            print("[megazword] the Start menu shortcut is Windows only", file=sys.stderr)
            return 2
        try:
            link = desktop.install_shortcut()
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[megazword] couldn't make the shortcut: {exc}", file=sys.stderr)
            return 1
        print(f"[megazword] Start menu: 'Mega Zword' ({link})", file=sys.stderr)
        if not desktop.available():
            print("[megazword] tip: `pip install pywebview` for the real desktop window; "
                  "without it the shortcut opens an Edge/Chrome app window", file=sys.stderr)
        return 0

    if args.command == "import-hive":
        from .hive_import import import_hive
        repo = Path(args.repo)
        if not (repo / "DECISIONS.md").exists() and not (repo / "handoffs").is_dir():
            print(f"[megazword] {repo} doesn't look like a Hive repo "
                  "(no DECISIONS.md or handoffs/)", file=sys.stderr)
            return 2
        memory = Memory(config.HOME, args.project, cfg.memory_lines)
        decisions, handoffs = import_hive(repo, memory)
        print(f"[megazword] imported {decisions} decisions and {handoffs} open handoffs "
              f"into '{memory.project}' memory (old repo not changed)", file=sys.stderr)
        return 0

    if args.command in ("note", "decide", "history"):
        memory = Memory(config.HOME, args.project or project_name(), cfg.memory_lines)
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

    if args.command == "room":
        from . import room
        action = getattr(args, "action", None)
        if not action:
            print("Usage: megazword room start|stop|say|show|post-summary", file=sys.stderr)
            return 2
        if action == "start":
            return room.run_room(args.room, args.turns, args.project, backends=backends, cfg=cfg,
                                 statuses=statuses or plan_statuses)
        if action == "stop":
            return room.stop(args.room)
        if action == "say":
            try:
                return room.say(args.room, args.text, author=args.by)
            except PermissionError as e:
                print(f"[megazword room] {e}", file=sys.stderr)
                return 2
        if action == "show":
            return room.show(args.room, n=args.n)
        if action == "post-summary":
            return room.post_summary(args.room, post=args.post)

    # command == "run"
    try:
        prompt = args.prompt if args.prompt is not None else (
            "" if sys.stdin.isatty() else sys.stdin.read())
    except (OSError, ValueError):
        print("No prompt given; pass a prompt or pipe text on stdin.", file=sys.stderr)
        return 2
    if not prompt.strip():
        print("No prompt given.", file=sys.stderr)
        return 2

    if args.compare:
        from . import compare
        if args.model or args.edit:
            print("[megazword] --compare can't be combined with -m or --edit "
                  "(parallel edits to one folder would collide)", file=sys.stderr)
            return 2
        apply_levels(backends, "medium", cfg.grok, cfg.levels)
        try:
            names = compare.parse_names(args.compare, backends)
        except ValueError as exc:
            print(f"[megazword] {exc}", file=sys.stderr)
            return 2
        memory = Memory(config.HOME, args.project or project_name(), cfg.memory_lines)
        sent = with_context(prompt, memory.context_block()) if args.context else prompt
        level = rater(prompt).level  # free local rating, so votes count per difficulty
        return compare.run(ONE_SHOT_NOTE + sent, prompt, names, backends, cfg, memory,
                           level=level)

    rating: Rating | None = None
    if args.model:
        apply_levels(backends, "medium", cfg.grok, cfg.levels)
        backend = backends.get(args.model)
        if backend is None and args.edit and args.model == "gemini":
            print("[megazword] Gemini edit mode is disabled (folder-contained writes "
                  "are unverified); use claude or codex for --edit", file=sys.stderr)
            return 2
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
        apply_levels(backends, rating.level, cfg.grok, cfg.levels)
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

    memory = Memory(config.HOME, args.project or project_name(), cfg.memory_lines)
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
            on_answer: Callable[[str], None] | None = None,
            tab_id: str | None = None) -> int:
    """Run the chain with escalation, log every attempt, print the answer,
    and remember the run so `megazword retry` can pick it up."""
    first_line = prompt.strip().splitlines()[0][:80]
    for b in chain:  # per-AI timeouts from config ([timeouts] claude = 600)
        b.timeout = cfg.timeouts.get(b.name, b.timeout)

    network = failures.Watch()

    def on_attempt(name, result, reason):
        failure = None
        if not result.ok:
            failure = explain_failure(name, result.error, cfg)
        trains = any(getattr(x, "trains_on_data", False) for x in chain if x.name == name)
        log.append(cfg.log_path, cfg.log_lines, backend=name, forced=forced, project=memory.project,
                   rating=rating.level if rating else None,
                   rater=rating.source if rating else None,
                   seconds=round(result.seconds, 2), ok=result.ok and not reason,
                   rejected=reason, prompt_chars=len(prompt), answer_chars=len(result.text),
                   est_tokens=(len(prompt) + len(result.text)) // 4,
                   trains_on_data=trains)
        memory.add("done", f"{'REJECTED (' + reason + ')' if reason else 'ok'}: {first_line}",
                   by=name)
        if reason and not failure:
            print(f"[megazword] {name} rejected after {result.seconds:.1f}s: {reason}",
                  file=sys.stderr)
        network.saw(failure)  # two network failures in a row stops the chain

    judge = looks_failed
    if cfg.quality_check and not forced:
        # Only auto-picked runs: if Phil chose the AI, don't second-guess it.
        from .quality import judge_for
        judge = judge_for(prompt, cfg.rater_model, looks_failed)
    try:
        outcome = escalate(ONE_SHOT_NOTE + sent, chain, judge=judge, on_attempt=on_attempt,
                           start_after=start_after, prior_answer=prior_answer)
    except failures.NetworkDown:
        print("[megazword] stopped: two AIs in a row couldn't reach the internet, so it's "
              "probably your connection. Check it and try again.", file=sys.stderr)
        return 1
    if outcome.result is None:
        print("[megazword] no AI gave a usable answer", file=sys.stderr)
        return 1
    result = outcome.result
    save_last_run(sent, prompt, [b.name for b in chain], result.backend, result.text,
                  memory.project, rating.level if rating else None, tab_id=tab_id)
    if on_answer is None:
        print(result.text)
    else:
        on_answer(result.text)
    print(f"[megazword] {result.backend} answered in {result.seconds:.1f}s"
          + (" (after escalating)" if outcome.escalated else ""), file=sys.stderr)
    return 0


def out_command(args, cfg: config.Config) -> int:
    path = config.HOME / "config.toml"
    if not args.ai and (args.until is not None or args.clear):
        print("[megazword] name an AI to mark out or clear", file=sys.stderr)
        return 2
    if args.ai and args.ai not in default_backends() and args.ai not in cfg.out_until:
        print(f"[megazword] Unknown AI {args.ai!r}", file=sys.stderr)
        return 2
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
    except OverflowError:
        print("[megazword] --until is too far in the future; use 7d, 5h or a date",
              file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"[megazword] {' '.join(str(exc).split())}", file=sys.stderr)
        return 2
    if until:
        print(f"[megazword] {args.ai} marked out until {until.astimezone():%a %b %d %I:%M %p}")
    else:
        print(f"[megazword] {args.ai} is back in the rotation")
    return 0


def explain_failure(name: str, error: str, cfg: config.Config):
    """Print a plain-English reason + fix for a failed attempt. Usage limits
    also mark the AI out; auth/network/missing/timeout never do."""
    failure = failures.classify(name, error)
    if failure is None:
        return None
    if failure.kind == "limit":
        auto_mark_out(name, error, cfg)
    else:
        print(f"[megazword] {failures.line(failure)}", file=sys.stderr)
    return failure


def auto_mark_out(name: str, error: str, cfg: config.Config) -> bool:
    """If `error` is a usage-limit message, mark that AI out until its reset
    so auto-pick skips it. Returns True if it marked one."""
    from .limits import detect
    hit = detect(error)
    if hit is None:
        return False
    try:
        config.set_out(config.HOME / "config.toml", name, hit.until)
    except (OSError, ValueError) as exc:
        print(f"[megazword] {name} hit its usage limit but I couldn't save that: {exc}",
              file=sys.stderr)
        return False
    cfg.out_until[name] = hit.until
    how = "" if hit.exact else " (reset time not given; guessing 1 hour)"
    print(f"[megazword] {name} hit its usage limit; marked out until "
          f"{hit.until.astimezone():%a %I:%M %p}{how}. Undo: megazword out {name} --clear",
          file=sys.stderr)
    return True


def last_run_path():
    return config.HOME / "last_run.json"


def save_last_run(sent, prompt, chain, backend, answer, project, level,
                  tab_id: str | None = None) -> None:
    import json
    from .filelock import write_atomic
    # Atomic: a parallel job finishing at the same time can't leave half a file.
    write_atomic(last_run_path(), json.dumps({"sent": sent, "prompt": prompt, "chain": chain,
                                              "backend": backend, "answer": answer,
                                              "project": project, "rating": level,
                                              "tab_id": tab_id}))
    from . import answers
    answers.add(prompt, answer, backend, project, level, tab_id=tab_id)


def retry_last(args, backends: dict[str, Backend], cfg: config.Config,
               on_answer: Callable[[str], None] | None = None) -> int:
    import json
    path = last_run_path()
    if not path.exists():
        print("[megazword] nothing to retry yet; run something first", file=sys.stderr)
        return 2
    last = json.loads(path.read_text(encoding="utf-8"))
    memory = Memory(config.HOME, last["project"], cfg.memory_lines)
    level = last.get("rating") or "medium"
    if level == "easy":
        level = "medium"  # a retry is real work, not a status pass
    apply_levels(backends, level, cfg.grok, cfg.levels)
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
