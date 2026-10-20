"""Land-gate: nothing reaches main until the suite passes.

On the night of 2026-10-19 a crash reached main in `megazword --help` (a bare
``%`` in a help string; argparse read it as a conversion). The tests caught it,
which means the suite was simply never run before the push. A red front door is
the first thing a stranger sees, so that is the one failure that must not be
possible to land.

Install the hook once per repo (it covers every worktree, because worktrees
share the repo config)::

    megazword gate --install     # git config core.hooksPath .githooks

Two escapes, both deliberate and both visible in the log: ``MZ_SKIP_GATE=1`` and
``git push --no-verify``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = ".githooks"
SKIP_ENV = "MZ_SKIP_GATE"
FLAKE_NOTE = ("a single failure that passes on its own is the known winpty "
              "contention flake (tests/test_terminal_input.py); re-run just that "
              "test before you decide the tree is broken")


def _git(args: list[str], cwd: Path | None = None, runner=subprocess.run):
    return runner(["git", *args], cwd=str(cwd) if cwd else None,
                  capture_output=True, text=True)


def repo_root(cwd: Path | None = None) -> Path:
    """The working tree to test in. Inside a worktree this is that worktree."""
    proc = _git(["rev-parse", "--show-toplevel"], cwd=cwd)
    top = (proc.stdout or "").strip()
    return Path(top) if top else Path(cwd or Path.cwd())


def configured_hooks_path(root: Path | None = None) -> str:
    proc = _git(["config", "--get", "core.hooksPath"], cwd=root)
    return (proc.stdout or "").strip()


def _norm(value: str) -> str:
    """Normalise a hooks path: either separator, optional leading './' and trailing '/'."""
    text = (value or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def installed(root: Path | None = None) -> bool:
    return _norm(configured_hooks_path(root)) == _norm(HOOKS_DIR)


def install(root: Path | None = None) -> int:
    """Point this repo at the tracked hooks directory (applies to every worktree)."""
    proc = _git(["config", "core.hooksPath", HOOKS_DIR], cwd=root)
    return proc.returncode


def suite_command(python: str | None = None) -> list[str]:
    return [python or sys.executable, "-m", "pytest", "-q"]


def run_gate(python: str | None = None, cwd: Path | None = None,
             env: dict | None = None, runner=subprocess.run) -> int:
    """Run the suite. Non-zero blocks the push."""
    env = os.environ if env is None else env
    if env.get(SKIP_ENV) == "1":
        print(f"land-gate: SKIPPED ({SKIP_ENV}=1) - nothing was verified")
        return 0
    print("land-gate: running the suite before this push (this takes a few minutes)")
    proc = runner(suite_command(python), cwd=str(cwd) if cwd else None)
    if proc.returncode == 0:
        print("land-gate: suite passed")
        return 0
    print(f"land-gate: SUITE FAILED ({proc.returncode}) - push blocked")
    print(f"land-gate: {FLAKE_NOTE}")
    print("land-gate: fix it, or 'git push --no-verify' if you are certain it is not you")
    return proc.returncode


def status_line(root: Path | None = None) -> str:
    if installed(root):
        return f"land-gate: installed (core.hooksPath={HOOKS_DIR})"
    current = configured_hooks_path(root) or "(unset)"
    return (f"land-gate: NOT installed (core.hooksPath={current}); "
            f"run 'megazword gate --install'")


def command(args) -> int:
    if args.install:
        root = repo_root(args.path)
        rc = install(root)
        print(status_line(root))
        return rc
    if args.status:
        print(status_line(args.path))
        return 0
    return run_gate(cwd=args.path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="run the gate (default)")
    parser.add_argument("--install", action="store_true", help="set core.hooksPath to .githooks")
    parser.add_argument("--status", action="store_true", help="say whether the gate is installed")
    parser.add_argument("--path", type=Path, help="repo or worktree to act on")
    args = parser.parse_args(argv)
    return command(args)


def add_parser(sub) -> None:
    gate = sub.add_parser("gate", help="run the suite before anything lands on main")
    gate.add_argument("--install", action="store_true", help="set core.hooksPath to .githooks")
    gate.add_argument("--status", action="store_true", help="say whether the gate is installed")
    gate.add_argument("--path", type=Path, help="repo or worktree to act on")


if __name__ == "__main__":
    raise SystemExit(main())
