"""Worker runner: real local git worktrees, scripted AIs, no network or paid calls."""
import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from megazword import config, job_workers as jobs, night
from megazword.backends import CLIBackend
from megazword.free_apis import OpenAICompatibleBackend, APIHTTPError
from megazword.meters import Summary


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def origin(tmp_path, monkeypatch):
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t",
                       "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_EMAIL": "t@example.com"}.items():
        monkeypatch.setenv(key, value)
    bare, seed = tmp_path / "origin.git", tmp_path / "seed"
    subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(bare)], check=True)
    subprocess.run(["git", "clone", "--quiet", str(bare), str(seed)], check=True, capture_output=True)
    (seed / "README.md").write_text("baseline\n")
    git(seed, "add", ".")
    git(seed, "commit", "-qm", "seed")
    git(seed, "push", "-q", "origin", "main")
    return bare


def piece(title="first", path="a.txt", level="easy", test=""):
    return {"title": title, "files": [path], "difficulty": level, "test": test}


def tool(name, **arguments):
    return {"tool_calls": [{"id": "tool", "function": {"name": name, "arguments": json.dumps(arguments)}}]}


@dataclass
class Free(OpenAICompatibleBackend):
    seen: list = field(default_factory=list)
    barrier: object = None
    fail: bool = False
    unexpected: bool = False

    def available(self):
        return True

    def chat(self, messages, tools=None, timeout=None):
        self.seen.append(messages)
        if self.fail:
            raise APIHTTPError(429)
        observations = [m for m in messages if m.get("role") == "tool"]
        if observations:
            return tool("finish", summary="piece implemented")
        if self.barrier:
            self.barrier.wait(timeout=10)
        prompt = "\n".join(m.get("content") or "" for m in messages)
        path = "unassigned.txt" if self.unexpected else re.search(r"Allowed files \(exact paths\): ([^\n,]+)", prompt)[1]
        return tool("write_file", path=path, text=f"implemented {path}\n")


@dataclass
class Paid(CLIBackend):
    calls: list = field(default_factory=list)
    action: object = None

    def available(self):
        return True

    def _run(self, prompt):
        self.calls.append((self.cwd, prompt))
        if self.action:
            return self.action(Path(self.cwd), prompt)
        path = re.search(r"Allowed files \(exact paths\): ([^\n,]+)", prompt)[1]
        (Path(self.cwd) / path).write_text("paid retry implementation\n")
        return "implemented"


def usage():
    return [Summary("codex", "meter", 10, "weekly"), Summary("claude", "meter", 40, "weekly")]


def cfg():
    return config.Config(agent={"pace": {"groq": 0, "gemini-api": 0},
                                "failover_order": ["groq", "gemini-api"]})


def run(origin, rows, backends, **options):
    return jobs.run_pieces({"pieces": rows}, origin, cfg=cfg(), backends=backends,
                          usage=usage, **options)


def test_real_parallel_worktrees_independent_commits_and_idempotent_report(origin):
    free = Free("groq", barrier=threading.Barrier(2))
    plan = [piece(), piece("second", "b.txt")]
    report = run(origin, plan, {"groq": free}, job_id="parallel", workers=2)
    assert report["runner_status"] == "complete"
    assert [r["index"] for r in report["results"]] == [1, 2]
    clone = config.HOME / "jobs" / "parallel" / "repo"
    for index, path in [(1, "a.txt"), (2, "b.txt")]:
        branch = report["results"][index-1]["branch"]
        assert git(clone, "show", f"{branch}:{path}") == f"implemented {path}"
        assert git(clone, "diff", "--name-only", report["base"], branch) == path
        assert report["results"][index-1]["requests"] == 2
    assert git(origin, "for-each-ref", "--format=%(refname:short)", "refs/heads") == "main"
    assert run(origin, plan, {"groq": free}, job_id="parallel") == report
    assert len(free.seen) == 4  # no rerun / duplicate workers


def test_overlap_and_private_paths_rejected_before_any_worker(origin):
    for rows in [[piece(path="a.txt"), piece(path="A.txt")], [piece(path="../out")],
                 [piece(path=".env")], [piece(path=".git/config")], [piece(path="src/*.py")]]:
        with pytest.raises(ValueError):
            run(origin, rows, {})
    assert not (config.HOME / "jobs").exists()


def test_free_failover_preserves_piece_and_never_repeats_it(origin):
    busy, good = Free("groq", fail=True), Free("gemini-api")
    report = run(origin, [piece()], {"groq": busy, "gemini-api": good}, job_id="failover")
    row = report["results"][0]
    assert row["status"] == "passed" and row["ai"] == "gemini-api"
    assert row["tried"] == ["groq", "gemini-api"]
    assert len(busy.seen) == 1 and len(good.seen) == 2


def test_easy_failure_gets_one_paid_retry_with_clean_worktree(origin):
    busy = Free("groq", fail=True)
    paid = Paid("codex")
    report = run(origin, [piece()], {"groq": busy, "codex": paid}, job_id="retry")
    row = report["results"][0]
    assert row["status"] == "passed" and row["ai"] == "codex"
    assert row["tried"] == ["groq", "codex"] and len(paid.calls) == 1


def test_worker_cannot_commit_unassigned_files(origin):
    free = Free("groq", unexpected=True)
    report = run(origin, [piece()], {"groq": free}, job_id="scope")
    row = report["results"][0]
    assert row["status"] == "failed" and "outside its piece" in row["reason"]
    assert not row["commit"]


def test_paid_worker_runs_tests_and_failure_is_not_delivered(origin, monkeypatch):
    paid = Paid("codex")
    actual = night.run_cmd
    seen = []
    def command(cmd, cwd=None, timeout=300, env=None):
        if "pytest" in cmd:
            seen.append((cmd, env))
            return subprocess.CompletedProcess(cmd, 1, "test failed", "")
        return actual(cmd, cwd, timeout, env)
    monkeypatch.setattr(night, "run_cmd", command)
    monkeypatch.setenv("PRIVATE_API_KEY", "a-private-test-value")
    report = run(origin, [piece(level="medium", test="python -m pytest -q")], {"codex": paid}, job_id="testfail")
    row = report["results"][0]
    assert row["status"] == "failed" and row["tests"] == "failed"
    assert not row["commit"] and len(seen) == 1
    assert "PRIVATE_API_KEY" not in seen[0][1]


def test_unread_or_exhausted_paid_meter_prevents_run(origin):
    paid = Paid("codex")
    report = jobs.run_pieces({"pieces": [piece(level="hard")]}, origin,
        cfg=cfg(), backends={"codex": paid}, usage=lambda: [], job_id="nometer")
    assert report["results"][0]["status"] == "skipped" and not paid.calls


def test_lock_and_unsafe_test_command(origin):
    with pytest.raises(ValueError):
        run(origin, [piece(test="python -c 'delete everything'")], {})
    with pytest.raises(ValueError):
        run(origin, [piece(test="npm test; git push")], {})
    folder = config.HOME / "jobs" / "locked"
    folder.mkdir(parents=True)
    (folder / "runner.lock").write_text("running")
    with pytest.raises(RuntimeError, match="already"):
        run(origin, [piece()], {}, job_id="locked")


def test_two_paid_pieces_use_distinct_workers(origin):
    barrier = threading.Barrier(2)
    def edit(folder, prompt):
        barrier.wait(timeout=10)
        path = re.search(r"Allowed files \(exact paths\): ([^\n,]+)", prompt)[1]
        (folder / path).write_text("implemented\n")
        return "done"
    codex, claude = Paid("codex", action=edit), Paid("claude", action=edit)
    report = run(origin, [piece(level="medium"), piece("second", "b.txt", "hard")],
                 {"codex": codex, "claude": claude}, job_id="paid-parallel", workers=2)
    assert report["runner_status"] == "complete"
    assert len(codex.calls) == len(claude.calls) == 1
    assert {r["ai"] for r in report["results"]} == {"codex", "claude"}


def test_worker_cannot_switch_to_main(origin):
    def switch(folder, prompt):
        git(folder, "checkout", "--ignore-other-worktrees", "main")
        (folder / "a.txt").write_text("wrong branch")
        return "done"
    report = run(origin, [piece(level="hard")], {"codex": Paid("codex", action=switch)}, job_id="branch-switch")
    row = report["results"][0]
    assert row["status"] == "failed" and "changed git branch" in row["reason"]
    assert not row["commit"]


def test_completed_id_cannot_be_reused_for_a_different_job(origin):
    run(origin, [piece()], {"groq": Free("groq")}, job_id="same-id")
    with pytest.raises(ValueError, match="different plan"):
        run(origin, [piece("different", "different.txt")], {}, job_id="same-id")


def test_planner_metadata_and_unicode_file_names_are_preserved(origin):
    plan = {"id": "saved-plan", "planner": "test-planner", "pieces": [piece(path="notes/π.txt")]}
    report = jobs.run_pieces(plan, origin, cfg=cfg(), backends={"groq": Free("groq")}, usage=usage)
    assert report["id"] == "saved-plan" and report["planner"] == "test-planner"
    assert report["runner_status"] == "complete"
    assert git(Path(report["clone"]), "show", "job/saved-plan-1:notes/π.txt") == "implemented notes/π.txt"
