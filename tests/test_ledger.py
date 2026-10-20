import json
import sys
from argparse import Namespace
from datetime import datetime, timedelta, timezone

from megazword import agent, ledger
from megazword.routing import spread
from test_agent import call, coding


def _log(home, rows):
    log = home / "log.jsonl"
    log.write_text("\n".join(json.dumps({"backend": n, "time": t.isoformat(), "ok": True,
                                         "requests": 1, "est_tokens": k})
                             for n, t, k in rows), encoding="utf-8")
    return log


def test_tencent_grants_are_seeded_and_never_billable(tmp_path):
    entries = ledger.load(tmp_path)
    assert entries["tencent-kimi-k3"]["grant_tokens"] == 1_000_000
    assert not any(e["can_bill"] for e in entries.values())


def test_reported_use_plus_later_runs_gives_left_and_runway(tmp_path):
    now = datetime.now(timezone.utc)
    ledger.save({"tencent-kimi-k3": {"used_reported": 100_000,
                                     "reported_at": (now - timedelta(hours=1)).isoformat()}}, tmp_path)
    log = _log(tmp_path, [("tencent-kimi-k3", now - timedelta(hours=2), 999),  # before report
                          ("tencent-kimi-k3", now - timedelta(minutes=5), 30_000)])
    row = ledger.status("tencent-kimi-k3", ledger.load(tmp_path)["tencent-kimi-k3"], log, now)
    assert row["used"] == 130_000 and row["left"] == 870_000
    assert round(row["days_left"]) == round(870_000 / ((30_000 + 999) / 3))


def test_billable_or_used_up_sources_are_dropped_from_routing(tmp_path):
    ledger.save({"tencent-glm-5.3": {"can_bill": True},
                 "tencent-kimi-k3": {"used_reported": 1_000_000,
                                     "reported_at": datetime.now(timezone.utc).isoformat()}}, tmp_path)
    log = _log(tmp_path, [])
    names = ["tencent-glm-5.3", "tencent-kimi-k3", "tencent-deepseek-v4-pro", "groq", "claude"]
    assert spread(names, "hard", log) == ["tencent-deepseek-v4-pro", "groq", "claude"]


def test_credits_set_records_console_figures(tmp_path, capsys):
    args = Namespace(action="set", name="alibaba-qwen-coder", used=5, grant=1_000_000,
                     expires="2027-01-14", can_bill="yes")
    assert ledger.command(args, tmp_path, tmp_path / "log.jsonl") == 0
    saved = ledger.load(tmp_path)["alibaba-qwen-coder"]
    assert saved["can_bill"] and saved["expires"] == "2027-01-14"
    assert "can bill" in capsys.readouterr().out


def test_stale_tool_output_is_trimmed_and_cuts_resent_text(tmp_path, monkeypatch):
    body = "x = 1\n" * 1000
    script = [call("write_file", path="a.py", text=body),
              *[call("read_file", path="a.py") for _ in range(4)],
              call("run_tests"), call("finish", summary="done")]
    kwargs = dict(test_command=(sys.executable, "-c", "print('ok')"))
    monkeypatch.setattr(agent, "SMALL_HISTORY", {})  # compare trimming alone, not condensing

    trimmed, model = coding(tmp_path / "t", list(script), **kwargs)
    (tmp_path / "t").mkdir()
    assert trimmed.run("edit a").ok
    last = model.seen[-1][0]
    tool_outputs = [m["content"] for m in last if m["role"] == "tool"]
    assert tool_outputs[0] == "wrote a.py" and tool_outputs[1].startswith("[trimmed")
    assert "[trimmed" in json.dumps([m for m in last if m.get("tool_calls")][0])

    monkeypatch.setattr(agent.AgentBackend, "_trim_stale", staticmethod(lambda m, **k: None))
    full, _ = coding(tmp_path / "f", list(script), **kwargs)
    (tmp_path / "f").mkdir()
    assert full.run("edit a").ok
    assert trimmed.prompt_chars < full.prompt_chars * 0.85


def test_native_calls_skip_duplicate_schemas_and_unneeded_web_tool(tmp_path):
    loop, model = coding(tmp_path, [call("run_tests"), call("finish", summary="ok")],
                         test_command=(sys.executable, "-c", "print('ok')"))
    loop.run("rename a variable in a.py")
    messages, tools, _ = model.seen[0]
    assert "tool schemas are" not in messages[0]["content"]
    assert "fetch_public_url" not in json.dumps(messages) + json.dumps(tools)

    loop, model = coding(tmp_path, [call("finish", summary="ok")])
    loop.run("read https://example.com/docs and summarize")
    assert "fetch_public_url" in json.dumps(model.seen[0][1])


def test_newest_read_of_each_file_stays_whole_until_the_file_is_written():
    def asked(i, name, **args):
        return {"role": "assistant", "content": None,
                "tool_calls": [{"id": f"c{i}", "function": {"name": name, "arguments": json.dumps(args)}}]}

    def told(i, text):
        return {"role": "tool", "tool_call_id": f"c{i}", "content": text}
    big = "line\n" * 300
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"},
                asked(1, "read_file", path="a.py"), told(1, "A" + big),
                asked(2, "read_file", path="b.py"), told(2, "B" + big),
                asked(3, "read_file", path="c.py"), told(3, "C" + big),
                asked(4, "run_tests"), told(4, "T" + big),
                asked(5, "write_file", path="b.py", text="new"), told(5, "wrote b.py"),
                asked(6, "list_files"), told(6, "L" + big),
                asked(7, "run_tests"), told(7, "R" + big)]
    agent.AgentBackend._trim_stale(messages)
    out = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
    assert out["c1"].startswith("A") and out["c3"].startswith("C")   # reads still needed
    assert out["c2"].startswith("[trimmed")   # b.py was rewritten after this read
    assert out["c4"].startswith("[trimmed")   # old test output
    assert out["c6"].startswith("L") and out["c7"].startswith("R")   # newest two
    agent.AgentBackend._trim_stale(messages, keep=2, keep_reads=False)  # over budget: reads go too
    out = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
    assert out["c1"].startswith("[trimmed") and out["c7"].startswith("R")


def test_http_402_marks_the_grant_used_up_and_routing_skips_it(tmp_path, monkeypatch):
    import io
    import pytest
    import urllib.error
    import urllib.request
    from megazword import config, ledger, routing
    from megazword.free_apis import OpenAICompatibleBackend, APIHTTPError
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setenv("TENCENT_TOKENHUB_API_KEY", "secret-test-credential")

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 402, "Payment Required", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    backend = OpenAICompatibleBackend("tencent-glm-5.3", base_url="https://example.test/v1", model="glm-5.3",
                                      key_env="TENCENT_TOKENHUB_API_KEY")
    with pytest.raises(APIHTTPError) as caught:
        backend.chat([{"role": "user", "content": "hi"}])
    assert caught.value.code == 402 and "used up" in str(caught.value)
    assert ledger.blocked(["tencent-glm-5.3", "tencent-kimi-k3"], home=tmp_path,
                          log_path=tmp_path / "log.jsonl") == {"tencent-glm-5.3": "grant used up"}
    assert "HTTP 402" in ledger.table(tmp_path, tmp_path / "log.jsonl")
    log = tmp_path / "log.jsonl"
    log.write_text("", encoding="utf-8")
    assert "tencent-glm-5.3" not in routing.spread(["tencent-glm-5.3", "groq"], "hard", log)
    assert ledger.mark_used_up("tencent", "402", home=tmp_path)  # alias of deepseek-v4-pro
    assert "tencent-deepseek-v4-pro" in ledger.blocked(["tencent-deepseek-v4-pro"], home=tmp_path, log_path=log)
    assert not ledger.mark_used_up("groq", "402", home=tmp_path)
