"""Tests use fake backends and a fake rater so they never spend paid usage."""

import json
from dataclasses import dataclass

import pytest

from megazword import config
from megazword.backends import Backend, CLIBackend
from megazword.cli import main
from megazword.rater import Rating, rule_rate


@dataclass
class FakeBackend(Backend):
    reply: str = "hello"
    fail: bool = False
    installed: bool = True

    def available(self) -> bool:
        return self.installed

    def _run(self, prompt: str) -> str:
        if self.fail:
            raise RuntimeError("boom")
        return f"{self.reply}: {prompt}"


@pytest.fixture
def cfg(tmp_path):
    return config.Config(
        route={"easy": ["cheap"], "medium": ["cheap"], "hard": ["gone", "strong"]},
        log_path=tmp_path / "log.jsonl",
    )


def fakes(**kw):
    return {"fake": FakeBackend("fake", **kw)}


def rated(level):
    return lambda prompt: Rating(level, "test", "fake")


def test_forced_model_prints_answer(capsys, cfg):
    assert main(["run", "hi there", "-m", "fake"], fakes(), cfg) == 0
    out = capsys.readouterr()
    assert out.out.strip().endswith("hi there") and "one-shot" in out.out
    assert "using fake" in out.err


def test_unknown_model(capsys, cfg):
    assert main(["run", "hi", "-m", "nope"], fakes(), cfg) == 2
    assert "Choose from: fake" in capsys.readouterr().err


def test_failure_is_reported_not_raised(capsys, cfg):
    assert main(["run", "hi", "-m", "fake"], fakes(fail=True), cfg) == 1
    assert "boom" in capsys.readouterr().err  # shown via the rejection reason


def test_auto_pick_skips_missing_and_logs(capsys, cfg):
    backends = {
        "cheap": FakeBackend("cheap", reply="c"),
        "gone": FakeBackend("gone", installed=False),
        "strong": FakeBackend("strong", reply="s"),
    }
    assert main(["run", "design a system"], backends, cfg, rated("hard"), dict) == 0
    out = capsys.readouterr()
    assert out.out.strip().endswith("design a system") and out.out.startswith("s: ")
    assert "rated hard" in out.err and "using strong" in out.err
    entry = json.loads(cfg.log_path.read_text().splitlines()[-1])
    assert entry["backend"] == "strong" and entry["rating"] == "hard" and entry["ok"]


def test_auto_pick_with_nothing_installed(capsys, cfg):
    assert main(["run", "hi"], {}, cfg, rated("easy"), dict) == 1
    assert "no installed AI" in capsys.readouterr().err


def test_backends_lists_availability(capsys, cfg):
    missing = CLIBackend("ghost", exe="definitely-not-a-real-cli-xyz")
    assert main(["backends"], {"ghost": missing}, cfg) == 0
    out = capsys.readouterr().out
    assert "ghost" in out and "not found" in out


def test_init_writes_only_installed_backends_and_refuses_overwrite(capsys, cfg, monkeypatch):
    monkeypatch.setattr(config, "HOME", cfg.log_path.parent / "home")
    backends = {"claude": FakeBackend("claude"),
                "codex": FakeBackend("codex", installed=False)}
    from megazword import ollama
    monkeypatch.setattr(ollama, "reachable", lambda: False)
    assert main(["init"], backends, cfg) == 0
    path = config.HOME / "config.toml"
    loaded = config.load(path)
    assert loaded.route == {"easy": ["claude"], "medium": ["claude"],
                            "hard": ["claude"]}
    assert "codex" not in path.read_text()
    assert main(["init"], backends, cfg) == 1
    assert "use --force" in capsys.readouterr().err


def test_prompt_placeholder_goes_in_args():
    b = CLIBackend("x", exe="python", args=["-c", "{prompt}"])
    cmd, stdin = b._command("print(1)")
    assert cmd[-1] == "print(1)" and stdin is None


def test_prompt_goes_to_stdin_without_placeholder():
    b = CLIBackend("x", exe="python", args=["-"])
    cmd, stdin = b._command("print(1)")
    assert stdin == "print(1)" and "print(1)" not in cmd


@pytest.mark.parametrize("prompt,level", [
    ("what's 2+2", "easy"),
    ("refactor the auth module", "hard"),
    ("x" * 500, "medium"),
])
def test_rule_rater(prompt, level):
    assert rule_rate(prompt).level == level


def test_rule_raises_low_local_rating(monkeypatch):
    from megazword import rater
    monkeypatch.setattr(rater.ollama, "generate",
                        lambda *a, **k: '{"rating": "medium", "reason": "meh"}')
    assert rater.rate("design a job queue").level == "hard"
    assert rater.rate("explain lists").level == "medium"


def test_rater_falls_back_when_ollama_down(monkeypatch):
    from megazword import rater

    def down(*a, **k):
        raise OSError("refused")
    monkeypatch.setattr(rater.ollama, "generate", down)
    r = rater.rate("hi")
    assert r.source == "rule" and "unavailable" in r.reason


def test_codex_usage_from_log(tmp_path, monkeypatch):
    from megazword import usage_sources
    day = tmp_path / ".codex" / "sessions" / "2026" / "10" / "10"
    day.mkdir(parents=True)
    rec = {"payload": {"rate_limits": {
        "primary": {"used_percent": 3.0, "window_minutes": 300, "resets_at": 1791711582},
        "secondary": {"used_percent": 0.0, "window_minutes": 10080, "resets_at": 1792298382}}}}
    (day / "rollout.jsonl").write_text(json.dumps(rec) + "\n")
    monkeypatch.setattr(usage_sources, "HOME", tmp_path)
    plan = usage_sources.codex()
    assert [(w.name, w.used_percent) for w in plan.windows] == [("5-hour", 3.0), ("weekly", 0.0)]


def test_note_decide_history(capsys, cfg):
    assert main(["decide", "Python only", "-p", "proj"], {}, cfg) == 0
    assert main(["note", "rater is slow cold", "-p", "proj", "--by", "codex"], {}, cfg) == 0
    capsys.readouterr()
    assert main(["history", "-p", "proj"], {}, cfg) == 0
    out = capsys.readouterr().out
    assert "decision" in out and "Python only" in out and "codex" in out


def test_run_records_done_and_passes_context(capsys, cfg):
    main(["decide", "be brief", "-p", "proj"], {}, cfg)
    backends = fakes()
    assert main(["run", "hi", "-m", "fake", "-p", "proj", "--context"], backends, cfg) == 0
    out = capsys.readouterr().out
    assert "be brief" in out and "[Task]" in out  # fake echoes the prompt it got
    from megazword.memory import Memory
    last = Memory(config.HOME, "proj").recent(1)[0]
    assert last.kind == "done" and last.by == "fake" and "ok: hi" in last.text


def test_pacing_skips_over_pace_plan(capsys, cfg):
    from megazword.pacing import PlanStatus
    cfg.route["easy"] = ["cheap", "strong"]
    backends = {"cheap": FakeBackend("cheap", reply="c"), "strong": FakeBackend("strong", reply="s")}
    over = lambda: {"cheap": PlanStatus("cheap", 30.0, 50.0, "hard-only", [])}
    assert main(["run", "hi"], backends, cfg, rated("easy"), over) == 0
    assert capsys.readouterr().out.startswith("s: ")


def test_unknown_window_does_not_block():
    from megazword.pacing import status
    from megazword.usage_sources import PlanUsage, Window
    s = status(PlanUsage("claude", [Window("iguana_necktie", 99.0, None)], "x"))
    assert s.verdict == "unknown" and s.unknown_windows == ["iguana_necktie"]


def test_refusal_escalates_to_next(capsys, cfg):
    cfg.route = {"easy": ["cheap"], "medium": [], "hard": ["strong"]}
    backends = {"cheap": FakeBackend("cheap", reply="I can't"),
                "strong": FakeBackend("strong", reply="s")}
    backends["cheap"]._run = lambda p: "I can't."
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 0
    out = capsys.readouterr()
    assert out.out.startswith("s: ") and "cheap rejected" in out.err
    assert "after escalating" in out.err


def test_all_fail_returns_1(capsys, cfg):
    cfg.route = {"easy": ["a", "b"], "medium": [], "hard": []}
    backends = {"a": FakeBackend("a", fail=True), "b": FakeBackend("b", fail=True)}
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 1
    assert "no AI gave a usable answer" in capsys.readouterr().err


def test_forced_model_does_not_escalate(capsys, cfg):
    backends = {"fake": FakeBackend("fake", fail=True), "cheap": FakeBackend("cheap")}
    assert main(["run", "hi", "-m", "fake"], backends, cfg) == 1
    assert "cheap" not in capsys.readouterr().err


def test_retry_moves_past_last_answerer(capsys, cfg):
    cfg.route = {"easy": ["cheap", "mid"], "medium": [], "hard": ["strong"]}
    backends = {"cheap": FakeBackend("cheap", reply="c"), "mid": FakeBackend("mid", reply="m"),
                "strong": FakeBackend("strong", reply="s")}
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 0
    capsys.readouterr()  # retry must go to strong (hard route), not mid
    assert main(["retry"], backends, cfg) == 0
    out = capsys.readouterr()
    assert out.out.startswith("s: ") and "not good enough" in out.out
    assert "cheap's answer rejected" in out.err and "trying a stronger AI" in out.err


def test_retry_with_nothing_left(capsys, cfg):
    cfg.route = {"easy": ["only"], "medium": [], "hard": ["only"]}
    backends = {"only": FakeBackend("only")}
    main(["run", "hi"], backends, cfg, rated("easy"), dict)
    assert main(["retry"], backends, cfg) == 1
    assert "no AI left" in capsys.readouterr().err


def test_retry_before_any_run(capsys, cfg):
    assert main(["retry"], {}, cfg) == 2


def test_project_retry_cannot_replay_another_projects_prompt(capsys, cfg):
    backends = {'cheap': FakeBackend('cheap'), 'strong': FakeBackend('strong')}
    assert main(['run', 'PRIVATE_OTHER_PROJECT_MARKER', '-p', 'other', '-m', 'cheap'], backends, cfg) == 0
    capsys.readouterr()
    assert main(['retry', '-p', 'current'], backends, cfg) == 2
    output = capsys.readouterr()
    assert 'PRIVATE_OTHER_PROJECT_MARKER' not in output.out + output.err
    assert 'nothing to retry in this project' in output.err


def test_project_retry_uses_its_saved_record_after_another_job(capsys, cfg):
    backends = {'cheap': FakeBackend('cheap'), 'strong': FakeBackend('strong')}
    assert main(['run', 'CURRENT_PROJECT_MARKER', '-p', 'current', '-m', 'cheap'], backends, cfg) == 0
    assert main(['run', 'PRIVATE_OTHER_PROJECT_MARKER', '-p', 'other', '-m', 'cheap'], backends, cfg) == 0
    capsys.readouterr()
    assert main(['retry', '-p', 'current', '-m', 'strong'], backends, cfg) == 0
    output = capsys.readouterr().out
    assert 'CURRENT_PROJECT_MARKER' in output
    assert 'PRIVATE_OTHER_PROJECT_MARKER' not in output


def test_marked_out_ai_is_skipped(capsys, cfg):
    from datetime import datetime, timedelta, timezone
    cfg.route = {"easy": ["cheap", "strong"], "medium": ["strong"], "hard": ["strong"]}
    cfg.out_until = {"cheap": datetime.now(timezone.utc) + timedelta(days=7)}
    backends = {"cheap": FakeBackend("cheap", reply="c"), "strong": FakeBackend("strong", reply="s")}
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 0
    out = capsys.readouterr()
    assert out.out.startswith("s: ") and "skipped (marked out in config): cheap" in out.err


def test_out_mark_expires(cfg):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    cfg.out_until = {"a": now - timedelta(hours=1), "b": now + timedelta(hours=1)}
    assert cfg.out_now() == {"b"}


def test_out_table_loads_dates_and_times(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[out]\ngrok = 2026-10-17T23:30:00-07:00\ncodex = 2026-10-12\n')
    cfg = config.load(p)
    assert cfg.out_until["grok"].isoformat() == "2026-10-17T23:30:00-07:00"
    assert cfg.out_until["codex"].tzinfo is not None
def test_cli_backends_always_have_full_access(monkeypatch):
    """Phil (2026-10-18): no read-only mode; every paid CLI gets every drive."""
    from megazword import backends as b
    monkeypatch.setattr(b, "drive_roots", lambda: ["C:\\", "D:\\"])
    for bs in (b.default_backends(), b.default_backends(edit=False), b.default_backends(edit=True)):
        claude = bs["claude"].args
        assert "--dangerously-skip-permissions" in claude and "--restricted" not in claude
        assert claude[claude.index("--add-dir") + 1] == "C:\\" and "D:\\" in claude
        assert "--dangerously-bypass-approvals-and-sandbox" in bs["codex"].args
        assert "-s" not in bs["codex"].args
        assert "--always-approve" in bs["grok"].args and "--sandbox" not in bs["grok"].args
        assert "gemini" in bs


def test_code_review_prompt_is_not_forced_read_only(cfg, capsys):
    from megazword.request_mode import code_review
    prompt = "audit your code"
    assert code_review(prompt)
    assert main(["run", prompt, "-m", "claude"], {"claude": FakeBackend("claude", reply="done")}, cfg) == 0
    out = capsys.readouterr()
    assert "done" in out.out and "read-only" not in out.err


def test_long_prompt_via_prompt_file_and_stdin():
    """50k chars would overflow a Windows command line (~32k)."""
    import sys
    big = "x" * 50_000
    by_file = CLIBackend("f", exe=sys.executable,
                         args=["-c", "import sys; print(len(open(sys.argv[1], encoding='utf-8').read()))",
                               "{prompt_file}"])
    by_stdin = CLIBackend("s", exe=sys.executable,
                          args=["-c", "import sys; print(len(sys.stdin.read()))"])
    for b in (by_file, by_stdin):
        r = b.run(big)
        assert r.ok and r.text == "50000", r.error


@pytest.mark.parametrize("answer,fail,expected_code", [
    ("123456", False, 0), ("", False, 1), ("I can't.", False, 1), ("", True, 1),
])
def test_attempt_logs_rough_tokens(cfg, answer, fail, expected_code):
    backend = FakeBackend("fake", fail=fail)
    if not fail:
        backend._run = lambda prompt: answer
    assert main(["run", "12345", "-m", "fake"], {"fake": backend}, cfg) == expected_code
    row = json.loads(cfg.log_path.read_text(encoding="utf-8"))
    assert row["prompt_chars"] == 5
    assert row["answer_chars"] == len(answer)
    assert row["est_tokens"] == (5 + len(answer)) // 4


def test_usage_displays_token_totals_and_empty_backends(monkeypatch, capsys, cfg):
    from megazword import log, usage_sources
    monkeypatch.setattr(usage_sources, "all_usage", lambda *args: [])
    path = config.HOME / "log.jsonl"
    log.append(path, backend="claude", ok=True, est_tokens=13)
    log.append(path, backend="claude", ok=False, est_tokens=4)
    log.append(path, backend="grok", ok=True, prompt_chars=100)
    assert main(["usage"], {}, cfg) == 0
    output = capsys.readouterr().out
    assert "chars est_tokens" in output
    rows = {parts[0]: parts for line in output.splitlines()
            if (parts := line.split()) and parts[0] in ("claude", "codex", "grok")}
    assert rows["claude"][-1] == "17"
    assert rows["codex"][-1] == rows["grok"][-1] == "0"


def test_usage_shows_cheap_budget_without_network(monkeypatch, capsys, cfg):
    from megazword import budget, usage_sources
    monkeypatch.setattr(usage_sources, "all_usage", lambda *args: [])
    monkeypatch.setattr(budget, "_fetch_spend", lambda: (_ for _ in ()).throw(AssertionError("network")))
    assert main(["usage"], {}, cfg) == 0
    assert "Cheap paid (OpenRouter): cap $1.00/month" in capsys.readouterr().out


def test_free_spread_line_counts_used_and_idle_sources():
    from types import SimpleNamespace
    from megazword.cli import free_spread_line
    total = len([n for n in config.DEFAULT_FREE_FAILOVER if not n.startswith("cheap-")])
    line = free_spread_line({"groq": SimpleNamespace(runs=3), "zai": SimpleNamespace(runs=0)})
    assert line.startswith(f"Free sources used (24h): 1 of {total}; idle: ")
    assert "groq," not in line and line.endswith(f"and {total - 1 - 8} more")
    every = {n: SimpleNamespace(runs=1) for n in config.DEFAULT_FREE_FAILOVER}
    assert free_spread_line(every) == f"Free sources used (24h): {total} of {total}"
