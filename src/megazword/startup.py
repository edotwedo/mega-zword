"""Bounded startup readings, without a model call, browser, suite or retries."""

import subprocess
import sys
from time import monotonic

from .backends import run_quick

READ_SECONDS = 10.0
# run_quick bounds process-tree termination to 15s and pipe cleanup to 5s.
MAX_SECONDS = READ_SECONDS + 20.0
READS = (("usage",), ("floor",), ("floor", "peek", "-n", "10"))


def reading(*, timeout=READ_SECONDS, run=None, clock=monotonic):
    """One shared read deadline, then at most 20s process-tree cleanup.

    A timeout ends the whole batch. Never multiply the deadline by the number of
    providers/commands, retry, or treat partial output as a successful reading.
    ``run`` and ``clock`` are injected by offline tests.
    """
    run = run or run_quick
    budget = max(0.0, min(float(timeout), READ_SECONDS))
    deadline = clock() + budget
    lines = [f"Startup: {budget:g}s shared read deadline; at most {MAX_SECONDS:g}s including cleanup."]
    for args in READS:
        remaining = deadline - clock()
        if remaining <= 0:
            lines.append("WARN startup: time budget exhausted; remaining readings unavailable (no retry)")
            break
        label = "megazword " + " ".join(args)
        try:
            result = run([sys.executable, "-m", "megazword.cli", *args], timeout=remaining)
        except subprocess.TimeoutExpired:
            lines.append(f"WARN {label}: timed out; remaining readings unavailable (no retry)")
            break
        except OSError:
            lines.append(f"WARN {label}: unavailable (no retry)")
            continue
        if result.returncode:
            lines.append(f"WARN {label}: unavailable (exit {result.returncode}; no retry)")
            continue
        # Current summaries only; do not flood the next model turn with history.
        output = "\n".join(result.stdout.splitlines()[:40])[:3000]
        lines.append(f"{label}:\n{output or '(no output)'}")
    return "\n".join(lines)


def run():
    print(reading())
    return 0  # Missing readings must not prevent a seat from starting.
