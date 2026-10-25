"""The rules land-gate, proved against real git: HEAD is what a push lands, not origin/main.

These are the PR #60 review fixes. `check` must look at the committed copy a push would actually
send, must still let a seat whose copy equals main through, must treat CRLF and LF as the same
file (Windows), and `approve` must refuse a ballot with no items. Local temp repos only, no
network.
"""

import hashlib
import json
import subprocess

import pytest

from megazword import rules


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True, timeout=30)


@pytest.fixture
def gated_repo(tmp_path, monkeypatch):
    """A one-file repo whose origin/main is HEAD, with `rules.REPO` pointed at it."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    # Deterministic bytes: the host's core.autocrlf must not rewrite what we commit.
    git(root, "config", "core.autocrlf", "false")
    (root / "docs").mkdir()
    rules_file = root / "docs" / "RULES.md"
    rules_file.write_bytes(b"v1\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "v1")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    monkeypatch.setattr(rules, "REPO", root)
    return root, rules_file


def record_approval(home, sha256, ballot="P9"):
    home.mkdir(parents=True, exist_ok=True)
    (home / "rules-approval.json").write_text(json.dumps({
        "file": "docs/RULES.md", "sha256": sha256, "ballot": ballot,
        "approved": "2026-01-01T00:00:00+00:00", "voters": ["Briar-20", "Nock-21"]}) + "\n",
        encoding="utf-8")


def test_crlf_and_lf_hash_the_same(tmp_path):
    """Windows writes CRLF; git stores LF. The same revision must hash the same."""
    lf = tmp_path / "lf.md"
    lf.write_bytes(b"one\ntwo\nthree\n")
    crlf = tmp_path / "crlf.md"
    crlf.write_bytes(b"one\r\ntwo\r\nthree\r\n")
    assert rules.hash_of(crlf) == rules.hash_of(lf)


def test_a_head_copy_neither_approved_nor_main_is_refused(gated_repo, tmp_path):
    """An unvoted commit to the rules file must fail, even though origin/main is untouched."""
    root, rules_file = gated_repo
    home = tmp_path / "home"
    record_approval(home, hashlib.sha256(b"v0\n").hexdigest())  # approved a different version
    rules_file.write_bytes(b"v2\n")                              # an unvoted edit, then commit it
    git(root, "add", ".")
    git(root, "commit", "-qm", "unvoted rules edit")

    allowed, message = rules.check(home=home, path=rules_file)
    assert allowed is False
    assert "changed without a vote" in message


def test_a_head_copy_identical_to_main_is_allowed(gated_repo, tmp_path):
    """A seat whose copy of the rules equals main's is not introducing an unvoted change."""
    root, rules_file = gated_repo
    home = tmp_path / "home"
    record_approval(home, hashlib.sha256(b"v0\n").hexdigest())
    (root / "unrelated.txt").write_bytes(b"an unrelated commit moves HEAD\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "unrelated")

    # HEAD moved, but its rules blob still equals origin/main's, so nothing unvoted is landing.
    assert rules.head_hash(rules_file) == rules.approved_hash(rules_file)
    allowed, message = rules.check(home=home, path=rules_file)
    assert allowed is True
    assert "P9" in message


def test_a_ballot_with_no_items_cannot_approve(tmp_path, monkeypatch):
    """No items means no counts, so whole-proposal "no" votes had nothing to reject against."""
    proposal = {"id": "P9", "question": "empty", "items": []}
    rows = [{"id": 1, "author": "Briar-20", "text": "Briar-20: vote P9 no"},
            {"id": 2, "author": "Nock-21", "text": "Nock-21: vote P9 no"},
            {"id": 3, "author": "Cinder-21", "text": "Cinder-21: vote P9 no"}]
    monkeypatch.setattr("megazword.vote.record", lambda identifier, home=None: proposal)
    path = tmp_path / "RULES.md"
    path.write_text("the rules\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no items"):
        rules.approve("P9", home=tmp_path, messages=rows, path=path)
    assert not rules.approval_path(tmp_path).exists()


def test_approve_then_check_round_trips_with_crlf_on_disk(gated_repo, tmp_path, monkeypatch):
    """The Windows bug: approve hashed the CRLF worktree, check the LF blob. They must agree."""
    root, rules_file = gated_repo
    rules_file.write_bytes(b"v1\r\n")  # a Windows checkout of the committed LF blob

    proposal = {"id": "P9", "question": "rules", "items": ["M1"]}
    rows = [{"id": 1, "author": "Briar-20", "text": "Briar-20: vote P9 M1=yes"},
            {"id": 2, "author": "Nock-21", "text": "Nock-21: vote P9 M1=yes"}]
    monkeypatch.setattr("megazword.vote.record", lambda identifier, home=None: proposal)
    home = tmp_path / "home"

    saved = rules.approve("P9", home=home, messages=rows, path=rules_file,
                          seats=["Briar-20", "Nock-21"])
    # The approval is the normalised hash, which is exactly what check reads back.
    assert saved["sha256"] == rules.hash_of(rules_file) == rules.head_hash(rules_file)

    allowed, message = rules.check(home=home, path=rules_file)
    assert allowed is True
    assert "P9" in message
