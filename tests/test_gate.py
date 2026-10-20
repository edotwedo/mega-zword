"""The land-gate: the suite runs before anything reaches main (2026-10-19).

A crash in `megazword --help` was landed without the suite being run, leaving the
front door red. These cover the gate's decision, the git wiring, and the hook
file itself (a CRLF shebang would silently break it under sh).
"""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from megazword import doctor, gate

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-push"


def _proc(returncode):
    return SimpleNamespace(returncode=returncode)


def test_suite_command_runs_the_whole_suite():
    assert gate.suite_command("python") == ["python", "-m", "pytest", "-q"]


def test_gate_passes_when_the_suite_passes():
    seen = []

    def runner(cmd, cwd=None):
        seen.append(cmd)
        return _proc(0)

    assert gate.run_gate(python="py", cwd=Path("."), env={}, runner=runner) == 0
    assert seen == [["py", "-m", "pytest", "-q"]]


def test_gate_blocks_the_push_when_the_suite_fails(capsys):
    assert gate.run_gate(python="py", env={}, runner=lambda cmd, cwd=None: _proc(1)) == 1
    out = capsys.readouterr().out
    assert "SUITE FAILED" in out and "push blocked" in out
    # The known flake must not look like a real break, or a seat learns to ignore the gate.
    assert "winpty" in out


def test_gate_can_be_skipped_loudly(capsys):
    def never(cmd, cwd=None):
        raise AssertionError("the suite must not run when the gate is skipped")

    assert gate.run_gate(env={gate.SKIP_ENV: "1"}, runner=never) == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_status_line_says_not_installed(tmp_path):
    if not (Path(tmp_path) / ".git").exists():
        pytest.skip("needs a git repo")
    assert "NOT installed" in gate.status_line(tmp_path)


def test_install_points_the_repo_at_the_tracked_hooks(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert not gate.installed(tmp_path)
    assert gate.install(tmp_path) == 0
    assert gate.installed(tmp_path)
    assert gate.configured_hooks_path(tmp_path) == gate.HOOKS_DIR
    assert "installed" in gate.status_line(tmp_path)


def test_hook_file_survives_the_windows_checkout():
    raw = HOOK.read_bytes()
    assert raw.startswith(b"#!/bin/sh"), "hook must be a sh script"
    assert b"\r\n" not in raw, "a CRLF shebang breaks the hook under sh"
    assert b"-m pytest" in raw, "hook must run the suite"
    # It must not pre-check the megazword install: that is how it skipped itself on
    # its first run, because the editable install pointed at the main checkout.
    assert b'-c "import megazword' not in raw
    # git exports GIT_DIR and friends to hooks; the suite makes its own temp repos and
    # would otherwise run those git commands against this repo.
    assert b"unset GIT_DIR" in raw


def test_install_check_flags_a_snapshot_install(tmp_path):
    snapshot = tmp_path / "site-packages" / "megazword" / "doctor.py"
    check = doctor.install_check(snapshot)
    assert check.level == "WARN"
    assert "pip install -e ." in check.hint


def test_install_check_accepts_an_editable_tree(tmp_path):
    live = tmp_path / "repo" / "src" / "megazword" / "doctor.py"
    assert doctor.install_check(live).level == "OK"
