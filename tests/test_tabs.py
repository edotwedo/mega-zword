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
