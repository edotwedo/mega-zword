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
