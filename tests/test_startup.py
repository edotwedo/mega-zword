"""Startup has one shared deadline; no real meters, network or model calls."""

import importlib.util
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from megazword import cli, startup


def test_reads_only_usage_floor_and_ten_latest_messages_with_one_deadline():
    calls = []
    ticks = iter([0, 0, 4, 9])

    def run(cmd, timeout):
        calls.append((cmd[3:], timeout))
        return SimpleNamespace(returncode=0, stdout="readable", stderr="")

    text = startup.reading(run=run, clock=lambda: next(ticks))
    assert calls == [(["usage"], 10), (["floor"], 6), (["floor", "peek", "-n", "10"], 1)]
    assert "readable" in text
    assert "30s including cleanup" in text


def test_first_timeout_stops_the_batch_instead_of_retrying_or_reading_more():
    calls = []

    def hung(cmd, timeout):
        calls.append(timeout)
        raise subprocess.TimeoutExpired(cmd, timeout)

    text = startup.reading(run=hung, clock=lambda: 0)
    assert calls == [10]
    assert "timed out" in text and "no retry" in text


def test_exhausted_shared_budget_never_starts_another_command():
    ticks = iter([0, 0, 11])
    calls = []

    def run(cmd, timeout):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="usage", stderr="")

    text = startup.reading(run=run, clock=lambda: next(ticks))
    assert len(calls) == 1
    assert "time budget exhausted" in text


def test_callers_cannot_extend_the_hard_read_deadline():
    seen = []

    def run(cmd, timeout):
        seen.append(timeout)
        raise subprocess.TimeoutExpired(cmd, timeout)

    startup.reading(timeout=900, run=run, clock=lambda: 0)
    assert seen == [10]


def test_zero_budget_does_not_start_any_process():
    def run(*args, **kwargs):
        raise AssertionError("zero budget started a child")

    assert "budget exhausted" in startup.reading(timeout=0, run=run, clock=lambda: 0)


def test_failed_commands_are_not_reported_as_live_readings_or_dumped():
    def run(cmd, timeout):
        return SimpleNamespace(returncode=1, stdout="PRIVATE PARTIAL", stderr="PRIVATE ERROR")

    text = startup.reading(run=run, clock=lambda: 0)
    assert text.count("unavailable (exit 1; no retry)") == 3
    assert "PRIVATE" not in text


def test_output_is_bounded_even_when_a_command_prints_history():
    def run(cmd, timeout):
        return SimpleNamespace(returncode=0, stdout=("x" * 200 + "\n") * 5000, stderr="")

    assert len(startup.reading(run=run, clock=lambda: 0)) < 9500


def test_real_sleeping_child_is_terminated_not_left_holding_the_pipes():
    # The real timeout path, but only a local sleeping Python: no CLI, meter or API.
    def sleeping_child(_cmd, timeout):
        return startup.run_quick([sys.executable, "-c", "import time; time.sleep(60)"], timeout)

    started = time.monotonic()
    text = startup.reading(timeout=0.15, run=sleeping_child)
    assert time.monotonic() - started < startup.MAX_SECONDS
    assert "timed out" in text


def test_startup_cli_does_not_run_tests_or_open_a_browser(monkeypatch, capsys):
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *_: (_ for _ in ()).throw(AssertionError("browser opened")))
    monkeypatch.setattr(startup, "reading", lambda: "bounded fake readings")
    assert cli.main(["startup"]) == 0
    assert capsys.readouterr().out.strip() == "bounded fake readings"


def test_usage_hook_uses_one_bounded_startup_call(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("usage_hook", root / ".claude/hooks/usage_check.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    monkeypatch.setattr(hook, "find_megazword", lambda: "fake-megazword")
    calls = []
    monkeypatch.setattr(hook, "run", lambda cmd, timeout: calls.append((cmd, timeout)) or "fake readings")
    assert hook.reading() == "fake readings"
    assert calls == [(["fake-megazword", "startup"], 35)]


def test_launcher_uses_bounded_startup_and_keeps_the_live_room_tools():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts/hive_up.ps1").read_text(encoding="utf-8")
    assert "& $mz startup" in script
    assert "& $mz floor introduce" not in script
    assert "take the next unclaimed file" not in script
    assert "hive_say" in script
