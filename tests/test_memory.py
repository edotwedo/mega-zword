from __future__ import annotations

import pytest
from pathlib import Path

from megazword.memory import (
    Memory,
    Entry,
    KINDS,
    project_name,
    list_projects,
    check_project,
    with_context,
)


def test_entry_roundtrip(tmp_path: Path) -> None:
    mem = Memory(tmp_path, "test-proj")
    assert mem.entries() == []

    # Add various entries
    e1 = mem.add("note", "  hello world  ", by="alice")
    e2 = mem.add("decision", "use python 3", by="bob")
    e3 = mem.add("done", "finished task", by="charlie")
    e4 = mem.add("lesson", "learned something", by="dave")

    assert e1.text == "hello world"
    assert e1.by == "alice"
    assert e1.kind == "note"

    entries = mem.entries()
    assert len(entries) == 4
    assert entries[0] == e1
    assert entries[1] == e2
    assert entries[2] == e3
    assert entries[3] == e4

    # Test filtering by kinds in recent()
    recent_notes = mem.recent(kinds=("note",))
    assert len(recent_notes) == 1
    assert recent_notes[0].text == "hello world"

    recent_default = mem.recent(n=2)
    assert len(recent_default) == 2
    assert recent_default[0].kind == "done"
    assert recent_default[1].kind == "lesson"


def test_validation_and_errors(tmp_path: Path) -> None:
    mem = Memory(tmp_path, "test-proj")
    with pytest.raises(ValueError, match="kind must be one of"):
        mem.add("invalid_kind", "some text")


def test_context_block(tmp_path: Path) -> None:
    mem = Memory(tmp_path, "my-proj")
    mem.add("decision", "rule number one")
    mem.add("note", "did some stuff")

    block = mem.context_block(n=5, max_decisions=5, max_chars=100)
    assert "[Project memory for 'my-proj', kept by Mega Zword]" in block
    assert "Decisions (follow these):" in block
    assert "- rule number one" in block
    assert "Recent activity:" in block
    assert "note: did some stuff" in block

    # with_context helper
    prompt = "Do something cool."
    combined = with_context(prompt, block)
    assert block in combined
    assert "[Task]\nDo something cool." in combined


def test_project_name_and_listing(tmp_path: Path) -> None:
    # project_name fallback / custom cwd
    sub = tmp_path / "My Project 123!"
    sub.mkdir()
    name = project_name(sub)
    assert name == "My_Project_123_"

    # list_projects & check_project
    mem1 = Memory(tmp_path, "proj-a")
    mem1.add("note", "first")

    mem2 = Memory(tmp_path, "proj-b")
    mem2.add("decision", "second")

    projects = list_projects(tmp_path)
    assert len(projects) == 2
    # sorted by last activity/name desc, so proj-b or proj-a depending on timestamps or order.
    names = {p.name for p in projects}
    assert names == {"proj-a", "proj-b"}

    checked = check_project(tmp_path, "proj-a")
    assert checked == "proj-a"

    with pytest.raises(ValueError, match="bad project name"):
        check_project(tmp_path, "../evil")

    with pytest.raises(ValueError, match="no project named"):
        check_project(tmp_path, "nonexistent")

    # allowed set in check_project
    allowed_checked = check_project(tmp_path, "brand-new", allowed={"brand-new"})
    assert allowed_checked == "brand-new"
