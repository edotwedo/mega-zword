import importlib.util
import json
import hashlib
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("backup_hive_room", Path(__file__).parents[1] / "scripts" / "backup_hive_room.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class FakeRoom:
    url = "https://room.example"
    room = "hive"

    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def request(self, method, suffix):
        self.calls.append((method, suffix))
        return {"messages": next(self.pages)}


def row(i):
    return {"id": i, "author": "test-seat", "text": "hello", "time": "2026-10-18T00:00:00Z"}


def test_pagination_and_verified_export(tmp_path):
    remote = FakeRoom([[row(i) for i in range(1, 201)], [row(202)]])
    dest = tmp_path / "export"
    result = backup.export_room(remote, dest)
    assert remote.calls == [("GET", "?since=0&limit=200"), ("GET", "?since=200&limit=200")]
    saved = (dest / "messages.json").read_bytes()
    assert json.loads(saved)["count"] == result["count"] == 201
    assert result["last_id"] == 202
    assert (dest / "SHA256SUMS").read_text().split()[0] == hashlib.sha256(saved).hexdigest()


@pytest.mark.parametrize("page", [[row(1), row(1)], [row(0)], [{"id": 1}], None, [dict(row(1), id=True)]])
def test_invalid_page_writes_nothing(tmp_path, page):
    dest = tmp_path / "export"
    with pytest.raises(ValueError):
        backup.export_room(FakeRoom([page]), dest)
    assert not dest.exists()


def test_existing_destination_preserved(tmp_path):
    marker = tmp_path / "messages.json"
    marker.write_text("prior backup")
    with pytest.raises(FileExistsError):
        backup.export_room(FakeRoom([[]]), tmp_path)
    assert marker.read_text() == "prior backup"


def test_page_limit_writes_nothing(tmp_path):
    dest = tmp_path / "export"
    with pytest.raises(ValueError):
        backup.export_room(FakeRoom([[row(i) for i in range(1, 201)]]), dest, max_pages=1)
    assert not dest.exists()
