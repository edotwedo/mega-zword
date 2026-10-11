"""Backends: each one runs a single prompt on one AI and returns the answer.

Paid CLIs are driven through their one-shot (non-interactive) modes. Where a
CLI accepts the prompt on stdin we use that, because Windows .cmd shims
(e.g. npm's codex.cmd) mangle special characters in command-line arguments.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 600  # seconds


@dataclass
class Result:
    backend: str
    text: str
    ok: bool
    seconds: float
    error: str = ""


@dataclass
class Backend:
    """Base class. Subclasses implement `_run`."""

    name: str
    timeout: int = DEFAULT_TIMEOUT

    def available(self) -> bool:
        return True

    def run(self, prompt: str) -> Result:
        start = time.monotonic()
        try:
            text = self._run(prompt)
            return Result(self.name, text.strip(), True, time.monotonic() - start)
        except Exception as exc:  # report any failure as a result, never crash the router
            return Result(self.name, "", False, time.monotonic() - start, str(exc))

    def _run(self, prompt: str) -> str:
        raise NotImplementedError


@dataclass
class CLIBackend(Backend):
    """Runs an installed CLI. `args` may contain "{prompt}" to pass it as an
    argument; otherwise the prompt goes to stdin."""

    exe: str = ""
    args: list[str] = field(default_factory=list)

    def available(self) -> bool:
        return shutil.which(self.exe) is not None

    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        path = shutil.which(self.exe)
        if path is None:
            raise RuntimeError(f"'{self.exe}' is not installed or not on PATH")
        if "{prompt}" in self.args:
            return [path, *(prompt if a == "{prompt}" else a for a in self.args)], None
        return [path, *self.args], prompt

    def _exec(self, cmd: list[str], stdin: str | None) -> str:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()[-500:]
            raise RuntimeError(f"{self.exe} exited with code {proc.returncode}: {detail}")
        return proc.stdout

    def _run(self, prompt: str) -> str:
        cmd, stdin = self._command(prompt)
        return self._exec(cmd, stdin)


@dataclass
class CodexBackend(CLIBackend):
    """Codex prints progress to stdout, so read the final answer from the
    file written by --output-last-message."""

    def _run(self, prompt: str) -> str:
        fd, out_path = tempfile.mkstemp(prefix="megazword-codex-", suffix=".txt")
        os.close(fd)
        try:
            cmd, stdin = self._command(prompt)
            self._exec([*cmd, "-o", out_path, "-"], stdin)
            with open(out_path, encoding="utf-8", errors="replace") as f:
                return f.read()
        finally:
            os.remove(out_path)


def default_backends() -> dict[str, Backend]:
    backends: list[Backend] = [
        CLIBackend("claude", exe="claude", args=["-p"]),
        CodexBackend("codex", exe="codex",
                     args=["exec", "--skip-git-repo-check", "-s", "read-only"]),
        CLIBackend("grok", exe="grok",
                   args=["-p", "{prompt}", "--output-format", "plain"]),
    ]
    return {b.name: b for b in backends}
