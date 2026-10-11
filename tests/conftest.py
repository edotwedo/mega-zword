import pytest

from megazword import config


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never let tests touch the real ~/.megazword."""
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
