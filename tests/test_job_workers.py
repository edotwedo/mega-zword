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


def test_easy_failure_gets_one_paid_retry_with_clean_worktree(origin, monkeypatch):
    from megazword import agent
    # Provider cooldowns are real in production; a scripted 429 need not wait.
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)
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


@pytest.mark.parametrize("level", ["medium", "hard"])
def test_free_worker_gets_first_pass_before_paid_worker(origin, level):
    free = Free("groq")
    paid = Paid("codex")
    report = run(origin, [piece(level=level)], {"groq": free, "codex": paid},
                 job_id=f"free-first-{level}")
    assert report["results"][0]["status"] == "passed"
    assert report["results"][0]["tried"][0] == "groq"
    assert not paid.calls


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


@pytest.mark.parametrize("args", [
    ["--basetemp=/unrelated"], ["--basetemp", "../outside"], ["--base=/unrelated"],
    ["--rootdir=.."], ["-c", "../pytest.ini"], ["-o", "cache_dir=../outside"],
    ["--junitxml=../report.xml"], ["../tests"], ["C:/outside"], ["/outside"],
    ["-p", "untrusted_plugin"], ["@outside-args.txt"],
])
def test_pytest_unsafe_options_and_targets_rejected_before_workers(args):
    with pytest.raises(ValueError):
        jobs._test(["pytest", *args])


def test_pytest_selectors_and_reporting_options_allowed():
    args = ["-q", "-x", "tests/test_a.py::test_one", "-k", "one or two", "--maxfail=2",
            "--tb", "short", "-p", "no:cacheprovider"]
    assert jobs._test(["pytest", *args])[3:] == tuple(args)


@pytest.mark.parametrize("explicit", [False, True])
def test_worker_tests_import_changed_src_checkout(origin, explicit):
    seed = origin.parent / "seed"
    (seed / "src").mkdir()
    (seed / "src" / "worker_proof.py").write_text("VALUE = 'old'\n")
    (seed / "tests").mkdir()
    (seed / "tests" / "test_proof.py").write_text(
        "from worker_proof import VALUE\ndef test_changed():\n    assert VALUE == 'new'\n")
    (seed / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    git(seed, "add", ".")
    git(seed, "commit", "-qm", "src fixture")
    git(seed, "push", "-q", "origin", "main")
    def edit(folder, prompt):
        (folder / "src" / "worker_proof.py").write_text("VALUE = 'new'\n")
        return "done"
    report = run(origin, [piece(path="src/worker_proof.py", level="medium",
                              test="pytest -q" if explicit else "")],
                 {"codex": Paid("codex", action=edit)}, job_id=f"src-{explicit}")
    assert report["results"][0]["status"] == "passed", report["results"]
    assert report["results"][0]["tests"] == "passed"


@pytest.mark.parametrize("name,level,model,effort", [
    ("claude", "hard", "review-model", "high"),
    ("codex", "medium", "coding-model", "medium"),
])
def test_worker_difficulty_settings_use_private_backend_copy(tmp_path, name, level, model, effort):
    source = CLIBackend(name, exe=name, args=["original"])
    settings = config.Config(levels={name: {level: (model, effort)}})
    runner = jobs.Runner(settings, {name: source})
    worker = runner._worker(tmp_path, jobs.Piece("piece", ("a.txt",), level), [], name)
    assert model in worker.args
    assert effort in worker.args or f"model_reasoning_effort={effort}" in worker.args
    assert source.args == ["original"] and source.cwd != str(tmp_path)


def test_runner_test_permission_comes_from_title_not_boilerplate(tmp_path):
    free = Free("groq")
    runner = jobs.Runner(cfg(), {"groq": free})
    ordinary = runner._worker(tmp_path, jobs.Piece("fix behavior", ("tests/test_a.py",), "easy"), [free], None)
    ordinary.run("Mega Zword runs the tests. Allowed files (exact paths): tests/test_a.py")
    assert ordinary._allow_test_edits is False
    assert not (tmp_path / "tests" / "test_a.py").exists()
    intended = runner._worker(tmp_path, jobs.Piece("add tests", ("tests/test_a.py",), "easy"), [free], None)
    assert intended.allow_test_edits is True


@dataclass
class Idle(Free):
    """Finishes without editing anything."""

    def chat(self, messages, tools=None, timeout=None):
        self.seen.append(messages)
        return tool("finish", summary="nothing to do")


def test_hard_piece_gets_three_free_families_before_giving_up(origin):
    order = ["groq", "zai", "ovh", "nvidia"]
    settings = config.Config(agent={"pace": {n: 0 for n in order}, "failover_order": order})
    backends = {"groq": Idle("groq"), "zai": Idle("zai"), "ovh": Free("ovh"), "nvidia": Free("nvidia")}
    report = jobs.run_pieces({"pieces": [piece(level="hard")]}, origin, cfg=settings,
                             backends=backends, usage=usage, job_id="hard")
    result = report["results"][0]
    assert result["status"] == "passed" and result["ai"] == "ovh"
    assert {"groq", "zai", "ovh"} <= set(result["tried"]) and not backends["nvidia"].seen


def test_easy_piece_gets_a_single_free_attempt(origin):
    order = ["groq", "zai", "ovh"]
    settings = config.Config(agent={"pace": {n: 0 for n in order}, "failover_order": order})
    backends = {"groq": Idle("groq"), "zai": Free("zai"), "ovh": Free("ovh")}
    report = jobs.run_pieces({"pieces": [piece(level="easy")]}, origin, cfg=settings,
                             backends=backends, usage=usage, job_id="easy-one")
    assert report["results"][0]["status"] == "failed" and not backends["zai"].seen


def test_free_attempts_groups_by_family():
    names = ["groq", "groq-120b", "zai", "zai-47", "ovh", "tencent-glm-5.3"]
    free = [Free(n) for n in names]
    groups = jobs.free_attempts(free, "hard")
    assert [[b.name for b in g] for g in groups] == [["groq", "groq-120b"], ["zai", "zai-47"], ["ovh"]]
    assert [len(g) for g in jobs.free_attempts(free, "medium")] == [6]
    assert jobs.free_attempts([], "hard") == []


def test_shared_brief_starts_every_worker_prompt(origin):
    free = Free("groq")
    report = jobs.run_pieces({"brief": "Add a widget; both pieces call it make_widget.",
                              "pieces": [piece()]}, origin, cfg=cfg(),
                             backends={"groq": free}, usage=usage, job_id="briefed")
    assert report["runner_status"] == "complete" and report["brief"].startswith("Add a widget")
    first = free.seen[0][1]["content"]
    assert first.startswith("Shared brief for every worker on this job: Add a widget; both pieces")
    unbriefed = Free("groq")
    run(origin, [piece()], {"groq": unbriefed}, job_id="plain")
    assert unbriefed.seen[0][1]["content"].startswith("Work on this independent piece only")
