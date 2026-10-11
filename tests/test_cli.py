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
def test_edit_mode_backend_args():
    from megazword.backends import default_backends
    ro, rw = default_backends(), default_backends(edit=True)
    assert "acceptEdits" not in ro["claude"].args and "acceptEdits" in rw["claude"].args
    assert "read-only" in ro["codex"].args and "workspace-write" in rw["codex"].args
    assert "bypassPermissions" not in " ".join(rw["claude"].args)


def test_grok_edit_only_with_sandbox(monkeypatch):
    from megazword import backends as b
    monkeypatch.setattr(b.sys, "platform", "win32")
    assert "grok" not in b.default_backends(edit=True) and "grok" in b.default_backends()
    monkeypatch.setattr(b.sys, "platform", "linux")
    args = b.default_backends(edit=True)["grok"].args
    assert args[args.index("--sandbox") + 1] == "workspace"


def test_forced_grok_edit_on_windows_explains(capsys, cfg, monkeypatch):
    from megazword import backends as b
    monkeypatch.setattr(b.sys, "platform", "win32")
    assert main(["run", "hi", "--edit", "-m", "grok"], None, cfg) == 2
    assert "can't edit files safely" in capsys.readouterr().err


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
