import sys
import tempfile
from pathlib import Path

import pytest

from megazword import config


def pytest_configure(config):
    """Give every test run its own temp folder (2026-10-17). Pytest's shared
    pytest-of-USER folder keeps only the newest few runs and deletes the rest, so
    a second run on this PC (another seat, the heartbeat, Night Shift) deleted
    folders a running suite still used: 39 errors in a heartbeat baseline."""
    if not config.option.basetemp:
        config.option.basetemp = tempfile.mkdtemp(prefix="mz-pytest-")
        config._mz_own_basetemp = config.option.basetemp


def pytest_unconfigure(config):
    own = getattr(config, "_mz_own_basetemp", None)
    if own:
        import shutil
        shutil.rmtree(own, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never let tests touch the real ~/.megazword."""
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    # Never read or write the real Windows credential store during tests.
    from megazword import credential_store
    monkeypatch.setattr(credential_store, "_api", lambda: None)
    # Usage meters read CLI logins under the user's home; point them at an
    # empty folder so no test can reach a real login or the network.
    from megazword import usage_sources
    monkeypatch.setattr(usage_sources, "HOME", tmp_path / "userhome")
    # ...and never run a real Antigravity CLI for its quota.
    monkeypatch.setattr(usage_sources, "_agy_path", lambda: None)
    # ...or a real Codex app server for its live rate limits.
    monkeypatch.setattr(usage_sources, "_codex_cmd", lambda: None)
    # ...or run a real AI CLI. Fakes live in this repo or a temp folder; anything else
    # (the real claude/codex/grok/agy on Phil's PC) is refused. A tab test once sent a
    # real prompt to Claude (2026-10-12) because claude is installed here.
    from megazword import backends as _backends
    real_exec = _backends.CLIBackend._exec
    allowed = [Path(__file__).resolve().parents[1], Path(tempfile.gettempdir()).resolve(),
               Path(sys.executable).resolve().parent, tmp_path.resolve()]

    def guarded_exec(self, cmd, stdin):
        exe = Path(cmd[0]).resolve()
        if not any(exe.is_relative_to(root) for root in allowed):
            raise RuntimeError(f"test tried to run a real CLI: {exe}")
        return real_exec(self, cmd, stdin)

    monkeypatch.setattr(_backends.CLIBackend, "_exec", guarded_exec)
    # ...or open the app window from a plain `megazword` (B13).
    monkeypatch.setenv("MEGAZWORD_NO_APP", "1")
    # ...or a real pywebview desktop window (B6b); tests that need it pass a fake.
    from megazword import desktop
    monkeypatch.setattr(desktop, "available", lambda: False)
    # ...or the real GitHub CLI, which would post room summaries to Q.
    from megazword import room
    monkeypatch.setattr(room, "_gh_path", lambda: None)
    # ...or Night Shift's: no Q posts and no real scheduled task from a test.
    from megazword import night
    monkeypatch.setattr(night, "_gh_path", lambda: None)

    def no_schtasks(args):
        raise RuntimeError(f"test tried to run real schtasks: {args}")

    monkeypatch.setattr(night, "_schtasks", no_schtasks)
    # ...or inherit a bot's seat, which would block posting as phil (B7).
    monkeypatch.delenv("MEGAZWORD_SEAT", raising=False)
    monkeypatch.delenv("MEGAZWORD_RUN_CONTROL", raising=False)
    for var in ("OPENROUTER_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "CLOUDFLARE_API_TOKEN",
                "CLOUDFLARE_ACCOUNT_ID", "ZAI_API_KEY", "GOOGLE_AI_API_KEY",
                "NVIDIA_API_KEY", "MISTRAL_API_KEY", "TENCENT_TOKENHUB_API_KEY"):
        monkeypatch.delenv(var, raising=False)
