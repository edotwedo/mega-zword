"""Fake reviewers and a fake GitHub only: no network, no real models."""
import json
import subprocess
from types import SimpleNamespace

from megazword import config, review
from megazword.backends import Result


def test_parse_reads_findings_and_normalises_severity():
    text = ("- [HIGH] src/a.py:12 - divides by zero when list is empty\n"
            "* [med] b.py:3 — leaks the key into the log\nnot a finding")
    found = review.parse(text, "groq")
    assert [(f.severity, f.path, f.line) for f in found] == [("high", "src/a.py", 12), ("medium", "b.py", 3)]


def test_merge_ranks_independent_agreement_first():
    findings = (review.parse("- [low] a.py:10 - off by one in total", "groq")
                + review.parse("- [high] b.py:5 - y", "zai")
                + review.parse("- [medium] src/a.py:12 - total is off by one", "cloudflare"))
    merged = review.merge(findings)
    assert merged[0].path.endswith("a.py") and sorted(merged[0].by) == ["cloudflare", "groq"]
    assert merged[0].severity == "medium"
    assert merged[1].path == "b.py"


def test_one_reviewer_repeating_itself_does_not_count_as_agreement():
    merged = review.merge(review.parse("- [low] a.py:1 - x\n- [low] a.py:2 - x again", "groq"))
    assert all(len(m.by) == 1 for m in merged)


def test_clip_keeps_whole_files_and_names_the_rest():
    diff = "diff --git a/a.py b/a.py\n" + "+x\n" * 10 + "diff --git a/big.py b/big.py\n" + "+y\n" * 100
    shown, note = review.clip(diff, limit=60)
    assert "a/a.py" in shown and "big.py" not in shown and "big.py" in note


class Fake:
    def __init__(self, name, answer):
        self.name, self.answer, self.timeout = name, answer, 60

    def available(self):
        return True

    def run(self, prompt):
        assert "```diff" in prompt
        return Result(self.name, self.answer, True, 0.1)


def test_run_merges_free_reviewers(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c"], check=True)
    fakes = [Fake("groq", "- [high] a.py:1 - wrong value"), Fake("zai", "- [high] a.py:1 - x is wrong"),
             Fake("mistral", "no bugs found")]
    monkeypatch.setattr(review, "pick_reviewers", lambda *a, **k: fakes)
    cfg = SimpleNamespace(log_path=tmp_path / "log.jsonl", log_lines=100, timeouts={})
    out = []
    assert review.run(repo, {}, cfg, count=3, write=out.append) == 0
    text = "\n".join(out)
    assert "a.py:1 (2 reviewers agree)" in text and "No bugs found by: mistral" in text
    logged = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert {r["backend"] for r in logged} == {"groq", "zai", "mistral"}


def test_greptile_respects_monthly_allowance(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    (tmp_path / "reviews.jsonl").write_text("\n".join(
        json.dumps({"time": now, "reviewer": "greptile", "credits": 1}) for _ in range(50)))
    findings, status = review.greptile(tmp_path, "x")
    assert findings == [] and "50/50" in status


def test_greptile_opens_collects_and_closes_pr(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    calls = []
    monkeypatch.setattr(review, "git", lambda repo, *a, **k: SimpleNamespace(
        returncode=0, stdout="abc1234\n", stderr=""))

    def gh(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("pr", "create"):
            return SimpleNamespace(returncode=0, stdout="https://github.com/edotwedo/mega-zword/pull/7\n", stderr="")
        if args[0] == "api" and args[1].endswith("/pulls/7/comments"):
            body = [{"user": {"login": "greptile-apps[bot]"}, "path": "src/a.py", "line": 4,
                     "body": "Null check missing"}]
            return SimpleNamespace(returncode=0, stdout=json.dumps(body), stderr="")
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")
    monkeypatch.setattr(review, "_gh", gh)
    findings, status = review.greptile(tmp_path, "x", sleep=lambda s: None)
    assert findings[0].path == "src/a.py" and findings[0].line == 4 and findings[0].by == ["greptile"]
    assert ("pr", "close", "7", "--repo", "edotwedo/mega-zword", "--delete-branch") in calls
    assert review.greptile_used_this_month(tmp_path / "reviews.jsonl") == 1


class Broken(Fake):
    def run(self, prompt):
        return Result(self.name, "", False, 0.1, "API returned an invalid or empty chat response")


def test_failed_reviewer_is_replaced_by_a_spare(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c"], check=True)
    picked = [Fake("groq", "no bugs found"), Broken("zai", ""), Fake("nvidia-lightning", "no bugs found"),
              Fake("ovh", "never asked")]
    monkeypatch.setattr(review, "pick_reviewers", lambda backends, count, log_path=None: picked[:count])
    cfg = SimpleNamespace(log_path=tmp_path / "log.jsonl", log_lines=100, timeouts={})
    out = []
    merged, raw, _ = review.collect(repo, {}, cfg, count=2, write=out.append)
    assert set(raw) == {"groq", "nvidia-lightning"}  # two completed reviews despite zai failing
    assert any("asking nvidia-lightning" in line for line in out)


def test_tiny_models_never_review():
    from megazword import routing
    from megazword.free_apis import OpenAICompatibleBackend

    class Up(OpenAICompatibleBackend):
        def available(self):
            return True
    names = ["groq-allam", "mistral", "groq", "zai"]
    backends = {n: Up(n, base_url="https://example.test/v1", model="m", key_env="X") for n in names}
    chosen = [b.name for b in review.pick_reviewers(backends, 4)]
    assert chosen and not set(chosen) & set(routing.WEAK_BACKENDS)


def test_greptile_badges_become_severity_and_title():
    body = ("**<sub><sub>![P1 Badge](https://img.shields.io/badge/P1-orange?style=flat)</sub></sub>  "
            "Require successful verdicts before merging**\n\nWhen no reviewers are available, "
            "every call fails. Thus unreviewed code merges.")
    assert review._badge(body) == ("high", "Require successful verdicts before merging: "
                                           "When no reviewers are available, every call fails.")
    low = "**![P3 Badge](x) Tidy a name**\n\nRename it."
    assert review._badge(low) == ("low", "Tidy a name: Rename it.")
    assert review._badge("plain text, no badge") == ("medium", "plain text, no badge")


def test_greptile_waits_for_line_comments_to_settle(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(review, "git", lambda repo, *a, **k: SimpleNamespace(
        returncode=0, stdout="abc1234\n", stderr=""))
    monkeypatch.setattr(review, "_gh", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="https://github.com/edotwedo/mega-zword/pull/8\n" if a[:2] == ("pr", "create") else "",
        stderr=""))
    rounds = [[], ["- [low] a.py:1 - summary"],
              ["- [low] a.py:1 - summary", "- [high] a.py:5 - bug", "- [medium] b.py:2 - risk"]]
    polls = []

    def comments(number):
        polls.append(number)
        return rounds[min(len(polls) - 1, len(rounds) - 1)]
    monkeypatch.setattr(review, "_greptile_comments", comments)
    findings, status = review.greptile(tmp_path, "x", sleep=lambda s: None)
    assert len(findings) == 3 and "3 comment(s)" in status
    assert len(polls) == 4  # nothing, summary, all three, all three again: settled


def test_different_problems_on_nearby_lines_are_not_agreement():
    findings = (review.parse("- [high] a.py:10 - missing null check on user", "groq")
                + review.parse("- [high] a.py:12 - timeout never cancelled", "zai")
                + review.parse("- [high] a.py:12 - the timeout leaks", "ovh"))
    merged = review.merge(findings)
    assert [sorted(f.by) for f in merged] == [["ovh", "zai"], ["groq"]]
    assert [f.line for f in review.blocking(merged)] == [12]


def test_greptile_credit_is_reserved_and_refunded_when_no_pr(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    deleted = []
    monkeypatch.setattr(review, "git", lambda repo, *a, **k: deleted.append(a) or SimpleNamespace(
        returncode=0, stdout="abc1234\n", stderr=""))
    monkeypatch.setattr(review, "_gh", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="no access"))
    findings, status = review.greptile(tmp_path, "x", sleep=lambda s: None)
    assert findings == [] and "PR not created: no access" in status
    assert ("push", "github", "--delete", "review/abc1234") in deleted
    assert review.greptile_used_this_month(tmp_path / "reviews.jsonl") == 0  # reserved, then refunded


def test_greptile_with_another_base_warns(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "change", lambda repo, base=None: ("diff --git a/a b/a\n+x\n", "label"))
    monkeypatch.setattr(review, "pick_reviewers", lambda *a, **k: [])
    monkeypatch.setattr(review, "greptile", lambda repo, label: ([], "greptile: done"))
    cfg = SimpleNamespace(log_path=tmp_path / "log.jsonl", log_lines=100, timeouts={})
    out = []
    review.collect(tmp_path, {}, cfg, base="v1.0", use_greptile=True, write=out.append)
    assert any("Greptile reviews against main" in line for line in out)


def test_review_bounds_free_reviewer_timeouts(tmp_path, monkeypatch):
    fakes = [Fake("cloudflare", "no bugs found"), Fake("slow-model", "no bugs found")]
    fakes[0].timeout = 600
    fakes[1].timeout = 600
    monkeypatch.setattr(review, "change", lambda repo, base=None: ("diff --git a/a b/a\n+x\n", "label"))
    monkeypatch.setattr(review, "pick_reviewers", lambda *a, **k: fakes)
    cfg = SimpleNamespace(log_path=tmp_path / "log.jsonl", log_lines=100, timeouts={"slow-model": 60})
    review.collect(tmp_path, {}, cfg, count=2, write=lambda s: None)
    assert fakes[0].timeout == review.DEFAULT_REVIEW_TIMEOUT
    assert fakes[1].timeout == 60
