"""Project memory persists notes and decisions in isolated temporary storage."""

import json

import pytest

from megazword.memory import Entry, Memory


def test_missing_memory_is_empty(tmp_path):
    memory = Memory(tmp_path, "sample")

    assert memory.entries() == []
    assert memory.recent() == []
    assert memory.context_block() == ""
    assert not memory.path.exists()


@pytest.mark.parametrize("kind", ["note", "decision"])
def test_entry_round_trip(tmp_path, kind):
    memory = Memory(tmp_path, "sample")
    timestamp = "2026-10-14T01:00:00+00:00"
    text = 'Keep "caf\u00e9" notes\nwith a second line.'
    expected = Entry(timestamp, kind, text, "cedar")

    added = memory.add(kind, f"  {text}\n", by="cedar", time=timestamp)

    assert added == expected
    path = tmp_path / "projects" / "sample" / "memory.jsonl"
    assert memory.path == path
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "time": timestamp, "kind": kind, "text": text, "by": "cedar",
    }
    assert Memory(tmp_path, "sample").entries() == [expected]


def test_appends_keep_notes_and_decisions_in_order(tmp_path):
    memory = Memory(tmp_path, "sample")
    expected = [
        Entry("2026-10-14T01:00:00+00:00", "note", "First note", "phil"),
        Entry("2026-10-14T02:00:00+00:00", "decision", "Use local storage", "cedar"),
        Entry("2026-10-14T03:00:00+00:00", "note", "Second note", "phil"),
    ]
    memory.add("note", expected[0].text, time=expected[0].time)
    # Append through a new instance to exercise persistence between callers.
    reopened = Memory(tmp_path, "sample")
    reopened.add("decision", expected[1].text, by="cedar", time=expected[1].time)
    reopened.add("note", expected[2].text, time=expected[2].time)

    restored = Memory(tmp_path, "sample")
    assert restored.entries() == expected
    assert restored.recent(2) == expected[1:]
    assert restored.recent(1, kinds=("note",)) == [expected[2]]
    assert restored.recent(kinds=("decision",)) == [expected[1]]


def test_projects_have_separate_storage(tmp_path):
    alpha = Memory(tmp_path, "alpha")
    beta = Memory(tmp_path, "beta")
    note = alpha.add("note", "Alpha note")
    decision = beta.add("decision", "Beta rule")

    assert Memory(tmp_path, "alpha").entries() == [note]
    assert Memory(tmp_path, "beta").entries() == [decision]


def test_invalid_kind_does_not_create_storage(tmp_path):
    memory = Memory(tmp_path, "sample")

    with pytest.raises(ValueError, match="kind must be one of"):
        memory.add("unknown", "Rejected entry")

    assert not memory.path.exists()
    assert memory.entries() == []
