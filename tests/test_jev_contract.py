"""Pin Jev answer shapes to the live OpenAPI spec. Skip when the network is down.

The spec is fetched, not vendored. A real schema change must fail here; the fix
is the parser, not a looser assertion.
"""

import inspect
import json
import re
import urllib.error
import urllib.request

import pytest

from megazword import decision
from megazword.decision import noul_probability

SPEC_URL = "https://api.typesafe.ai/openapi.json"


def _spec():
    try:
        with urllib.request.urlopen(SPEC_URL, timeout=10) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"openapi unreachable: {exc}")
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503, 504):
            pytest.skip(f"openapi unreachable: HTTP {exc.code}")
        raise


def _schemas():
    return _spec()["components"]["schemas"]


def _required(schemas, name):
    return set(schemas[name].get("required") or [])


def _parser_noul_field() -> str:
    """The first field noul_probability treats as the official probability."""
    source = inspect.getsource(noul_probability)
    found = re.search(r"""['"](\w+)['"]\s+in answer""", source)
    return found.group(1) if found else ""


def _drift(kind, spec_fields, parser_fields):
    spec_only = ", ".join(sorted(spec_fields - parser_fields)) or "(none)"
    parser_only = ", ".join(sorted(parser_fields - spec_fields)) or "(none)"
    return f"{kind}: spec requires {spec_only}; parser reads {parser_only}"


def test_noul_answer_matches_parser():
    required = _required(_schemas(), "NoulAnswer")
    assert required == {"type", "noul"}
    parser = {"type", _parser_noul_field()}
    if required != parser:
        pytest.fail(_drift("NoulAnswer", required, parser))
    # Docs shape. A reader that looks at "probability" first fails this.
    assert noul_probability({"type": "noul", "noul": 0.91, "probability": 0.1}) == 0.91
    from megazword.quality import jev_check
    source = inspect.getsource(decision.noul_probability) + inspect.getsource(jev_check)
    assert '["confidence"]' not in source and 'get("confidence")' not in source


def test_choice_score_and_box_required_fields():
    schemas = _schemas()
    assert _required(schemas, "ChoiceAnswer") == {"type", "choice", "confidence", "probabilities"}
    assert _required(schemas, "ScoreAnswer") == {
        "type", "score", "confidence", "legend", "probabilities"}
    assert _required(schemas, "BoxAnswer") == {"type", "box", "confidence"}
    confidence = schemas["BoxAnswer"]["properties"]["confidence"]
    nullable = any(option.get("type") == "null" for option in confidence.get("anyOf", []))
    assert nullable, "BoxAnswer.confidence must be nullable"


def test_response_requires_usage_and_parser_keeps_it():
    required = _required(_schemas(), "SystemOneResponse")
    assert required == {"model", "answers", "usage"}
    source = inspect.getsource(decision.JevDecision.choose)
    if "usage" not in source or "input_tokens" not in source:
        pytest.fail("SystemOneResponse: spec requires usage; parser discards it")


def test_score_stays_fractional():
    score = _schemas()["ScoreAnswer"]["properties"]["score"]
    assert score.get("type") == "number"
    assert 1.7 in score.get("examples", [])
    source = inspect.getsource(decision)
    assert "int(answer" not in source and "int(score" not in source
