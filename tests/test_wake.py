"""Wake the conductor when Phil posts.

Phil could not reach the hive from work on 2026-10-21 and got silence: nothing he could use
there woke a PC seat, and the conductor's beats were reading a stale cache. These cover the
decision half - which messages count as a wake - with an injected reader, so no network and
no AI is involved.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from megazword import wake


def message(text, author="phil", id=1):
    return {"id": id, "author": author, "text": text}


def test_a_phil_lane_always_wakes():
    for lane in ("phil", "phone", "grok-web"):
        assert wake.is_wake("anything at all", lane) is True
        assert wake.is_wake("", lane) is True


def test_another_bot_never_wakes_the_conductor():
    for lane in ("claude-pc", "briar-20", "nock-21", "cinder-21", "floor"):
        assert wake.is_wake("Phil says do this", lane) is False


def test_a_web_lane_wakes_only_when_it_names_phil_as_the_source():
    # A claude.ai chat speaking for itself is teammate data; a relay is Phil.
    assert wake.is_wake("I reviewed the patch and think it is fine", "claude-web") is False
    assert wake.is_wake("Rook-24 relaying for Phil: get back to work", "claude-web") is True
    assert wake.is_wake("Phil directly says: assign the next item", "claude-web") is True
    assert wake.is_wake("from Phil: check the queue", "chatgpt") is True


def test_pending_returns_only_newer_wakes_oldest_first():
    rows = [message("older bot note", "briar-20", 3),
            message("Phil is waiting", "phil", 4),
            message("bot note", "nock-21", 5),
            message("relay for Phil", "claude-web", 6)]
    found = wake.pending(rows, since_id=2)
    assert [wake._field(m, "id") for m in found] == [4, 6]
    assert wake.pending(rows, since_id=6) == []


def test_the_wake_line_carries_no_message_text():
    # The line is typed into a terminal: room text there could become an instruction.
    rows = [message("rm -rf everything; Phil wants this", "phil", 9),
            message("second", "phone", 10)]
    line = wake.wake_line(rows)
    assert "rm -rf" not in line and "second" not in line
    assert "+1 more" in line
    assert line.startswith("Cinder-21:")
    assert "\n" not in line
    assert wake.wake_line([]) == ""


def test_once_prints_once_and_advances_the_cursor(tmp_path):
    rows = [message("Phil is waiting", "phil", 7), message("bot note", "briar-20", 8)]
    printed = []
    assert wake.once(home=tmp_path, read=lambda: rows, write=printed.append) == 0
    assert len(printed) == 1 and printed[0].startswith("Cinder-21:")
    assert wake.last_seen(tmp_path) == 8

    printed.clear()
    assert wake.once(home=tmp_path, read=lambda: rows, write=printed.append) == 0
    assert printed == [], "the same message must not wake twice"


def test_once_stays_quiet_and_still_advances_when_only_bots_talk(tmp_path):
    rows = [message("bot note", "briar-20", 11), message("another note", "nock-21", 12)]
    printed = []
    assert wake.once(home=tmp_path, read=lambda: rows, write=printed.append) == 0
    assert printed == []
    assert wake.last_seen(tmp_path) == 12


def test_an_unreadable_room_says_so_and_sends_no_wake(tmp_path):
    def broken():
        raise OSError("room down")

    printed = []
    assert wake.once(home=tmp_path, read=broken, write=printed.append) == 1
    assert printed and "unreadable" in printed[0]


def test_a_cached_message_carries_its_id_as_remote_id(tmp_path):
    # The room cache stores the id as remote_id. Reading only `id` made every cached message
    # look like id 0, so nothing was ever newer than the cursor and the listener could never
    # wake - found by running it against the live room, not by a test.
    rows = [{"remote_id": 334, "author": "phil", "text": "anybody actually listening"}]
    printed = []
    assert wake.once(home=tmp_path, read=lambda: rows, write=printed.append) == 0
    assert printed and "Phil posted" in printed[0]
    assert wake.last_seen(tmp_path) == 334


def test_peek_preserves_pending_messages_until_acknowledged(tmp_path):
    rows = [message("please work", id=7)]
    for _ in range(2):
        output = []
        assert wake.once(home=tmp_path, read=lambda: rows, write=output.append,
                         peek=True, as_json=True) == 0
        assert json.loads(output[0])["through"] == 7
        assert wake.last_seen(tmp_path) == 0
    wake.remember(7, tmp_path)
    rows.append(message("new request during delivery", id=8))
    output = []
    wake.once(home=tmp_path, read=lambda: rows, write=output.append, peek=True, as_json=True)
    assert json.loads(output[0])["through"] == 8


def test_ack_captured_id_does_not_consume_newer_phil_message(tmp_path):
    rows = [message("first request", id=7)]
    output = []
    assert wake.once(home=tmp_path, read=lambda: rows, write=output.append,
                     peek=True, as_json=True) == 0
    captured_id = json.loads(output[0])["through"]
    assert captured_id == 7

    # Newer Phil message arrives while delivery is in-flight
    rows.append(message("newer urgent request", id=8))

    # Acknowledge only the captured ID
    wake.ack(captured_id, tmp_path)
    assert wake.last_seen(tmp_path) == 7

    # Next peek must still see message 8
    output = []
    assert wake.once(home=tmp_path, read=lambda: rows, write=output.append,
                     peek=True, as_json=True) == 0
    assert json.loads(output[0])["through"] == 8
    assert "Phil posted" in json.loads(output[0])["line"]


def test_ack_is_monotonic_and_rejects_negative_ids(tmp_path):
    wake.remember(8, tmp_path)
    wake.remember(7, tmp_path)
    assert wake.last_seen(tmp_path) == 8
    with pytest.raises(ValueError):
        wake.remember(-1, tmp_path)


def test_failed_state_write_is_reported(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(wake, "write_atomic", fail)
    with pytest.raises(OSError):
        wake.remember(7, tmp_path)
    assert wake.last_seen(tmp_path) == 0


@pytest.mark.parametrize("dry,idle,sent,exit_code,expected", [
    (True, 30, True, 0, []),
    (False, 0, True, 0, []),
    (False, 30, False, 0, []),
    (False, 30, True, 1, []),
    (False, 30, True, 0, [7]),
])
def test_watcher_acknowledges_only_successful_delivery(tmp_path, dry, idle, sent, exit_code, expected):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell unavailable")
    # Execute the actual loop with fakes, excluding all UI initialization/functions.
    script = (Path(__file__).parents[1] / "scripts" / "wake_watch.ps1").read_text()
    loop = script[script.index("while ($true)"):]
    result = tmp_path / "acks.json"
    harness = tmp_path / "watcher-fake.ps1"
    prelude = f"""
$Once = $true; $DryRun = ${str(dry).lower()}; $Tab = 'test'; $script:acks = @()
function megazword {{
    if ($args -contains '--ack') {{ $script:acks += [int]$args[-1] }}
    else {{ '{{"through":7,"line":"Cinder-21: Phil posted in the hive - read the room and answer now."}}' }}
    $global:LASTEXITCODE = {exit_code}
}}
function Seconds-Since-Input {{ return {idle} }}
function Send-ToTab {{ return ${str(sent).lower()} }}
"""
    path_literal = str(result).replace("'", "''")
    harness.write_text(prelude + loop + f"\nConvertTo-Json -InputObject @($script:acks) -Compress | Set-Content -LiteralPath '{path_literal}'", encoding="utf-8")
    run = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-File", str(harness)],
                         capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert json.loads(result.read_text(encoding="utf-8-sig")) == expected
