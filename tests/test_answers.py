"""Focused storage tests for answer history."""
import json

import pytest

from megazword import answers


def test_add_saves_record_and_recent_returns_it(tmp_path, monkeypatch):
    monkeypatch.setattr(answers.config, "HOME", tmp_path)

    answers.add("question", "answer", "gemini-api", "project-a", "easy",
                tab_id="tab-1")

    rows = [json.loads(line) for line in answers.path().read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert {key: rows[0][key] for key in
            ("backend", "project", "rating", "prompt", "answer", "tab_id")} == {
                "backend": "gemini-api", "project": "project-a", "rating": "easy",
                "prompt": "question", "answer": "answer", "tab_id": "tab-1",
            }
    assert answers.recent() == rows
    assert rows[0]["time"].endswith("+00:00")


def test_recent_is_newest_first_and_can_filter_project(tmp_path, monkeypatch):
    monkeypatch.setattr(answers.config, "HOME", tmp_path)
    answers.add("older", "a1", "mistral", "alpha", None)
    answers.add("middle", "a2", "groq", "beta", "medium")
    answers.add("newer", "a3", "gemini-api", "alpha", "easy")

    assert [row["prompt"] for row in answers.recent()] == ["newer", "middle", "older"]
    assert [row["prompt"] for row in answers.recent(project="alpha")] == ["newer", "older"]


def test_add_retains_only_last_keep_records(tmp_path, monkeypatch):
    monkeypatch.setattr(answers.config, "HOME", tmp_path)
    for i in range(4):
        answers.add(f"q{i}", f"a{i}", "groq", "project", None, keep=2)

    assert [row["prompt"] for row in answers.recent()] == ["q3", "q2"]
    assert [json.loads(line)["prompt"] for line in
            answers.path().read_text(encoding="utf-8").splitlines()] == ["q2", "q3"]


@pytest.mark.parametrize("keep", [0, -1])
def test_add_rejects_nonpositive_retention(tmp_path, monkeypatch, keep):
    monkeypatch.setattr(answers.config, "HOME", tmp_path)

    with pytest.raises(ValueError, match="keep must be positive"):
        answers.add("q", "a", "groq", "project", None, keep=keep)

    assert not answers.path().exists()


def test_recent_skips_malformed_and_non_object_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(answers.config, "HOME", tmp_path)
    answers.path().write_text(
        '{"prompt":"older","answer":"a"}\nnot json\nnull\n[]\n{"prompt":"newer"}\n',
        encoding="utf-8",
    )

    assert answers.recent() == [{"prompt": "newer"}, {"prompt": "older", "answer": "a"}]
