"""Focused checks for JSON-lines append and retention behavior."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from megazword import config, log


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(config, "HOME", tmp_path / ".megazword")
    return config.HOME / "nested" / "log.jsonl"


def test_append_creates_parents_and_preserves_json_records(log_path):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    log.append(log_path, message="hello\n世界", count=2, ok=True)
    after = datetime.now(timezone.utc)
    log.append(log_path, time="supplied timestamp", message="second", ok=False)

    text = log_path.read_text(encoding="utf-8")
    first, second = [json.loads(line) for line in text.splitlines()]
    timestamp = datetime.fromisoformat(first.pop("time"))
    assert before <= timestamp <= after
    assert timestamp.utcoffset().total_seconds() == 0
    assert timestamp.microsecond == 0
    assert first == {"message": "hello\n世界", "count": 2, "ok": True}
    assert second == {"time": "supplied timestamp", "message": "second", "ok": False}
    assert text.endswith("\n")


def test_append_trims_existing_records_to_exact_newest(log_path):
    for index in range(6):
        log.append(log_path, max_lines=5, index=index, message="x" * 150)
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 6

    log.append(log_path, max_lines=5, index=6, message="x" * 150)
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [record["index"] for record in records] == [2, 3, 4, 5, 6]


@pytest.mark.parametrize("keep", [0, -1])
def test_nonpositive_keep_leaves_file_unchanged(tmp_path, keep):
    path = tmp_path / "log.jsonl"
    original = ("record\n" * 10).encode()
    path.write_bytes(original)
    assert log.trim(path, keep) is False
    assert path.read_bytes() == original


def test_trim_missing_file_does_not_create_log(tmp_path):
    path = tmp_path / "missing.jsonl"
    assert log.trim(path, keep=5) is False
    assert not path.exists()


def test_byte_precheck_leaves_small_file_unchanged(tmp_path):
    path = tmp_path / "log.jsonl"
    original = b"x\n" * 7
    path.write_bytes(original)
    assert log.trim(path, keep=5) is False
    assert path.read_bytes() == original


@pytest.mark.parametrize("count, trimmed", [(5, False), (6, False), (7, True)])
def test_trim_twenty_percent_threshold(tmp_path, count, trimmed):
    path = tmp_path / "log.jsonl"
    lines = [f"{index}:" + "x" * 150 for index in range(count)]
    original = "\n".join(lines) + "\n"
    path.write_text(original, encoding="utf-8")

    assert log.trim(path, keep=5) is trimmed
    expected = lines[-5:] if trimmed else lines
    assert path.read_text(encoding="utf-8") == "\n".join(expected) + "\n"
    assert log.trim(path, keep=5) is False


def test_protected_lines_do_not_count_toward_retention(tmp_path):
    path = tmp_path / "log.jsonl"
    lines = ["decision:first", "old:1", "decision:middle", "old:2", "new:3", "new:4", "decision:last"]
    lines = [line + "x" * 150 for line in lines]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    protect = lambda line: line.startswith("decision:")
    assert log.trim(path, keep=2, protect=protect) is True
    assert path.read_text(encoding="utf-8").splitlines() == [lines[i] for i in (0, 2, 4, 5, 6)]
    assert log.trim(path, keep=2, protect=protect) is False


def test_all_protected_lines_leave_file_unchanged(tmp_path):
    path = tmp_path / "log.jsonl"
    original = ("decision:" + "x" * 150 + "\n") * 5
    path.write_text(original, encoding="utf-8")
    assert log.trim(path, keep=1, protect=lambda line: line.startswith("decision:")) is False
    assert path.read_text(encoding="utf-8") == original
