"""`megazword job cost ID`: steps and tokens per model for one saved job.

Pins the two ways this readout could lie: counting another job's runs (the run
log is shared by every project) and presenting the token estimate as a bill.
"""

import json

from megazword import config, job, job_cost

JOB = "20261019-010203-abc123"


def write_job(home, job_id=JOB):
    folder = home / "jobs" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.json").write_text(json.dumps({"id": job_id, "pieces": []}), encoding="utf-8")


def write_log(home, records):
    path = home / "log.jsonl"
    path.write_text("".join(json.dumps({"time": "2026-10-19T01:00:00+00:00", **r}) + "\n"
                            for r in records), encoding="utf-8")
    return path


def run(home, job_id=JOB):
    lines = []
    code = job_cost.cost_job(job_id, home / "log.jsonl", write=lines.append)
    return code, "\n".join(lines)


def test_totals_steps_and_tokens_per_model(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    write_job(tmp_path)
    log = write_log(tmp_path, [
        {"backend": "claude", "project": JOB, "requests": 3, "est_tokens": 900, "ok": True},
        {"backend": "claude", "project": JOB, "requests": 2, "est_tokens": 100, "ok": False},
        {"backend": "codex", "project": JOB, "requests": 1, "est_tokens": 50, "ok": True},
    ])
    code, out = run(tmp_path, JOB)
    assert code == 0
    assert "6 steps in 3 attempts over 2 model(s), 1,050 est_tokens" in out
    # the expensive model is the first row read
    assert out.index("claude") < out.index("codex")


def test_another_projects_runs_are_not_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    write_job(tmp_path)
    write_log(tmp_path, [
        {"backend": "claude", "project": JOB, "requests": 1, "est_tokens": 10, "ok": True},
        {"backend": "claude", "project": "some-other-job", "requests": 9, "est_tokens": 9999, "ok": True},
        {"backend": "claude", "requests": 5, "est_tokens": 500, "ok": True},  # no project at all
    ])
    code, out = run(tmp_path, JOB)
    assert code == 0
    assert "10 est_tokens" in out and "9,999" not in out and "500" not in out


def test_the_estimate_says_what_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    write_job(tmp_path)
    write_log(tmp_path, [{"backend": "codex", "project": JOB, "requests": 1, "est_tokens": 4, "ok": True}])
    _, out = run(tmp_path, JOB)
    assert job_cost.TOKEN_NOTE in out
    assert "not billed tokens" in out


def test_a_job_with_no_logged_runs_says_so_rather_than_showing_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    write_job(tmp_path)
    write_log(tmp_path, [{"backend": "codex", "project": "other", "requests": 1, "est_tokens": 4}])
    code, out = run(tmp_path, JOB)
    assert code == 0
    assert "nothing in the run log" in out


def test_an_unknown_job_is_an_error_not_an_empty_table(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    write_log(tmp_path, [])
    code, out = run(tmp_path, "no-such-job")
    assert code == 1
    assert "no job no-such-job" in out


def test_steps_fall_back_to_one_when_the_log_omits_requests(tmp_path):
    rows = job_cost.by_model([{"backend": "grok", "est_tokens": 5}])
    assert rows == [{"ai": "grok", "steps": 1, "runs": 1, "ok": 0, "est_tokens": 5}]


def test_the_command_is_registered():
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    job.add_parser(sub)
    args = parser.parse_args(["job", "cost", JOB])
    assert args.job_cmd == "cost" and args.id == JOB
