"""Compare mode: the same prompt on 2-3 AIs at once, answers side by side.

No escalation and no rating: you picked the AIs. Each run is logged like a
normal forced run (with compare=true) so usage and stats stay right.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from . import config, log
from .backends import Backend, Result
from .memory import Memory

MIN_AIS, MAX_AIS = 2, 3
# The dashboard splits compare output on these header lines.
HEADER = "=== {name} · {status} ==="


def parse_names(text: str, backends: dict[str, Backend]) -> list[str]:
    names = list(dict.fromkeys(n.strip() for n in text.split(",") if n.strip()))
    if not MIN_AIS <= len(names) <= MAX_AIS:
        raise ValueError(f"compare needs {MIN_AIS} or {MAX_AIS} AIs, e.g. --compare claude,codex")
    unknown = [n for n in names if n not in backends]
    if unknown:
        raise ValueError(f"unknown AI {', '.join(unknown)}. Choose from: {', '.join(backends)}")
    missing = [n for n in names if not backends[n].available()]
    if missing:
        raise ValueError(f"not installed: {', '.join(missing)}")
    return names


def run(sent: str, prompt: str, names: list[str], backends: dict[str, Backend],
        cfg: config.Config, memory: Memory, write=print) -> int:
    """Run every AI in parallel, then print each answer under a header.
    Returns 0 if at least one AI answered."""
    chosen = [backends[n] for n in names]
    for b in chosen:
        b.timeout = cfg.timeouts.get(b.name, b.timeout)
    print(f"[megazword] comparing {', '.join(names)} (running at the same time)",
          file=sys.stderr)
    with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        results: list[Result] = list(pool.map(lambda b: b.run(sent), chosen))

    first_line = prompt.strip().splitlines()[0][:80]
    for r in results:
        log.append(cfg.log_path, cfg.log_lines, backend=r.backend, forced=True, compare=True,
                   rating=None, rater=None, seconds=round(r.seconds, 2), ok=r.ok,
                   rejected=None if r.ok else f"failed: {r.error}"[:200],
                   prompt_chars=len(prompt), answer_chars=len(r.text),
                   est_tokens=(len(prompt) + len(r.text)) // 4)
        memory.add("done", f"{'ok' if r.ok else 'FAILED'} (compare): {first_line}", by=r.backend)

    for i, r in enumerate(results):
        status = f"{r.seconds:.1f}s" if r.ok else f"failed after {r.seconds:.1f}s"
        if i:
            write("")
        write(HEADER.format(name=r.backend, status=status))
        write(r.text if r.ok else r.error)
    fastest = min((r for r in results if r.ok), key=lambda r: r.seconds, default=None)
    if fastest:
        print(f"[megazword] fastest: {fastest.backend} ({fastest.seconds:.1f}s)", file=sys.stderr)
    return 0 if fastest else 1
