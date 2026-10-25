"""Keep the Python and deployed Worker claim grammars in step, without network.

Read the Worker's real regexes AND execute its extracted parser: copying its rules
into this test would miss another drift in the code that actually protects claims.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from megazword import claims


WORKER = Path(__file__).resolve().parents[1] / "cloud" / "hive-room" / "index.js"
DESIGNATIONS = [
    ("Cinder-21", True), ("Harbor022", True), ("Briar-20", True),
    ("Nock-21", True), ("Forge-22", True), ("Word-28", True),
    ("B15", False), ("Phase2", False), ("3D-20", False), ("harbor022", True),
]
# Expected item, or None for ordinary speech / an unkeyed claim. A matching
# designation alone must never be enough to hold a claim.
BODIES = [
    ("claiming #21", "#21"), ("claiming item 21", "item 21"),
    ("claiming 'seat watch'", "'seat watch'"),
    ('claiming "seat watch"', '"seat watch"'),
    ("claiming `seat watch`", "`seat watch`"),
    ("CLAIMING 'Seat   Watch'", "'Seat   Watch'"),
    ("taking #22", "#22"), ("reserving 'room health'", "'room health'"),
    ("claiming #21. Also looking at #22", "#21"),
    ("claiming 'seat watch'\n#99 is unrelated", "'seat watch'"),
    ("claiming seat watch", None), ("claiming", None),
    ("claiming work about 'seat watch'", None),
    ("claiming 'x'", None), ("claiming ''", None),
    ("claiming '   '", None), ('claiming "  "', None),
    ("status - working on #21", None), ("not claiming #21", None),
    ("releasing 'seat watch'", None),
]
CASES = [(f"{name}: {body}", (name, item) if valid and item is not None else None)
         for name, valid in DESIGNATIONS for body, item in BODIES]
QUOTED_ITEMS = [
    ("'seat watch'", "seat watch"), ('"seat watch"', "seat watch"),
    ("`seat watch`", "seat watch"), ("  'Seat   Watch' trailing context", "seat watch"),
    ("'ab'", "ab"), ("'" + "x" * 60 + "'", "x" * 60),
    ("'" + "x" * 61 + "'", None), ("'x'", None), ("''", None),
    ("work about 'seat watch'", None), ("seat watch", None),
    ("'two\nlines'", None),
]


@pytest.fixture(scope="module")
def worker_source():
    return WORKER.read_text(encoding="utf-8")


def extract(pattern, source, label):
    match = re.search(pattern, source, re.MULTILINE | re.DOTALL)
    assert match, f"Cannot extract Worker {label}; update this drift guard, do not skip it"
    return match.group(1)


@pytest.fixture(scope="module")
def worker_prefix(worker_source):
    pattern = extract(r"^const claimPrefix = /([^\n]+)/[a-z]*;", worker_source, "claimPrefix")
    return re.compile(pattern)


@pytest.fixture(scope="module")
def worker_quoted_rule(worker_source):
    body = extract(r"^const quotedName = text => \{\n(.*?)^\};", worker_source, "quotedName")
    pattern = extract(r"const match = /([^\n]+)/[a-z]*\.exec\(", body, "quoted-name regex")
    return re.compile(pattern)


def test_designation_pattern_is_identical(worker_prefix):
    # A pattern-only edit on either side must fail even if the fixture list happens
    # not to exercise the newly changed character class or length limit.
    worker_designation = extract(r"^\^\((.*?)\)", worker_prefix.pattern, "designation pattern")
    assert worker_designation == claims.DESIGNATION


@pytest.mark.parametrize("name,valid", DESIGNATIONS)
def test_designations_match_and_near_misses_do_not(worker_prefix, name, valid):
    text = f"{name}: claiming #21"
    assert bool(worker_prefix.match(text)) is valid
    assert bool(claims.PREFIX.match(text)) is valid


@pytest.mark.parametrize("item,expected", QUOTED_ITEMS)
def test_leading_quoted_item_rule_agrees(worker_quoted_rule, item, expected):
    match = worker_quoted_rule.match(item)
    worker_name = " ".join(match[1].lower().split()) if match else None
    python_names = {key for key in claims.item_keys(item) if isinstance(key, str)}
    assert worker_name == expected
    assert python_names == ({expected} if expected is not None else set())


@pytest.fixture(scope="module")
def worker_results(worker_source):
    # This block contains the actual prefix, claim verb, item-number and quoted
    # rules, plus claimFromText's decision to accept either type of item.
    parser = extract(r"(^const claimPrefix = .*?)(?=^function activeClaims\()",
                     worker_source, "claim parser block")
    node = shutil.which("node")
    assert node, "Node.js is required to check the Worker's actual claim parser"
    program = parser + """
const fs = require('node:fs');
const inputs = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = inputs.map(text => {
  const claim = claimFromText(text);
  return claim ? [claim.designation, claim.item] : null;
});
process.stdout.write(JSON.stringify(results));
"""
    result = subprocess.run([node, "-e", program],
                            input=json.dumps([text for text, _ in CASES]),
                            capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, f"Worker parser execution failed: {result.stderr}"
    rows = json.loads(result.stdout)
    assert len(rows) == len(CASES)
    return [tuple(row) if row is not None else None for row in rows]


@pytest.mark.parametrize("index,text,expected", [(i, *case) for i, case in enumerate(CASES)],
                         ids=[text for text, _ in CASES])
def test_worker_and_python_agree_on_claims(worker_results, index, text, expected):
    assert claims.claim_from_text(text) == expected
    assert worker_results[index] == expected
