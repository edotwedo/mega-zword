"""Timeouts: a hung AI (and anything it started) is killed and reported."""

import sys
import time

from megazword import config
from megazword.backends import CLIBackend
from megazword.cli import main
from tests.test_cli import FakeBackend, rated

HANG = ("import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "time.sleep(60)")


def test_hung_cli_and_its_child_are_killed_quickly():
    b = CLIBackend("slow", exe=sys.executable, args=["-c", HANG], timeout=2)
    start = time.monotonic()
    r = b.run("ignored")
    assert not r.ok and "gave no answer within 2s" in r.error
    assert time.monotonic() - start < 20  # didn't wait on the grandchild's pipes


def test_timeouts_load_from_config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[timeouts]\nclaude = 900\ngrok = -1\ncodex = \"x\"\n")
    assert config.load(p).timeouts == {"claude": 900}


def test_execute_applies_per_ai_timeout_and_escalates(tmp_path, capsys):
    cfg = config.Config(log_path=tmp_path / "log.jsonl", timeouts={"slow": 1})
    cfg.route = {"easy": ["slow"], "medium": [], "hard": ["fast"]}
    slow = CLIBackend("slow", exe=sys.executable, args=["-c", HANG])
    backends = {"slow": slow, "fast": FakeBackend("fast", reply="f")}
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 0
    out = capsys.readouterr()
    assert slow.timeout == 1
    assert out.out.startswith("f: ") and "gave no answer within 1s" in out.err


def test_chat_survives_a_timeout(tmp_path):
    from megazword import chat
    cfg = config.Config(log_path=tmp_path / "log.jsonl", timeouts={"slow": 1})
    cfg.route = {"easy": ["slow"], "medium": [], "hard": []}
    backends = {"slow": CLIBackend("slow", exe=sys.executable, args=["-c", HANG])}
    lines = iter(["hello", "/quit"])
    written = []
    assert chat.run(backends, cfg, rated("easy"), dict,
                    read=lambda _p: next(lines), write=written.append) == 0


def test_dashboard_cancel_kills_the_ai_underneath():
    """The job's child (the AI CLI) keeps printing until it's dead."""
    from megazword.dashboard import Job
    tick = "import sys, time\nwhile True:\n    print('tick', flush=True); time.sleep(0.1)"
    parent = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {tick!r}]); "
              "time.sleep(60)")
    job = Job("j1", "t", [sys.executable, "-c", parent], "")
    deadline = time.monotonic() + 10
    while not job.out and time.monotonic() < deadline:
        time.sleep(0.1)
    assert job.out, "child never started"
    job.cancel()
    # The child holds the job's stdout open, and a job only reports done after
    # its output readers hit end-of-file, so "done" means the child is dead.
    deadline = time.monotonic() + 30
    while not job.view()["done"] and time.monotonic() < deadline:
        time.sleep(0.05)
    assert job.view()["done"], "the AI process kept running after cancel"
    assert "cancelled" in "".join(job.err)
