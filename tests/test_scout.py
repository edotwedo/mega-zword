import json
from unittest.mock import MagicMock, patch

from megazword import scout


def test_providers_from_endpoints_normal():
    payload = {
        "data": {
            "endpoints": [
                {"provider_name": "ProviderA", "pricing": {}},
                {"provider_name": "ProviderB", "pricing": {}},
                {"provider_name": "ProviderA", "pricing": {}},  # duplicate
            ]
        }
    }
    result = scout.providers_from_endpoints(payload)
    assert result == ["ProviderA", "ProviderB"]


def test_providers_from_endpoints_missing_fields():
    payload = {
        "data": {
            "endpoints": [
                {"provider_name": "ProviderA"},
                {"not_provider": "ProviderB"},
                {},
                {"provider_name": ""},  # empty string
                {"provider_name": "  ProviderC  "},  # whitespace
            ]
        }
    }
    result = scout.providers_from_endpoints(payload)
    assert result == ["ProviderA", "ProviderC"]


def test_providers_from_endpoints_empty():
    payload = {"data": {"endpoints": []}}
    assert scout.providers_from_endpoints(payload) == []

    payload = {"data": {}}
    assert scout.providers_from_endpoints(payload) == []

    payload = {}
    assert scout.providers_from_endpoints(payload) == []

    payload = {"data": {"endpoints": None}}
    assert scout.providers_from_endpoints(payload) == []


def test_fetch_endpoints_monkeypatched():
    # Mock the urlopen to return a fake response
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "data": {
            "endpoints": [
                {"provider_name": "FakeProvider", "pricing": {}},
            ]
        }
    }).encode('utf-8')
    mock_response.__enter__.return_value = mock_response

    with patch("megazword.scout.urlopen", return_value=mock_response) as mock_urlopen:
        result = scout.fetch_endpoints("test/model")
        mock_urlopen.assert_called_once()
        # Check that the request was made with the correct URL and headers
        args, kwargs = mock_urlopen.call_args
        request = args[0]
        assert request.full_url == "https://openrouter.ai/api/v1/models/test/model/endpoints"
        from megazword import __version__
        assert request.get_header("User-agent") == f"megazword/{__version__}"
        assert result == {
            "data": {
                "endpoints": [
                    {"provider_name": "FakeProvider", "pricing": {}},
                ]
            }
        }



def test_zero_price_litellm_keeps_only_listed_zero_costs():
    payload = {
        "sample_spec": {"litellm_provider": "x", "input_cost_per_token": 0, "output_cost_per_token": 0},
        "free/model": {"litellm_provider": "groq", "input_cost_per_token": 0, "output_cost_per_token": 0.0},
        "paid/model": {"litellm_provider": "groq", "input_cost_per_token": 1e-6, "output_cost_per_token": 0},
        "unknown/model": {"litellm_provider": "mystery"},
        "a/free": {"litellm_provider": "cerebras", "input_cost_per_token": 0, "output_cost_per_token": 0},
        "broken": "not a dict",
    }
    assert scout.zero_price_litellm(payload) == [
        {"provider": "cerebras", "model": "a/free"},
        {"provider": "groq", "model": "free/model"},
    ]


def test_known_families_come_from_key_names():
    known = scout.known_families()
    assert {"groq", "cerebras", "nvidia", "tencent", "zai", "mistral", "gemini"} <= known


def test_leads_merges_sources_new_first():
    rows = scout.leads({"openrouter": ["Groq", "Chutes", "DeepInfra"],
                        "litellm": ["groq", "deepinfra", ""]},
                       today="2026-10-16", known={"groq"})
    assert [r["provider"] for r in rows] == ["Chutes", "DeepInfra", "Groq"]
    deepinfra = rows[1]
    assert deepinfra["seen_in"] == ["litellm", "openrouter"]
    assert deepinfra["already_have"] is False
    assert rows[2]["already_have"] is True
    assert all(r["first_seen"] == "2026-10-16" and r["new"] for r in rows)


def test_leads_keeps_first_seen_and_marks_old():
    previous = [{"provider": "Chutes", "seen_in": ["openrouter"], "already_have": False,
                 "first_seen": "2026-10-01"}]
    rows = scout.leads({"openrouter": ["chutes", "SiliconFlow"]}, previous,
                       today="2026-10-16", known=set())
    assert rows[0]["provider"] == "SiliconFlow" and rows[0]["new"]
    assert rows[1] == {"provider": "Chutes", "seen_in": ["openrouter"], "already_have": False,
                       "first_seen": "2026-10-01", "new": False}


def test_update_leads_saves_and_keeps_unseen(tmp_path):
    path = tmp_path / "scout" / "leads.json"
    scout.update_leads({"openrouter": ["Chutes"]}, path, today="2026-10-01")
    rows = scout.update_leads({"litellm": ["SiliconFlow"]}, path, today="2026-10-16")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == rows
    assert {r["provider"]: r["first_seen"] for r in saved} == {
        "SiliconFlow": "2026-10-16", "Chutes": "2026-10-01"}
    assert [r["new"] for r in saved] == [True, False]


def test_update_leads_survives_broken_file(tmp_path):
    path = tmp_path / "leads.json"
    path.write_text("not json", encoding="utf-8")
    rows = scout.update_leads({"openrouter": ["Chutes"]}, path, today="2026-10-16")
    assert rows[0]["provider"] == "Chutes"


CATALOG = {"data": [
    {"id": "a/free-one", "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]},
    {"id": "b/free-two", "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]},
    {"id": "c/paid", "pricing": {"prompt": "1", "completion": "1"}, "supported_parameters": ["tools"]},
]}
ENDPOINTS = {
    "a/free-one": {"data": {"endpoints": [{"provider_name": "Chutes"}, {"provider_name": "Groq"}]}},
    "b/free-two": {"data": {"endpoints": [{"provider_name": "Chutes"}]}},
}
LITELLM = {"x": {"litellm_provider": "siliconflow", "input_cost_per_token": 0, "output_cost_per_token": 0}}


def fake_fetchers(**over):
    def endpoints(model_id):
        if model_id not in ENDPOINTS:
            raise AssertionError("paid model looked up: " + model_id)
        return ENDPOINTS[model_id]
    fetchers = dict(catalog=lambda: CATALOG, endpoints=endpoints, litellm=lambda: LITELLM)
    fetchers.update(over)
    return fetchers


def test_scout_command_prints_new_first_then_known(tmp_path):
    path = tmp_path / "leads.json"
    lines = []
    assert scout.command(path, lines.append, **fake_fetchers()) == 0
    assert lines[0] == "New providers (3):"
    assert "Known providers (0):" in lines
    groq = next(l for l in lines if "Groq" in l)
    assert "(have a key)" in groq and "openrouter" in groq
    assert any("a person checks" in l for l in lines)

    lines.clear()
    scout.command(path, lines.append, **fake_fetchers(litellm=lambda: {}))
    assert lines[0] == "New providers (0):"
    assert lines[1] == "Known providers (3):"
    assert any("siliconflow" in l for l in lines)  # kept although this run didn't see it


def test_scout_command_limits_lookups_and_reports_failures(tmp_path):
    asked = []

    def endpoints(model_id):
        asked.append(model_id)
        raise OSError("timed out")

    lines = []
    sources, problems = scout.gather(**fake_fetchers(endpoints=endpoints), limit=1)
    assert asked == ["a/free-one"]
    assert sources == {"litellm": ["siliconflow"]}
    assert problems == ["OpenRouter endpoints: 1 of 1 lookups failed"]


def test_scout_command_with_no_sources_keeps_file(tmp_path):
    path = tmp_path / "leads.json"
    path.write_text("[]", encoding="utf-8")

    def down():
        raise OSError("offline")

    lines = []
    assert scout.command(path, lines.append, catalog=down, litellm=down) == 1
    assert lines[-1] == "No sources answered; leads.json left as it was."
    assert path.read_text(encoding="utf-8") == "[]"


def test_scout_is_a_cli_command(monkeypatch, tmp_path):
    from megazword.cli import main
    called = []
    monkeypatch.setattr(scout, "command", lambda: called.append(1) or 0)
    assert main(["scout"]) == 0 and called


class FakeAPI:
    def __init__(self, reply=None, error=None, model="m", up=True):
        self.reply, self.error, self.model, self.up, self.calls = reply, error, model, up, []

    def available(self):
        return self.up

    def chat(self, messages, tools=None, timeout=None):
        self.calls.append((messages, tools, timeout))
        if self.error:
            raise RuntimeError(self.error)
        return self.reply


FINISH = {"tool_calls": [{"id": "1", "function": {"name": "finish", "arguments": '{"summary": "ok"}'}}]}


def test_probe_sends_one_finish_tool_call_per_free_api(monkeypatch, tmp_path):
    from megazword import agent, config, free_test
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(agent, "pace_call", lambda name, pace, deadline: None)
    monkeypatch.setattr(free_test.openrouter_catalog, "fetch_catalog", lambda: {})
    monkeypatch.setattr(free_test.openrouter_catalog, "free_tool_models", lambda c: [{"id": "free/model"}])
    good, text, broken = FakeAPI(FINISH), FakeAPI({"content": "ok"}), FakeAPI(error="HTTP 500 boom")
    grant, paid = FakeAPI(FINISH), FakeAPI(FINISH, model="paid/model")
    router, down, out = FakeAPI(FINISH, model="free/model"), FakeAPI(FINISH, up=False), FakeAPI(FINISH)
    backends = {"groq": good, "mistral": text, "cloudflare": broken, "tencent-glm-5.3": grant,
                "kimi": paid, "openrouter": router, "zai": down, "ovh": out}
    rows = {name: (ok, why) for name, ok, _, why in scout.probe(backends, out_now={"ovh"})}
    assert rows["groq"] == ("ok", "") and rows["openrouter"] == ("ok", "")
    assert rows["mistral"][0] == "failed" and "finish" in rows["mistral"][1]
    assert rows["cloudflare"] == ("failed", "HTTP 500 boom")
    assert rows["tencent-glm-5.3"][0] == "skipped" and not grant.calls  # one-time grant
    assert rows["kimi"][0] == "skipped" and not paid.calls  # not free on OpenRouter right now
    assert rows["ovh"] == ("skipped", "marked out") and not out.calls
    assert "zai" not in rows and not down.calls
    messages, tools, timeout = good.calls[0]
    assert len(good.calls) == 1 and [t["function"]["name"] for t in tools] == ["finish"]
    assert timeout == scout.PROBE_SECONDS
    # Named explicitly, a grant is probed; the exit code reports any failure.
    lines = []
    assert scout.test_command(backends, ["tencent-glm-5.3"], out=lines.append) == 0
    assert grant.calls and "tencent-glm-5.3" in lines[1] and " ok " in lines[1]
    assert scout.test_command(backends, ["cloudflare"], out=lines.append) == 1


def test_scout_test_flag_runs_the_probe(monkeypatch):
    from megazword import cli
    seen = []
    monkeypatch.setattr(scout, "test_command", lambda b, names, out_now: seen.append(names) or 0)
    monkeypatch.setattr(scout, "command", lambda: seen.append("leads") or 0)
    assert cli.main(["scout", "--test", "--provider", "groq"], backends={}) == 0
    assert cli.main(["scout"], backends={}) == 0
    assert seen == [["groq"], "leads"]
