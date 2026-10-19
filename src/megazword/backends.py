"""Backends: each one runs a single prompt on one AI and returns the answer.

Paid CLIs are driven through their one-shot (non-interactive) modes. Where a
CLI accepts the prompt on stdin we use that, because Windows .cmd shims
(e.g. npm's codex.cmd) mangle special characters in command-line arguments.
"""

from __future__ import annotations

import json
from pathlib import Path
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
        from .keys import redact_known
        start = time.monotonic()
        try:
            prompt = redact_known(prompt)
            if self.trains_on_data:  # B15: the one light guard for AIs that train on prompts
                from .guard import scrub
                prompt = scrub(prompt)
            text = self._run(prompt)
            return Result(self.name, redact_known(text.strip()), True, time.monotonic() - start)
        except Exception as exc:  # report any failure as a result, never crash the router
            return Result(self.name, "", False, time.monotonic() - start, redact_known(str(exc)))

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


def no_window() -> dict:
    """Hide short console helpers launched from the windowless desktop app."""
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


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

    Registered as a zero-cost local option; availability is checked before routing.
    `available` only checks that the server answers, not that `model` is pulled.
    """

    model: str = ""
    url: str = ollama.DEFAULT_URL

    def available(self) -> bool:
        return ollama.reachable(self.url)

    def _run(self, prompt: str) -> str:
        return ollama.generate(prompt, self.model, self.url, timeout=self.timeout)


def drive_roots() -> list[str]:
    """Every drive on this PC (C:, D:, ...), or / elsewhere. Phil (2026-10-18):
    the AIs get all of his folders, not just the one a run starts in."""
    if os.name != "nt":
        return ["/"]
    return [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]


def add_dirs(roots: list[str] | None = None) -> list[str]:
    return [a for root in (drive_roots() if roots is None else roots) for a in ("--add-dir", root)]


def grok_backend(model: str = "grok-4.6", effort: str = "medium",
                 edit: bool = True) -> CLIBackend:
    """One-shot Grok with a model id and reasoning effort, full access (no sandbox)."""
    args = ["--prompt-file", "{prompt_file}", "--output-format", "plain", "--always-approve",
            "-m", model, "--effort", effort]
    return CLIBackend("grok", exe="grok", args=args)


def cmdc_backend(name: str = "cmdc", model: str = "") -> CLIBackend:
    """Command Code's own CLI on Phil's GOAT plan, full access. Phil, 2026-10-18: "we need
    megazword to behave exactly like this thing". Side by side, it finished a tested,
    pushed job while our agent loop on a Command Code model spent 60 steps reading."""
    args = ["-p", "--yolo", "--skip-onboarding", "--no-auto-update", "--max-turns", "60",
            *(["-m", model] if model else []), *add_dirs()]
    return CmdcBackend(name, exe="cmdc", args=args)  # prompt goes in on stdin


@dataclass
class CmdcBackend(CLIBackend):
    def available(self) -> bool:
        # Signed out (or a test's empty HOME) means every run would fail.
        return super().available() and (Path.home() / ".commandcode" / "auth.json").exists()


def grok_can_edit() -> bool:
    """Grok runs with full access everywhere now (Phil, 2026-10-18)."""
    return True


def apply_grok_effort(backends: dict[str, Backend], level: str,
                      grok: dict[str, tuple[str, str]]) -> None:
    """Swap in a Grok CLI tuned for this difficulty. Test fakes are left alone."""
    current = backends.get("grok")
    if not isinstance(current, CLIBackend) or current.exe != "grok":
        return
    model, effort = grok.get(level, grok.get("medium", ("grok-4.6", "medium")))
    backends["grok"] = grok_backend(model, effort)


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
# --restricted is no longer used: it removes code-running tools, keeps file
# tools in one folder and refuses full access (Phil, 2026-10-18: no read-only).
CLAUDE_LEAN = ["--strict-mcp-config", "--disable-slash-commands"]

# Codex: `-c` (documented config override) empties mcp_servers for the run, so
# MCP servers from ~/.codex/config.toml aren't started. Measured 2026-10-11,
# 2 runs each: 5.5s/6.0s -> 4.7s/4.8s, tokens identical (6,315), same answer.
# The sandbox (-s) and Phil's model settings are untouched. Not used:
# --ignore-user-config (drops his model choice), --ephemeral (no session log,
# so the Codex usage meter goes blind).
CODEX_LEAN = ["-c", "mcp_servers={}"]


# Checked live with agy 1.3.3 on Phil's PC (2026-10-11): -p takes the prompt as
# its value and ignores stdin; --disable-slash-commands switches plan mode off
# ("--mode plan has no effect"), so it is not used. Plan mode itself is gone
# (Phil, 2026-10-18): agy gets full access; --add-dir for every drive is added at run time.
AGY_ARGS = ["--dangerously-skip-permissions", "--output-format", "text", "-p", "{prompt}"]
OLD_GEMINI_ARGS = ["--approval-mode", "yolo", "--output-format", "text"]
AGY_DEFAULT_MODEL = "gemini-3.8-flash-high"  # from `agy models`, 2026-10-16
AGY_MAX_PROMPT = 30_000  # the prompt is a command-line argument; Windows caps those near 32k


@dataclass
class GeminiBackend(CLIBackend):
    """Gemini through Google's Antigravity CLI (`agy`) when installed, else the
    old Gemini CLI. Google retired the Gemini CLI for personal accounts on
    2026-06-18. Both run with full access (Phil, 2026-10-18).
    Picked at run time, not at construction, so building the table stays cheap."""

    exe: str = "gemini"
    args: list[str] = field(default_factory=lambda: list(OLD_GEMINI_ARGS))
    # B12: agy's --model/--effort for this task's level; empty = agy's own default.
    level_args: list[str] = field(default_factory=list)

    def _pick(self) -> None:
        if shutil.which("agy"):
            # agy's own default can be a Claude/GPT model with a separate quota that runs
            # out first; without a level choice, use Google's own model (2026-10-16).
            level = self.level_args or ["--model", AGY_DEFAULT_MODEL]
            self.exe, self.args = "agy", [*AGY_ARGS[:-2], *level, *add_dirs(), *AGY_ARGS[-2:]]
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
        # agy can exit 0 with status SUCCESS and an empty response (seen when a
        # tool was auto-denied) and still charge quota.
        if self.exe != "agy":
            return
        text = (out or "").strip()
        err_l = (err or "").lower()
        denied = ("auto-denied" in err_l or "jetski: no output" in err_l
                  or "headless mode cannot prompt" in err_l)
        if _agy_bare_success(text) or denied:
            raise RuntimeError(
                "agy produced no answer (a tool was auto-denied or it stopped early; "
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


def default_backends(edit: bool = True,
                     free_models: dict[str, str] | None = None,
                     lean: bool = True) -> dict[str, Backend]:
    """CLI and opt-in API backends. Phil (2026-10-18): no read-only mode. Every
    paid CLI has full access to every drive and can run commands, whatever
    `edit` says (kept so old callers still work)."""
    claude_args = ["-p", "--dangerously-skip-permissions", *add_dirs()]
    if lean:
        claude_args += CLAUDE_LEAN
    backends: list[Backend] = [
        CLIBackend("claude", exe="claude", args=claude_args),
        CodexBackend("codex", exe="codex",
                     args=["exec", "--skip-git-repo-check",
                           "--dangerously-bypass-approvals-and-sandbox",
                           *(CODEX_LEAN if lean else [])]),
        grok_backend(),
        cmdc_backend(),  # the CLI's default model (DeepSeek V4 Flash) works fine in its own harness
        cmdc_backend("cmdc-glm", "z-ai/glm-5.3-flash"),
        cmdc_backend("cmdc-qwen", "Qwen/Qwen3.8-27B"),
        GeminiBackend("gemini"),  # piped stdin selects the old Gemini CLI's headless mode
    ]
    from .config import Config, load
    from .free_apis import cheap_backends, free_backends
    if free_models is None:
        try:
            free_models = load().free
        except (ValueError, TypeError, OSError):
            free_models = Config().free
    backends.extend(free_backends(free_models))
    backends.extend(cheap_backends(free_models))
    backends.append(OllamaBackend("ollama", model=free_models.get("ollama", "qwen2.5-coder:7b")))
    return {b.name: b for b in backends}
