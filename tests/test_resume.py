"""Respawn: one tab per seat, under its own name, with its conversation back.

Phil, 2026-10-20: "the point of the respawn was to RESPAWN - resume everything and retain
the seat." These cover finding each seat's directory and its newest session, which is the
half neither launcher did. The real store layouts they read are verified against this
machine, so the fakes here mirror them exactly.
"""

import io
import json

from megazword import config, resume

ROSTER = """
# Hive roster

| Designation | Worker | Role / lane | Notes |
| --- | --- | --- | --- |
| Juniper-16 | Claude Code | owner | |
| Gauge-18 | Grok | advice | |
| Lumen-20 | Command Code | android | |
| Cinder-21 | Command Code | **Conductor** | |
| Sauna-Mech | ? | confirm with Phil | |
"""


def test_slug_matches_how_the_clis_key_their_project_folders():
    assert resume.slug(r"C:\Users\mrmar") == "C--Users-mrmar"
    assert resume.slug(r"C:\Users\mrmar\mz-seats\cinder-21") == "C--Users-mrmar-mz-seats-cinder-21"


def test_seats_reads_the_roster_table_and_maps_workers_to_clis():
    assert resume.seats(ROSTER) == [
        ("Juniper-16", "claude"),
        ("Gauge-18", "grok"),
        ("Lumen-20", "cmdc"),
        ("Cinder-21", "cmdc"),
    ]


def test_seats_ignores_a_worker_it_does_not_know():
    assert resume.seats("| Sauna-Mech | ? | x | |\n") == []


def test_claude_session_is_the_newest_transcript_for_that_directory(tmp_path):
    folder = tmp_path / resume.slug(r"C:\Users\mrmar\mz-seats\beacon-17")
    folder.mkdir(parents=True)
    (folder / "older.jsonl").write_text("{}", encoding="utf-8")
    newest = folder / "0b2c1d4e-0000-4000-8000-000000000001.jsonl"
    newest.write_text("{}", encoding="utf-8")
    import os
    os.utime(folder / "older.jsonl", (1, 1))
    os.utime(newest, (2, 2))
    assert resume.claude_session(r"C:\Users\mrmar\mz-seats\beacon-17", tmp_path) == \
        "0b2c1d4e-0000-4000-8000-000000000001"


def test_claude_session_is_none_when_the_seat_never_ran(tmp_path):
    assert resume.claude_session(r"C:\nope", tmp_path) is None


def test_cmdc_session_uses_the_lowercased_project_folder(tmp_path):
    folder = tmp_path / resume.slug(r"C:\Users\mrmar\mz-seats\cinder-21").lower()
    folder.mkdir(parents=True)
    (folder / "4c1ea4b5-7d9d-41c1-9ccd-187670d193ba.jsonl").write_text("{}", encoding="utf-8")
    assert resume.cmdc_session(r"C:\Users\mrmar\mz-seats\cinder-21", tmp_path) == \
        "4c1ea4b5-7d9d-41c1-9ccd-187670d193ba"


def test_codex_session_is_matched_by_the_directory_recorded_inside(tmp_path):
    root = tmp_path / "sessions" / "2026" / "10" / "20"
    root.mkdir(parents=True)
    (root / "rollout-2026-10-20T14-21-16-01a15b30-9f70-73f2-9f96-296fc0325d4f.jsonl").write_text(
        json.dumps({"cwd": r"C:\Users\mrmar", "type": "session_meta"}) + "\n", encoding="utf-8")
    other = root / "rollout-2026-10-20T15-00-00-01a15b30-0000-7000-8000-000000000002.jsonl"
    other.write_text(json.dumps({"cwd": r"C:\somewhere\else"}) + "\n", encoding="utf-8")
    sessions = tmp_path / "sessions"
    assert resume.codex_session(r"C:\Users\mrmar", sessions) == \
        "01a15b30-9f70-73f2-9f96-296fc0325d4f"
    assert resume.codex_session(r"C:\nobody", sessions) is None


def test_claude_session_for_falls_back_to_a_folder_named_after_the_seat(tmp_path):
    """On 2026-10-20 Beacon-17's worktree existed but its transcript did not, because
    Claude had been started somewhere else - the folder name carried the seat instead."""
    folder = tmp_path / "C--Users-mrmar-mz-seats-beacon-17"
    folder.mkdir(parents=True)
    (folder / "aaaa1111-0000-4000-8000-000000000001.jsonl").write_text("{}", encoding="utf-8")
    # The seat's own directory has nothing, so only the designation can find it.
    assert resume.claude_session_for("Beacon-17", r"C:\elsewhere\beacon-17-scratch", tmp_path) == \
        "aaaa1111-0000-4000-8000-000000000001"


def test_resume_args_name_the_session_when_we_have_it():
    assert resume.resume_args("claude", "d", "abc") == ["--permission-mode", "acceptEdits", "--resume", "abc"]
    assert resume.resume_args("grok", "d", "abc") == ["--permission-mode", "acceptEdits", "--resume", "abc"]
    assert resume.resume_args("cmdc", "d", "abc") == ["-r", "abc"]
    assert resume.resume_args("codex", "d", "abc") == ["resume", "abc"]


def test_resume_args_fall_back_to_this_directory_not_a_stranger():
    """Every CLI has a "most recent in THIS directory" form. Starting a stranger when the
    seat's own directory has a conversation is the bug respawn was supposed to fix."""
    assert resume.resume_args("claude", "d", None) == ["--permission-mode", "acceptEdits", "-c"]
    assert resume.resume_args("grok", "d", None) == ["--permission-mode", "acceptEdits", "-c"]
    assert resume.resume_args("cmdc", "d", None) == ["-c"]
    assert resume.resume_args("codex", "d", None) == ["resume", "--last"]


def test_resume_args_fresh_resumes_nothing():
    assert resume.resume_args("claude", "d", "abc", fresh=True) == ["--permission-mode", "acceptEdits"]
    assert resume.resume_args("codex", "d", "abc", fresh=True) == []


def test_grok_session_is_keyed_by_the_url_encoded_directory(tmp_path):
    """~/.grok/sessions/<quoted-cwd>/<session-id>/chat_history.jsonl"""
    folder = tmp_path / resume.urllib.parse.quote(r"C:\Users\mrmar\mz-seats\gauge-18", safe="")
    session = folder / "01a15240-1fc1-7de2-ad1a-0a92d6c45786"
    session.mkdir(parents=True)
    (session / "chat_history.jsonl").write_text("{}", encoding="utf-8")
    assert resume.grok_session(r"C:\Users\mrmar\mz-seats\gauge-18", tmp_path) == \
        "01a15240-1fc1-7de2-ad1a-0a92d6c45786"
    assert resume.grok_session(r"C:\nobody", tmp_path) is None


def test_record_stdin_takes_what_a_launcher_handed_over(tmp_path, monkeypatch):
    """PowerShell collapses a one-element array to a bare object, so both shapes must work."""
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"designation": "Gauge-18", "cli": "grok", "dir": r"C:\mz-seats\gauge-18"})))
    assert resume.main(["--record-stdin"]) == 0
    assert resume.read_recorded(tmp_path)["gauge-18"]["dir"] == r"C:\mz-seats\gauge-18"

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([
        {"designation": "Cinder-21", "cli": "cmdc", "dir": "d"},
        {"designation": "", "cli": "x", "dir": "d"},
    ])))
    assert resume.main(["--record-stdin"]) == 0
    recorded = resume.read_recorded(tmp_path)
    assert recorded["cinder-21"]["cli"] == "cmdc"
    assert "" not in recorded, "an entry with no designation must be dropped"


def test_record_stdin_ignores_junk(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("{ not json"))
    assert resume.main(["--record-stdin"]) == 1


def test_plan_prefers_a_seat_worktree_and_falls_back_to_the_repo(tmp_path):
    seats = tmp_path / "mz-seats"
    (seats / "cinder-21").mkdir(parents=True)
    plan = resume.plan(ROSTER, seats, tmp_path / "mega-zword")
    by_seat = {entry["designation"]: entry for entry in plan}
    assert by_seat["Cinder-21"]["dir"] == str(seats / "cinder-21")
    # Juniper-16 has no worktree on this machine, so it must fall back rather than vanish.
    assert by_seat["Juniper-16"]["dir"] == str(tmp_path / "mega-zword")
    assert by_seat["Juniper-16"]["cli"] == "claude"


def test_record_remembers_where_a_seat_was_launched(tmp_path, monkeypatch):
    """The whole reason respawn never worked: nothing recorded which seat ran where."""
    monkeypatch.setattr(config, "HOME", tmp_path)
    resume.record([{"designation": "Juniper-16", "cli": "claude", "dir": r"C:\somewhere\else"}],
                  tmp_path)
    assert resume.read_recorded(tmp_path)["juniper-16"]["dir"] == r"C:\somewhere\else"


def test_a_recorded_launch_beats_the_directory_guess(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    seats = tmp_path / "mz-seats"
    (seats / "cinder-21").mkdir(parents=True)
    # Without a record, the guess is the worktree named after the seat.
    guess = {e["designation"]: e for e in resume.plan(ROSTER, seats, tmp_path / "repo", home=tmp_path)}
    assert guess["Cinder-21"]["dir"] == str(seats / "cinder-21")
    # With one, the seat is resumed where it actually ran.
    resume.record([{"designation": "Cinder-21", "cli": "cmdc",
                    "dir": str(tmp_path / "elsewhere")}], tmp_path)
    (tmp_path / "elsewhere").mkdir()
    recorded = {e["designation"]: e for e in resume.plan(ROSTER, seats, tmp_path / "repo", home=tmp_path)}
    assert recorded["Cinder-21"]["dir"] == str(tmp_path / "elsewhere")


def test_record_survives_a_corrupt_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    resume.registry_path(tmp_path).write_text("{ not json", encoding="utf-8")
    assert resume.read_recorded(tmp_path) == {}
    resume.record([{"designation": "Gauge-18", "cli": "grok", "dir": "d"}], tmp_path)
    assert resume.read_recorded(tmp_path)["gauge-18"]["cli"] == "grok"
