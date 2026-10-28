import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("length_watch", ROOT / "hive" / "length_watch.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

CFG = {"yellow_chars": 100, "red_chars": 200, "long_prompt_chars": 50, "chat_check_every": 3}


def transcript(tmp_path, *entries):
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def says(n):
    return {"type": "user", "message": {"role": "user", "content": "x" * n}}


def test_counts_only_text_after_the_last_compaction(tmp_path):
    path = transcript(tmp_path, says(500),
                      {"type": "system", "subtype": "compact_boundary", "uuid": "c1"},
                      says(30),
                      {"type": "assistant", "message": {"content": [{"type": "text", "text": "y" * 20}]}},
                      {"type": "queue-operation", "content": "z" * 999})
    assert watch.measure(path) == (50, "c1")


def test_yellow_then_red_fire_once_each(tmp_path):
    cfg = {**CFG, "chat_check_every": 0}
    state = {"fired": []}
    small = {"transcript_path": str(transcript(tmp_path, says(150))), "prompt": "hi"}
    assert "yellow" in watch.check(small, cfg, state)[0]
    assert watch.check(small, cfg, state) == []
    big = {"transcript_path": str(transcript(tmp_path, says(250))), "prompt": "hi"}
    notes = watch.check(big, cfg, state)
    assert len(notes) == 1 and "red" in notes[0]
    assert watch.check(big, cfg, state) == []


def test_jumping_straight_to_red_skips_yellow(tmp_path):
    state = {"fired": []}
    event = {"transcript_path": str(transcript(tmp_path, says(250))), "prompt": "hi"}
    assert ["red" in n for n in watch.check(event, CFG, state)] == [True]


def test_a_new_compaction_rearms_the_levels(tmp_path):
    state = {"fired": ["yellow"], "era": "old"}
    event = {"transcript_path": str(transcript(tmp_path, {"type": "system", "subtype": "compact_boundary",
                                                          "uuid": "new"}, says(150))), "prompt": "hi"}
    assert "yellow" in watch.check(event, CFG, state)[0]


def test_chatty_check_on_long_prompt_and_every_nth(tmp_path):
    state = {"fired": []}
    assert "CHATTY" in watch.check({"prompt": "w" * 60}, CFG, state)[0]
    assert watch.check({"prompt": "short"}, CFG, state) == []
    assert "3 messages" in watch.check({"prompt": "short"}, CFG, state)[0]


def test_numbers_come_from_config(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "home", lambda: tmp_path)
    (tmp_path / "config.toml").write_text("[hive.length_watch]\nred_chars = 7\n", encoding="utf-8")
    cfg = watch.settings()
    assert cfg["red_chars"] == 7 and cfg["yellow_chars"] == watch.DEFAULTS["yellow_chars"]
