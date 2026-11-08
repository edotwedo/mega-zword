"""The land-gate: the suite runs before anything reaches main (2026-10-19).

A crash in `megazword --help` was landed without the suite being run, leaving the
front door red. These cover the gate's decision, the git wiring, and the hook
file itself (a CRLF shebang would silently break it under sh).
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from megazword import doctor, gate

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-push"
PRE_COMMIT = ROOT / ".githooks" / "pre-commit"


def _find_sh():
    """The hook is a sh script. Git Bash's sh is usually not on PATH in PowerShell,
    and a test that always skips is not a test - so look where Git installs it."""
    found = shutil.which("sh")
    if found:
        return found
    for candidate in (r"C:\Program Files\Git\bin\sh.exe",
                      r"C:\Program Files (x86)\Git\bin\sh.exe"):
        if Path(candidate).is_file():
            return candidate
    return None


SH = _find_sh()


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


@pytest.mark.skipif(SH is None, reason="needs sh (Git Bash) on PATH")
def test_hook_skips_a_delete_only_push():
    """Deleting a branch cannot break the suite. Running it anyway turned a branch
    cleanup into a four-minute push (2026-10-19), which is how a gate earns a
    reputation for being in the way and gets bypassed."""
    proc = subprocess.run([SH, str(HOOK)], input="(delete) 0 refs/heads/old abc123\n",
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0
    assert "delete-only" in proc.stdout
    assert "running the suite" not in proc.stdout


@pytest.mark.skipif(SH is None, reason="needs sh (Git Bash) on PATH")
def test_hook_skips_docs_only_push(tmp_path):
    """The hook is run against a docs-only commit made here, in a throwaway worktree.
    The first version pinned commit 0a7e7b5, which a CI checkout (depth 1) does not have,
    and ran in the real checkout, where the hook rewrote docs/MEMORY-INDEX.md and hid a
    stale committed index from test_memory_index (2026-11-08)."""
    def git(*args, cwd=ROOT):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                              text=True).stdout.strip()
    base = git("rev-parse", "HEAD")
    wt = tmp_path / "wt"
    git("worktree", "add", "--detach", str(wt), base)
    try:
        readme = wt / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nhook probe\n", encoding="utf-8")
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid",
            "commit", "-qam", "docs probe", cwd=wt)
        head = git("rev-parse", "HEAD", cwd=wt)
        # The hook also runs the rules check, which needs a recorded ballot. A runner has none,
        # so hand it an approval for the rules exactly as committed; this test is about the
        # docs-only shortcut, and test_rules covers the check itself.
        home = tmp_path / "home"
        home.mkdir()
        rules_blob = subprocess.run(["git", "show", "HEAD:docs/SYSTEM-DRAFT.md"], cwd=wt,
                                    check=True, capture_output=True).stdout
        (home / "rules-approval.json").write_text(json.dumps(
            {"sha256": hashlib.sha256(rules_blob).hexdigest(), "ballot": "TEST"}), encoding="utf-8")
        proc = subprocess.run([SH, str(HOOK)],
                              input=f"refs/heads/main {head} refs/heads/main {base}\n",
                              capture_output=True, text=True, cwd=wt,
                              env={**os.environ, "MEGAZWORD_HOME": str(home)})
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "docs-only push" in proc.stdout
        assert "running the suite" not in proc.stdout
    finally:
        git("worktree", "remove", "--force", str(wt))


def test_hook_does_not_shortcut_a_real_push():
    """The counterpart: a normal push must fall through to the suite, not the shortcut.
    MZ_PYTHON points at `false`, so this stops at the python probe instead of running
    the whole suite from inside the suite."""
    proc = subprocess.run([SH, str(HOOK)], input="refs/heads/x abc refs/heads/x 000\n",
                          capture_output=True, text=True, cwd=ROOT,
                          env={**os.environ, "MZ_PYTHON": "false"})
    assert "delete-only" not in proc.stdout
    assert "NOTHING WAS VERIFIED" in proc.stdout


def test_pre_commit_hook_survives_the_windows_checkout():
    """The pre-commit hook refreshes the memory index when the commit is made, so a
    docs-only change no longer needs a second commit and a second suite run (#755)."""
    raw = PRE_COMMIT.read_bytes()
    assert raw.startswith(b"#!/bin/sh"), "hook must be a sh script"
    assert b"\r\n" not in raw, "a CRLF shebang breaks the hook under sh"
    assert b"docs/MEMORY-INDEX.md" in raw, "the hook must refresh the index"
    # It is a convenience, not a gate: the suite belongs to pre-push, and paying for it
    # twice was the bug being fixed.
    assert b"-m pytest" not in raw, "pre-commit must not run the suite"
    assert b"unset GIT_DIR" in raw


@pytest.mark.skipif(SH is None, reason="needs sh (Git Bash) on PATH")
def test_pre_commit_hook_never_blocks_a_commit(tmp_path):
    """A commit hook that blocks work it cannot verify is one people learn to bypass.
    With no python to run, it exits 0 and says nothing - pre-push still holds the line."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    proc = subprocess.run([SH, str(PRE_COMMIT)], capture_output=True, text=True,
                          cwd=tmp_path, env={**os.environ, "MZ_PYTHON": "false"})
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


@pytest.mark.skipif(SH is None, reason="needs sh (Git Bash) on PATH")
def test_pre_commit_hook_stands_down_during_a_rebase(tmp_path):
    """A rebase replays many commits; regenerating on each is noise, and pre-push still
    covers the result. The hook must do nothing rather than fight the replay."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".git" / "rebase-merge").mkdir()
    proc = subprocess.run([SH, str(PRE_COMMIT)], capture_output=True, text=True,
                          cwd=tmp_path, env={**os.environ, "MZ_PYTHON": "false"})
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_install_check_flags_a_snapshot_install(tmp_path):
    snapshot = tmp_path / "site-packages" / "megazword" / "doctor.py"
    check = doctor.install_check(snapshot)
    assert check.level == "WARN"
    assert "pip install -e ." in check.hint


def test_install_check_accepts_an_editable_tree(tmp_path):
    live = tmp_path / "repo" / "src" / "megazword" / "doctor.py"
    assert doctor.install_check(live).level == "OK"
