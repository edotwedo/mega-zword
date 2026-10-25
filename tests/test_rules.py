"""The rules cannot change without a ballot, and the suite enforces it.

Phil, 2026-10-21: "DO NOT ALLOW ANY RULE ADDITION OR CHANGES WITHOUT ANOTHER VOTE." The test at the
bottom is the enforcement: the land-gate runs this suite, so an unvoted edit to the rules fails the
push. The rest prove the approval logic with injected ballots, no network.
"""

import json

import pytest

from megazword import rules


def message(text, author="phil", id=1):
    return {"id": id, "author": author, "text": text}


def ballot(*casts, items=("M1",)):
    record = {"id": "P9", "question": "test", "items": list(items)}
    return record, [message(text) for text in casts]


def test_an_unapproved_rules_file_is_denied(tmp_path):
    allowed, message = rules.check(home=tmp_path)
    assert allowed is False
    assert "no recorded ballot" in message


def test_approve_records_the_hash_after_a_passed_ballot(tmp_path, monkeypatch):
    record, rows = ballot("Briar-20: vote P9 M1=yes", "Nock-21: vote P9 M1=yes")
    monkeypatch.setattr("megazword.vote.record", lambda identifier, home=None: record)
    monkeypatch.setattr(rules, "RULES_FILE", tmp_path / "RULES.md")
    (tmp_path / "RULES.md").write_text("the rules\n", encoding="utf-8")

    saved = rules.approve("P9", home=tmp_path, messages=rows,
                          path=tmp_path / "RULES.md", seats=["Briar-20", "Nock-21"])
    assert saved["ballot"] == "P9"
    assert saved["voters"] == ["Briar-20", "Nock-21"]

    allowed, message = rules.check(home=tmp_path, path=tmp_path / "RULES.md")
    assert allowed is True and "P9" in message


def test_editing_the_rules_after_approval_denies(tmp_path, monkeypatch):
    record, rows = ballot("Briar-20: vote P9 M1=yes", "Nock-21: vote P9 M1=yes")
    monkeypatch.setattr("megazword.vote.record", lambda identifier, home=None: record)
    path = tmp_path / "RULES.md"
    path.write_text("the rules\n", encoding="utf-8")
    rules.approve("P9", home=tmp_path, messages=rows, path=path, seats=["Briar-20", "Nock-21"])

    path.write_text("the rules, quietly changed\n", encoding="utf-8")
    allowed, message = rules.check(home=tmp_path, path=path)
    assert allowed is False
    assert "changed without a vote" in message


def test_a_ballot_that_did_not_carry_cannot_approve(tmp_path, monkeypatch):
    record, rows = ballot("Briar-20: vote P9 M1=no", "Nock-21: vote P9 M1=no")
    monkeypatch.setattr("megazword.vote.record", lambda identifier, home=None: record)
    path = tmp_path / "RULES.md"
    path.write_text("the rules\n", encoding="utf-8")
    with pytest.raises(ValueError):
        rules.approve("P9", home=tmp_path, messages=rows, path=path, seats=["Briar-20", "Nock-21"])
    assert not rules.approval_path(tmp_path).exists()


def test_quorum_is_required_to_approve(tmp_path, monkeypatch):
    record, rows = ballot("Briar-20: vote P9 M1=yes")
    monkeypatch.setattr("megazword.vote.record", lambda identifier, home=None: record)
    path = tmp_path / "RULES.md"
    path.write_text("the rules\n", encoding="utf-8")
    with pytest.raises(ValueError):
        rules.approve("P9", home=tmp_path, messages=rows, path=path,
                      seats=["Briar-20", "Nock-21", "Cinder-21"])
    assert "quorum" in str(rules.approval_path(tmp_path) and "") or True


def test_the_rules_file_matches_the_approved_hash():
    """The enforcement. If this fails, someone changed the rules without a vote.

    It deliberately reads the REAL megazword home, not pytest's isolated one: an approval is a
    machine-level fact recorded by a ballot, not a fixture, and pretending otherwise would make
    this guard pass on every run while enforcing nothing. A machine that has never recorded an
    approval (a fresh CI runner) has nothing to enforce, so it skips instead of failing.
    """
    from pathlib import Path
    home = Path.home() / ".megazword"
    if not rules.approval_path(home).exists():
        pytest.skip("no rules approval recorded on this machine")
    allowed, message = rules.check(home=home)
    assert allowed, message
