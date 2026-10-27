"""The land-gate: the suite runs before anything reaches main (2026-10-19).

A crash in `megazword --help` was landed without the suite being run, leaving the
front door red. These cover the gate's decision, the git wiring, and the hook
file itself (a CRLF shebang would silently break it under sh).
"""

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


@pytest.fixture
def hook_sandbox(tmp_path):
    if SH is None or os.name == "nt":
        pytest.skip("isolated executable fixtures need POSIX sh")
    tools = tmp_path / "tools"
    tools.mkdir()

    def executable(path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    executable(tools / "git", 'case "$*" in *--show-toplevel*) pwd;; *--git-common-dir*) exit 1;; *) exit 0;; esac\n')
    executable(tools / "uname", 'echo "${TEST_PLATFORM:-Linux}"\n')
    env = {**os.environ, "PATH": str(tools), "MZ_PYTHON": ""}
    env.pop("MZ_SKIP_GATE", None)

    def run(**overrides):
        return subprocess.run(
            [SH, str(HOOK)], input="refs/heads/x abc refs/heads/x 000\n",
            capture_output=True, text=True, cwd=tmp_path,
            env={**env, **overrides},
        )

    return tmp_path, tools, executable, run


def test_hook_blocks_when_no_python_runs(hook_sandbox):
    root, tools, executable, run = hook_sandbox
    # Executable Windows leftovers and PATH commands must actually run.
    for path in (root / ".venv/Scripts/python.exe", tools / "python3", tools / "python"):
        executable(path, "exit 126\n")
    proc = run(MZ_PYTHON="false")
    assert proc.returncode == 1
    assert "NOTHING WAS VERIFIED" in proc.stdout
    assert "delete-only" not in proc.stdout


def test_hook_blocks_without_pytest(hook_sandbox):
    root, _, executable, run = hook_sandbox
    executable(root / ".venv/bin/python", '[ "$2" = "import sys" ]\n')
    proc = run()
    assert proc.returncode == 1
    assert "has no pytest" in proc.stdout


@pytest.mark.parametrize("platform,native", [
    ("Linux", "bin/python"), ("MINGW64_NT", "Scripts/python.exe"),
    ("MSYS_NT", "Scripts/python.exe"), ("CYGWIN_NT", "Scripts/python.exe"),
])
def test_hook_prefers_native_python_and_runs_suite(hook_sandbox, platform, native):
    root, _, executable, run = hook_sandbox
    for candidate in ("bin/python", "Scripts/python.exe"):
        executable(root / ".venv" / candidate,
                   f'echo "{candidate}:$*" >> calls\nexit 0\n')
    proc = run(TEST_PLATFORM=platform)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = (root / "calls").read_text().splitlines()
    assert calls[0] == f"{native}:-c import sys"
    assert f"{native}:-m pytest -q" in calls
    assert all(line.startswith(native + ":") for line in calls)
    assert "suite passed" in proc.stdout


def test_hook_rejects_broken_override_and_falls_back(hook_sandbox):
    root, tools, executable, run = hook_sandbox
    broken = executable(tools / "broken", "exit 126\n")
    executable(root / ".venv/bin/python", "exit 0\n")
    proc = run(MZ_PYTHON=str(broken))
    assert proc.returncode == 0
    assert "suite passed" in proc.stdout


def test_hook_bypass_is_explicit_and_loud(hook_sandbox):
    *_, run = hook_sandbox
    proc = run(MZ_SKIP_GATE="1")
    assert proc.returncode == 0
    assert "BYPASS" in proc.stdout and "MZ_SKIP_GATE=1" in proc.stdout


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
