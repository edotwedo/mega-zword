"""Night Shift: queue parsing, stop rules and a 3-job dry run against a local
bare repo with fake AIs (no real CLI, no network, no Q post, no scheduled task)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

from megazword import night
from megazword.backends import Backend
from megazword.cli import main
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
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_CONFIG_KEY_0"] == "credential.helper"
    assert env["MEGAZWORD_NO_USER_ENV"] == "1" and "PATH" in env


def test_tests_that_move_head_are_not_pushed(origin):
    """Codex review P1: the tests ran after the secret scan, so a test that commits is refused."""
    job = night.Job(0, " ", str(origin), "Fix the typo", "receive",
                    test="git commit -q --allow-empty -m sneaky")
    n = night.Night(fakes(("codex", typo_fix)), usage=meters(codex=10), date="2026-10-13")
    o = n.run_job(job)
    assert o.status == "failed" and "HEAD moved" in o.reason and not o.branch
    assert "night/2026-10-13-1" not in heads(origin)
