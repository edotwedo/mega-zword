"""A human-selected owner is independent of spare capacity or availability."""
from datetime import datetime, timedelta, timezone

import pytest

from megazword import cli, config, floor, start, usage_sources
from megazword.usage_sources import PlanUsage, Window


def test_owner_persists_without_rewriting_other_settings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('# retain this\n[usage.reserve]\ncodex = 30\n')
    config.set_work_owner("cmdc", path)
    cfg = config.load(path)
    assert cfg.work_owner == "cmdc" and cfg.usage_reserve == {"codex": 30}
    assert "# retain this" in path.read_text()
    config.set_work_owner("", path)
    assert config.load(path).work_owner == ""


@pytest.mark.parametrize("text", ['[work]\nowner = 3', '[work]\nowner = "x\\nforged"', 'work = false'])
def test_invalid_owner_is_not_used_as_output_or_code(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        config.load(path)


def test_plan_keeps_cmdc_as_owner_even_if_another_ai_has_more_room(monkeypatch, capsys):
    config.set_work_owner("cmdc")
    monkeypatch.setattr(usage_sources, "all_usage", lambda path=None: [
        PlanUsage("cmdc", [Window("weekly", 18, None)], "test"),
        PlanUsage("gemini", [Window("weekly", 1, None)], "test"),
    ])
    assert cli.main(["plan"]) == 0
    out = capsys.readouterr().out
    assert "Work owner: cmdc" in out and "cmdc owns assignments" in out
    assert "New work goes to gemini" not in out and "99% left" in out
    assert config.load().work_owner == "cmdc"


def test_out_owner_delegates_execution_without_losing_ownership():
    seats = [floor.Seat("cmdc", "cli", "out"), floor.Seat("codex", "cli", "seated")]
    assert floor.suggest_seat("edit", seats, owner="cmdc") == "codex"
    assert "Work owner: cmdc" in floor.format_roster(seats, owner="cmdc")
    seats[0] = floor.Seat("cmdc", "cli", "seated")
    assert floor.suggest_seat("decide", seats, owner="cmdc") == "cmdc"


def test_owner_and_cmdc_alias_activity_appear_in_usage(monkeypatch, capsys):
    config.set_work_owner("cmdc")
    monkeypatch.setattr(usage_sources, "all_usage", lambda path=None: [
        PlanUsage("cmdc", [Window("weekly", 18, None)], "test", note="GOAT Plan; monthly 9% used")])
    assert cli.main(["usage"]) == 0
    out = capsys.readouterr().out
    assert "Work owner: cmdc" in out and "82% left" in out and "monthly 9% used" in out
    assert "cmdc" in out.split("Mega Zword runs (last 24h)")[1]
    assert "Work owner: cmdc" in start.render(config.load(), meters=[], color=False)


def test_cmdc_is_a_real_cli_roster_slot():
    assert "cmdc" in floor.CLI_SEATS
    assert next(s for s in floor.roster({}) if s.name == "cmdc").status == "empty"


def test_shared_quota_blocks_all_cmdc_models_but_not_other_providers():
    from megazword.pacing import PlanStatus, rank
    quota = PlanStatus("cmdc", 0, 100, "out", [])
    assert rank({"cmdc": quota}, ["cmdc", "cmdc-glm", "cmdc-qwen", "grok"], "hard") == ["grok"]


def test_configured_owner_plans_jobs_and_can_delegate_when_unavailable():
    from megazword import job
    from tests.test_job import FakeAI
    cmdc, grok = FakeAI("cmdc"), FakeAI("grok")
    assert job.pick_planner({"cmdc": cmdc, "grok": grok}, owner="cmdc") is cmdc
    assert job.pick_planner({"grok": grok}, owner="cmdc") is grok


def test_explicit_cmdc_out_mark_also_excludes_model_aliases(tmp_path):
    from megazword.rater import Rating
    from tests.test_job import FakeAI
    backends = {name: FakeAI(name) for name in ("cmdc", "cmdc-glm", "grok")}
    chain = cli.candidates(Rating("medium", "test", "test"), {"medium": list(backends)},
                           backends, out={"cmdc"}, log_path=tmp_path / "empty-log")
    assert [b.name for b in chain] == ["grok"]
