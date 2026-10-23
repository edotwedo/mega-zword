"""Who counts as Phil is config, not a hardcoded tuple.

Hardcoding it is why a new instance of his went unrecognised on 2026-10-23 and looked like a
"relay" to be verified. `[phil] authors` in config.toml is the one place to add one.
"""

from megazword import config, room_wait, wake


def _write_config(text: str) -> None:
    config.HOME.mkdir(parents=True, exist_ok=True)
    (config.HOME / "config.toml").write_text(text, encoding="utf-8")


def test_defaults_are_the_confirmed_lanes():
    assert config.phil_authors() == ("phil", "phone", "grok-web")


def test_a_new_instance_in_config_is_recognised_everywhere():
    _write_config('[phil]\nauthors = ["phil", "claude-web", "briar-22"]\n')
    expected = ("phil", "claude-web", "briar-22")
    assert config.phil_authors() == expected
    assert room_wait.phil_authors() == expected
    # A configured lane wakes with no "relay" phrase - it is simply him.
    assert wake.is_wake("", "claude-web") is True
    assert wake.is_wake("", "briar-22") is True
    assert wake.is_wake("", "some-bot") is False


def test_a_malformed_config_falls_back_and_never_raises():
    _write_config('[phil]\nauthors = "not-a-list"\n')
    assert config.phil_authors() == ("phil", "phone", "grok-web")
