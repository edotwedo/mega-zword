"""The `megazword` command."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .backends import Backend, default_backends


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="megazword",
        description="Run your AI CLIs from one place.",
    )
    parser.add_argument("--version", action="version", version=f"megazword {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a prompt on an AI")
    run.add_argument("prompt", nargs="?", help="the prompt (reads stdin if left out)")
    run.add_argument("-m", "--model", required=True, help="which AI to use, e.g. claude")

    sub.add_parser("backends", help="list AIs and whether they're installed")
    return parser


def main(argv: list[str] | None = None, backends: dict[str, Backend] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backends = backends if backends is not None else default_backends()

    if args.command == "backends":
        for name, b in backends.items():
            print(f"{name:10} {'installed' if b.available() else 'not found'}")
        return 0

    # command == "run"
    backend = backends.get(args.model)
    if backend is None:
        print(f"Unknown AI '{args.model}'. Choose from: {', '.join(backends)}", file=sys.stderr)
        return 2
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        print("No prompt given.", file=sys.stderr)
        return 2

    print(f"[megazword] using {backend.name}", file=sys.stderr)
    result = backend.run(prompt)
    if not result.ok:
        print(f"[megazword] {backend.name} failed after {result.seconds:.1f}s: {result.error}",
              file=sys.stderr)
        return 1
    print(result.text)
    print(f"[megazword] {backend.name} answered in {result.seconds:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
