"""Per-turn CLI adapters; shared router backends never carry tab state."""

from dataclasses import dataclass, field, replace
import json
import os
import re
import tempfile
import uuid

from .backends import Backend, CLIBackend, CodexBackend


def session_missing(error: str) -> bool:
    text = error.lower()
    return bool(re.search(
        r"(?:session|conversation|thread).{0,100}(?:not found|unknown|expired|does not exist|no longer exists)"
        r"|(?:no|unknown|expired|could not find|cannot find|failed to find).{0,40}(?:session|conversation|thread)",
        text))


@dataclass
class SessionBackend(Backend):
    cli: CLIBackend = field(default_factory=lambda: CLIBackend(""))
    session_id: str = ""
    message: str = ""
    note: str = ""

    def available(self) -> bool:
        return self.cli.available()

    def _run(self, prompt: str) -> str:
        try:
            return self._turn(self.message if self.session_id else prompt, self.session_id)
        except Exception as exc:
            if not self.session_id or not session_missing(str(exc)):
                raise
            self.session_id = ""
            self.note = "Previous session unavailable; started a new session."
            # One fresh attempt, with the tab's recent history to restore context.
            return self._turn(prompt, "")

    def _turn(self, prompt: str, resume: str) -> str:
        cli = replace(self.cli, args=list(self.cli.args), timeout=self.timeout)
        if cli.exe == "claude":
            cli.args += ["--output-format", "json"]
            if resume:
                cli.args += ["--resume", resume]
            data = json.loads(cli._run(prompt))
            if not isinstance(data, dict):
                raise RuntimeError("claude returned invalid session output")
            if data.get("is_error"):
                raise RuntimeError(str(data.get("result") or data.get("errors") or "claude failed"))
            text = str(data.get("result") or "").strip()
            session = data.get("session_id")
        elif isinstance(cli, CodexBackend):
            # -s is an exec option, absent from resume's options: keep it before
            # the subcommand. Model/config options retain their usual meaning.
            if resume:
                cli.args += ["resume", resume]
            cli.args += ["--json"]
            fd, output = tempfile.mkstemp(prefix="megazword-session-", suffix=".txt")
            os.close(fd)
            try:
                cmd, stdin = cli._command(prompt)
                events = cli._exec([*cmd, "-o", output, "-"], stdin)
                with open(output, encoding="utf-8", errors="replace") as f:
                    text = f.read().strip()
                session = resume
                for line in events.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(event, dict) and event.get("type") == "thread.started":
                        session = event.get("thread_id")
            finally:
                os.remove(output)
        else:  # Grok accepts an explicit UUID for a new persisted conversation.
            session = resume or str(uuid.uuid4())
            cli.args += ["--resume", session] if resume else ["--session-id", session]
            text = cli._run(prompt).strip()
        if not text:
            raise RuntimeError(f"{cli.name} returned no answer")
        if not isinstance(session, str) or not session.strip():
            raise RuntimeError(f"{cli.name} returned no session id")
        self.session_id = session
        return text


def supports_sessions(backend: Backend) -> bool:
    return isinstance(backend, CLIBackend) and (
        backend.exe in ("claude", "grok") or isinstance(backend, CodexBackend))
