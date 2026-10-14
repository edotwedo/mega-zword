"""Direct contracts for JSON-lines logging and protected-line trimming."""

import json
from datetime import datetime, timezone

import pytest

from megazword import log
from megazword.filelock import locked


@pytest.fixture(params=["trim", "trim_unlocked"])
def trim_file(request):
    """Exercise both public trimming and trimming under an existing lock."""
    if request.param == "trim":
        return log.trim

    def trim_under_lock(path, keep, protect=None):
        with locked(path):
            return log.trim_unlocked(path, keep, protect)

    return trim_under_lock


def test_append_creates_parents_and_writes_json_records(tmp_path):
    path = tmp_path / "nested" / "logs" / "run.jsonl"
    before = datetime.now(timezone.utc).replace(microsecond=0)

    assert log.append(path, backend="test", text="café\nnext line", n=1) is None
    assert log.append(path, backend="other", ok=False, details={"n": 2}) is None

    after = datetime.now(timezone.utc)
    raw = path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in raw.splitlines()]
    assert raw.endswith("\n")
    assert len(records) == 2
    for record in records:
        stamp = datetime.fromisoformat(record.pop("time"))
        assert stamp.utcoffset().total_seconds() == 0
        assert before <= stamp <= after
    assert records == [
        {"backend": "test", "text": "café\nnext line", "n": 1},
        {"backend": "other", "ok": False, "details": {"n": 2}},
    ]


def test_append_preserves_supplied_time(tmp_path):
    path = tmp_path / "run.jsonl"
    log.append(path, time="recorded earlier", n=3)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "time": "recorded earlier", "n": 3,
    }


@pytest.mark.parametrize("keep", [0, -1])
def test_trim_nonpositive_keep_leaves_contents(tmp_path, trim_file, keep):
    path = tmp_path / "run.jsonl"
    original = "old\nnew\n"
    path.write_text(original, encoding="utf-8")

    assert trim_file(path, keep) is False
    assert path.read_text(encoding="utf-8") == original


def test_trim_missing_path_returns_false(tmp_path, trim_file):
    path = tmp_path / "missing" / "run.jsonl"
    assert trim_file(path, 2) is False
    assert not path.exists()


def test_trim_keeps_protected_lines_outside_keep_count(tmp_path, monkeypatch, trim_file):
    monkeypatch.setattr(log, "_BYTES_PER_LINE_GUESS", 1)
    path = tmp_path / "run.jsonl"
    path.write_text(
        "protected first\nold one\nprotected middle\nold two\n"
        "new one\nprotected late\nnew two\nprotected last\n",
        encoding="utf-8",
    )
    protect = lambda line: line.startswith("protected")

    assert trim_file(path, 2, protect) is True
    expected = (
        "protected first\nprotected middle\nnew one\n"
        "protected late\nnew two\nprotected last\n"
    )
    assert path.read_text(encoding="utf-8") == expected
    assert trim_file(path, 2, protect) is False
    assert path.read_text(encoding="utf-8") == expected


def test_trim_drops_oldest_unprotected_lines(tmp_path, monkeypatch, trim_file):
    monkeypatch.setattr(log, "_BYTES_PER_LINE_GUESS", 1)
    path = tmp_path / "run.jsonl"
    path.write_text("oldest\nolder\nnewer\nnewest\n", encoding="utf-8")

    assert trim_file(path, 2) is True
    assert path.read_text(encoding="utf-8") == "newer\nnewest\n"


def test_trim_waits_until_twenty_percent_threshold_is_exceeded(
    tmp_path, monkeypatch, trim_file,
):
    monkeypatch.setattr(log, "_BYTES_PER_LINE_GUESS", 1)
    path = tmp_path / "run.jsonl"
    original = "".join(f"line {n}\n" for n in range(6))
    path.write_text(original, encoding="utf-8")

    assert trim_file(path, 5) is False
    assert path.read_text(encoding="utf-8") == original

    path.write_text(original + "line 6\n", encoding="utf-8")
    assert trim_file(path, 5) is True
    assert path.read_text(encoding="utf-8") == "".join(
        f"line {n}\n" for n in range(2, 7)
    )


def test_trim_all_protected_leaves_file_unchanged(tmp_path, monkeypatch, trim_file):
    monkeypatch.setattr(log, "_BYTES_PER_LINE_GUESS", 1)
    path = tmp_path / "run.jsonl"
    original = "decision one\ndecision two\ndecision three\n"
    path.write_text(original, encoding="utf-8")

    assert trim_file(path, 1, lambda line: line.startswith("decision")) is False
    assert path.read_text(encoding="utf-8") == original
