import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("history", ROOT / "hive" / "history.py")
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)

CHATGPT = [{"id": "g1", "title": "Taxes 2025", "create_time": 1760000000, "mapping": {
    "a": {"message": {"author": {"role": "user"}, "create_time": 1760000001,
                      "content": {"parts": ["How do I file a W-2 with the IRS?"]}}},
    "b": {"message": {"author": {"role": "assistant"}, "create_time": 1760000002,
                      "content": {"parts": ["Use Form 1040 and attach the W-2."]}}},
    "root": {"message": None}}}]
CLAUDE = [{"uuid": "c1", "name": "Etsy shop", "created_at": "2026-10-01T10:00:00Z", "chat_messages": [
    {"sender": "human", "text": "Name ideas for the orange candle listing", "created_at": "2026-10-01T10:00:00Z"},
    {"sender": "assistant", "text": "", "content": [{"type": "text", "text": "Try Citrus Glow."}]}]}]


def make_exports(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "chatgpt").mkdir()
    (tmp_path / "chatgpt" / "conversations.json").write_text(json.dumps(CHATGPT))
    (tmp_path / "claude").mkdir()
    (tmp_path / "claude" / "conversations.json").write_text(json.dumps(CLAUDE))
    (tmp_path / "grok").mkdir()
    (tmp_path / "grok" / "export.json").write_text(json.dumps(
        {"conversations": [{"title": "Up Dawg jokes", "responses": [
            {"sender": "human", "message": "Alarm app jokes from licensed comics only"}]}]}))
    (tmp_path / "notes.md").write_text("Phil's bakery idea\n\nSourdough on Saturdays")
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    return tmp_path


def test_indexes_each_format_and_finds_by_words(tmp_path):
    db = history.connect(tmp_path / "idx.sqlite")
    added, skipped = history.index(make_exports(tmp_path / "x"), db, write=lambda s: None)
    assert (added, skipped) == (4, 0)
    hit = history.search(db, "W-2 IRS")
    assert hit[0][0] == "chatgpt:g1" and hit[0][2] == "Taxes 2025" and "[IRS]" in hit[0][5]
    assert history.search(db, "Citrus")[0][1] == "claude"
    assert history.search(db, "licensed comics")[0][1] == "grok"
    assert history.search(db, "sourdough")[0][2] == "notes"
    assert history.search(db, "candle", source="chatgpt") == []


def test_show_returns_a_conversation_in_order(tmp_path):
    db = history.connect(tmp_path / "idx.sqlite")
    history.index(make_exports(tmp_path / "x"), db, write=lambda s: None)
    rows = history.show(db, "chatgpt:g1")
    assert [r[2] for r in rows] == ["user", "assistant"]
    assert rows[0][1].startswith("2025-")
    assert [r[0] for r in history.show(db, "chatgpt:g1", find="form 1040")] == [2]


def test_reindex_skips_unchanged_and_replaces_changed_files(tmp_path):
    db = history.connect(tmp_path / "idx.sqlite")
    folder = make_exports(tmp_path / "x")
    history.index(folder, db, write=lambda s: None)
    assert history.index(folder, db, write=lambda s: None) == (0, 4)
    note = folder / "notes.md"
    note.write_text("Totally different text now")
    os.utime(note, (1, 1))
    assert history.index(folder, db, write=lambda s: None) == (1, 3)
    assert history.search(db, "sourdough") == []
    assert history.search(db, "different")[0][2] == "notes"


def test_a_broken_export_is_skipped_not_fatal(tmp_path):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "bad.json").write_text("{not json")
    (folder / "ok.txt").write_text("still indexed")
    lines = []
    db = history.connect(tmp_path / "idx.sqlite")
    assert history.index(folder, db, write=lines.append) == (1, 0)
    assert any("skip" in line and "bad.json" in line for line in lines)


def test_plain_words_with_punctuation_and_advanced_syntax(tmp_path):
    db = history.connect(tmp_path / "idx.sqlite")
    history.index(make_exports(tmp_path / "x"), db, write=lambda s: None)
    assert history.search(db, "W-2")[0][0] == "chatgpt:g1"
    assert {r[2] for r in history.search(db, "Citrus OR sourdough")} == {"Etsy shop", "notes"}
    assert history.search(db, "sour*")[0][2] == "notes"
