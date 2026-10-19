"""Manual, read-only room transcript export; not a full D1 or machine backup."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from megazword import config
from megazword.room import RemoteRoom


def export_room(remote, destination: Path, *, max_pages: int = 10000) -> dict:
    """Read every page without flushing pending messages or updating the cache."""
    rows, cursor = [], 0
    for _ in range(max_pages):
        page = remote.request("GET", f"?since={cursor}&limit=200").get("messages")
        if not isinstance(page, list) or len(page) > 200:
            raise ValueError("Invalid message page")
        for row in page:
            if (not isinstance(row, dict) or type(row.get("id")) is not int
                    or row["id"] <= cursor
                    or any(not isinstance(row.get(k), str) for k in ("author", "text", "time"))):
                raise ValueError("Invalid or non-increasing message record")
            cursor = row["id"]
            rows.append({k: row[k] for k in ("id", "author", "text", "time")})
        if len(page) < 200:
            break
    else:
        raise ValueError("Export page limit reached; no export written")

    payload = {"format": "megazword-room-transcript-v1", "origin": remote.url,
               "room": remote.room, "exported_at": datetime.now(timezone.utc).isoformat(),
               "count": len(rows), "last_id": cursor, "messages": rows}
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # A fresh directory prevents overwriting a prior recovery point.
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / "messages.json"
    with path.open("xb") as stream:
        stream.write(data)
    saved = path.read_bytes()
    if saved != data or json.loads(saved) != payload:
        raise OSError("Export verification failed")
    digest = hashlib.sha256(saved).hexdigest()
    with (destination / "SHA256SUMS").open("x", encoding="ascii") as stream:
        stream.write(f"{digest}  messages.json\n")
    if (destination / "SHA256SUMS").read_text(encoding="ascii") != f"{digest}  messages.json\n":
        raise OSError("Checksum verification failed")
    return {"count": len(rows), "last_id": cursor, "sha256": digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New directory in private local storage")
    parser.add_argument("--room", default="hive")
    args = parser.parse_args()
    try:
        result = export_room(RemoteRoom(args.room, config.load(), None), args.destination)
    except Exception:
        # HTTP errors or third-party exception text may contain credentials/message text.
        print("Export failed; check credentials, network and a fresh writable private destination. No server data was changed.")
        return 1
    print(f"Verified {result['count']} messages through ID {result['last_id']}; SHA256 {result['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
