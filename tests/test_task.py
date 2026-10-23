"""M2 leases and actual Git push rejection, using only local temporary repos."""

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from megazword import cli, task

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 23, 5, tzinfo=timezone.utc)
ZERO = "0" * 40


def git(repo, *args, check=True, env=None):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", check=check, env=env, timeout=30)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "work.py").write_text("before\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "initial")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def test_task_allocates_id_branch_and_lease_without_switching(repo):
    result = task.new(repo, "one", ["work.py"], seat="Briar-20", now=NOW)
    assert result["branch"] == "task/" + result["id"]
    assert git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert git(repo, "rev-parse", result["branch"]).stdout == git(repo, "rev-parse", "HEAD").stdout
    assert result["expires_at"] == (NOW + timedelta(minutes=30)).isoformat()
    assert result["files"] == ["work.py"]


def test_second_worktree_cannot_claim_a_held_file(repo, tmp_path):
    other = tmp_path / "other"
    git(repo, "worktree", "add", "-qb", "other", str(other))
    task.new(repo, "one", ["work.py"], seat="Briar-20", now=NOW)
    with pytest.raises(task.TaskError, match="held by Briar-20"):
        task.new(other, "two", ["work.py"], seat="Nock-21", now=NOW)


def test_simultaneous_claims_have_only_one_winner(repo):
    def claim(seat):
        try:
            return task.new(repo, seat, ["work.py"], seat=seat, now=NOW)["id"]
        except task.TaskError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["Briar-20", "Nock-21"]))
    assert sum(result is not None for result in results) == 1


def test_expiry_and_heartbeat_are_thirty_minutes_and_cannot_resurrect(repo):
    first = task.new(repo, "one", ["work.py"], seat="Briar-20", now=NOW)
    renewed = task.update(repo, first["id"], seat="Briar-20", now=NOW + timedelta(minutes=20))
    assert renewed["tick"] == 1
    with pytest.raises(task.TaskError, match="held"):
        task.new(repo, "two", ["work.py"], seat="Nock-21", now=NOW + timedelta(minutes=49))
    second = task.new(repo, "two", ["work.py"], seat="Nock-21", now=NOW + timedelta(minutes=50))
    assert second["id"] != first["id"]
    with pytest.raises(task.TaskError, match="expired"):
        task.update(repo, first["id"], seat="Briar-20", now=NOW + timedelta(minutes=51))


def test_heartbeat_can_extend_the_file_set_but_not_take_another_lease(repo):
    first = task.new(repo, "one", ["work.py"], seat="Briar-20", now=NOW)
    task.new(repo, "other", ["held.py"], seat="Nock-21", now=NOW)
    renewed = task.update(repo, first["id"], seat="Briar-20", now=NOW, files=["new.py"])
    assert renewed["files"] == ["new.py", "work.py"]
    with pytest.raises(task.TaskError, match="additional files held"):
        task.update(repo, first["id"], seat="Briar-20", now=NOW, files=["held.py"])


def test_only_owner_renews_or_releases_and_release_does_not_declare_done(repo):
    first = task.new(repo, "one", ["work.py"], seat="Briar-20", now=NOW)
    with pytest.raises(task.TaskError, match="owning seat"):
        task.update(repo, first["id"], seat="Nock-21", now=NOW, release=True)
    released = task.update(repo, first["id"], seat="briar-20", now=NOW, release=True)
    assert released["state"] == "released"
    assert task.new(repo, "two", ["work.py"], seat="Nock-21", now=NOW)


def test_hot_files_are_never_locked(repo):
    paths = ["src/megazword/cli.py", "docs/STATUS.md", "docs/HIVE-ROSTER.md"]
    assert task.new(repo, "one", paths, seat="Briar-20", now=NOW)["files"] == []
    assert task.new(repo, "two", paths, seat="Nock-21", now=NOW)["files"] == []


@pytest.mark.parametrize("path", ["../outside.py", ".git/config", ".git", "."])
def test_paths_cannot_escape_or_lock_git_metadata(repo, path):
    with pytest.raises(task.TaskError):
        task.new(repo, "bad", [path], seat="Briar-20", now=NOW)


def test_busy_registry_fails_closed(repo, monkeypatch):
    @contextmanager
    def busy(*_args, **_kwargs):
        yield False
    monkeypatch.setattr(task, "locked", busy)
    with pytest.raises(task.TaskError, match="registry busy"):
        task.new(repo, "bad", ["work.py"], seat="Briar-20", now=NOW)
    assert git(repo, "branch", "--list", "task/*").stdout == ""


def test_corrupt_registry_never_becomes_an_empty_lock_set(repo):
    (repo / ".git/megazword-tasks.json").write_text("broken")
    with pytest.raises(task.TaskError, match="registry invalid"):
        task.check_push("", repo=repo, now=NOW)


def change(repo):
    (repo / "work.py").write_text("after\n")
    git(repo, "add", "work.py")
    git(repo, "commit", "-qm", "change")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_push_of_new_branch_blocks_foreign_files_and_ignores_expired_lease(repo, monkeypatch):
    first = task.new(repo, "one", ["work.py"], seat="Briar-20", now=NOW)
    sha = change(repo)
    refs = f"refs/heads/main {sha} refs/heads/other {ZERO}\n"
    assert task.check_push(refs, repo=repo, now=NOW)[0][0] == first["id"]
    assert task.check_push(refs, repo=repo, now=NOW + timedelta(minutes=30)) == []
    monkeypatch.setenv("MEGAZWORD_SEAT", "Briar-20")
    refs = f"refs/heads/{first['branch']} {sha} refs/heads/other {ZERO}\n"
    assert task.check_push(refs, repo=repo, now=NOW) == []
    monkeypatch.setenv("MEGAZWORD_SEAT", "Nock-21")
    assert task.check_push(refs, repo=repo, now=NOW)


def test_existing_remote_ref_and_delete_only_push(repo):
    task.new(repo, "one", ["work.py"], seat="Briar-20", now=NOW)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    sha = change(repo)
    assert task.check_push(f"refs/heads/main {sha} refs/heads/main {base}", repo=repo, now=NOW)
    assert task.check_push(f"(delete) {ZERO} refs/heads/main {base}", repo=repo, now=NOW) == []


def test_cli_is_discoverable_and_allocates_a_task(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("MEGAZWORD_SEAT", "Briar-20")
    assert "task" in cli.build_parser().format_help()
    assert cli.main(["task", "new", "--title", "one", "--files", "work.py"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert cli.main(["task", "beat", created["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["tick"] == 1


def test_actual_pre_push_blocks_before_suite_and_allows_after_expiry(repo, tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    # Run the tracked hook on a tiny repo with the actual task/filelock modules.
    package = repo / "src/megazword"
    package.mkdir(parents=True)
    for name in ("__init__.py", "task.py", "filelock.py"):
        shutil.copyfile(ROOT / "src/megazword" / name, package / name)
    (repo / "test_ok.py").write_text("def test_ok(): assert True\n")
    hookdir = repo / ".githooks"
    hookdir.mkdir()
    hook = hookdir / "pre-push"
    hook.write_bytes((ROOT / ".githooks/pre-push").read_bytes())
    hook.chmod(0o755)
    git(repo, "config", "core.hooksPath", ".githooks")
    task.new(repo, "foreign", ["work.py"], seat="Nock-21")
    change(repo)
    env = {**os.environ, "MZ_PYTHON": sys.executable, "MEGAZWORD_SEAT": "Briar-20"}
    env.pop("MZ_SKIP_GATE", None)
    rejected = git(repo, "push", "origin", "main", check=False, env=env)
    assert rejected.returncode != 0
    assert "task gate: push blocked" in rejected.stdout + rejected.stderr
    assert "running the suite" not in rejected.stdout + rejected.stderr
    # No sleep and no real registry: age only this temporary lease.
    registry = repo / ".git/megazword-tasks.json"
    state = json.loads(registry.read_text())
    for row in state["tasks"].values():
        row["expires_at"] = "2000-01-01T00:00:00+00:00"
    registry.write_text(json.dumps(state))
    allowed = git(repo, "push", "origin", "main", check=False, env=env)
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert "suite passed" in allowed.stdout + allowed.stderr
