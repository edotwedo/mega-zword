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


def test_seats_accepts_a_designation_without_a_hyphen():
    # Phil, 2026-10-21: "hyphen no hyphen it's him" - Harbor022 is a real designation.
    # A row the pattern does not match is dropped silently, which is how a whole seat
    # disappears from the respawn plan with no error to read.
    roster = """
| Designation | Worker | Role / lane | Notes |
| --- | --- | --- | --- |
| Harbor022 | Claude Code | review | |
| Briar-20 | Codex | edits | |
"""
    assert resume.seats(roster) == [("Harbor022", "claude"), ("Briar-20", "codex")]


def test_seats_maps_a_gemini_seat_to_the_binary_that_exists():
    # The roster word is "Gemini" but the binary on this PC is agy (Antigravity). Mapping it
    # to `gemini` made hive_resume.ps1 run a command that is not on PATH, so Forge-22's tab
    # died on open. Harbor022 caught it reviewing the first version, 2026-10-21.
    assert resume.seats("| Forge-22 | Gemini | advisor | |\n") == [("Forge-22", "agy")]


def test_seats_ignores_a_worker_it_does_not_know():
    assert resume.seats("| Sauna-Mech | ? | x | |\n") == []


def test_agy_resumes_the_newest_conversation_or_one_named_exactly():
    """MIKE-54 supplied the real forms on 2026-10-26: `agy -c` and `agy --conversation <id>`.
    An earlier version asserted the opposite - that agy had no resume form - because the flag
    list was wrong, not because agy lacks one. A blank seat restored as "fresh" was the symptom."""
    assert "agy" in resume.HAS_RECENT_FORM
    assert resume.resume_args("agy", "/x", None) == ["-c"]
    assert resume.resume_args("agy", "/x", "69bf406f-0726-46de-808b-8f1acdc67930") == \
        ["--conversation", "69bf406f-0726-46de-808b-8f1acdc67930"]


def test_agy_session_is_the_newest_conversation_db(tmp_path):
    """agy keeps one <conversation-id>.db per conversation in a single global folder, so unlike
    the other CLIs its newest transcript is not scoped to a working directory."""
    import os
    folder = tmp_path / "conversations"
    folder.mkdir(parents=True)
    older = folder / "0659f7d9-f15c-4de9-b951-6b341ed50fff.db"
    older.write_text("{}", encoding="utf-8")
    newest = folder / "69bf406f-0726-46de-808b-8f1acdc67930.db"
    newest.write_text("{}", encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newest, (2, 2))
    assert resume.agy_session("/anywhere", folder) == "69bf406f-0726-46de-808b-8f1acdc67930"
    assert resume.agy_session("/anywhere", tmp_path / "nope") is None


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


def test_seats_maps_a_worker_named_plain_claude():
    """The roster's Worker column says "Claude". The map knew only the literal "Claude
    Code", so the row was dropped from the respawn plan silently - the same disappearing-seat
    bug Harbor022 hit from the other direction (2026-10-26)."""
    assert resume.seats("| Harbor022 | Claude | review | |\n") == [("Harbor022", "claude")]
    # A parenthetical names the lane, not a different CLI, so the row still counts.
    assert resume.seats("| Harbor022 | Claude (review) | review | |\n") == [("Harbor022", "claude")]


def test_seats_skips_a_cloud_seat_with_no_local_tab():
    """Tern-25 and Vesper-25 run in a browser ("Claude (cloud)"), so there is no window on
    this machine to respawn. Dropping them is deliberate - unlike an unparsed row, there is
    nothing local the plan could launch."""
    roster = "| Tern-25 | Claude (cloud) | guard | |\n| Harbor022 | Claude | review | |\n"
    assert resume.seats(roster) == [("Harbor022", "claude")]


def test_a_designation_with_no_digit_is_invisible_to_the_plan():
    """Documented behaviour, not a bug to fix here: DESIGNATION requires two digits so that a
    SPEC section like "B15" and prose like "Phase2:" are not read as seats. A roster row named
    "Patcher" therefore registers no claims and never appears in the respawn plan, which is the
    roster's documented designation shape ([A-Za-z]{3,}-?\\d{1,4}) being broken, not the parser."""
    assert resume.seats("| Patcher | Claude | review | |\n") == []


def test_cmdc_slug_drops_the_leading_separator_command_code_drops():
    """Verified on Linux 2026-10-26: /home/edotwedo/workspace/mega-zword is filed by Command
    Code as 'home-edotwedo-workspace-mega-zword', while Claude files the same directory as
    '-home-edotwedo-workspace-mega-zword'. cmdc_session kept the dash, so every cmdc seat on
    this machine reported "no session found" and was told to start fresh."""
    assert resume.cmdc_slug("/home/edotwedo/workspace/mega-zword") == \
        "home-edotwedo-workspace-mega-zword"
    assert resume.slug("/home/edotwedo/workspace/mega-zword") == \
        "-home-edotwedo-workspace-mega-zword"
    # A Windows drive letter is alphanumeric, so Windows behaviour is unchanged.
    assert resume.cmdc_slug(r"C:\Users\mrmar\mz-seats\cinder-21") == \
        "c--users-mrmar-mz-seats-cinder-21"


def test_cmdc_session_is_found_under_the_separator_less_folder(tmp_path):
    folder = tmp_path / "home-edotwedo-workspace-mega-zword"
    folder.mkdir(parents=True)
    (folder / "4cc21ea8-f8bb-4b47-ba7a-13bc4c49ed54.jsonl").write_text("{}", encoding="utf-8")
    assert resume.cmdc_session("/home/edotwedo/workspace/mega-zword", tmp_path) == \
        "4cc21ea8-f8bb-4b47-ba7a-13bc4c49ed54"


def test_cmdc_session_never_returns_a_checkpoints_file_as_a_session(tmp_path):
    """'<id>.checkpoints.jsonl' is a .jsonl beside '<id>.jsonl', and it is the newer of the
    two while a seat is working - so picking the newest file handed back '<id>.checkpoints'
    as a session id (measured on this machine, 2026-10-26)."""
    import os
    folder = tmp_path / resume.cmdc_slug("/proj")
    folder.mkdir(parents=True)
    transcript = folder / "aaaa1111-0000-4000-8000-000000000001.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    checkpoints = folder / "aaaa1111-0000-4000-8000-000000000001.checkpoints.jsonl"
    checkpoints.write_text("{}", encoding="utf-8")
    os.utime(transcript, (1, 1))
    os.utime(checkpoints, (2, 2))
    assert resume.cmdc_session("/proj", tmp_path) == "aaaa1111-0000-4000-8000-000000000001"
