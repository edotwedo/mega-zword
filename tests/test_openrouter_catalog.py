import json

from megazword import cli, config, openrouter_catalog


def model(model_id, prompt="0", completion="0", params=("tools",), **extra):
    return {"id": model_id, "name": model_id.upper(),
            "context_length": 32768,
            "pricing": {"prompt": prompt, "completion": completion},
            "supported_parameters": list(params), **extra}


def test_free_tool_models_filters_prices_and_tool_support():
    payload = {"data": [
        model("z/free"), model("a:free", prompt="0.000001"),
        model("b:free", params=("temperature",)),
        "malformed", model("c:free", completion=None),
    ]}
    assert [item["id"] for item in openrouter_catalog.free_tool_models(payload)] == ["z/free"]


def test_free_models_cli_fetches_public_catalog_and_formats_result(monkeypatch, capsys):
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps({"data": [model("a:free")]}).encode()

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["timeout"] = timeout
        observed["ua"] = request.get_header("User-agent")
        return Response()

    monkeypatch.setattr(openrouter_catalog, "urlopen", fake_urlopen)
    assert cli.main(["free", "models"], {}, config.Config()) == 0
    output = capsys.readouterr().out
    assert "a:free" in output and "32,768 tokens" in output
    assert "Catalog only" in output
    from megazword import __version__
    assert observed == {"url": openrouter_catalog.CATALOG_URL,
                        "timeout": openrouter_catalog.TIMEOUT_SECONDS,
                        "ua": f"megazword/{__version__}"}


def test_catalog_failure_is_reported_without_traceback(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(openrouter_catalog, "urlopen", fail)
    assert openrouter_catalog.command() == 1
    assert "catalog request failed" in capsys.readouterr().err
