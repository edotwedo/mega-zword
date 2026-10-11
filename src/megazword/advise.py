"""Routing advisor: suggest a route order per difficulty. Never applies it.

Reads the run log (how often each AI answered, how often Mega Zword had to
move on, how long it took, rough tokens) and Phil's compare votes, then
ranks the AIs for each difficulty. Routing is Phil's call, so this only
prints; he applies it in the dashboard Settings panel or config.toml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, log, runlog
from .filelock import locked

LEVELS = ("easy", "medium", "hard")
WINDOW = timedelta(days=30)
MIN_RUNS = 3  # fewer than this and an AI keeps its current place
VOTES_KEEP = 2000


# --- votes ----------------------------------------------------------------

def votes_path() -> Path:
    return config.HOME / "votes.jsonl"


def add_vote(ai: str, rating: str | None, prompt_line: str) -> None:
    """Phil said this AI's compare answer was the best one."""
    log.append(votes_path(), VOTES_KEEP, ai=ai, rating=rating or None,
               prompt=prompt_line.strip().splitlines()[0][:120] if prompt_line.strip() else "")


def read_votes() -> list[dict]:
    with locked(votes_path()):  # don't read halfway through a trim
        return _read_jsonl(votes_path())


def _read_jsonl(path: Path) -> list[dict]:
    import json
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("ai"):
            out.append(row)
    return out


# --- scoring --------------------------------------------------------------

@dataclass
class Score:
    ai: str
    runs: int = 0
    ok: int = 0
    seconds: float = 0.0
    tokens: int = 0
    votes: int = 0

    @property
    def ok_rate(self) -> float:
        return self.ok / self.runs if self.runs else 0.0

    @property
    def avg_seconds(self) -> float:
        return self.seconds / self.runs if self.runs else 0.0

    @property
    def value(self) -> float:
        """Higher is better. Answering well matters most, then Phil's votes,
        then speed; escalations are already counted as not-ok."""
        return self.ok_rate * 100 + self.votes * 8 - min(self.avg_seconds, 120) * 0.15


@dataclass
class Advice:
    level: str
    current: list[str]
    suggested: list[str]
    reason: str
    scores: list[Score] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.current != self.suggested


def _since(row: dict, cutoff: datetime) -> bool:
    try:
        t = datetime.fromisoformat(str(row.get("time", "")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)) >= cutoff


def advise(cfg: config.Config, now: datetime | None = None) -> list[Advice]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - WINDOW
    runs = [r for r in runlog.read(cfg.log_path) if _since(r, cutoff)]
    votes = [v for v in read_votes() if _since(v, cutoff)]
    out = []
    for level in LEVELS:
        current = list(cfg.route.get(level, []))
        scores: dict[str, Score] = {n: Score(n) for n in current}
        for r in runs:
            if r.get("rating") != level:
                continue
            s = scores.setdefault(str(r["backend"]), Score(str(r["backend"])))
            s.runs += 1
            s.ok += bool(r.get("ok"))
            s.seconds += float(r.get("seconds") or 0)
            s.tokens += int(r.get("est_tokens") or 0)
        for v in votes:
            if v.get("rating") in (level, None):
                scores.setdefault(str(v["ai"]), Score(str(v["ai"]))).votes += 1
        out.append(_rank(level, current, list(scores.values())))
    return out


def _rank(level: str, current: list[str], scores: list[Score]) -> Advice:
    measured = [s for s in scores if s.runs >= MIN_RUNS]
    if len(measured) < 2:
        return Advice(level, current, current,
                      f"not enough {level} runs yet (need {MIN_RUNS}+ for two AIs); keep as is",
                      scores)
    # Measured AIs are ordered by score; unmeasured ones keep their relative
    # place after them, so the advice never drops an AI Phil put in the route.
    ranked = sorted(measured, key=lambda s: -s.value)
    rest = [n for n in current if n not in {s.ai for s in ranked}]
    suggested = [s.ai for s in ranked if s.ai in current or s.votes or s.runs] + rest
    best = ranked[0]
    why = (f"{best.ai} answered {best.ok_rate:.0%} of {best.runs} {level} runs"
           f" in {best.avg_seconds:.0f}s avg" + (f", {best.votes} votes" if best.votes else ""))
    if suggested[:len(current)] == current:
        why = "current order already fits the numbers: " + why
    return Advice(level, current, suggested, why, scores)


def text(advice: list[Advice]) -> str:
    rows = []
    for a in advice:
        mark = "suggest" if a.changed else "keep   "
        rows.append(f"{a.level:6} {mark} {' > '.join(a.suggested) or '(empty)'}")
        rows.append(f"       {a.reason}")
    rows.append("Nothing was changed. To apply: dashboard Settings > Routing, "
                "or edit [route] in ~/.megazword/config.toml.")
    return "\n".join(rows)


def as_dict(advice: list[Advice]) -> list[dict]:
    return [{"level": a.level, "current": a.current, "suggested": a.suggested,
             "changed": a.changed, "reason": a.reason} for a in advice]
