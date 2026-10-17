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
        assert request.get_header("User-agent") == "megazword/0.1.0b1"
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
