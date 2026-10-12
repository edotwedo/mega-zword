"""Usage-limit errors are spotted and the AI is marked out until reset."""

from datetime import datetime, timedelta

import pytest

from megazword import config
from megazword.cli import main
from megazword.limits import FALLBACK, detect
from tests.test_cli import FakeBackend, rated

NOW = datetime(2026, 10, 11, 1, 30).astimezone()
CODEX = ("ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
         "visit https://chatgpt.com/settings/usage to purchase more credits or try again at 2:39 AM.")


@pytest.mark.parametrize("text,expect", [
    (CODEX, NOW.replace(hour=2, minute=39, second=0, microsecond=0)),
    ("You've hit your usage limit ... try again at 1:00 AM.",  # already passed today
     NOW.replace(hour=1, minute=0, second=0, microsecond=0) + timedelta(days=1)),
    ("You've hit your usage limit. Try again at Oct 17th, 2026 9:39 PM.",
     NOW.replace(month=10, day=17, hour=21, minute=39, second=0, microsecond=0)),
    ("5-hour limit reached ∙ resets 3am", NOW.replace(hour=3, minute=0, second=0, microsecond=0)),
    ("Rate limit exceeded, try again in 2 hours 15 minutes", NOW + timedelta(hours=2, minutes=15)),
])
def test_reset_times(text, expect):
    hit = detect(text, NOW)
    assert hit and hit.exact and hit.until == expect


def test_epoch_form():
    hit = detect("Claude AI usage limit reached|1792000000", NOW)
    assert hit.exact and int(hit.until.timestamp()) == 1792000000


def test_limit_without_time_falls_back():
    hit = detect("quota exceeded", NOW)
    assert hit and not hit.exact and hit.until == NOW + FALLBACK


@pytest.mark.parametrize("text", ["exited with code 1: file not found",
                                  "gave no answer within 600s", ""])
def test_ordinary_errors_are_not_limits(text):
    assert detect(text, NOW) is None


@pytest.fixture
def cfg(tmp_path):
    c = config.Config(log_path=tmp_path / "log.jsonl")
    c.route = {"easy": ["codex", "claude"], "medium": [], "hard": []}
    return c


def test_run_marks_out_and_moves_on(cfg, capsys):
    codex = FakeBackend("codex", fail=True)
    codex._run = lambda p: (_ for _ in ()).throw(RuntimeError(CODEX))
    backends = {"codex": codex, "claude": FakeBackend("claude", reply="c")}
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 0
    err = capsys.readouterr().err
    assert "codex hit its usage limit; marked out until" in err
    saved = config.load()
    assert "codex" in saved.out_until and "codex" in saved.out_now()
    # Next run skips codex without trying it.
    called = []
    codex._run = lambda p: called.append(p) or "x"
    assert main(["run", "hi"], backends, config.load(), rated("easy"), dict) == 0
    assert not called


def test_agy_quota_message_reads_run_together_reset():
    # Captured live from agy on Phil's PC, 2026-10-11 (Gemini weekly quota used up).
    text = ("error: Individual quota reached. Please upgrade your subscription to increase "
            "your limits. Resets in 165h2m5s.\nAGY_ERROR: {\"short_error\":\"RESOURCE_EXHAUSTED "
            "(code 429): Individual quota reached.\"}")
    now = datetime(2026, 10, 11, 19, 0).astimezone()
    hit = detect(text, now)
    assert hit and hit.exact
    assert hit.until == now + timedelta(hours=165, minutes=2)
