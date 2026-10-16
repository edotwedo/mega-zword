"""Chat tabs: persist, pin, Auto route, out marks, history. Fakes only."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from megazword import answers, config, tabs
from megazword.backends import Backend
from megazword.rater import Rating


@dataclass
class Capture(Backend):
    calls: list = field(default_factory=list)
    reply: str = "ok"
    fail: bool = False
    installed: bool = True

    def available(self) -> bool:
        return self.installed

    def _run(self, prompt: str) -> str:
        self.calls.append(prompt)
        if self.fail:
            raise RuntimeError("boom")
        return f"{self.reply}: {prompt.splitlines()[-1][:40]}"


def backends():
    return {"claude": Capture("claude", reply="c"),
            "cheap": Capture("cheap", reply="cheap"),
            "strong": Capture("strong", reply="strong")}


def cfg(**kw):
    base = dict(route={"easy": ["cheap"], "medium": ["strong"], "hard": ["strong"]},
                log_path=config.HOME / "log.jsonl")
    base.update(kw)
    return config.Config(**base)


def rate(level="easy"):
    return lambda prompt: Rating(level, "test", "fake")


def test_backend_receives_only_its_tab_and_opted_in_project_memory():
    from megazword.memory import Memory
    models = backends()
    Memory(config.HOME, 'current').add('note', 'CURRENT_PROJECT_CONTEXT_MARKER')
    Memory(config.HOME, 'other').add('note', 'PRIVATE_OTHER_PROJECT_MARKER')
    own = tabs.create('cheap', 'current', backends=models)
    other = tabs.create('cheap', 'other', backends=models)
    tabs.send(other['id'], 'PRIVATE_OTHER_CONVERSATION_MARKER', models, cfg(), rate(), dict)
    tabs.send(own['id'], 'current task', models, cfg(), rate(), dict)
    sent = models['cheap'].calls[-1]
    assert 'CURRENT_PROJECT_CONTEXT_MARKER' not in sent
    assert 'PRIVATE_OTHER_PROJECT_MARKER' not in sent
    assert 'PRIVATE_OTHER_CONVERSATION_MARKER' not in sent
    tabs.send(own['id'], 'continue current task', models, cfg(), rate(), dict, context=True)
    sent = models['cheap'].calls[-1]
    assert 'CURRENT_PROJECT_CONTEXT_MARKER' in sent
    assert 'PRIVATE_OTHER_PROJECT_MARKER' not in sent
    assert 'PRIVATE_OTHER_CONVERSATION_MARKER' not in sent


def test_create_list_rename_close_persist():
    first = tabs.create("claude", "alpha", title="Work", backends=backends())
    assert first["id"] == "t1" and first["ai"] == "claude" and first["title"] == "Work"
    second = tabs.create("auto", "alpha")
    assert second["id"] == "t2"
    listed = tabs.list_tabs()
    assert [t["id"] for t in listed] == ["t1", "t2"]
    renamed = tabs.rename("t1", "Renamed")
    assert renamed["title"] == "Renamed"
    assert tabs.list_tabs()[0]["title"] == "Renamed"
    tabs.close("t1")
    assert [t["id"] for t in tabs.list_tabs()] == ["t2"]
    assert tabs.path().exists()
    again = tabs.create("auto", "alpha")
    assert again["id"] == "t1"


def test_unknown_ai_and_bad_project():
    with pytest.raises(ValueError, match="unknown AI"):
        tabs.create("nope", "alpha", backends=backends())
    with pytest.raises(ValueError, match="bad project"):
        tabs.create("auto", "../x")
    with pytest.raises(ValueError, match="empty title"):
        t = tabs.create("auto", "alpha")
        tabs.rename(t["id"], "  ")
    with pytest.raises(ValueError, match="no tab"):
        tabs.close("t99")


def test_max_tabs(monkeypatch):
    monkeypatch.setattr(tabs, "MAX_TABS", 2)
    tabs.create("auto", "alpha")
    tabs.create("auto", "alpha")
    with pytest.raises(ValueError, match="at most"):
        tabs.create("auto", "alpha")


def test_pinned_send_and_history_and_tab_id():
    bs = backends()
    tab = tabs.create("claude", "alpha", backends=bs)
    first = tabs.send(tab["id"], "hello", bs, cfg(), rate(), statuses=dict)
    assert first["ok"] and first["backend"] == "claude"
    assert "[New message]" in bs["claude"].calls[0]
    assert "hello" in bs["claude"].calls[0]
    second = tabs.send(tab["id"], "what next?", bs, cfg(), rate(), statuses=dict)
    assert second["ok"]
    assert "[Conversation so far]" in bs["claude"].calls[1]
    assert "User: hello" in bs["claude"].calls[1]
    stored = tabs.list_tabs()[0]
    assert len(stored["history"]) == 2
    rows = answers.recent()
    assert any(r.get("tab_id") == tab["id"] and r["prompt"] == "what next?" for r in rows)


def test_auto_send_uses_route():
    bs = backends()
    tab = tabs.create("auto", "alpha", backends=bs)
    out = tabs.send(tab["id"], "design a system", bs, cfg(), rate("medium"), statuses=dict)
    assert out["ok"] and out["backend"] == "strong"
    assert bs["cheap"].calls == [] and bs["strong"].calls


def test_auto_skips_out_pinned_still_sends():
    until = datetime.now(timezone.utc) + timedelta(days=1)
    bs = backends()
    auto = tabs.create("auto", "alpha", backends=bs)
    pinned = tabs.create("cheap", "alpha", backends=bs)
    route = {"easy": ["cheap", "strong"], "medium": ["strong"], "hard": ["strong"]}
    skipped = tabs.send(auto["id"], "hello", bs,
                        cfg(route=route, out_until={"cheap": until}),
                        rate("easy"), statuses=dict)
    assert skipped["ok"] and skipped["backend"] == "strong"
    forced = tabs.send(pinned["id"], "still go", bs,
                       cfg(route=route, out_until={"cheap": until}),
                       rate("easy"), statuses=dict)
    assert forced["ok"] and forced["backend"] == "cheap"


def test_send_failure_text():
    bs = {"claude": Capture("claude", fail=True)}
    tab = tabs.create("claude", "alpha", backends=bs)
    out = tabs.send(tab["id"], "hello", bs, cfg(), rate(), statuses=dict)
    assert not out["ok"] and out["error"] == "no AI gave a usable answer"


def test_empty_prompt_rejected():
    tab = tabs.create("auto", "alpha")
    with pytest.raises(ValueError, match="empty prompt"):
        tabs.send(tab["id"], "  ", backends(), cfg(), rate(), statuses=dict)


def test_changes_during_a_slow_answer_are_kept():
    """While one tab waits on its AI, another tab answers, one is renamed and one is closed."""
    bs = backends()
    a = tabs.create("claude", "alpha", backends=bs)
    b = tabs.create("cheap", "alpha", backends=bs)
    c = tabs.create("auto", "alpha", backends=bs)

    class Slow(Capture):
        def _run(self, prompt):
            tabs.send(b["id"], "meanwhile", bs, cfg(), rate(), statuses=dict)
            tabs.rename(a["id"], "Renamed")
            tabs.close(c["id"])
            return "slow answer"

    bs["claude"] = Slow("claude")
    out = tabs.send(a["id"], "take your time", bs, cfg(), rate(), statuses=dict)
    assert out["ok"] and out["answer"] == "slow answer"
    saved = {t["id"]: t for t in tabs.list_tabs()}
    assert set(saved) == {a["id"], b["id"]}                    # the closed tab stays closed
    assert saved[a["id"]]["title"] == "Renamed"                  # the rename survived
    assert [h["user"] for h in saved[a["id"]]["history"]] == ["take your time"]
    assert [h["user"] for h in saved[b["id"]]["history"]] == ["meanwhile"]


def test_send_does_not_change_the_shared_backends(monkeypatch):
    from megazword.backends import CLIBackend
    # Never run the real Claude CLI installed on this PC: make it look missing.
    monkeypatch.setattr("megazword.backends.shutil.which", lambda exe: None)
    shared = {"claude": CLIBackend("claude", exe="claude", args=["-p"])}
    tab = tabs.create("claude", "alpha", backends=shared)
    levels = {"claude": {"medium": ("opus", "high")}, "codex": {}, "gemini": {}}
    tabs.send(tab["id"], "hi", shared, cfg(levels=levels), rate(), statuses=dict)
    assert shared["claude"].args == ["-p"]


def test_damaged_tabs_file_reads_as_empty_and_bad_entries_are_dropped():
    tabs.path().parent.mkdir(parents=True, exist_ok=True)
    tabs.path().write_text("{not json", encoding="utf-8")
    assert tabs.list_tabs() == []
    tabs.path().write_text('["a list"]', encoding="utf-8")
    assert tabs.list_tabs() == []
    tabs.path().write_text('{"tabs": [5, {"title": "no id"}, {"id": "t1", "history": "x"}]}',
                           encoding="utf-8")
    assert [t["id"] for t in tabs.list_tabs()] == ["t1"]
    # Writing on top of a damaged file starts it fresh.
    made = tabs.create("claude", "default")
    assert made["id"] == "t2" and len(tabs.list_tabs()) == 2


def test_tab_pinned_to_an_uninstalled_ai_is_refused():
    tab = tabs.create("gone", "default")  # no backends given: any name is kept
    with pytest.raises(ValueError, match="unknown AI 'gone'"):
        tabs.send(tab["id"], "hi", backends(), cfg(), rate(), statuses=dict)


def test_auto_tab_with_no_ai_for_the_level_says_so():
    tab = tabs.create("auto", "default")
    result = tabs.send(tab["id"], "hi", backends(), cfg(route={"easy": [], "medium": [], "hard": []}),
                       rate(), statuses=dict)
    assert result["ok"] is False and "no installed AI for a easy task" in result["error"]
    assert tabs.list_tabs()[0]["history"] == []
