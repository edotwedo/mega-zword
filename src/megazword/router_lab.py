"""Zero-network prototype for capability-gated, cost-aware routing.

All catalog entries and outputs are synthetic. This module deliberately has no
provider SDK, credentials, network access, or paid execution path.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Task:
    name: str
    label: str
    minimum_reliable_rate: float
    input_tokens: int
    output_tokens: int
    required_capabilities: frozenset[str]
    verify: Callable[[str], tuple[bool, str]]


@dataclass(frozen=True)
class Candidate:
    name: str
    provider: str
    input_usd_per_million: float | None
    output_usd_per_million: float | None
    capabilities: frozenset[str]
    success_counts: dict[str, tuple[int, int]]
    outputs: dict[str, str]
    remote: bool
    available: bool = True

    def estimate(self, task: Task) -> float | None:
        if self.input_usd_per_million is None or self.output_usd_per_million is None:
            return None
        return (task.input_tokens * self.input_usd_per_million
                + task.output_tokens * self.output_usd_per_million) / 1_000_000


TASKS = {
    "summary": Task(
        "summary", "Three-point summary", .80, 1000, 200,
        frozenset({"chat"}),
        lambda text: ((sum(line.startswith("- ") for line in text.splitlines()) == 3,
                       "expected exactly three bullet points")),
    ),
    "extract": Task(
        "extract", "JSON extraction", .92, 400, 100,
        frozenset({"chat", "json"}),
        lambda text: _verify_json(text),
    ),
    "code": Task(
        "code", "Small code edit", .90, 1800, 800,
        frozenset({"chat", "tools", "code"}),
        lambda text: _verify_code(text),
    ),
}


def _verify_json(text: str) -> tuple[bool, str]:
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return False, "output is not valid JSON"
    if result != {"name": "Mina", "quantity": 2}:
        return False, "JSON does not match the expected name and quantity"
    return True, "JSON parses and matches the expected fields"


def _verify_code(text: str) -> tuple[bool, str]:
    namespace: dict[str, object] = {}
    try:
        exec(compile(text, "<offline-route-lab>", "exec"), {"__builtins__": {}}, namespace)
        add = namespace["add"]
        if not callable(add) or add(2, 3) != 5 or add(-2, 2) != 0:
            return False, "example assertions failed"
    except Exception as exc:  # synthetic code fixture only
        return False, f"code check failed: {type(exc).__name__}"
    return True, "two local assertions passed"


_SUMMARY_OK = "- first point\n- second point\n- third point"
_SUMMARY_BAD = "- first point\n- second point"
_JSON_OK = '{"name":"Mina","quantity":2}'
_JSON_BAD = '{"name":"Mina"}'
_CODE_OK = "def add(a, b):\n    return a + b\n"
_CODE_BAD = "def add(a, b):\n    return a - b\n"


def fixtures(include_unknown_price: bool = False) -> tuple[Candidate, ...]:
    """Small made-up catalog. Pass counts are synthetic, not model measurements."""
    catalog = (
        Candidate("local-small", "local", 0, 0, frozenset({"chat", "json"}),
                  {"summary": (82, 100), "extract": (69, 100), "code": (51, 100)},
                  {"summary": _SUMMARY_BAD, "extract": _JSON_BAD, "code": _CODE_BAD}, False),
        Candidate("free-hosted", "free-api", 0, 0,
                  frozenset({"chat", "json", "tools", "code"}),
                  {"summary": (88, 100), "extract": (80, 100), "code": (64, 100)},
                  {"summary": _SUMMARY_OK, "extract": _JSON_BAD, "code": _CODE_BAD}, True),
        Candidate("economy-api", "example-provider", .20, .60,
                  frozenset({"chat", "json", "tools", "code"}),
                  {"summary": (92, 100), "extract": (95, 100), "code": (83, 100)},
                  {"summary": _SUMMARY_OK, "extract": _JSON_OK, "code": _CODE_BAD}, True),
        Candidate("strong-api", "example-provider", 1.0, 5.0,
                  frozenset({"chat", "json", "tools", "code"}),
                  {"summary": (97, 100), "extract": (98, 100), "code": (96, 100)},
                  {"summary": _SUMMARY_OK, "extract": _JSON_OK, "code": _CODE_OK}, True),
    )
    if include_unknown_price:
        catalog += (Candidate("unpriced-api", "unknown-provider", None, None,
                              frozenset({"chat", "json", "tools", "code"}),
                              {"summary": (99, 100), "extract": (99, 100), "code": (99, 100)},
                              {}, True),)
    return catalog


def wilson_lower_bound(successes: int, trials: int, z: float = 1.96) -> float:
    """Approximate 95% Wilson lower bound; unknown samples are never qualified."""
    if trials <= 0 or successes < 0 or successes > trials:
        return 0.0
    p = successes / trials
    z2 = z * z
    denom = 1 + z2 / trials
    center = p + z2 / (2 * trials)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * trials)) / trials)
    return max(0.0, (center - margin) / denom)


def reliability(candidate: Candidate, task: Task) -> float:
    successes, trials = candidate.success_counts.get(task.name, (0, 0))
    return wilson_lower_bound(successes, trials)


def qualified(candidate: Candidate, task: Task, budget_usd: float,
              allow_remote: bool = True,
              reliability_floor: float | None = None) -> tuple[bool, str]:
    if not candidate.available:
        return False, "provider currently unavailable"
    if candidate.remote and not allow_remote:
        return False, "remote execution disallowed by user"
    missing = task.required_capabilities - candidate.capabilities
    if missing:
        return False, "missing capabilities: " + ", ".join(sorted(missing))
    lower = reliability(candidate, task)
    floor = task.minimum_reliable_rate if reliability_floor is None else reliability_floor
    if lower < floor:
        return False, (f"95% lower bound {lower:.1%} below task floor "
                       f"{floor:.0%}")
    cost = candidate.estimate(task)
    if cost is None:
        return False, "price unknown; fail closed"
    if cost > budget_usd:
        return False, f"estimated ${cost:.6f} exceeds user-set ${budget_usd:.6f} ceiling"
    return True, f"reliability lower bound {lower:.1%}; estimate ${cost:.6f}"


def choose(task: Task, budget_usd: float,
           candidates: tuple[Candidate, ...] | None = None,
           allow_remote: bool = True,
           reliability_floor: float | None = None) -> tuple[Candidate | None, list[tuple[Candidate, bool, str]]]:
    candidates = candidates or fixtures()
    reviewed = [(candidate, *qualified(candidate, task, budget_usd,
                                        allow_remote, reliability_floor))
                for candidate in candidates]
    eligible = [candidate for candidate, ok, _ in reviewed if ok]
    winner = min(eligible, key=lambda c: (c.estimate(task), -reliability(c, task), c.name),
                 default=None)
    return winner, reviewed


def _run_fixture(candidate: Candidate, task: Task) -> tuple[bool, str, str]:
    """Execute only a fixed local fixture, then run its separate deterministic checker."""
    output = candidate.outputs.get(task.name, "")
    passed, detail = task.verify(output)
    return passed, output, detail


def preview(task: Task, budget_usd: float, approve: bool = False,
            allow_remote: bool = True, reliability_floor: float | None = None,
            out: Callable[[str], None] = print) -> int:
    winner, reviewed = choose(task, budget_usd, fixtures(include_unknown_price=True),
                              allow_remote, reliability_floor)
    floor = task.minimum_reliable_rate if reliability_floor is None else reliability_floor
    out(f"Task: {task.label} | reliability floor: {floor:.0%} "
        f"(95% lower confidence bound) | simulated ceiling: ${budget_usd:.6f}")
    out("Candidates:")
    for candidate, ok, reason in reviewed:
        mark = "ELIGIBLE" if ok else "skip"
        cost = candidate.estimate(task)
        price = "unknown" if cost is None else f"${cost:.6f}/task"
        destination = "remote" if candidate.remote else "local"
        out(f"  {candidate.name:<14} {mark:<8} {price:<16} {destination}: {reason}")
    if winner is None:
        out("Decision: STOP. No candidate meets capability, evidence, and budget rules.")
        return 1
    out(f"Proposed: {winner.name} ({winner.provider}), estimate ${winner.estimate(task):.6f}.")
    out("Approval: not given. Nothing executed." if not approve else
        "Approval: given for the local simulator only; no provider/network call is possible.")
    if not approve:
        out("To approve this synthetic demonstration, add --approve. It cannot contact a model.")
        return 0
    passed, response, detail = _run_fixture(winner, task)
    out("Synthetic response: " + response.replace("\n", "\\n"))
    out(f"Independent local verification: {'PASS' if passed else 'FAIL'} - {detail}")
    out(f"Audit record: task={task.name}; candidate={winner.name}; estimated_cost=${winner.estimate(task):.6f}; "
        f"approved=true; verified={str(passed).lower()}; simulated=true")
    return 0 if passed else 1


def benchmark(out: Callable[[str], None] = print) -> int:
    """Compare synthetic policy choices; 100 expected trials per task, no randomness."""
    catalog = fixtures()
    rows = {name: {"calls": 0, "successes": 0.0, "cost": 0.0}
            for name in ("cheapest-only", "LiteLLM cost-based", "qualified-cheapest", "strongest")}
    qualified_count = 0
    for task in TASKS.values():
        cheapest = min(catalog, key=lambda c: (c.estimate(task), c.name))
        strong = max(catalog, key=lambda c: (c.success_counts[task.name][0]
                                              / c.success_counts[task.name][1], -c.estimate(task)))
        gated, _ = choose(task, budget_usd=1.0, candidates=catalog)
        choices = {"cheapest-only": cheapest,
                   "LiteLLM cost-based": cheapest,
                   "qualified-cheapest": gated,
                   "strongest": strong}
        if gated is not None:
            qualified_count += 1
        for name, candidate in choices.items():
            trials = 100
            successes, _ = candidate.success_counts[task.name]
            rows[name]["calls"] += trials
            rows[name]["successes"] += successes
            rows[name]["cost"] += trials * candidate.estimate(task)
    out("Synthetic benchmark: 3 task profiles x 100 expected trials = 300 simulated requests.")
    out("Made-up pass counts and prices; deterministic arithmetic, no models or providers contacted.")
    out(f"{'Policy':<23} {'Pass rate':>10} {'Tasks meeting floor':>19} {'Est. total':>14}")
    for name, stats in rows.items():
        meets = 0
        for task in TASKS.values():
            candidate = (min(catalog, key=lambda c: (c.estimate(task), c.name)) if name in
                         ("cheapest-only", "LiteLLM cost-based") else
                         max(catalog, key=lambda c: (c.success_counts[task.name][0]
                                                     / c.success_counts[task.name][1], -c.estimate(task)))
                         if name == "strongest" else choose(task, 1.0, catalog)[0])
            if candidate and reliability(candidate, task) >= task.minimum_reliable_rate:
                meets += 1
        rate = stats["successes"] / stats["calls"]
        out(f"{name:<23} {rate:>9.1%} {meets:>14}/3  ${stats['cost']:>12.6f}")
    low_cost = rows["qualified-cheapest"]["cost"]
    high_cost = rows["strongest"]["cost"]
    saved = 100 * (1 - low_cost / high_cost) if high_cost else 0
    out(f"Qualified-cheapest modeled savings vs strongest: {saved:.1f}% at the same 3/3 task-floor count.")
    out(f"Qualified task profiles: {qualified_count}/3. These are scenario results, not real-model accuracy claims.")
    return 0


def command(args, out: Callable[[str], None] = print) -> int:
    if args.route_action == "benchmark":
        return benchmark(out)
    if args.route_action == "preview":
        if args.reliability_floor is not None and not 0 <= args.reliability_floor <= 1:
            out("--reliability-floor must be between 0 and 1")
            return 2
        return preview(TASKS[args.task], max(0.0, args.budget_usd), args.approve,
                       not args.no_remote, args.reliability_floor, out)
    out("Choose `preview` or `benchmark`.")
    return 2
