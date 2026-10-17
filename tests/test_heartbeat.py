"""Heartbeat with fakes: no network, no real AI, no scheduled task."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from megazword import config, heartbeat, night

ROADMAP = """# Mega Zword roadmap

## Done
- [x] Old thing

## Next, in order
1. [phil] **Review command** waiting on Phil.
2. [ ] **Keymaster** small version (handoff: docs/handoffs/k.md)
   Done when: keys load from the vault and tests pass.
3. [ ] **Heartbeat** schedule it.
"""


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(night, "home", lambda: tmp_path / "night")
    monkeypatch.setattr(night, "stop_path", lambda: tmp_path / "STOP")


def test_parse_reads_items_marks_and_done_when():
    items = heartbeat.parse(ROADMAP)
    assert [(i.num, i.mark, i.title) for i in items] == [
        (1, "phil", "Review command"), (2, " ", "Keymaster"), (3, " ", "Heartbeat")]
    assert items[1].done_when == "keys load from the vault and tests pass."


def test_next_item_skips_phil_and_claimed_items():
    items = heartbeat.parse(ROADMAP)
    item, _ = heartbeat.next_item(items, "# Status\n**Active: none.**")
    assert item.num == 2
    claimed = "# Status\n**Active: Lark-17 (Codex) 3 PM. ROADMAP #2 Keymaster.**"
    item, _ = heartbeat.next_item(items, claimed)
    assert item.num == 3  # someone has #2; the heartbeat picks another task


def test_failed_or_shelved_items_are_skipped_not_a_dead_stop():
    items = heartbeat.parse(ROADMAP.replace("2. [ ]", "2. [!]"))
    assert heartbeat.next_item(items, "")[0].num == 3
    item, why = heartbeat.next_item(heartbeat.parse(ROADMAP), "", shelved={2: {}, 3: {}})
    assert item is None and "#2, #3" in why


def _fake_clone(monkeypatch, roadmap=ROADMAP, status="**Active: none.**"):
    files = {"docs/ROADMAP.md": roadmap, "docs/STATUS.md": status, "docs/handoffs/k.md": "HANDOFF TEXT"}
    monkeypatch.setattr(night, "cache_clone", lambda repo: Path("."))
    monkeypatch.setattr(heartbeat, "_show", lambda clone, path: files.get(path, ""))


def test_beat_hands_next_item_to_night_shift_and_merges_on_green(monkeypatch, tmp_path):
    _fake_clone(monkeypatch)
    seen = {}

    class Runner:
        def run_job(self, job):
            seen["job"] = job
            return night.Outcome(job, "done", branch="night/x-1", ai="groq", tests="passed")
    merged = []
    text = heartbeat.beat({}, config.Config(), runner=Runner(),
                          merger=lambda clone, branch, b, c: merged.append(branch) or "merged into main",
                          write=lambda s: None)
    assert "ROADMAP item 2: Keymaster" in seen["job"].task and "HANDOFF TEXT" in seen["job"].task
    assert seen["job"].repo == heartbeat.GITEA
    assert merged == ["night/x-1"] and "merged into main" in text
    assert not (tmp_path / "heartbeat" / "lock").exists()


def test_beat_does_not_merge_failed_tests(monkeypatch):
    _fake_clone(monkeypatch)

    class Runner:
        def run_job(self, job):
            return night.Outcome(job, "failed", reason="tests failed", branch="night/x-1", tests="failed")
    text = heartbeat.beat({}, config.Config(), runner=Runner(),
                          merger=lambda *a: pytest.fail("must not merge"), write=lambda s: None)
    assert "failed" in text


def test_stop_file_and_lock_skip_the_beat(monkeypatch, tmp_path):
    (tmp_path / "STOP").write_text("x")
    assert "STOP" in heartbeat.beat({}, config.Config(), write=lambda s: None)
    (tmp_path / "STOP").unlink()
    (tmp_path / "heartbeat").mkdir(exist_ok=True)
    (tmp_path / "heartbeat" / "lock").write_text(str(__import__("os").getpid()))  # a live beat
    assert "another beat" in heartbeat.beat({}, config.Config(), write=lambda s: None)


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_merge_blocks_on_agreed_high_finding_and_merges_otherwise(tmp_path):
    from megazword import review
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], check=True, capture_output=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(seed, *args)
    (seed / "a.py").write_text("x = 1\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "base")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    (seed / "a.py").write_text("x = 2\n")
    _git(seed, "commit", "-qam", "change")
    _git(seed, "push", "-q", "origin", "HEAD:refs/heads/night/t-1")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(clone, *args)

    two = {"groq": "", "zai": ""}
    bad = [review.Finding("high", "a.py", 1, "wrong", ["groq", "zai"])]
    text = heartbeat.merge(clone, "night/t-1", {}, None, review_fn=lambda *a, **k: (bad, two, ""))
    assert text.startswith("not merged: reviewers agree")
    # One answer (the other reviewer failed) or none at all must not count as approval.
    text = heartbeat.merge(clone, "night/t-1", {}, None, review_fn=lambda *a, **k: ([], {"groq": ""}, ""))
    assert text == "not merged: needs 2 completed reviews, got 1"
    text = heartbeat.merge(clone, "night/t-1", {}, None, review_fn=lambda *a, **k: (None, {}, ""))
    assert text.startswith("not merged: needs 2")
    ok = [review.Finding("high", "a.py", 1, "maybe", ["groq"])]
    text = heartbeat.merge(clone, "night/t-1", {}, None, review_fn=lambda *a, **k: (ok, two, ""))
    assert text.startswith("merged into main")
    shown = subprocess.run(["git", "-C", str(bare), "show", "main:a.py"], capture_output=True, text=True)
    assert shown.stdout == "x = 2\n"

    # main moves after a job starts: the tested commit is no longer what would ship.
    (seed / "a.py").write_text("x = 3\n")
    _git(seed, "commit", "-qam", "job")
    _git(seed, "push", "-q", "origin", "HEAD:refs/heads/night/t-2")
    _git(seed, "reset", "-q", "--hard", "HEAD~1")
    (seed / "b.py").write_text("y = 1\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "someone else")
    _git(seed, "pull", "-q", "--no-rebase", "origin", "main")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    # main moved under the job: the step is rebased and retested, never shipped untested.
    text = heartbeat.merge(clone, "night/t-2", {}, None, review_fn=lambda *a, **k: ([], two, ""),
                           test_fn=lambda work: (False, "1 failed"))
    assert text == "not merged: main moved; tests fail on the new main (1 failed)"
    tested = []
    text = heartbeat.merge(clone, "night/t-2", {}, None, review_fn=lambda *a, **k: ([], two, ""),
                           test_fn=lambda work: tested.append(work) or (True, "ok"))
    assert text.startswith("merged into main") and "rebased onto the new main" in text and tested
    for name, value in (("a.py", "x = 3\n"), ("b.py", "y = 1\n")):
        shown = subprocess.run(["git", "-C", str(bare), "show", f"main:{name}"], capture_output=True, text=True)
        assert shown.stdout == value  # both the step and the other seat's work survive

    # A step that conflicts with the new main is refused.
    (seed / "a.py").write_text("x = 4\n")
    _git(seed, "commit", "-qam", "job 3")
    _git(seed, "push", "-q", "origin", "HEAD:refs/heads/night/t-3")
    _git(seed, "reset", "-q", "--hard", "HEAD~1")
    _git(seed, "pull", "-q", "--no-rebase", "origin", "main")
    (seed / "a.py").write_text("x = 5\n")
    _git(seed, "commit", "-qam", "someone else again")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    text = heartbeat.merge(clone, "night/t-3", {}, None, review_fn=lambda *a, **k: ([], two, ""),
                           test_fn=lambda work: pytest.fail("must not test a conflict"))
    assert text.startswith("not merged: main moved and the step conflicts")


def test_lock_is_atomic_and_stale_locks_expire(monkeypatch, tmp_path):
    assert heartbeat._locked() is False
    assert heartbeat._locked() is True
    lock = tmp_path / "heartbeat" / "lock"
    old = lock.stat().st_mtime - heartbeat.LOCK_HOURS * 3600 - 60
    import os
    os.utime(lock, (old, old))
    assert heartbeat._locked() is True  # its beat is still alive: a long run keeps the lock
    lock.write_text("", encoding="utf-8")  # no PID recorded: only the age decides
    os.utime(lock, (old, old))
    assert heartbeat._locked() is False


def test_install_needs_valid_times_and_yes(capsys):
    assert heartbeat.install("9am", 2, "23:00") == 2
    assert heartbeat.install("09:00", 2, "23:00") == 0
    assert "add --yes" in capsys.readouterr().out


def test_step_names_the_existing_handoff_as_the_log(monkeypatch):
    _fake_clone(monkeypatch)
    seen = {}

    class Runner:
        def run_job(self, job):
            seen["task"] = job.task
            return night.Outcome(job, "failed", reason="x")
    heartbeat.beat({}, config.Config(), runner=Runner(), write=lambda s: None)
    assert "in docs/handoffs/k.md, append" in seen["task"].replace("\n", " ")
    assert "roadmap-2.md" not in seen["task"]


def test_notes_only_change_is_not_merged(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], check=True, capture_output=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(seed, *args)
    (seed / "a.py").write_text("x = 1\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "base")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    (seed / "docs" / "handoffs").mkdir(parents=True)
    (seed / "docs" / "handoffs" / "roadmap-4.md").write_text("plan\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "notes")
    _git(seed, "push", "-q", "origin", "HEAD:refs/heads/night/n-1")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    text = heartbeat.merge(clone, "night/n-1", {}, None,
                           review_fn=lambda *a, **k: pytest.fail("no review for notes-only"))
    assert text == "not merged: only notes changed, no real progress"


def test_code_without_tests_is_not_merged(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], check=True, capture_output=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(seed, *args)
    (seed / "README").write_text("x\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "base")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    (seed / "src").mkdir()
    (seed / "src" / "a.py").write_text("def f(): return 1\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "code only")
    _git(seed, "push", "-q", "origin", "HEAD:refs/heads/night/c-1")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    text = heartbeat.merge(clone, "night/c-1", {}, None, review_fn=lambda *a, **k: pytest.fail("no review"))
    assert text == "not merged: code changed without tests"


def test_lock_left_by_a_dead_beat_is_taken_over(tmp_path):
    (tmp_path / "heartbeat").mkdir(exist_ok=True)
    (tmp_path / "heartbeat" / "lock").write_text("999999 2026-10-16 17:12")  # no such process
    assert heartbeat._locked() is False
    assert heartbeat._alive(__import__("os").getpid()) is True


def test_step_failing_twice_is_shelved_with_a_note_and_next_task_picked(monkeypatch):
    from megazword import briefing
    _fake_clone(monkeypatch)
    monkeypatch.setattr(night, "git", lambda args, cwd: SimpleNamespace(stdout="aaa\n", returncode=0))
    jobs = []

    class Runner:
        def run_job(self, job):
            jobs.append(job.task)
            return night.Outcome(job, "failed", reason="agent step cap reached (60)")

    def beat():
        return heartbeat.beat({}, config.Config(), runner=Runner(),
                              merger=lambda *a: pytest.fail("must not merge"), write=lambda s: None)

    assert "shelved" not in beat()
    assert "shelved #2" in beat()
    assert heartbeat.shelf()[2]["title"] == "Keymaster"
    note = heartbeat.notes_path().read_text(encoding="utf-8")
    assert "## Shelved #2 Keymaster" in note and "step cap" in note and "unshelve 2" in note
    card = briefing.snapshot()
    assert "Shelved for Phil: #2 Keymaster" in str(card)
    beat()
    assert "ROADMAP item 3: Heartbeat" in jobs[-1]  # moved on to the next task
    assert heartbeat.unshelve(2, write=lambda s: None) == 0 and 2 not in heartbeat.shelf()


def test_no_room_beats_and_merges_do_not_count_as_failures(monkeypatch):
    _fake_clone(monkeypatch)
    monkeypatch.setattr(night, "git", lambda args, cwd: SimpleNamespace(stdout="aaa\n", returncode=0))
    outcomes = [night.Outcome(None, "skipped", reason="no AI has room: codex: out"),
                night.Outcome(None, "skipped", reason="baseline tests failed before model work: 9 failed"),
                night.Outcome(None, "skipped", reason="no AI has room: codex: out")]

    class Runner:
        def run_job(self, job):
            return outcomes.pop()

    for _ in range(3):
        assert not heartbeat.beat({}, config.Config(), runner=Runner(),
                                  write=lambda s: None).startswith("stopped")
