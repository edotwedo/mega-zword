"""The ballot: parsing, one-vote-per-seat, and a tally read from the room.

Phil, 2026-10-21: the room votes on a change instead of one seat deciding and calling it agreed.
No network here - messages and the room's `say` are injected.
"""

import pytest

from megazword import vote


def message(text, author="phil", id=1):
    return {"id": id, "author": author, "text": text}


def test_a_whole_proposal_vote_is_parsed():
    assert vote.parse_vote("Briar-20: vote P1 yes | it stops duplicate edits") == (
        "Briar-20", "P1", {"": "yes"}, "it stops duplicate edits")


def test_per_item_votes_are_parsed():
    parsed = vote.parse_vote("Nock-21: vote P1 M1=yes M2=no M3=abstain | locks are unbuildable for me")
    assert parsed[1] == "P1"
    assert parsed[2] == {"M1": "yes", "M2": "no", "M3": "abstain"}
    assert parsed[3] == "locks are unbuildable for me"


def test_item_votes_win_over_a_stray_leading_word():
    parsed = vote.parse_vote("Cinder-21: vote P1 yes M1=no")
    assert parsed[2] == {"M1": "no"}


def test_lines_that_are_not_votes_are_ignored():
    for text in ("Briar-20: status - working", "vote P1 yes", "Briar-20: vote P1 maybe",
                 "Briar-20: I reviewed the draft"):
        assert vote.parse_vote(text) is None


def test_one_vote_per_seat_and_the_later_one_wins():
    rows = [message("Briar-20: vote P1 yes"), message("Nock-21: vote P1 no"),
            message("Briar-20: vote P1 no | changed my mind")]
    cast = vote.collect(rows, "P1")
    assert cast["briar-20"]["choices"] == {"": "no"}
    assert cast["nock-21"]["choices"] == {"": "no"}


def test_a_vote_for_another_proposal_does_not_count():
    rows = [message("Briar-20: vote P2 yes")]
    assert vote.collect(rows, "P1") == {}


def test_tally_counts_items_quorum_and_who_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(vote, "record", lambda identifier, home=None: {
        "id": "P1", "question": "the seven mechanisms", "items": ["M1", "M2"]})
    rows = [message("Briar-20: vote P1 M1=yes M2=yes"),
            message("Nock-21: vote P1 M1=yes M2=no"),
            message("Cinder-21: vote P1 M1=yes")]
    result = vote.tally(rows, "P1", seats=["Cinder-21", "Briar-20", "Nock-21", "Forge-22"])
    assert result["counts"]["M1"] == {"yes": 3, "no": 0, "abstain": 0}
    assert result["counts"]["M2"] == {"yes": 1, "no": 1, "abstain": 0}
    assert result["reached"] is True
    assert result["missing"] == ["Forge-22"]
    assert result["incomplete"] == ["Cinder-21"]  # voted M1 only

    text = vote.render(result)
    assert "M1: yes 3" in text and "not voted: Forge-22" in text
    assert "voted but skipped an item: Cinder-21" in text


def test_quorum_is_two_thirds_and_never_padded(tmp_path, monkeypatch):
    # Two thirds of the seats asked, floor of two: one vote can never decide a ballot alone.
    monkeypatch.setattr(vote, "record", lambda identifier, home=None: {"id": "P1", "question": "q", "items": []})
    seats = ["Cinder-21", "Briar-20", "Nock-21"]
    one = vote.tally([message("Briar-20: vote P1 yes")], "P1", seats=seats)
    assert one["quorum"] == 2 and one["reached"] is False

    two = vote.tally([message("Briar-20: vote P1 yes"), message("Nock-21: vote P1 no")], "P1", seats=seats)
    assert two["reached"] is True
    assert "no quorum (needs 2)" in vote.render(one)


def test_create_allocates_ids_and_announces(tmp_path):
    announced = []
    first = vote.create("replace the rules", ["M1", "M2"], home=tmp_path,
                        say=lambda room, text, author: announced.append(text))
    second = vote.create("another question", home=tmp_path, say=lambda room, text, author: announced.append(text))
    assert first["id"] == "P1" and second["id"] == "P2"
    assert "BALLOT P1 is open: replace the rules" in announced[0]
    assert "M1=yes|no|abstain" in announced[0]
    assert vote.proposal_path("P1", tmp_path).exists()


def test_cast_needs_a_seat_and_a_valid_choice():
    with pytest.raises(ValueError):
        vote.cast("P1", {"": "yes"}, seat="")
    with pytest.raises(ValueError):
        vote.cast("P1", {"": "maybe"}, seat="Briar-20")
    with pytest.raises(ValueError):
        vote.cast("P1", {"M1": "yes", "BOGUS": "no"}, seat="Briar-20")


def test_cast_posts_the_canonical_line():
    sent = []
    line = vote.cast("P1", {"M1": "yes", "M2": "no"}, "locks worry me", seat="Briar-20",
                     say=lambda room, text, author: sent.append(text))
    assert line == "Briar-20: vote P1 M1=yes M2=no | locks worry me"
    assert sent == [line]
    # and it parses back into the same vote
    assert vote.parse_vote(sent[0])[2] == {"M1": "yes", "M2": "no"}
