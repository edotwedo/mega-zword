"""Stand-in for `codex app-server` (JSON-RPC over stdio) used by test_codex_live.
Answers initialize and account/rateLimits/read; "silent" as argv[1] never answers."""

import json
import sys
import time

if len(sys.argv) > 1 and sys.argv[1] == "silent":
    time.sleep(60)
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("id") == 1:
        print(json.dumps({"id": 1, "result": {"userAgent": "fake"}}), flush=True)
    elif msg.get("id") == 2:
        print(json.dumps({"id": 2, "result": {"rateLimits": {
            "limitId": "codex",
            "primary": {"usedPercent": 10, "windowDurationMins": 300, "resetsAt": 1900000000},
            "secondary": {"usedPercent": 29, "windowDurationMins": 10080, "resetsAt": 1900500000},
        }}}), flush=True)
