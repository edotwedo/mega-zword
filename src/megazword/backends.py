"""Backends: each one runs a single prompt on one AI and returns the answer.

Paid CLIs are driven through their one-shot (non-interactive) modes. Where a
CLI accepts the prompt on stdin we use that, because Windows .cmd shims
(e.g. npm's codex.cmd) mangle special characters in command-line arguments.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, replace

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
    trains_on_data: bool = False

    def available(self) -> bool:
        return True

    def run(self, prompt: str) -> Result:
        start = time.monotonic()
        try:
            if self.trains_on_data:  # B15: the one light guard for AIs that train on prompts
                from .guard import scrub
                prompt = scrub(prompt)
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
    cwd: str = ""  # folder the CLI works in; "" = this process's folder (night jobs set it)

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
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="replace", cwd=self.cwd or None,
                                env=self._env(), **process_group())
        try:
            out, err = proc.communicate(stdin, timeout=self.timeout)
        except KeyboardInterrupt:
            # Ctrl+C: the CLI is in its own process group so it didn't get the
            # signal; stop it (and its children) before passing Ctrl+C on.
            _kill_tree(proc)
            raise
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise TimeoutError(f"{self.exe} gave no answer within {self.timeout}s "
                               "(change [timeouts] in config.toml)") from None
        if proc.returncode != 0:
            detail = (err or out).strip()[-500:]
            raise RuntimeError(f"{self.exe} exited with code {proc.returncode}: {detail}")
        self._check_output(out, err)
        return out

    def _env(self) -> dict[str, str] | None:
        """Child environment; None keeps the normal inherited environment."""
        return None

    def _check_output(self, out: str, err: str) -> None:
        """Hook for backends that must inspect stderr even on exit 0."""
        return

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


def run_quick(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    """subprocess.run for short commands (e.g. `--version`) that can't hang:
    on timeout the whole tree is killed, so a .cmd shim's node child can't
    keep the pipes open. Raises subprocess.TimeoutExpired like run()."""
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", **process_group())
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def process_group() -> dict:
    """Popen kwargs that start a child in its own process group, so
    _kill_tree() can later take down everything it started. On Windows the child also
    gets a hidden console: started from a windowless app (the Hive widget, the desktop
    window) each AI CLI, and the MCP servers it starts, flashed a console window per turn."""
    return ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
            if os.name == "nt" else {"start_new_session": True})


def _kill_tree(proc: subprocess.Popen, reap: bool = True) -> None:
    """Kill a process and everything it started. With reap=False the caller
    is already reading the pipes and waiting on the process (dashboard jobs)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        proc.kill()
    if not reap:
        return
    try:
        proc.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError):
        pass


@dataclass
class CodexBackend(CLIBackend):
    """Codex prints progress to stdout, so read the final answer from the
    file written by --output-last-message."""

    def _env(self) -> dict[str, str] | None:
        if sys.platform != "win32":
            return None
        # Codex's Windows sandbox cannot launch Store PowerShell from WindowsApps.
        # Let it find System32 Windows PowerShell instead, only in this child.
        env = os.environ.copy()
        for key in env:
            if key.casefold() == "path":
                env[key] = ";".join(
                    entry for entry in env[key].split(";")
                    if "windowsapps" not in entry.casefold()
                    and "powershell\\7" not in entry.replace("/", "\\").casefold()
                )
        return env

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


LEVEL_AIS = ("claude", "codex", "gemini")


def apply_levels(backends: dict[str, Backend], level: str,
                 grok: dict[str, tuple[str, str]],
                 levels: dict[str, dict[str, tuple[str, str]]] | None = None) -> None:
    """B12: Grok plus Claude, Codex and Gemini get the model and effort set for this
    difficulty in config.toml ([claude.hard] etc.). Unset = that CLI's own default.
    Only the real CLIs are swapped (a copy each); test fakes are left alone."""
    apply_grok_effort(backends, level, grok)
    for name, table in (levels or {}).items():
        model, effort = table.get(level, ("", ""))
        current = backends.get(name)
        if not (model or effort) or not isinstance(current, CLIBackend):
            continue
        if isinstance(current, GeminiBackend):
            extra = [*(["--model", model] if model else []), *(["--effort", effort] if effort else [])]
            backends[name] = replace(current, args=list(current.args), level_args=extra)
        elif current.exe == "claude":
            extra = [*(["--model", model] if model else []), *(["--effort", effort] if effort else [])]
            backends[name] = replace(current, args=[*current.args, *extra])
        elif current.exe == "codex":
            extra = [*(["-m", model] if model else []),
                     *(["-c", f"model_reasoning_effort={effort}"] if effort else [])]
            backends[name] = replace(current, args=[*current.args, *extra])


def grok_label(backend: Backend) -> str:
    """'grok (grok-4.6 medium)', 'codex (gpt-5.5 high)': the model and effort when set."""
    if not isinstance(backend, CLIBackend):
        return backend.name
    args = [*backend.args, *getattr(backend, "level_args", [])]
    model = effort = ""
    for flag in ("-m", "--model"):
        if flag in args[:-1]:
            model = args[args.index(flag) + 1]
    if "--effort" in args[:-1]:
        effort = args[args.index("--effort") + 1]
    for a in args:
        if a.startswith("model_reasoning_effort="):
            effort = a.split("=", 1)[1]
    extra = " ".join(p for p in (model, effort) if p)
    return f"{backend.name} ({extra})" if extra else backend.name


# Documented `claude` flags that make a routed one-shot leaner without
# touching login or safety (permission mode stays as set). Measured
# 2026-10-11, "Reply with exactly: pong": ~6.7s -> ~3.5s, ~33k -> ~10.7k
# context tokens, same answer. Not used: --bare (it skips OAuth, so a
# subscription login stops working).
#   --strict-mcp-config      no MCP servers (none given via --mcp-config)
#   --disable-slash-commands no skills
#   --restricted             no code-running tools; ignores user/project
#                            settings files; file tools stay in the folder
CLAUDE_LEAN = ["--strict-mcp-config", "--disable-slash-commands", "--restricted"]

# Codex: `-c` (documented config override) empties mcp_servers for the run, so
# MCP servers from ~/.codex/config.toml aren't started. Measured 2026-10-11,
# 2 runs each: 5.5s/6.0s -> 4.7s/4.8s, tokens identical (6,315), same answer.
# The sandbox (-s) and Phil's model settings are untouched. Not used:
# --ignore-user-config (drops his model choice), --ephemeral (no session log,
# so the Codex usage meter goes blind).
CODEX_LEAN = ["-c", "mcp_servers={}"]


# Checked live with agy 1.3.3 on Phil's PC (2026-10-11): -p takes the prompt as
# its value and ignores stdin; --disable-slash-commands switches plan mode off
# ("--mode plan has no effect"), so it is not used.
AGY_ARGS = ["--mode", "plan", "--output-format", "text", "-p", "{prompt}"]
OLD_GEMINI_ARGS = ["--approval-mode", "plan", "--output-format", "text"]
AGY_MAX_PROMPT = 30_000  # the prompt is a command-line argument; Windows caps those near 32k


@dataclass
class GeminiBackend(CLIBackend):
    """Gemini through Google's Antigravity CLI (`agy`) when installed, else the
    old Gemini CLI. Google retired the Gemini CLI for personal accounts on
    2026-06-18. --mode plan is agy's read-only mode.
    Picked at run time, not at construction, so building the table stays cheap."""

    exe: str = "gemini"
    args: list[str] = field(default_factory=lambda: list(OLD_GEMINI_ARGS))
    # B12: agy's --model/--effort for this task's level; empty = agy's own default.
    level_args: list[str] = field(default_factory=list)

    def _pick(self) -> None:
        if shutil.which("agy"):
            self.exe, self.args = "agy", [*AGY_ARGS[:-2], *self.level_args, *AGY_ARGS[-2:]]
        else:
            self.exe, self.args = "gemini", list(OLD_GEMINI_ARGS)

    def available(self) -> bool:
        self._pick()
        return super().available()

    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        self._pick()
        if self.exe == "agy" and len(prompt) > AGY_MAX_PROMPT:
            raise RuntimeError(f"prompt is {len(prompt):,} characters; agy takes it on the "
                               f"command line, which fits about {AGY_MAX_PROMPT:,}. "
                               "Shorten it or use another AI.")
        return super()._command(prompt)

    def _check_output(self, out: str, err: str) -> None:
        # Headless `--mode plan` auto-denies file/command tools, then exits 0
        # with status SUCCESS and an empty response, and still charges quota.
        if self.exe != "agy":
            return
        text = (out or "").strip()
        err_l = (err or "").lower()
        denied = ("auto-denied" in err_l or "jetski: no output" in err_l
                  or "headless mode cannot prompt" in err_l)
        if _agy_bare_success(text) or denied:
            raise RuntimeError(
                "agy produced no answer (headless plan mode auto-denied a tool; "
                "quota was still charged)")


def _agy_bare_success(text: str) -> bool:
    """True when stdout is empty, the word SUCCESS, or JSON with empty response."""
    raw = (text or "").strip()
    if not raw:
        return True
    if raw.strip("\"'").upper() == "SUCCESS":
        return True
    if raw[:1] == "{":
        try:
            payload = json.loads(raw)
        except ValueError:
            return False
        if isinstance(payload, dict) and str(payload.get("status") or "").upper() == "SUCCESS":
            response = payload.get("response")
            if response in (None, "", []):
                return True
            if isinstance(response, str) and not response.strip():
                return True
    return False


def default_backends(edit: bool = False,
                     free_models: dict[str, str] | None = None,
                     lean: bool = True) -> dict[str, Backend]:
    """CLI and opt-in API backends. With edit=True the AIs may change files in
    the current folder: Claude auto-accepts file edits only (other tools
    still need approval, which a one-shot can't give, so they're refused),
    Codex gets its workspace-write sandbox, and Grok joins only where its OS
    sandbox works (not on Windows)."""
    claude_args = ["-p", "--permission-mode", "acceptEdits"] if edit else ["-p"]
    if lean:
        claude_args += CLAUDE_LEAN
    codex_sandbox = "workspace-write" if edit else "read-only"
    backends: list[Backend] = [
        CLIBackend("claude", exe="claude", args=claude_args),
        CodexBackend("codex", exe="codex",
                     args=["exec", "--skip-git-repo-check", "-s", codex_sandbox,
                           *(CODEX_LEAN if lean else [])]),
    ]
    if not edit or grok_can_edit():
        backends.append(grok_backend(edit=edit))
    if not edit:
        # Piped stdin selects Gemini's headless mode (no -p value needed).
        # Plan mode is its documented read-only approval mode; unsupported
        # versions must fail, never fall back to permissive approvals.
        # Keep it out of edit mode: folder-contained sandbox writes have not
        # been verified, especially on Windows. auto_edit is not containment.
        backends.append(GeminiBackend("gemini"))
    from .config import Config, load
    from .free_apis import free_backends
    if free_models is None:
        try:
            free_models = load().free
        except (ValueError, TypeError, OSError):
            free_models = Config().free
    backends.extend(free_backends(free_models))
    if edit:
        backends.append(OllamaBackend("ollama", model=free_models.get("ollama", "qwen2.5-coder:7b")))
    return {b.name: b for b in backends}
