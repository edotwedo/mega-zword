"""Team job scoreboard: which AI delivers pieces that pass, from every saved job.json."""
from __future__ import annotations

import json
from pathlib import Path


def scoreboard(reports: list[dict]) -> list[dict]:
    """Per AI: pieces delivered (passed, by that AI), failed tries (listed in `tried` of a
    piece it didn't deliver), pass rate and estimated tokens of what it delivered. Best first."""
    stats: dict[str, dict] = {}
    for report in reports:
        for row in report.get("results") or []:
            ai, passed = row.get("ai") or "", row.get("status") == "passed"
            if ai and passed:
                entry = stats.setdefault(ai, {"delivered": 0, "failed": 0, "est_tokens": 0})
                entry["delivered"] += 1
                entry["est_tokens"] += int(row.get("est_tokens") or 0)
            for name in set(row.get("tried") or []):
                if name and not (passed and name == ai):
                    stats.setdefault(name, {"delivered": 0, "failed": 0, "est_tokens": 0})["failed"] += 1
    rows = []
    for name, entry in stats.items():
        total = entry["delivered"] + entry["failed"]
        rows.append({"ai": name, **entry, "pass_rate": entry["delivered"] / total if total else 0.0})
    return sorted(rows, key=lambda r: (-r["delivered"], -r["pass_rate"], r["ai"]))


def load_reports(folder: Path) -> list[dict]:
    """Every folder/*/job.json that reads as a JSON object; others are skipped."""
    reports = []
    for path in sorted(folder.glob("*/job.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            reports.append(data)
    return reports


def format_scores(rows: list[dict]) -> str:
    if not rows:
        return "no job results yet"
    width = max(len(r["ai"]) for r in rows)
    lines = [f"{'AI':<{width}}  delivered  failed  pass  est_tokens"]
    lines += [f"{r['ai']:<{width}}  {r['delivered']:>9}  {r['failed']:>6}  {r['pass_rate']:>4.0%}  {r['est_tokens']:>10}"
              for r in rows]
    return "\n".join(lines)
