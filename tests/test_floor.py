"""Tests for Hive floor seats, readiness, and local snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path

import pytest

from megazword import floor
from megazword.backends import Backend


@dataclass
class FakeBackend(Backend):
    available_flag: bool = True

    def available(self) -> bool:
        return self.available_flag

    def _run(self, prompt: str) -> str:
        raise AssertionError("Floor tests must never run a model")


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("name,kind", [("claude", "cli"), ("groq", "http")])
@pytest.mark.parametrize("available", [True, False])
def test_roster_seated_or_empty(name, kind, available):
    seats = floor.roster(
        {name: FakeBackend(name, available_flag=available)}, now=NOW
    )
    by_name = {seat.name: seat for seat in seats}

    assert len(seats) == len(floor.CLI_SEATS) + len(floor.HTTP_SEATS)
    assert set(by_name) == set(floor.CLI_SEATS + floor.HTTP_SEATS)
    assert by_name[name].kind == kind
    assert by_name[name].status == ("seated" if available else "empty")
    assert by_name[name].until is None
    assert all(seat.status == "empty" for seat in seats if seat.name != name)


@pytest.mark.parametrize("name", ["codex", "cloudflare"])
@pytest.mark.parametrize("available", [True, False, None])
def test_roster_future_out_until_overrides_availability(name, available):
    until = NOW + timedelta(hours=2)
    backends = (
        {} if available is None
        else {name: FakeBackend(name, available_flag=available)}
    )
    seats = floor.roster(backends, out_until={name: until}, now=NOW)
    seat = next(seat for seat in seats if seat.name == name)

    assert seat.status == "out"
    assert seat.until == until


@pytest.mark.parametrize("available", [True, False])
@pytest.mark.parametrize("offset", [timedelta(0), timedelta(seconds=-1)])
def test_roster_expired_out_until_uses_availability(available, offset):
    seats = floor.roster(
        {"grok": FakeBackend("grok", available_flag=available)},
        out_until={"grok": NOW + offset},
        now=NOW,
    )
    seat = next(seat for seat in seats if seat.name == "grok")

    assert seat.status == ("seated" if available else "empty")
    assert seat.until is None


@pytest.mark.parametrize("statuses", [
    s for s in product(("seated", "out"), repeat=3) if "seated" in s
])
def test_ready_when_required_cli_seated_or_out(statuses):
    seats = [
        floor.Seat(name, "cli", status)
        for name, status in zip(("claude", "codex", "grok"), statuses)
    ]
    seats.append(floor.Seat("gemini", "cli", "empty"))
    seats.append(floor.Seat("groq", "http", "empty"))

    assert floor.ready(seats) is True


@pytest.mark.parametrize("empty_name", ["claude", "codex", "grok"])
def test_ready_false_when_required_cli_empty(empty_name):
    seats = [
        floor.Seat(name, "cli", "empty" if name == empty_name else "seated")
        for name in ("claude", "codex", "grok")
    ]
    seats.append(floor.Seat("groq", "http", "seated"))

    assert floor.ready(seats) is False


def test_ready_false_when_required_cli_all_out():
    """B7: all three out means nobody is on the floor, even with HTTP seats up."""
    seats = [floor.Seat(name, "cli", "out") for name in ("claude", "codex", "grok")]
    seats.append(floor.Seat("gemini", "cli", "seated"))
    seats.append(floor.Seat("groq", "http", "seated"))

    assert floor.ready(seats) is False


@pytest.mark.parametrize("backends", [{}, {
    name: FakeBackend(name) for name in floor.CLI_SEATS + floor.HTTP_SEATS
}])
def test_introduce_text_has_no_mentions(backends):
    seats = floor.roster(backends, out_until={"grok": NOW + timedelta(hours=2)}, now=NOW)

    text = floor.introduce_text(seats)

    assert "@" not in text
    assert "Out: grok." in text
    assert "Wait here for Phil" in text


@pytest.mark.parametrize("codex_available", [True, False])
def test_save_snapshot_writes_floor_json(tmp_path, codex_available):
    until = NOW + timedelta(hours=2)
    seats = floor.roster(
        {
            "claude": FakeBackend("claude"),
            "codex": FakeBackend("codex", available_flag=codex_available),
            "groq": FakeBackend("groq", trains_on_data=True),
        },
        out_until={"grok": until},
        now=NOW,
    )
    home = tmp_path / "nested" / "home"

    path = floor.save_snapshot(seats, home=home)

    assert path == home / "floor.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready"] is codex_available
    saved = {seat["name"]: seat for seat in payload["seats"]}
    assert len(payload["seats"]) == len(seats)
    assert set(saved) == {seat.name for seat in seats}
    assert saved["grok"] == {
        "name": "grok", "kind": "cli", "status": "out",
        "until": until.isoformat(), "trains_on_data": False,
    }
    assert saved["codex"]["status"] == ("seated" if codex_available else "empty")
    assert saved["claude"]["until"] is None
    assert saved["groq"]["kind"] == "http"
    assert saved["groq"]["trains_on_data"] is True


def _seats(**statuses):
    kinds = {name: "cli" for name in floor.CLI_SEATS}
    kinds.update({name: "http" for name in floor.HTTP_SEATS})
    return [floor.Seat(name, kind, statuses.get(name.replace("-", "_"), "empty"))
            for name, kind in kinds.items()]


def test_suggest_bulk_prefers_groq_then_cloudflare_skipping_out_and_cli():
    seats = _seats(claude="seated", groq="out", mistral="seated", cloudflare="seated")
    assert floor.suggest_seat("bulk", seats) == "cloudflare"
    seats = _seats(claude="seated", groq="seated", mistral="seated")
    assert floor.suggest_seat("bulk", seats) == "groq"
    assert floor.suggest_seat("bulk", _seats(claude="seated")) is None


def test_suggest_edit_prefers_codex_then_claude():
    assert floor.suggest_seat("edit", _seats(codex="seated", claude="seated")) == "codex"
    assert floor.suggest_seat("edit", _seats(codex="out", claude="seated")) == "claude"
    assert floor.suggest_seat("edit", _seats(grok="seated", groq="seated")) is None


def test_suggest_decide_prefers_claude_grok_codex():
    assert floor.suggest_seat("decide", _seats(claude="seated", grok="seated")) == "claude"
    assert floor.suggest_seat("decide", _seats(claude="out", grok="seated")) == "grok"
    assert floor.suggest_seat("decide", _seats(claude="empty", codex="seated")) == "codex"


def test_suggest_review_skips_empty_and_out():
    assert floor.suggest_seat("review", _seats(claude="out", grok="empty",
                                               codex="seated")) == "codex"
    assert floor.suggest_seat("review", _seats(groq="seated")) is None


def test_floor_suggest_missing_kind_exits_2(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: tmp_path / "floor.json")
    out: list[str] = []
    args = SimpleNamespace(action="suggest", kind=None, room=None)
    assert floor.command(args, {}, SimpleNamespace(out_until={}), write=out.append) == 2
    assert out == ["Usage: megazword floor suggest bulk|edit|decide|review"]


def test_floor_suggest_bulk_without_seated_http_prints_no_seat(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: tmp_path / "floor.json")
    backends = {name: FakeBackend(name) for name in floor.CLI_SEATS}
    backends.update({name: FakeBackend(name, available_flag=False) for name in floor.HTTP_SEATS})
    out: list[str] = []
    args = SimpleNamespace(action="suggest", kind="bulk", room=None)
    assert floor.command(args, backends, SimpleNamespace(out_until={}), write=out.append) == 1
    assert out == ["(no seat)"]


def test_floor_suggest_command_prints_name(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: tmp_path / "floor.json")
    backends = {"groq": FakeBackend("groq"), "claude": FakeBackend("claude")}
    cfg = SimpleNamespace(out_until={})
    out: list[str] = []
    args = SimpleNamespace(action="suggest", kind="bulk", room=None)
    assert floor.command(args, backends, cfg, write=out.append) == 0
    assert out == ["groq"]


def _log(path, *records):
    with path.open("a", encoding="utf-8") as f:
        for backend, ok, rejected in records:
            f.write(json.dumps({"time": "2026-10-13T02:00:00+00:00", "backend": backend,
                                "ok": ok, "rejected": rejected}) + "\n")


def test_auth_failed_uses_latest_run_per_backend(tmp_path):
    log = tmp_path / "log.jsonl"
    _log(log,
         ("groq", False, "failed: API HTTP error 403: forbidden (auth rejected, check the API key or model access)"),
         ("mistral", False, "failed: API HTTP error 401: unauthorized (auth failed, check the API key)"),
         ("mistral", True, None),  # fixed since: latest run wins
         ("zai", False, "failed: API connection failed: unable to connect (network or DNS)"),
         ("claude", False, "failed: Error: Not logged in. Please run /login"),
         ("codex", False, "too short (mentions 401)"))  # judge rejection, not a failed call
    assert floor.auth_failed(log) == {"groq", "claude"}
    assert floor.auth_failed(tmp_path / "missing.jsonl") == set()
    assert floor.auth_failed(None) == set()


def test_suggest_skips_auth_failed_without_marking_out(tmp_path):
    seats = _seats(claude="seated", grok="seated", groq="seated", mistral="seated")
    assert floor.suggest_seat("bulk", seats, {"groq"}) == "mistral"
    assert floor.suggest_seat("decide", seats, {"claude"}) == "grok"
    assert floor.suggest_seat("bulk", seats, {"groq", "mistral"}) is None
    assert {s.name: s.status for s in seats}["groq"] == "seated"


def test_floor_suggest_command_skips_groq_after_403(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: tmp_path / "floor.json")
    log = tmp_path / "log.jsonl"
    _log(log, ("groq", False, "failed: API HTTP error 403: forbidden (auth rejected, check the API key or model access)"))
    backends = {"groq": FakeBackend("groq"), "mistral": FakeBackend("mistral")}
    cfg = SimpleNamespace(out_until={}, log_path=log)
    out: list[str] = []
    args = SimpleNamespace(action="suggest", kind="bulk", room=None)
    assert floor.command(args, backends, cfg, write=out.append) == 0
    assert out == ["mistral"]
    assert cfg.out_until == {}


def test_peek_and_wait_share_the_hive_log(tmp_path, monkeypatch):
    from megazword import room
    monkeypatch.setattr(floor, "sleep", lambda _s: None)
    room.append_message("hive", "phil", "seat up", home=tmp_path)
    assert "[phil] seat up" in floor.peek_text("hive", n=5, home=tmp_path)
    already = floor.wait_for("hive", home=tmp_path, after=0, timeout=0, pause=0)
    assert len(already) == 1
    none = floor.wait_for("hive", home=tmp_path, after=1, timeout=0, pause=0)
    assert none == []
    assert floor.peek_text("hive", n=5, home=tmp_path).endswith("\n(after=1)")


def test_floor_wait_command_after_catches_missed_message(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from megazword import room
    monkeypatch.setattr(room.config, "HOME", tmp_path)
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: tmp_path / "floor.json")
    monkeypatch.setattr(floor, "sleep", lambda _s: pytest.fail("must not block"))
    room.append_message("hive", "phil", "seen")
    room.append_message("hive", "quill-12", "missed")
    cfg = SimpleNamespace(out_until={})
    out: list[str] = []
    args = SimpleNamespace(action="wait", room=None, timeout=0.001, after=1)
    assert floor.command(args, {}, cfg, write=out.append) == 0
    assert out == ["[quill-12] missed\n(after=2)"]
    out.clear()
    args.after = 2
    monkeypatch.setattr(floor, "monotonic", iter([0.0, 1.0]).__next__)
    assert floor.command(args, {}, cfg, write=out.append) == 1
    assert out == ["(no new hive message)\n(after=2)"]


def test_floor_peek_n0_and_wait_timeout0_are_not_defaults(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from megazword import room
    monkeypatch.setattr(room.config, "HOME", tmp_path)
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: tmp_path / "floor.json")
    monkeypatch.setattr(floor, "sleep", lambda _s: pytest.fail("timeout 0 must not block"))
    room.append_message("hive", "phil", "one")
    room.append_message("hive", "phil", "two")
    cfg = SimpleNamespace(out_until={})
    out: list[str] = []
    assert floor.command(SimpleNamespace(action="peek", room=None, n=0), {}, cfg,
                         write=out.append) == 0
    assert out == ["(after=2)"]
    out.clear()
    args = SimpleNamespace(action="wait", room=None, timeout=0, after=None)
    assert floor.command(args, {}, cfg, write=out.append) == 1
    assert out == ["(no new hive message)\n(after=2)"]


def test_floor_snapshot_only_on_status_and_introduce(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from megazword import room
    monkeypatch.setattr(room.config, "HOME", tmp_path)
    monkeypatch.setattr(floor, "sleep", lambda _s: None)
    saved = []
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: saved.append(1))
    cfg = SimpleNamespace(out_until={})
    for action in ("peek", "wait", "suggest"):
        args = SimpleNamespace(action=action, room=None, n=None, timeout=0, after=None,
                               kind="bulk")
        floor.command(args, {}, cfg, write=lambda s: None)
    assert saved == []
    for action in ("status", "introduce"):
        floor.command(SimpleNamespace(action=action, room=None), {}, cfg, write=lambda s: None)
    assert saved == [1, 1]


def test_floor_bad_room_is_one_line_exit_2(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: pytest.fail("no snapshot"))
    cfg = SimpleNamespace(out_until={})
    for action in ("peek", "wait", "introduce"):
        out: list[str] = []
        args = SimpleNamespace(action=action, room="../x", n=None, timeout=0, after=None)
        assert floor.command(args, {}, cfg, write=out.append) == 2
        assert len(out) == 1 and "\n" not in out[0]
        assert out[0].startswith("floor: room name '../x'")


def test_hear_and_format_heard(tmp_path, monkeypatch):
    monkeypatch.setattr(floor.config, "HOME", tmp_path)
    now = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)
    assert "none" in floor.format_heard(home=tmp_path, now=now)
    floor.hear("grok", home=tmp_path, now=now)
    floor.hear("phil", home=tmp_path, now=now)  # ignored
    floor.hear("bot", home=tmp_path, now=now)
    later = now + timedelta(seconds=9)
    text = floor.format_heard(home=tmp_path, now=later)
    assert "grok 9s ago" in text
    assert "phil" not in text
    roster = floor.format_roster([])
    assert "Heard in Hive MCP" in roster


def test_hive_up_sets_seat_env():
    script = (Path(__file__).parents[1] / "scripts" / "hive_up.ps1").read_text(encoding="utf-8")
    assert "MEGAZWORD_SEAT" in script
    assert "hive_say" in script
