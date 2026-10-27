"""Night Shift: queue parsing, stop rules and a 3-job dry run against a local
bare repo with fake AIs (no real CLI, no network, no Q post, no scheduled task)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

from megazword import night
from megazword.backends import Backend
from megazword.cli import main
from megazword.free_apis import OpenAICompatibleBackend
from megazword.meters import Summary


@dataclass
class FakeAI(Backend):
    """Edits files in its cwd like an AI CLI would; records each call."""
    cwd: str = ""
    action: Callable | None = None
    calls: list = field(default_factory=list)

    def _run(self, prompt: str) -> str:
        self.calls.append((self.cwd, self.timeout, prompt))
        return self.action(Path(self.cwd), prompt) if self.action else ""


def typo_fix(folder: Path, prompt: str) -> str:
    (folder / "README.md").write_text("receive\n", encoding="utf-8")
    return "fixed the typo"


def add_note(folder: Path, prompt: str) -> str:
    (folder / "docs" / "NOTE.md").write_text("note\n", encoding="utf-8")
    return "added a note"


def does_nothing(folder: Path, prompt: str) -> str:
    return "nothing to do"


def meters(**used) -> Callable[[], list]:
    return lambda: [Summary(name, "meter", pct, "weekly") for name, pct in used.items()]


QUEUE = """# Night queue

- [ ] {repo} | Fix the typo in README.md | done when: README says receive
- [ ] {repo} | Add docs/NOTE.md, ask @codex | done when: the file exists | test: exit 0
- [ ] {repo} | Break the tests | done when: never | test: exit 1
- [x] {repo} | Already done | done when: yes
"""


def sh(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def origin(tmp_path, monkeypatch):
    """A bare repo standing in for GitHub, with README.md and docs/QUEUE.md on main."""
    for var, val in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                     ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(var, val)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "--quiet", "--bare", str(bare)],
                   check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "--quiet", str(bare), str(seed)], check=True,
                   capture_output=True)
    sh(["checkout", "-q", "-b", "main"], seed)
    (seed / "README.md").write_text("recieve\n", encoding="utf-8")
    (seed / "docs").mkdir()
    (seed / "docs" / "QUEUE.md").write_text(QUEUE.format(repo=bare), encoding="utf-8")
    sh(["add", "-A"], seed)
    sh(["commit", "-q", "-m", "seed"], seed)
    sh(["push", "-q", "origin", "main"], seed)
    return bare


def heads(bare: Path) -> dict[str, str]:
    out = sh(["for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads"], bare)
    return dict(line.split() for line in out.splitlines())


def show(bare: Path, ref: str, path: str) -> str:
    return sh(["show", f"{ref}:{path}"], bare)


def fakes(*pairs) -> dict[str, FakeAI]:
    return {name: FakeAI(name, action=action) for name, action in pairs}


def test_parse_queue_skips_notes_and_reads_test():
    jobs = night.parse_queue(QUEUE.format(repo="o/r") + "- [ ] missing fields\n")
    assert [j.mark for j in jobs] == [" ", " ", " ", "x"]
    assert jobs[0].repo == "o/r" and jobs[0].done_when == "README says receive"
    assert jobs[1].test == "exit 0" and jobs[0].test == ""


def test_three_job_dry_run(origin):
    """The Done-when check from the spec: 3 jobs, fake AIs, real git, nothing on main."""
    main_before = heads(origin)["main"]
    actions = iter([typo_fix, add_note, add_note])
    ai = FakeAI("codex", action=lambda folder, prompt: next(actions)(folder, prompt))
    n = night.Night({"codex": ai, "claude": FakeAI("claude")}, usage=meters(codex=20, claude=50),
                    date="2026-10-13", job_minutes=7)
    lines = []
    assert night.run_night(n, queue=str(origin), max_jobs=5, write=lines.append) == 0

    branches = heads(origin)
    assert branches["main"] == main_before  # never main
    assert show(origin, "night/2026-10-13-1", "README.md") == "receive\n"
    assert show(origin, "night/2026-10-13-2", "docs/NOTE.md") == "note\n"
    assert "night/2026-10-13-3" in branches          # failed tests: branch still pushed for review
    marks = show(origin, "night/2026-10-13-4", "docs/QUEUE.md")
    assert marks.count("[x]") == 3 and marks.count("[!]") == 1  # 2 done + the old one; 1 failed
    assert "Tests: failed" in sh(["log", "-1", "--format=%B", "night/2026-10-13-3"], origin)
    assert all(timeout == 7 * 60 for _, timeout, _ in ai.calls)  # per-job time cap
    assert not ai.calls[0][0].startswith(str(origin))             # the AI works in a scratch checkout

    summary = (night.home() / "summary-2026-10-13.md").read_text(encoding="utf-8")
    assert "@" not in summary
    assert summary.count("- done by codex") == 2 and "- failed by codex" in summary
    assert "tests failed" in summary

    # A second run finds nothing left to do.
    lines.clear()
    night.run_night(n, queue=str(origin), write=lines.append)
    assert any("0 job(s) waiting" in line for line in lines)


def test_next_ai_when_first_makes_no_change(origin):
    ais = fakes(("codex", does_nothing), ("claude", typo_fix))
    n = night.Night(ais, usage=meters(codex=10, claude=60), date="2026-10-13")
    job = night.parse_queue(QUEUE.format(repo=origin))[0]
    o = n.run_job(job)
    assert o.status == "done" and o.ai == "claude" and o.tried == ["codex", "claude"]


def test_usage_floor_and_unknown_meters_fail_closed(origin):
    ais = fakes(("codex", typo_fix), ("claude", typo_fix))
    names, why = night.eligible(ais, meters(codex=90, claude=50)(), floor=15)
    assert names == ["claude"] and any("under the 15% floor" in w for w in why)
    names, why = night.eligible(ais, [Summary("codex", "none"), Summary("claude", "meter", 10, "5-hour",
                                                                        stale=True)])
    assert names == [] and len(why) == 2

    n = night.Night(ais, usage=meters(codex=95, claude=99), date="2026-10-13")
    lines = []
    night.run_night(n, queue=str(origin), write=lines.append)
    assert not ais["codex"].calls and not ais["claude"].calls
    assert not night.load_state()  # skipped jobs stay queued for the next night
    assert "night/2026-10-13-1" not in heads(origin)


@dataclass
class FreeHTTP(OpenAICompatibleBackend):
    """Scripted free API: writes README.md through the coding loop."""
    seen: list = field(default_factory=list)

    def available(self):
        return True

    def chat(self, messages, tools=None, timeout=None):
        self.seen.append(messages)
        if any(m.get("role") == "tool" for m in messages):
            args = json.dumps({"summary": "fixed"})
            return {"tool_calls": [{"id": "t", "function": {"name": "finish", "arguments": args}}]}
        args = json.dumps({"path": "README.md", "text": "receive\n"})
        return {"tool_calls": [{"id": "t", "function": {"name": "write_file", "arguments": args}}]}


def test_free_http_without_meter_is_eligible_before_paid():
    ais = {"groq": FreeHTTP("groq"), "codex": FakeAI("codex", action=typo_fix)}
    names, why = night.eligible(ais, [Summary("codex", "none")])
    assert names[0] == "groq" and "codex" not in names
    assert any("codex: no meter" in w for w in why)


def test_night_uses_free_http_when_paid_has_no_room(origin):
    groq = FreeHTTP("groq")
    n = night.Night({"groq": groq, "codex": FakeAI("codex")},
                    usage=lambda: [Summary("codex", "none")], date="2026-10-13")
    night.run_night(n, queue=str(origin), max_jobs=1, write=lambda s: None)
    assert show(origin, "night/2026-10-13-1", "README.md") == "receive\n"
    assert groq.seen



@dataclass
class IdleHTTP(FreeHTTP):
    """Free API that finishes without editing anything."""

    def chat(self, messages, tools=None, timeout=None):
        self.seen.append(messages)
        args = json.dumps({"summary": "nothing"})
        return {"tool_calls": [{"id": "t", "function": {"name": "finish", "arguments": args}}]}


def test_night_stops_free_tries_at_cap_then_uses_paid(origin):
    free = {f"free{i}": IdleHTTP(f"free{i}") for i in range(night.MAX_FREE_TRIES + 2)}
    codex = FakeAI("codex", action=typo_fix)
    n = night.Night({**free, "codex": codex}, usage=meters(codex=10), date="2026-10-13")
    night.run_night(n, queue=str(origin), max_jobs=1, write=lambda s: None)
    assert sum(bool(ai.seen) for ai in free.values()) == night.MAX_FREE_TRIES
    assert codex.calls
    assert show(origin, "night/2026-10-13-1", "README.md") == "receive\n"


def test_night_tries_cheap_after_free_cap_before_paid(origin):
    free = {f"free{i}": IdleHTTP(f"free{i}") for i in range(night.MAX_FREE_TRIES + 1)}
    cheap = FreeHTTP("cheap-deepseek-flash")
    codex = FakeAI("codex", action=typo_fix)
    n = night.Night({"cheap-deepseek-flash": cheap, **free, "codex": codex},
                    usage=meters(codex=10), date="2026-10-13")
    night.run_night(n, queue=str(origin), max_jobs=1, write=lambda s: None)
    assert sum(bool(ai.seen) for ai in free.values()) == night.MAX_FREE_TRIES
    assert cheap.seen and not codex.calls  # cheap fixed it, so Codex was never called

def test_night_status_shows_stop_lock_jobs_and_summary(capsys):
    night.home().mkdir(parents=True, exist_ok=True)
    night.stop_path().write_text("stopped\n", encoding="utf-8")
    (night.home() / "running.lock").write_text("1", encoding="utf-8")
    night.save_state({
        "job-a": {"at": "2026-10-13T01:00:00", "status": "done",
                  "branch": "night/2026-10-13-1", "ai": "codex"},
    })
    (night.home() / "summary-2026-10-13.md").write_text("# summary\n", encoding="utf-8")
    assert main(["night", "status"]) == 0
    out = capsys.readouterr().out
    assert "STOP file: yes" in out
    assert "lock: a run is going" in out
    assert "night/2026-10-13-1" in out and "codex" in out
    assert "summary-2026-10-13.md" in out


def test_night_resume_when_no_stop_file(capsys):
    assert not night.stop_path().exists()
    assert main(["night", "resume"]) == 0
    assert "on again" in capsys.readouterr().out
    assert not night.stop_path().exists()


def test_stop_file_and_job_cap(origin):
    ais = fakes(("codex", typo_fix))
    n = night.Night(ais, usage=meters(codex=10), date="2026-10-13")
    assert main(["night", "stop"]) == 0
    night.run_night(n, queue=str(origin), write=lambda s: None)
    assert not ais["codex"].calls
    assert main(["night", "resume"]) == 0
    night.run_night(n, queue=str(origin), max_jobs=1, write=lambda s: None)
    assert len(ais["codex"].calls) == 1
    assert "1-job cap" in (night.home() / "summary-2026-10-13.md").read_text(encoding="utf-8")


def test_refuses_secrets(origin):
    def leak(folder, prompt):
        (folder / ".env").write_text("X=1\n", encoding="utf-8")
        return "added .env"
    n = night.Night(fakes(("codex", leak)), usage=meters(codex=10), date="2026-10-13")
    o = n.run_job(night.parse_queue(QUEUE.format(repo=origin))[0])
    assert o.status == "failed" and "secrets file" in o.reason and not o.branch
    assert "night/2026-10-13-1" not in heads(origin)


def test_push_refuses_anything_but_night(tmp_path):
    for bad in ("main", "night/", "feature/x"):
        with pytest.raises(RuntimeError, match="refusing"):
            night.push_branch(tmp_path, bad)


def test_one_run_at_a_time(origin):
    lock = night.home() / "running.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("1", encoding="utf-8")
    n = night.Night(fakes(("codex", typo_fix)), usage=meters(codex=10))
    assert night.run_night(n, queue=str(origin), write=lambda s: None) == 1


def test_install_prints_plan_and_needs_yes(monkeypatch, capsys):
    monkeypatch.setattr(night, "_ON_WINDOWS", True)
    calls = []
    monkeypatch.setattr(night, "_schtasks", lambda args: calls.append(args) or
                        subprocess.CompletedProcess(args, 0, "", ""))
    assert night.install("01:30") == 0 and calls == []
    assert night.install("25:00", yes=True) == 2 and calls == []
    assert night.install("01:30", yes=True) == 0
    assert calls[0][:2] == ["/Create", "/TN"] and "DAILY" in calls[0] and "01:30" in calls[0]
    assert "night run --post" in calls[0][calls[0].index("/TR") + 1]
    assert night.remove() == 0 and calls[1][0] == "/Delete"


def test_summary_post_is_off_in_tests(origin):
    n = night.Night(fakes(("codex", typo_fix)), usage=meters(codex=10), date="2026-10-13")
    lines = []
    night.run_night(n, queue=str(origin), max_jobs=1, post=True, write=lines.append)
    assert any("NOT posted" in line for line in lines)


def test_failed_ai_partial_edits_are_discarded(origin):
    """Codex review P1: an AI that errors (e.g. timeout) after editing must not be committed."""
    def half_then_crash(folder, prompt):
        (folder / "README.md").write_text("half\n", encoding="utf-8")
        raise TimeoutError("no answer within 1800s")
    ais = fakes(("codex", half_then_crash), ("claude", typo_fix))
    n = night.Night(ais, usage=meters(codex=10, claude=60), date="2026-10-13")
    o = n.run_job(night.parse_queue(QUEUE.format(repo=origin))[0])
    assert o.status == "done" and o.ai == "claude"
    assert show(origin, o.branch, "README.md") == "receive\n"

    n = night.Night(fakes(("codex", half_then_crash)), usage=meters(codex=10), date="2026-10-14")
    o = n.run_job(night.parse_queue(QUEUE.format(repo=origin))[0])
    assert o.status == "failed" and "partial edits were discarded" in o.reason and not o.branch


def test_job_tests_get_no_keys_or_git_login(monkeypatch, tmp_path):
    """Codex review P1: job tests are AI-written code; they get no tokens and can't push."""
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "XAI_API_KEY", "CLOUDFLARE_API_TOKEN", "MY_SECRET"):
        monkeypatch.setenv(var, "x")
    env = night.test_env(tmp_path)
    assert not {"GH_TOKEN", "GITHUB_TOKEN", "XAI_API_KEY", "CLOUDFLARE_API_TOKEN", "MY_SECRET"} & set(env)
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_CONFIG_PARAMETERS"] == "'credential.helper='"
    assert not any(k.startswith("GIT_CONFIG_") and k != "GIT_CONFIG_PARAMETERS" for k in env)
    assert env["MEGAZWORD_NO_USER_ENV"] == "1" and "PATH" in env


def test_tests_that_move_head_are_not_pushed(origin):
    """Codex review P1: the tests ran after the secret scan, so a test that commits is refused."""
    job = night.Job(0, " ", str(origin), "Fix the typo", "receive",
                    test="git commit -q --allow-empty -m sneaky")
    n = night.Night(fakes(("codex", typo_fix)), usage=meters(codex=10), date="2026-10-13")
    o = n.run_job(job)
    assert o.status == "failed" and "HEAD moved" in o.reason and not o.branch
    assert "night/2026-10-13-1" not in heads(origin)


def python_suite(origin, assertion):
    seed = origin.parent / "seed"
    (seed / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (seed / "tests").mkdir(exist_ok=True)
    (seed / "tests" / "test_baseline.py").write_text(
        f"def test_existing():\n    assert {assertion}\n", encoding="utf-8")
    sh(["add", "-A"], seed)
    sh(["commit", "-qm", "baseline suite"], seed)
    sh(["push", "-q", "origin", "main"], seed)


def test_broken_baseline_spends_no_model_calls_and_stays_queued(origin, monkeypatch):
    python_suite(origin, "1 == 2")
    ai = FakeAI("codex", action=typo_fix)
    n = night.Night({"codex": ai}, usage=meters(codex=10))
    actual, suites = night.run_cmd, []
    def record(cmd, cwd=None, timeout=300, env=None):
        if "pytest" in cmd:
            suites.append(str(cwd))
        return actual(cmd, cwd, timeout, env)
    monkeypatch.setattr(night, "run_cmd", record)
    night.run_night(n, queue=str(origin), max_jobs=2, write=lambda s: None)
    assert not ai.calls and len(suites) == 1  # same failing revision checked once
    assert not night.load_state()  # repair can retry; not marked permanently failed
    assert list(heads(origin)) == ["main"]
    logs = list((night.home() / "test-results").glob("*-baseline.log"))
    assert len(logs) == 1 and "test_existing" in logs[0].read_text(encoding="utf-8")
    assert "baseline tests failed before model work" in (
        night.home() / f"summary-{n.date}.md").read_text(encoding="utf-8")
    # A repaired base gets a fresh preflight even in the same Night instance.
    python_suite(origin, "1 == 1")
    outcome = n.run_job(night.Job(0, " ", str(origin), "Fix typo", "README says receive"))
    assert outcome.status == "done" and len(ai.calls) == 1 and len(suites) == 3


def test_healthy_baseline_checked_once_and_worker_tests_still_run(origin, monkeypatch):
    python_suite(origin, "1 == 1")
    ai = FakeAI("codex", action=typo_fix)
    n = night.Night({"codex": ai}, usage=meters(codex=10))
    actual, suites = night.run_cmd, []
    def record(cmd, cwd=None, timeout=300, env=None):
        if "pytest" in cmd:
            suites.append(str(cwd))
        return actual(cmd, cwd, timeout, env)
    monkeypatch.setattr(night, "run_cmd", record)
    for i in range(2):
        o = n.run_job(night.Job(i, " ", str(origin), f"Fix typo {i}", "README says receive"))
        assert o.status == "done" and o.tests == "passed"
    assert len(ai.calls) == 2 and len(suites) == 3


def test_night_command_passes_free_model_config(monkeypatch):
    import argparse
    from megazword import backends, config
    calls = []
    monkeypatch.setattr(backends, "default_backends", lambda **kwargs: calls.append(kwargs) or {})
    monkeypatch.setattr(night, "run_night", lambda worker, *args: calls.append(worker.cfg) or 0)
    cfg = config.Config(free={"ollama": "custom-coder"}, agent={"max_steps": 4})
    args = argparse.Namespace(night_cmd="run", floor=15, job_minutes=2, queue=None, max=1, post=False)
    assert night.command(args, cfg) == 0
    assert calls[0]["free_models"] == {"ollama": "custom-coder"}
    assert calls[1] is cfg


def test_paid_capacity_rechecked_before_call(origin):
    ai = FakeAI("codex", action=typo_fix)
    readings = iter([meters(codex=10)(), meters(codex=95)()])
    worker = night.Night({"codex": ai}, usage=lambda: next(readings))
    out = worker.run_job(night.parse_queue(QUEUE.format(repo=origin))[0])
    assert out.status == "skipped" and "no fresh capacity" in out.reason
    assert not ai.calls and list(heads(origin)) == ["main"]


def test_default_branch_prefers_main_over_a_stale_remote_head(tmp_path):
    import subprocess
    from megazword import night
    bare = tmp_path / "r.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "s"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], check=True, capture_output=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(seed), *args], check=True)
    (seed / "a").write_text("1")
    subprocess.run(["git", "-C", str(seed), "add", "."], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-qm", "c"], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:main", "HEAD:old"], check=True)
    subprocess.run(["git", "-C", str(bare), "symbolic-ref", "HEAD", "refs/heads/old"], check=True)
    clone = tmp_path / "c"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    assert night.default_branch(clone) == "origin/main"


def test_night_gives_the_job_to_the_least_used_free_source(origin, tmp_path):
    from megazword import config, log
    cfg = config.Config()
    cfg.log_path = tmp_path / "fair.jsonl"
    for _ in range(3):
        log.append(cfg.log_path, backend="groq", ok=True)  # groq is busy today; zai is idle
    groq, zai = FreeHTTP("groq"), FreeHTTP("zai")
    n = night.Night({"groq": groq, "zai": zai}, usage=lambda: [], date="2026-10-13", cfg=cfg)
    night.run_night(n, queue=str(origin), max_jobs=1, write=lambda s: None)
    assert zai.seen and not groq.seen


def test_night_runs_are_written_to_the_run_log(origin, tmp_path):
    from megazword import config
    from megazword.runlog import summarize
    from datetime import timedelta
    cfg = config.Config()
    cfg.log_path = tmp_path / "night-log.jsonl"
    groq = FreeHTTP("groq")
    n = night.Night({"groq": groq}, usage=lambda: [], date="2026-10-13", cfg=cfg)
    night.run_night(n, queue=str(origin), max_jobs=1, write=lambda s: None)
    runs = summarize(cfg.log_path, timedelta(days=1))
    assert runs["groq"].runs >= 1 and runs["groq"].est_tokens > 0


def test_tests_run_with_console_python_even_under_pythonw(tmp_path, monkeypatch):
    folder = tmp_path / "py"
    folder.mkdir()
    (folder / "python.exe").write_text("")
    (folder / "pythonw.exe").write_text("")
    monkeypatch.setattr(night.sys, "executable", str(folder / "pythonw.exe"))
    assert night.console_python() == str(folder / "python.exe")
    work = tmp_path / "repo"
    (work / "tests").mkdir(parents=True)
    (work / "pyproject.toml").write_text("")
    cmd, _ = night.test_command(work, night.Job(0, " ", "", "t", "d"))
    assert cmd[0] == str(folder / "python.exe")
    monkeypatch.setattr(night.sys, "executable", str(folder / "python.exe"))
    assert night.console_python() == str(folder / "python.exe")


def test_night_tries_only_one_cheap_model(origin):
    free = {f"free{i}": IdleHTTP(f"free{i}") for i in range(night.MAX_FREE_TRIES)}
    pro, flash = IdleHTTP("cheap-deepseek-pro"), IdleHTTP("cheap-deepseek-flash")
    codex = FakeAI("codex", action=typo_fix)
    n = night.Night({**free, "cheap-deepseek-pro": pro, "cheap-deepseek-flash": flash, "codex": codex},
                    usage=meters(codex=10), date="2026-10-13")
    night.run_night(n, queue=str(origin), max_jobs=1, write=lambda s: None)
    assert pro.seen and not flash.seen  # the first cheap model only, then paid
    assert codex.calls


def _fake_systemd(monkeypatch, returncode=0):
    calls = []
    monkeypatch.setattr(night, "_ON_WINDOWS", False)
    monkeypatch.setattr(night, "_systemd", lambda action, name, files=None: calls.append((action, name, files))
                        or subprocess.CompletedProcess([action], returncode, "", "boom" if returncode else ""))
    return calls


def test_linux_install_writes_a_daily_systemd_timer(monkeypatch, capsys):
    calls = _fake_systemd(monkeypatch)
    monkeypatch.setenv("MEGAZWORD_HOME", "/home/x/my mz")
    assert night.install("01:30") == 0 and calls == []
    assert night.install("01:30", yes=True) == 0
    action, name, files = calls[0]
    assert (action, name) == ("install", night.TASK_NAME)
    service, timer = files["megazword-nightshift.service"], files["megazword-nightshift.timer"]
    assert "Type=oneshot" in service and "night run --post" in service
    assert 'Environment="MEGAZWORD_HOME=/home/x/my mz"' in service
    assert "OnCalendar=*-*-* 01:30:00" in timer and "WantedBy=timers.target" in timer
    assert night.remove() == 0 and calls[1][:2] == ("remove", night.TASK_NAME)


def test_linux_install_failure_is_reported(monkeypatch, capsys):
    _fake_systemd(monkeypatch, returncode=1)
    assert night.install("01:30", yes=True) == 1
    assert "scheduling failed: boom" in capsys.readouterr().err


def test_unit_files_escape_percent_for_systemd():
    files = night.unit_files("MegaZword-X", '"/opt/50%/python" -m megazword.cli x', ["OnActiveSec=1min"], "x")
    assert "ExecStart=\"/opt/50%%/python\" -m megazword.cli x" in files["megazword-x.service"]


def test_real_systemd_is_never_touched_by_tests():
    with pytest.raises(RuntimeError, match="real systemctl"):
        night._systemd("install", "MegaZword-X", {})


@pytest.mark.parametrize("home, written", [
    ("/tmp/50%quota", "/tmp/50%%quota"),  # %q would expand to the hostname
    ('/tmp/a"b', '/tmp/a\\"b'),
    ("/tmp/a\\b", "/tmp/a\\\\b"),
])
def test_custom_home_is_written_literally_for_systemd(monkeypatch, home, written):
    monkeypatch.setenv("MEGAZWORD_HOME", home)
    service = night.unit_files("MegaZword-X", "x", [], "x")["megazword-x.service"]
    assert f'Environment="MEGAZWORD_HOME={written}"' in service


def test_custom_home_with_newline_is_refused(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_HOME", "/tmp/a\nExecStart=/bin/evil")
    with pytest.raises(ValueError, match="newline"):
        night.unit_files("MegaZword-X", "x", [], "x")


def test_install_with_unwritable_home_reports_instead_of_crashing(monkeypatch, capsys):
    calls = _fake_systemd(monkeypatch)
    monkeypatch.setenv("MEGAZWORD_HOME", "/tmp/a\nb")
    assert night.install("01:30", yes=True) == 1 and calls == []
    assert "newline" in capsys.readouterr().err
