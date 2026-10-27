"""Run the commit hook against hybrid virtualenvs and real Git staging."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from megazword import memory_index


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-commit"
SH = shutil.which("sh")
pytestmark = pytest.mark.skipif(os.name == "nt" or not SH, reason="POSIX executable fixtures")


def executable(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@pytest.mark.parametrize("platform,native", [
    ("Linux", "bin/python"), ("MINGW64_NT", "Scripts/python.exe"),
    ("MSYS_NT", "Scripts/python.exe"), ("CYGWIN_NT", "Scripts/python.exe"),
])
def test_commit_hook_uses_native_runnable_interpreter(tmp_path, monkeypatch, platform, native):
    tools = tmp_path / "tools"
    executable(tools / "git", 'case "$*" in *--show-toplevel*) pwd;; *--git-dir*) echo .git;; *--git-common-dir*) exit 1;; *) exit 0;; esac\n')
    executable(tools / "uname", f"echo {platform}\n")
    for candidate in ("bin/python", "Scripts/python.exe"):
        executable(tmp_path / ".venv" / candidate,
                   f'echo "{candidate}:$*" >> calls\nexit 0\n')
    monkeypatch.setenv("PATH", str(tools))
    monkeypatch.delenv("MZ_PYTHON", raising=False)
    monkeypatch.delenv("MZ_SKIP_GATE", raising=False)
    proc = subprocess.run([SH, str(HOOK)], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = (tmp_path / "calls").read_text().splitlines()
    assert calls[0] == f"{native}:-c import sys"
    assert all(call.startswith(native + ":") for call in calls)
    assert any("memory_index.write()" in call for call in calls)


@pytest.mark.parametrize("broken_override", [False, True])
@pytest.mark.parametrize("linked_worktree", [False, True])
def test_commit_stages_fresh_index_despite_broken_windows_python(tmp_path, monkeypatch, broken_override, linked_worktree):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    package = repo / "src" / "megazword"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    shutil.copyfile(ROOT / "src/megazword/memory_index.py", package / "memory_index.py")
    docs = repo / "docs"
    docs.mkdir()
    (docs / "STATUS.md").write_text("# A changed status\n")
    (docs / "MEMORY-INDEX.md").write_text("stale index\n")
    executable(repo / ".venv/Scripts/python.exe", "exit 126\n")
    executable(repo / ".venv/bin/python",
                        f'exec {shlex.quote(sys.executable)} "$@"\n')
    if broken_override:
        monkeypatch.setenv("MZ_PYTHON", str(executable(repo / "broken-python", "exit 126\n")))
    else:
        monkeypatch.delenv("MZ_PYTHON", raising=False)
    monkeypatch.delenv("MZ_SKIP_GATE", raising=False)
    subprocess.run(["git", "add", "src", "docs"], cwd=repo, check=True)
    if linked_worktree:
        no_hooks = tmp_path / "no-hooks"
        no_hooks.mkdir()
        subprocess.run(["git", "-c", "user.name=Gate Test", "-c", "user.email=gate@example.invalid",
                        "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={no_hooks}",
                        "commit", "-qm", "seed linked worktree"], cwd=repo, check=True)
        linked = tmp_path / "linked checkout with spaces"
        subprocess.run(["git", "worktree", "add", "-qb", "task/fixture", str(linked)], cwd=repo, check=True)
        repo, docs = linked, linked / "docs"
        (docs / "STATUS.md").write_text("# Status changed in the linked worktree\n")
        subprocess.run(["git", "add", "docs"], cwd=repo, check=True)
    proc = subprocess.run(
        ["git", "-c", "user.name=Gate Test", "-c", "user.email=gate@example.invalid",
         "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={HOOK.parent}",
         "commit", "-qm", "stage generated memory index"],
        cwd=repo, capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    committed = subprocess.run(["git", "show", "HEAD:docs/MEMORY-INDEX.md"],
                               cwd=repo, capture_output=True, text=True, check=True).stdout
    assert committed == memory_index.render(docs)
    assert "refreshed docs/MEMORY-INDEX.md" in proc.stdout + proc.stderr
