"""Answer history stores exact content and returns the requested records."""

import json
from datetime import datetime, timezone

import pytest

from megazword import answers, config


@pytest.fixture
def answer_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path / "answers-home")
    return config.HOME / "answers.jsonl"


def test_missing_history_is_empty(answer_path):
    assert answers.path() == answer_path
    assert answers.recent() == []
    assert not answer_path.exists()


@pytest.mark.parametrize("tab_id", [None, "", "tab-7"])
def test_add_saves_and_returns_exact_content(answer_path, tab_id):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    content = {
        "prompt": 'Explain "café"\nwith a second line.',
        "answer": "First line\nSecond line: 雪",
        "backend": "codex",
        "project": "demo",
        "rating": None,
    }
    answers.add(**content, tab_id=tab_id)
    after = datetime.now(timezone.utc).replace(microsecond=0)

    text = answer_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert len(text.splitlines()) == 1
    saved = json.loads(text)
    timestamp = datetime.fromisoformat(saved["time"])
    assert timestamp.tzinfo == timezone.utc
    assert before <= timestamp <= after
    expected = dict(content, time=saved["time"])
    if tab_id:
        expected["tab_id"] = tab_id
    assert saved == expected
    assert answers.recent() == [expected]


def test_add_trims_storage_and_recent_returns_newest_first(answer_path):
    for i in range(4):
        answers.add(f"prompt {i}", f"answer {i}", "codex", "demo", "easy", keep=2)

    saved = [json.loads(line) for line in answer_path.read_text(encoding="utf-8").splitlines()]
    assert [row["prompt"] for row in saved] == ["prompt 2", "prompt 3"]
    assert [row["answer"] for row in saved] == ["answer 2", "answer 3"]
    assert all(row["rating"] == "easy" for row in saved)
    assert answers.recent() == saved[::-1]
    assert answers.recent(n=1) == [saved[-1]]


def test_recent_filters_project_before_limiting(answer_path):
    for i, project in enumerate(["demo", "other", "demo", "other"]):
        answers.add(f"prompt {i}", f"answer {i}", "codex", project, "medium")

    saved = [json.loads(line) for line in answer_path.read_text(encoding="utf-8").splitlines()]
    assert answers.recent(n=1, project="demo") == [saved[2]]
    assert answers.recent(n=10, project="demo") == [saved[2], saved[0]]
    assert answers.recent(project="missing") == []


def test_recent_skips_damaged_lines_and_non_objects(answer_path):
    older = {"prompt": "old", "answer": "first", "project": "demo"}
    newer = {"prompt": "new", "answer": "last", "project": "demo"}
    answer_path.parent.mkdir()
    answer_path.write_text(
        "\n".join([json.dumps(older), "not json", "[]", "null", "42",
                   '"text"', "", json.dumps(newer), "{broken"]),
        encoding="utf-8",
    )

    assert answers.recent() == [newer, older]
    assert answers.recent(n=1, project="demo") == [newer]


@pytest.mark.parametrize("keep", [0, -1])
def test_invalid_keep_preserves_saved_history(answer_path, keep):
    answers.add("original", "saved answer", "codex", "demo", "hard")
    original = answer_path.read_bytes()

    with pytest.raises(ValueError, match="keep must be positive"):
        answers.add("rejected", "new answer", "codex", "demo", None, keep=keep)

    assert answer_path.read_bytes() == original
    assert answers.recent()[0]["answer"] == "saved answer"
