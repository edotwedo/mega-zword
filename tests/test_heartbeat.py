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


def test_next_item_skips_phil_items_and_waits_on_claims():
    items = heartbeat.parse(ROADMAP)
    item, _ = heartbeat.next_item(items, "# Status\n**Active: none.**")
    assert item.num == 2
    claimed = "# Status\n**Active: Lark-17 (Codex) 3 PM. ROADMAP #2 Keymaster.**"
    item, why = heartbeat.next_item(items, claimed)
    assert item is None and "#2" in why and "no skipping" in why


def test_failed_item_stops_the_heartbeat():
    items = heartbeat.parse(ROADMAP.replace("2. [ ]", "2. [!]"))
    item, why = heartbeat.next_item(items, "")
    assert item is None and "failed" in why


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
    (tmp_path / "heartbeat" / "lock").write_text("busy")
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

    bad = [review.Finding("high", "a.py", 1, "wrong", ["groq", "zai"])]
    text = heartbeat.merge(clone, "night/t-1", {}, None, review_fn=lambda *a, **k: (bad, {"groq": ""}, ""))
    assert text.startswith("not merged: reviewers agree")
    ok = [review.Finding("high", "a.py", 1, "maybe", ["groq"])]
    text = heartbeat.merge(clone, "night/t-1", {}, None, review_fn=lambda *a, **k: (ok, {"groq": ""}, ""))
    assert text.startswith("merged into main")
    shown = subprocess.run(["git", "-C", str(bare), "show", "main:a.py"], capture_output=True, text=True)
    assert shown.stdout == "x = 2\n"


def test_install_needs_valid_times_and_yes(capsys):
    assert heartbeat.install("9am", 2, "23:00") == 2
    assert heartbeat.install("09:00", 2, "23:00") == 0
    assert "add --yes" in capsys.readouterr().out
