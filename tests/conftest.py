import pytest

from megazword import config


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never let tests touch the real ~/.megazword."""
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    # Usage meters read CLI logins under the user's home; point them at an
    # empty folder so no test can reach a real login or the network.
    from megazword import usage_sources
    monkeypatch.setattr(usage_sources, "HOME", tmp_path / "userhome")
    # ...and never run a real Antigravity CLI for its quota.
    monkeypatch.setattr(usage_sources, "_agy_path", lambda: None)
    # ...or a real Codex app server for its live rate limits.
    monkeypatch.setattr(usage_sources, "_codex_cmd", lambda: None)
    for var in ("OPENROUTER_API_KEY", "GROQ_API_KEY", "CLOUDFLARE_API_TOKEN",
                "CLOUDFLARE_ACCOUNT_ID", "ZAI_API_KEY", "GOOGLE_AI_API_KEY",
                "NVIDIA_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
