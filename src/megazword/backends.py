"""Backends: each one runs a single prompt on one AI and returns the answer.

Paid CLIs are driven through their one-shot (non-interactive) modes. Where a
CLI accepts the prompt on stdin we use that, because Windows .cmd shims
(e.g. npm's codex.cmd) mangle special characters in command-line arguments.
"""

from __future__ import annotations

import os
import shutil
import sys
import subprocess
import tempfile
import time
from dataclasses import dataclass, field

from . import ollama

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
    """Runs an installed CLI. `args` may contain "{prompt_file}" (the prompt is
    written to a temp file and its path passed) or "{prompt}" (passed as an
    argument; Windows caps a command line at ~32k chars, so avoid it);
    otherwise the prompt goes to stdin."""

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
        # Own process group so a timeout can kill the whole tree: on Windows
        # the CLIs are .cmd shims whose node child would otherwise keep the
        # pipes open and hang us after the shim itself is killed.
        group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                 if os.name == "nt" else {"start_new_session": True})
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="replace", **group)
        try:
            out, err = proc.communicate(stdin, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise TimeoutError(f"{self.exe} gave no answer within {self.timeout}s "
                               "(change [timeouts] in config.toml)") from None
        if proc.returncode != 0:
            detail = (err or out).strip()[-500:]
            raise RuntimeError(f"{self.exe} exited with code {proc.returncode}: {detail}")
        return out

    def _run(self, prompt: str) -> str:
        if "{prompt_file}" not in self.args:
            cmd, stdin = self._command(prompt)
            return self._exec(cmd, stdin)
        fd, path = tempfile.mkstemp(prefix="megazword-prompt-", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
            exe = shutil.which(self.exe)
            if exe is None:
                raise RuntimeError(f"'{self.exe}' is not installed or not on PATH")
            return self._exec([exe, *(path if a == "{prompt_file}" else a
                                      for a in self.args)], None)
        finally:
            os.remove(path)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process and everything it started, then reap it."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        proc.kill()
    try:
        proc.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError):
        pass


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


@dataclass
class OllamaBackend(Backend):
    """A model on a local Ollama server.

    Not added by default_backends(); the router registers the ones it wants.
    `available` only checks that the server answers, not that `model` is pulled.
    """

    model: str = ""
    url: str = ollama.DEFAULT_URL

    def available(self) -> bool:
        return ollama.reachable(self.url)

    def _run(self, prompt: str) -> str:
        return ollama.generate(prompt, self.model, self.url, timeout=self.timeout)


def grok_backend(model: str = "grok-4.6", effort: str = "medium",
                 edit: bool = False) -> CLIBackend:
    """One-shot Grok with a model id and reasoning effort."""
    args = ["--prompt-file", "{prompt_file}", "--output-format", "plain", "-m", model, "--effort", effort]
    if edit:
        # Grok's path-scoped allow rules don't hold (tested 2026-10-11: with
        # Write(<folder>/**) allowed it still wrote to ../ and absolute paths),
        # so only its OS sandbox can keep edits in the folder.
        args += ["--sandbox", "workspace", "--allow", "Write", "--allow", "Edit"]
    return CLIBackend("grok", exe="grok", args=args)


def grok_can_edit() -> bool:
    """Grok's sandbox exists only on Linux (Landlock) and macOS (Seatbelt)."""
    return sys.platform.startswith("linux") or sys.platform == "darwin"


def apply_grok_effort(backends: dict[str, Backend], level: str,
                      grok: dict[str, tuple[str, str]]) -> None:
    """Swap in a Grok CLI tuned for this difficulty. Test fakes are left alone."""
    current = backends.get("grok")
    if not isinstance(current, CLIBackend) or current.exe != "grok":
        return
    model, effort = grok.get(level, grok.get("medium", ("grok-4.6", "medium")))
    backends["grok"] = grok_backend(model, effort, edit="--sandbox" in current.args)


def grok_label(backend: Backend) -> str:
    """'grok (grok-4.6 medium)' when those flags are present."""
    if not isinstance(backend, CLIBackend) or "--effort" not in backend.args:
        return backend.name
    args = backend.args
    model = args[args.index("-m") + 1] if "-m" in args else ""
    effort = args[args.index("--effort") + 1]
    extra = " ".join(p for p in (model, effort) if p)
    return f"{backend.name} ({extra})" if extra else backend.name


def default_backends(edit: bool = False,
                     free_models: dict[str, str] | None = None) -> dict[str, Backend]:
    """CLI and opt-in API backends. With edit=True the AIs may change files in
    the current folder: Claude auto-accepts file edits only (other tools
    still need approval, which a one-shot can't give, so they're refused),
    Codex gets its workspace-write sandbox, and Grok joins only where its OS
    sandbox works (not on Windows)."""
    claude_args = ["-p", "--permission-mode", "acceptEdits"] if edit else ["-p"]
    codex_sandbox = "workspace-write" if edit else "read-only"
    backends: list[Backend] = [
        CLIBackend("claude", exe="claude", args=claude_args),
        CodexBackend("codex", exe="codex",
                     args=["exec", "--skip-git-repo-check", "-s", codex_sandbox]),
    ]
    if not edit or grok_can_edit():
        backends.append(grok_backend(edit=edit))
    if not edit:
        from .config import load
        from .free_apis import free_backends
        backends.extend(free_backends(free_models if free_models is not None else load().free))
    return {b.name: b for b in backends}
