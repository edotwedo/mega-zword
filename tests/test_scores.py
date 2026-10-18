from megazword import config, job
from megazword.cli import main
from megazword.scores import format_scores, load_reports, scoreboard


def piece(status, ai="", tried=None, est=None):
    row = {"status": status, "ai": ai, "tried": tried}
    if est is not None:
        row["est_tokens"] = est
    return row


def test_scoreboard_counts_deliveries_and_failed_tries():
    reports = [{"results": [piece("passed", "groq", ["nvidia", "groq"], 100),
                            piece("failed", "", ["groq", "zai"])]},
               {"results": [piece("passed", "zai", None), piece("passed", "zai", ["zai"], 50)]}]
    rows = {r["ai"]: r for r in scoreboard(reports)}
    assert rows["groq"] == {"ai": "groq", "delivered": 1, "failed": 1, "est_tokens": 100, "pass_rate": 0.5}
    assert rows["zai"]["delivered"] == 2 and rows["zai"]["failed"] == 1 and rows["zai"]["est_tokens"] == 50
    assert rows["nvidia"]["delivered"] == 0 and rows["nvidia"]["pass_rate"] == 0.0


def test_scoreboard_sorts_best_first_and_skips_blank_names():
    reports = [{"results": [piece("passed", "b"), piece("passed", "a"), piece("passed", "c"),
                            piece("passed", "c"), piece("failed", "", ["a", ""])]}]
    assert [r["ai"] for r in scoreboard(reports)] == ["c", "b", "a"]
    assert scoreboard([]) == [] and scoreboard([{}]) == []


def test_load_reports_skips_bad_files(tmp_path):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "job.json").write_text('{"results": []}', encoding="utf-8")
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "job.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "list").mkdir()
    (tmp_path / "list" / "job.json").write_text("[]", encoding="utf-8")
    assert load_reports(tmp_path) == [{"results": []}]


def test_format_scores():
    assert format_scores([]) == "no job results yet"
    text = format_scores(scoreboard([{"results": [piece("passed", "groq", est=10), piece("failed", "", ["groq"])]}]))
    assert text.splitlines()[1].split() == ["groq", "1", "1", "50%", "10"]


def test_job_scores_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(job.config, "HOME", tmp_path)
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    assert main(["job", "scores"], backends={}, cfg=cfg) == 0
    assert "no job results yet" in capsys.readouterr().out
    (tmp_path / "jobs" / "j1").mkdir(parents=True)
    (tmp_path / "jobs" / "j1" / "job.json").write_text('{"results": [{"status": "passed", "ai": "zai"}]}', encoding="utf-8")
    assert main(["job", "scores"], backends={}, cfg=cfg) == 0
    assert "zai" in capsys.readouterr().out
