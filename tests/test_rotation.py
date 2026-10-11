"""Log and memory files are capped; decisions are never dropped."""

import json

from megazword import config, log
from megazword.memory import Memory


def lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_log_trims_to_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(log, "_BYTES_PER_LINE_GUESS", 1)
    p = tmp_path / "log.jsonl"
    for i in range(30):
        log.append(p, max_lines=10, backend="x", n=i)
    kept = [json.loads(l)["n"] for l in lines(p)]
    assert len(kept) <= 12 and kept[-1] == 29 and kept == sorted(kept)


def test_small_files_are_left_alone(tmp_path):
    p = tmp_path / "log.jsonl"
    for i in range(30):
        log.append(p, max_lines=20, backend="x", n=i)
    # 30 lines is past 20 * 1.2, but the file is under the byte pre-check
    # (20 lines * 120 bytes), so it isn't even read yet.
    assert len(lines(p)) == 30


def test_memory_keeps_every_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(log, "_BYTES_PER_LINE_GUESS", 1)
    mem = Memory(tmp_path, "p", max_lines=5)
    mem.add("decision", "rule A")
    for i in range(40):
        mem.add("done", f"run {i}")
    mem.add("decision", "rule B")
    entries = mem.entries()
    texts = [e.text for e in entries]
    assert "rule A" in texts and "rule B" in texts and "run 39" in texts
    assert len([e for e in entries if e.kind != "decision"]) <= 6


def test_limits_load_from_config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[limits]\nlog_lines = 100\nmemory_lines = -5\n")
    cfg = config.load(p)
    assert cfg.log_lines == 100 and cfg.memory_lines == 2000
