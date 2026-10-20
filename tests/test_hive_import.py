"""Hive import reads a fake repo folder; never the network."""

from megazword import config
from megazword.cli import main
from megazword.hive_import import parse_decisions, parse_handoff
from megazword.memory import Memory

DECISIONS = """# Decisions
## Decisions
- 2026-10-08: Phil's vocabulary: "yeet" means yes. Source: chat.
- 2026-10-04: **Budget** rule here. Source: BUDGET.md.
not a decision line
"""

OPEN = """# Handoff: phone runner
- **For:** grok
- **Status:** open
## The job
Run the local model
on the phone.
## Done when
- it runs
"""

DONE = OPEN.replace("open", "done 2026-10-08 by Rook").replace("phone runner", "finished")


def make_repo(tmp_path):
    repo = tmp_path / "workshop"
    (repo / "handoffs").mkdir(parents=True)
    (repo / "DECISIONS.md").write_text(DECISIONS, encoding="utf-8")
    (repo / "handoffs" / "a.md").write_text(OPEN, encoding="utf-8")
    (repo / "handoffs" / "b.md").write_text(DONE, encoding="utf-8")
    (repo / "handoffs" / "TEMPLATE.md").write_text(OPEN, encoding="utf-8")
    return repo


def test_parse_decisions_oldest_first_and_strips_bold():
    found = parse_decisions(DECISIONS)
    assert found[0] == ("2026-10-04", "Budget rule here. Source: BUDGET.md.")
    assert len(found) == 2


def test_parse_handoff_fields():
    h = parse_handoff("a.md", OPEN)
    assert (h.title, h.status, h.owner, h.job) == ("phone runner", "open", "grok",
                                                   "Run the local model on the phone.")
    assert parse_handoff("x.md", "no heading") is None


def test_import_is_idempotent_and_skips_done(tmp_path, capsys):
    repo = make_repo(tmp_path)
    assert main(["import-hive", str(repo)]) == 0
    assert main(["import-hive", str(repo)]) == 0  # second run adds nothing
    err = capsys.readouterr().err
    assert "imported 2 decisions and 1 open handoffs" in err
    assert "imported 0 decisions and 0 open handoffs" in err
    entries = Memory(config.HOME, "hive").entries()
    assert [e.kind for e in entries] == ["decision", "decision", "note"]
    assert entries[0].time.startswith("2026-10-04")
    assert "phone runner" in entries[2].text and "finished" not in entries[2].text


def test_import_rejects_non_hive_folder(tmp_path, capsys):
    assert main(["import-hive", str(tmp_path)]) == 2


def test_context_block_caps_decisions():
    mem = Memory(config.HOME, "cap")
    for i in range(30):
        mem.add("decision", f"rule {i:02d} " + "x" * 400, time=f"2026-10-{i % 28 + 1:02d}")
    block = mem.context_block(max_decisions=5, max_chars=50)
    assert block.count("- rule") == 5 and "..." in block
    assert len(block) < 600


def test_import_hive_end_to_end_is_rerun_safe_and_read_only(tmp_path):
    from megazword.hive_import import import_hive
    from megazword.memory import Memory
    repo = tmp_path / "workshop"
    (repo / "handoffs").mkdir(parents=True)
    (repo / "DECISIONS.md").write_bytes(
        "# Decisions\n- 2026-10-11: **Truth only.** Check sources.\n- 2026-10-01: Old call\n".encode()
        + b"- 2026-10-02: bad byte \xff here\n")
    (repo / "handoffs" / "a.md").write_text(
        "# Handoff: Build it\n- **For:** codex\n- **Status:** open\n\n## The job\nDo the thing.\n",
        encoding="utf-8")
    (repo / "handoffs" / "b.md").write_text("# Done one\n- **Status:** done 2026-10-01\n", encoding="utf-8")
    (repo / "handoffs" / "TEMPLATE.md").write_text("# T\n- **Status:** open\n", encoding="utf-8")
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    mem = Memory(tmp_path / "home", "workshop")

    assert import_hive(repo, mem) == (3, 1)
    assert import_hive(repo, mem) == (0, 0)  # second run adds nothing
    entries = mem.entries()
    decisions = [e for e in entries if e.kind == "decision"]
    assert decisions[0].text.startswith("2026-10-01") and decisions[0].time.startswith("2026-10-01")
    assert any("Truth only. Check sources." in e.text for e in decisions)
    note = next(e for e in entries if e.kind == "note")
    assert "Build it" in note.text and "for codex" in note.text and "Do the thing." in note.text
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()} == before
