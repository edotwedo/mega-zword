"""Offline routing lab: synthetic, deterministic, and zero-network.

These tests never touch a provider: the "catalog" is made up and every check
runs against local fixtures.
"""

from __future__ import annotations

from megazword import cli, router_lab


def test_wilson_lower_bound_is_conservative():
    assert router_lab.wilson_lower_bound(0, 0) == 0.0
    assert router_lab.wilson_lower_bound(0, 10) == 0.0
    assert router_lab.wilson_lower_bound(100, 100) < 1.0  # never certifies certainty
    assert router_lab.wilson_lower_bound(96, 100) > router_lab.wilson_lower_bound(82, 100)
    assert router_lab.wilson_lower_bound(82, 100) < 0.82  # shrinks toward the sample mean


def test_unknown_price_fails_closed():
    task = router_lab.TASKS["code"]
    unpriced = next(c for c in router_lab.fixtures(include_unknown_price=True)
                    if c.name == "unpriced-api")
    ok, reason = router_lab.qualified(unpriced, task, budget_usd=1.0)
    assert ok is False and "price unknown" in reason


def test_missing_capability_is_skipped():
    task = router_lab.TASKS["code"]        # needs chat + tools + code
    local = router_lab.fixtures()[0]        # local-small only has chat + json
    ok, reason = router_lab.qualified(local, task, budget_usd=1.0)
    assert ok is False and "missing capabilities" in reason


def test_remote_requires_opt_in():
    beta = next(c for c in router_lab.fixtures() if c.name == "free-hosted")
    ok, reason = router_lab.qualified(beta, router_lab.TASKS["code"], budget_usd=1.0,
                                      allow_remote=False)
    assert ok is False and "remote execution disallowed" in reason


def test_choose_prefers_the_cheapest_that_clears_the_floor():
    winner, _ = router_lab.choose(router_lab.TASKS["summary"], budget_usd=1.0)
    assert winner is not None and winner.name == "free-hosted"   # free and above the floor


def test_only_the_strong_model_clears_the_code_floor():
    winner, _ = router_lab.choose(router_lab.TASKS["code"], budget_usd=1.0)
    assert winner is not None and winner.name == "strong-api"


def test_zero_budget_still_allows_a_free_source():
    winner, _ = router_lab.choose(router_lab.TASKS["summary"], budget_usd=0.0)
    assert winner is not None and winner.estimate(router_lab.TASKS["summary"]) == 0.0


def test_budget_ceiling_can_refuse_every_candidate():
    winner, reviewed = router_lab.choose(router_lab.TASKS["code"], budget_usd=0.0)
    assert winner is None
    assert all(not ok for _, ok, _ in reviewed)


def test_reliability_floor_override_is_respected():
    winner, _ = router_lab.choose(router_lab.TASKS["summary"], budget_usd=1.0,
                                  reliability_floor=0.99)
    assert winner is None


def test_preview_stops_without_approval_then_executes_only_locally():
    lines = []
    assert router_lab.preview(router_lab.TASKS["code"], budget_usd=1.0, out=lines.append) == 0
    assert any("Approval: not given" in line for line in lines)
    assert not any("simulated=true" in line for line in lines)   # nothing ran

    lines = []
    assert router_lab.preview(router_lab.TASKS["code"], budget_usd=1.0, approve=True,
                              out=lines.append) == 0
    text = "\n".join(lines)
    assert "Independent local verification: PASS" in text
    assert "simulated=true" in text


def test_preview_stops_when_nothing_qualifies():
    lines = []
    assert router_lab.preview(router_lab.TASKS["code"], budget_usd=0.0, out=lines.append) == 1
    assert any(line.startswith("Decision: STOP") for line in lines)


def test_benchmark_is_synthetic_and_says_so():
    lines = []
    assert router_lab.benchmark(out=lines.append) == 0
    text = "\n".join(lines)
    assert "300 simulated requests" in text
    assert "not real-model accuracy claims" in text


def test_cli_wires_route_lab(capsys):
    assert cli.main(["route-lab", "benchmark"]) == 0
    assert "simulated requests" in capsys.readouterr().out
    assert cli.main(["route-lab", "preview", "--task", "code", "--budget-usd", "1"]) == 0
    assert "Proposed:" in capsys.readouterr().out
