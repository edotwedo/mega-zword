"""WIP cap tests: room text is authoritative; transport is always fake."""

import pytest

from megazword import config, room
from megazword.claims import active_claims, claim_conflicts, kind_of, kinds_of
from megazword.cli import main


def message(text, id=1, author="claude-pc"):
    return dict(text=text, id=id, time="2026-10-19T12:00:00Z", author=author)


def test_claim_parsing_uses_text_prefix_and_preserves_metadata():
    rows = [message("Cedar-21: CLAIMING roadmap #10", 4),
            message("Birch-22: claiming item 11", 5),
            message("quoted Cedar-23: claiming #12"),
            message("claiming #13", author="Willow-24")]
    assert active_claims(rows) == {
        "Cedar-21": ("roadmap #10", 4, rows[0]["time"]),
        "Birch-22": ("item 11", 5, rows[1]["time"]),
    }


def test_kind_of_labels_a_line_without_policing_it():
    # The point of a kind is to label what was said, not to refuse it. A claim is still
    # the only thing the ledger acts on, and this never overrides that.
    assert kind_of("Harbor022: claiming #3") == ("Harbor022", "claim", "claiming #3")
    assert kind_of("Cinder-21: assigned #A1 to Briar-20")[1] == "assign"
    assert kind_of("Nock-21: done on seat/nock-21")[1] == "done"
    assert kind_of("Briar-20: blocked on the Worker deploy")[1] == "blocked"
    assert kind_of("Forge-22: retire - context window full")[1] == "retire"
    assert kind_of("Cinder-21: online - awaiting assignment")[1] == "online"
    assert kind_of("no designation on this line") is None


def test_an_unrecognised_verb_is_a_note_never_an_error():
    # Most of the room is prose. A parser that refuses prose is one nobody keeps using.
    assert kind_of("Cinder-21: I think the claim leash is too short")[1] == "note"


def test_kinds_of_keeps_order_and_drops_chatter():
    rows = [message("Cinder-21: claiming #4"), message("Cinder-21: hello everyone"),
            message("Cinder-21: done #4"), message("no designation here")]
    assert [kind for _designation, kind, _body in kinds_of(rows)] == ["claim", "done"]


def test_a_designation_without_a_hyphen_is_still_a_designation():
    # Phil named a seat "Harbor022" on 2026-10-21. The old pattern required a hyphen, so
    # that seat's claims never registered and `resume` dropped its roster row entirely.
    rows = [message("Harbor022: claiming #21")]
    assert list(active_claims(rows)) == ["Harbor022"]


def test_a_spec_section_name_is_not_read_as_a_designation():
    # "B15" is a SPEC section. Three letters minimum keeps ordinary text ordinary, so a
    # line starting "B15: ..." cannot be mistaken for a seat claiming work.
    assert active_claims([message("B15: claiming #9")]) == {}


@pytest.mark.parametrize("release", ["releasing", "released", "landed #10", "item 10 done",
                                     "roadmap #10 done"])
def test_release_and_reclaim(release):
    rows = [message("Cedar-21: claiming roadmap #10"),
            message("cedar-21: " + release),
            message("Cedar-21: claiming item 11", 3)]
    assert active_claims(rows)["Cedar-21"][0:2] == ("item 11", 3)


def test_another_seat_closes_a_dead_claim_when_it_names_the_item():
    # Reversed deliberately (2026-10-19). Holder-only release looked safer, but a
    # seat went dark holding #4: the conductor reassigned and shipped it and the
    # ledger still showed the dead seat holding it, so `room claims` - the ledger
    # the WIP cap trusts - told the next worker the item was taken. A re-claim
    # costs one line; a stale claim blocks real work.
    rows = [message("Cinder-21: claiming #4"), message("Quill-21: #4 job cost is landed")]
    assert active_claims(rows) == {}


def test_an_unrelated_or_negated_release_does_not_close_a_claim():
    rows = [message("Cedar-21: claiming #10"), message("Birch-22: done #100"),
            message("Birch-22: #10 is not done yet")]
    assert active_claims(rows)["Cedar-21"][0] == "#10"


def test_other_claim_verbs_count_too():
    rows = [message("Beacon-17: taking #5"), message("Gauge-18: claiming #7")]
    claims = active_claims(rows)
    assert claims["Beacon-17"][0] == "#5"
    assert claims["Gauge-18"][0] == "#7"


def test_only_the_first_line_is_taken_as_the_item():
    rows = [message("Beacon-17: taking #5 now. Also landed #18 ages ago.\n#99 much later")]
    item = active_claims(rows)["Beacon-17"][0]
    assert item == "#5 now"
    assert item != "taking #5 now. Also landed #18"  # the sentence before the stop holds


def test_a_phrase_without_an_item_number_is_not_a_claim():
    # Widening the verbs made "taking conductor for the rest of the night" register
    # as a claim and block the room on a phrase, so a claim must point at an item.
    rows = [message("Quill-21: taking conductor for the rest of the night"),
            message("Quill-21: taking over the floor")]
    assert active_claims(rows) == {}


def test_newest_claim_wins_so_a_stale_first_claim_does_not_block():
    rows = [message("Cinder-21: claiming #4"), message("Cinder-21: claiming #8")]
    assert active_claims(rows)["Cinder-21"][0] == "#8"


def test_release_words_cover_merged_and_shipped():
    for word in ("merged", "shipped", "complete"):
        rows = [message("Cedar-21: claiming #10"), message(f"Cedar-21: #10 {word}")]
        assert active_claims(rows) == {}, word


def test_stale_window_can_be_shortened_for_a_night_shift(monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setenv("MEGAZWORD_CLAIM_STALE_MINUTES", "45")
    noon = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    rows = [message("Gauge-18: claiming #5 design")]
    assert active_claims(rows, now=noon + timedelta(minutes=44)) != {}
    assert active_claims(rows, now=noon + timedelta(minutes=46)) == {}


def test_named_non_numbered_item_done():
    assert active_claims([message("Cedar-21: claiming fix tests"),
                          message("Cedar-21: fix tests landed")]) == {}


def test_conflicts_use_item_number_not_lane():
    claims = active_claims([message("Cedar-21: claiming roadmap #10"),
                            message("Birch-22: claiming item 10"),
                            message("Oak-23: claiming #100")])
    assert claim_conflicts(claims) == [("Cedar-21", "Birch-22", 10)]


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.delenv("HIVE_ROOM_URL", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    return config.Config()


@pytest.mark.parametrize("text", ["cedar-21: claiming #11", "Birch-22: claiming item 10"])
def test_cli_refuses_cap_and_item_conflict(local, tmp_path, capsys, text):
    room.append_message("hive", "claude-pc", "Cedar-21: claiming #10", home=tmp_path)
    assert main(["room", "say", text], cfg=local, backends={}) == 1
    out = capsys.readouterr().out
    assert "post 'Cedar-21: releasing #10' first" in out
    assert len(out.splitlines()) == 1
    assert len(room.read_messages("hive", tmp_path)) == 1
    assert main(["room", "say", text, "--force"], cfg=local, backends={}) == 0
    assert len(room.read_messages("hive", tmp_path)) == 2


def test_cli_claims_prints_claims_and_conflicts(local, tmp_path, capsys):
    for text in ["Cedar-21: claiming #10", "Birch-22: claiming item 10"]:
        room.append_message("hive", "claude-pc", text, home=tmp_path)
    assert main(["room", "claims"], cfg=local, backends={}) == 0
    out = capsys.readouterr().out
    assert "Cedar-21: #10" in out and "Birch-22: item 10" in out
    assert "Conflict: Cedar-21 and Birch-22 both claim #10" in out


@pytest.mark.parametrize("offline", [False, True])
def test_remote_refresh_once_and_unreadable_room_posts(local, tmp_path, monkeypatch, offline):
    monkeypatch.setenv("HIVE_ROOM_URL", "https://room.example")
    calls = []

    class FakeRoom:
        def __init__(self, *args):
            pass

        def refresh(self):
            calls.append("refresh")
            if offline:
                raise OSError("offline")

        def cached(self):
            calls.append("cached")
            # A live claim: the shared fixture date is fixed and goes stale after 24 h.
            from datetime import datetime, timezone
            return [dict(message("Cedar-21: claiming #10"), time=datetime.now(timezone.utc).isoformat())]

        def flush(self, text):
            calls.append(text)
            return 0

    monkeypatch.setattr(room, "RemoteRoom", FakeRoom)
    text = "Cedar-21: claiming #11"
    assert room.say("hive", text, cfg=local, home=tmp_path, write=lambda _: None) == (0 if offline else 1)
    # After posting, the claim is re-read once for the race check.
    assert calls == (["refresh", text, "refresh"] if offline else ["refresh", "cached"])


def test_a_claim_must_name_its_item(local, tmp_path):
    out = []
    text = "Beacon-17: claiming Phil-approved fixes: (1) announce, (2) the WIP check"
    assert room.say("hive", text, cfg=local, home=tmp_path, write=out.append) == 1
    assert "#N or a quoted 'name'" in out[0]
    assert not room.room_path("hive", tmp_path).exists()
    assert room.say("hive", "Fathom-19: claiming 'claim lock' (Phil's order)", cfg=local,
                    home=tmp_path, write=lambda _: None) == 0
    assert active_claims(room.read_messages("hive", tmp_path))["Fathom-19"][0].startswith("'claim lock'")


def test_quoted_names_conflict_and_release_like_numbers(local, tmp_path):
    rows = [message("Fathom-19: claiming 'Claim  Lock'", 1), message("Beacon-17: taking 'claim lock' too", 2)]
    assert claim_conflicts(active_claims(rows)) == [("Fathom-19", "Beacon-17", "claim lock")]
    rows.append(message("Lumen-20: claim lock landed on main", 3))
    assert active_claims(rows) == {}
    out = []
    room.say("hive", "Fathom-19: claiming 'claim lock'", cfg=local, home=tmp_path, write=lambda _: None)
    assert room.say("hive", "Beacon-17: claiming 'claim lock'", cfg=local, home=tmp_path, write=out.append) == 1
    assert "Fathom-19 has open claim" in out[0]


def test_two_claims_seconds_apart_the_later_one_backs_out(local, tmp_path, monkeypatch):
    """Both seats passed the check before either post landed: the earliest room id
    wins and the later seat posts its own release, which leaves the winner's claim."""
    from megazword import claims as claims_mod
    # Simulate the race: the pre-post check sees an empty room.
    real = room.claim_messages
    monkeypatch.setattr(room, "claim_messages", lambda *a: [])
    room.say("hive", "Fathom-19: claiming #10", cfg=local, home=tmp_path, write=lambda _: None)
    monkeypatch.setattr(room, "claim_messages", real)
    out = []
    state = {"first": True}

    def racing(*a):
        if state.pop("first", False):
            return []  # Beacon-17's check ran before Fathom-19's post arrived
        return real(*a)
    monkeypatch.setattr(room, "claim_messages", racing)
    assert room.say("hive", "Beacon-17: claiming #10 WIP cap", cfg=local, home=tmp_path, write=out.append) == 1
    assert "Fathom-19 claimed it first" in out[-1]
    rows = room.read_messages("hive", tmp_path)
    assert rows[-1].text == "Beacon-17: releasing my claim; Fathom-19 claimed it first."
    assert list(active_claims(rows)) == ["Fathom-19"]
    assert claims_mod.first_holder(rows, "Fathom-19", "#10") is None


def test_unreadable_local_room_posts(local, tmp_path, monkeypatch):
    monkeypatch.setattr(room, "read_messages", lambda *a: (_ for _ in ()).throw(OSError("unreadable")))
    assert room.say("hive", "Cedar-21: claiming #10", cfg=local, home=tmp_path) == 0
    assert "claiming #10" in room.room_path("hive", tmp_path).read_text()


def test_designation_with_lane_label_still_parses():
    claims = active_claims([message("Beacon-17 (claude-pc): claiming #9 spot warning")])
    assert claims["Beacon-17"][0] == "#9 spot warning"


def test_claims_older_than_a_day_expire():
    from datetime import datetime, timedelta, timezone
    rows = [message("Gauge-18: claiming #5 design")]
    noon = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    assert "Gauge-18" in active_claims(rows, now=noon + timedelta(hours=23))
    assert active_claims(rows, now=noon + timedelta(hours=25)) == {}
    assert "Gauge-18" in active_claims(rows)  # no clock: nothing expires


def test_a_quotation_inside_a_claim_is_not_an_item():
    rows = [message('Quill-21: taking conductor for the night - Phil\'s words, "conduct, own it"')]
    assert active_claims(rows) == {}
