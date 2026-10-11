"""Several megazword processes writing at once: no lost or torn lines."""

import json
import multiprocessing as mp
from pathlib import Path

from megazword.filelock import locked

WORKERS = 4


def _append_worker(path: str, worker: int, count: int, keep: int) -> None:
    from megazword import log
    for i in range(count):
        log.append(Path(path), max_lines=keep, backend=f"w{worker}", i=i, pad="x" * 60)


def _answers_worker(home: str, worker: int, count: int) -> None:
    from megazword import answers, config
    config.HOME = Path(home)
    for i in range(count):
        answers.add(f"p{worker}-{i}", "a" * 50, f"w{worker}", "proj", None, keep=50)


def _memory_worker(home: str, worker: int, count: int) -> None:
    from megazword.memory import Memory
    mem = Memory(Path(home), "proj", max_lines=40)
    for i in range(count):
        mem.add("done", f"w{worker}-{i} " + "y" * 80, by=f"w{worker}")


def run_all(target, args_for):
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=target, args=args_for(w)) for w in range(WORKERS)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
        assert p.exitcode == 0


def unbroken_tails(values_by_worker: dict, last: int) -> bool:
    """Trimming keeps the newest lines overall, so each worker that still has
    lines must have an unbroken run ending at its final one; any gap means a
    concurrent write lost a line."""
    return all(sorted(v) == list(range(min(v), last + 1))
               for v in values_by_worker.values() if v)


def by_worker(pairs) -> dict:
    out: dict = {}
    for worker, i in pairs:
        out.setdefault(worker, []).append(i)
    return out


def records(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]  # raises on any torn line


def test_parallel_appends_lose_nothing(tmp_path):
    p = tmp_path / "log.jsonl"
    run_all(_append_worker, lambda w: (str(p), w, 150, 10**9))
    rows = records(p)
    assert len(rows) == WORKERS * 150
    assert len({(r["backend"], r["i"]) for r in rows}) == WORKERS * 150


def test_trim_during_parallel_appends_keeps_the_newest(tmp_path):
    p = tmp_path / "log.jsonl"
    run_all(_append_worker, lambda w: (str(p), w, 300, 60))
    rows = records(p)
    assert len(rows) <= 60 * 1.2 + 1
    # Without the lock, a trim's rewrite can drop lines appended meanwhile.
    assert unbroken_tails(by_worker((r["backend"], r["i"]) for r in rows), 299)
    assert rows[-1]["i"] == 299  # the very last write overall survived


def test_parallel_answers_and_memory(tmp_path):
    run_all(_answers_worker, lambda w: (str(tmp_path), w, 40))
    rows = records(tmp_path / "answers.jsonl")
    assert len(rows) == 50
    pairs = (r["prompt"][1:].split("-") for r in rows)
    assert unbroken_tails(by_worker((w, int(i)) for w, i in pairs), 39)

    run_all(_memory_worker, lambda w: (str(tmp_path), w, 120))
    mem = records(tmp_path / "projects" / "proj" / "memory.jsonl")
    pairs = (r["text"].split(" ")[0][1:].split("-") for r in mem)
    assert unbroken_tails(by_worker((w, int(i)) for w, i in pairs), 119)


def test_lock_times_out_instead_of_hanging(tmp_path, capsys):
    p = tmp_path / "f.jsonl"
    ctx = mp.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold, args=(str(p), ready, release))
    holder.start()
    try:
        assert ready.wait(30)
        with locked(p, timeout=0.3) as got:
            assert got is False
        assert "writing anyway" in capsys.readouterr().err
    finally:
        release.set()
        holder.join(30)


def _hold(path, ready, release):
    with locked(Path(path)):
        ready.set()
        release.wait(30)
