"""Team engine combine: real local git, fake tests and reviewers, no network."""
import json
import subprocess
from pathlib import Path

import pytest

from megazword import config, review, team


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def job(tmp_path, monkeypatch):
    """A job folder like run_pieces leaves it: a clone with two passed piece branches."""
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t",
                       "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_EMAIL": "t@example.com"}.items():
        monkeypatch.setenv(key, value)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(bare)], check=True)
    folder = config.HOME / "jobs" / "J1"
    clone = folder / "repo"
    subprocess.run(["git", "clone", "--quiet", str(bare), str(clone)], check=True, capture_output=True)
    git(clone, "checkout", "-q", "-b", "main")
    (clone / "a.txt").write_text("a\n")
    (clone / "b.txt").write_text("b\n")
    git(clone, "add", ".")
    git(clone, "commit", "-qm", "base")
    git(clone, "push", "-q", "origin", "main")
    base = git(clone, "rev-parse", "HEAD")
    for n, name, text in ((1, "a.txt", "a by groq\n"), (2, "b.txt", "b by zai\n")):
        git(clone, "checkout", "-q", "-b", f"job/J1-{n}", base)
        (clone / name).write_text(text)
        git(clone, "commit", "-qam", f"piece {n}")
    git(clone, "checkout", "-q", "main")
    report = {"id": "J1", "repo": str(bare), "base": base, "clone": str(clone), "results": [
        {"index": 1, "title": "edit a", "status": "passed", "ai": "groq-120b", "branch": "job/J1-1"},
        {"index": 2, "title": "edit b", "status": "passed", "ai": "zai", "branch": "job/J1-2"},
        {"index": 3, "title": "broken", "status": "failed", "ai": "", "branch": ""}]}
    (folder / "job.json").write_text(json.dumps(report), encoding="utf-8")
    return {"bare": bare, "clone": clone, "folder": folder, "base": base}


def two_reviews(seen=None):
    def fake(work, backends, cfg, base=None, count=2):
        if seen is not None:
            seen.append(sorted(backends))
        return [], {"ovh": "no bugs found", "nvidia-lightning": "no bugs found"}, ""
    return fake


def show(bare, ref, path):
    return subprocess.run(["git", "-C", str(bare), "show", f"{ref}:{path}"],
                          capture_output=True, text=True).stdout


def test_combine_merges_passed_pieces_tests_reviews_and_pushes_job_branch(job):
    seen = []
    backends = {"groq": 1, "groq-120b": 1, "zai": 1, "zai-47": 1, "ovh": 1, "nvidia-lightning": 1}
    combined = team.combine("J1", backends, None, review_fn=two_reviews(seen),
                            test_fn=lambda work: ("passed", "2 passed"))
    assert combined["status"] == "ready" and combined["pieces"] == [1, 2]
    assert seen == [["nvidia-lightning", "ovh"]]  # no reviewer from a family that wrote a piece
    assert show(job["bare"], "job/J1", "a.txt") == "a by groq\n"
    assert show(job["bare"], "job/J1", "b.txt") == "b by zai\n"
    assert show(job["bare"], "main", "a.txt") == "a\n"  # main untouched
    saved = json.loads((job["folder"] / "job.json").read_text(encoding="utf-8"))
    assert saved["combined"]["status"] == "ready"
    assert "job/J1: ready" in team.format_combined(combined)
    # A second combine never force-pushes over the branch already there.
    again = team.combine("J1", backends, None, review_fn=two_reviews(),
                         test_fn=lambda work: ("passed", ""))
    assert again["status"] == "ready, not pushed" and "already exists" in again["detail"]


def test_conflicting_pieces_stop_before_tests(job):
    clone = job["clone"]
    git(clone, "checkout", "-q", "job/J1-2")
    (clone / "a.txt").write_text("a by zai too\n")
    git(clone, "commit", "-qam", "piece 2 also edits a")
    git(clone, "checkout", "-q", "main")
    combined = team.combine("J1", {}, None, review_fn=lambda *a, **k: pytest.fail("no review"),
                            test_fn=lambda work: pytest.fail("no tests"), push=False)
    assert combined["status"] == "conflict" and "piece 2" in combined["detail"]


def test_failing_tests_and_missing_reviews_are_recorded(job):
    combined = team.combine("J1", {}, None, review_fn=lambda *a, **k: pytest.fail("no review"),
                            test_fn=lambda work: ("failed", "1 failed"), push=False)
    assert (combined["status"], combined["detail"]) == ("tests failed", "1 failed")
    one = lambda *a, **k: ([], {"ovh": "no bugs found"}, "")
    combined = team.combine("J1", {}, None, review_fn=one, test_fn=lambda work: ("passed", ""), push=False)
    assert combined["status"] == "needs review"
    bad = [review.Finding("high", "a.txt", 1, "wrong", ["ovh", "nvidia-lightning"])]
    combined = team.combine("J1", {}, None, review_fn=lambda *a, **k: (bad, {"ovh": "", "x": ""}, ""),
                            test_fn=lambda work: ("passed", ""), push=False)
    assert combined["status"] == "review found problems"
    assert not subprocess.run(["git", "-C", str(job["bare"]), "rev-parse", "--verify", "-q", "job/J1"],
                              capture_output=True).stdout  # nothing pushed


def test_missing_job_and_nothing_passed(job):
    with pytest.raises(FileNotFoundError):
        team.combine("NOPE", {}, None)
    path = job["folder"] / "job.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    for row in report["results"]:
        row["status"] = "failed"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert team.combine("J1", {}, None)["status"] == "nothing to combine"


def test_job_combine_command(job, monkeypatch, capsys):
    from types import SimpleNamespace
    from megazword import job as job_cmd
    monkeypatch.setattr(team, "combine", lambda job_id, backends, cfg, push=True:
                        {"branch": f"job/{job_id}", "status": "ready", "detail": "", "tests": "passed",
                         "reviewers": ["ovh"], "findings": []})
    lines = []
    args = SimpleNamespace(job_cmd="combine", id="J1", no_push=False)
    assert job_cmd.command(args, {}, None, write=lines.append) == 0
    assert lines[0].splitlines()[0] == "job/J1: ready"
    args = SimpleNamespace(job_cmd="combine", id="NOPE", no_push=True)
    monkeypatch.undo()
    monkeypatch.setattr(config, "HOME", job["folder"].parent.parent)
    assert job_cmd.command(args, {}, None, write=lines.append) == 1 and "no job NOPE" in lines[-1]
