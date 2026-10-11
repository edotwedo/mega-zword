"""Quality check uses a fake generate(); never the network."""

from megazword import config
from megazword.cli import main
from megazword.escalate import looks_failed
from megazword.quality import check, judge_for
from megazword.rater import Rating
from tests.test_cli import FakeBackend


def gen(reply):
    return lambda *a, **k: reply


def test_dodge_is_flagged_with_reason():
    r = check("sum 2+2", "I'll get back to you", "m", gen('{"verdict": "dodge", "reason": "no answer"}'))
    assert r == "quality check: no answer"


def test_ok_junk_and_errors_keep_the_answer():
    assert check("q", "a", "m", gen('{"verdict": "ok"}')) is None
    assert check("q", "a", "m", gen("not json")) is None

    def down(*a, **k):
        raise OSError("refused")
    assert check("q", "a", "m", down) is None


def test_judge_runs_rules_first():
    calls = []

    def spy(*a, **k):
        calls.append(1)
        return '{"verdict": "ok"}'
    judge = judge_for("q", "m", looks_failed, spy)
    assert judge("") == "empty answer" and not calls  # rule caught it, no model call
    assert judge("fine answer") is None and calls


def run_with(cfg, monkeypatch, verdict, args):
    from megazword import quality
    monkeypatch.setattr(quality.ollama, "generate", gen(verdict))
    cfg.route = {"easy": ["cheap"], "medium": [], "hard": ["strong"]}
    backends = {"cheap": FakeBackend("cheap", reply="c"), "strong": FakeBackend("strong", reply="s")}
    return main(args, backends, cfg, lambda p: Rating("easy", "t", "t"), dict)


def test_on_flagged_answer_escalates(tmp_path, monkeypatch, capsys):
    cfg = config.Config(log_path=tmp_path / "log.jsonl", quality_check=True)
    calls = iter(['{"verdict": "dodge", "reason": "off topic"}', '{"verdict": "ok"}'])
    from megazword import quality
    monkeypatch.setattr(quality.ollama, "generate", lambda *a, **k: next(calls))
    cfg.route = {"easy": ["cheap"], "medium": [], "hard": ["strong"]}
    backends = {"cheap": FakeBackend("cheap", reply="c"), "strong": FakeBackend("strong", reply="s")}
    assert main(["run", "hi"], backends, cfg, lambda p: Rating("easy", "t", "t"), dict) == 0
    out = capsys.readouterr()
    assert out.out.startswith("s: ") and "quality check: off topic" in out.err


def test_off_by_default_and_never_for_forced(tmp_path, monkeypatch, capsys):
    dodge = '{"verdict": "dodge", "reason": "x"}'
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    assert run_with(cfg, monkeypatch, dodge, ["run", "hi"]) == 0
    assert capsys.readouterr().out.startswith("c: ")
    cfg.quality_check = True
    assert run_with(cfg, monkeypatch, dodge, ["run", "hi", "-m", "cheap"]) == 0
    assert capsys.readouterr().out.startswith("c: ")


def test_config_switch_loads(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("quality_check = true\n")
    assert config.load(p).quality_check and not config.load(tmp_path / "none.toml").quality_check
