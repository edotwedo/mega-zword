"""The `megazword` command."""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from . import __version__, config, log
from .backends import Backend, default_backends
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

    sub.add_parser("backends", help="list AIs and whether they're installed")
    return parser


def pick(rating: Rating, route: dict[str, list[str]],
         backends: dict[str, Backend]) -> Backend | None:
    """First installed AI in the route list for this difficulty."""
    for name in route.get(rating.level, []):
        b = backends.get(name)
        if b is not None and b.available():
            return b
    return None


def main(argv: list[str] | None = None,
         backends: dict[str, Backend] | None = None,
         cfg: config.Config | None = None,
         rater: Callable[[str], Rating] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backends = backends if backends is not None else default_backends()
    cfg = cfg if cfg is not None else config.load()
    rater = rater if rater is not None else (lambda p: rate(p, cfg.rater_model))

    if args.command == "backends":
        for name, b in backends.items():
            print(f"{name:10} {'installed' if b.available() else 'not found'}")
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
        print(f"[megazword] using {backend.name} (you chose it)", file=sys.stderr)
    else:
        rating = rater(prompt)
        backend = pick(rating, cfg.route, backends)
        if backend is None:
            print(f"[megazword] no installed AI for a {rating.level} task; "
                  f"check the route in {config.HOME / 'config.toml'}", file=sys.stderr)
            return 1
        print(f"[megazword] rated {rating.level} ({rating.reason}) -> using {backend.name}",
              file=sys.stderr)

    result = backend.run(prompt)
    log.append(cfg.log_path, backend=backend.name, forced=bool(args.model),
               rating=rating.level if rating else None,
               rater=rating.source if rating else None,
               seconds=round(result.seconds, 2), ok=result.ok,
               prompt_chars=len(prompt), answer_chars=len(result.text))
    if not result.ok:
        print(f"[megazword] {backend.name} failed after {result.seconds:.1f}s: {result.error}",
              file=sys.stderr)
        return 1
    print(result.text)
    print(f"[megazword] {backend.name} answered in {result.seconds:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
