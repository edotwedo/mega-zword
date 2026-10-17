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
