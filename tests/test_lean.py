"""[oneshot] lean: documented trimming flags for routed one-shots."""

from megazword import config
from megazword.backends import CLAUDE_LEAN, default_backends


def test_lean_by_default_and_safety_flags_kept():
    ro, rw = default_backends(), default_backends(edit=True)
    for flag in CLAUDE_LEAN:
        assert flag in ro["claude"].args and flag in rw["claude"].args
    assert rw["claude"].args[:2] == ["-p", "--dangerously-skip-permissions"]
    assert "--bare" not in ro["claude"].args  # would skip the OAuth login
    assert "--restricted" not in ro["claude"].args  # it refuses full access


def test_lean_can_be_turned_off(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[oneshot]\nlean = false\n")
    cfg = config.load(p)
    assert cfg.lean is False
    plain = default_backends(lean=cfg.lean)
    assert not any(f in plain["claude"].args for f in CLAUDE_LEAN)


def test_bad_value_keeps_default(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[oneshot]\nlean = "yes"\n')
    assert config.load(p).lean is True


def test_codex_lean_skips_mcp_with_full_access():
    from megazword.backends import CODEX_LEAN
    ro, rw = default_backends(), default_backends(edit=True)
    for b in (ro["codex"], rw["codex"]):
        args = b.args
        assert "--dangerously-bypass-approvals-and-sandbox" in args and "-s" not in args
        assert args[-2:] == CODEX_LEAN
        assert "--ignore-user-config" not in args and "--ephemeral" not in args
    assert CODEX_LEAN[0] not in default_backends(lean=False)["codex"].args
