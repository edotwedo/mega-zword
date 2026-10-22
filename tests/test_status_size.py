"""STATUS.md is a live file, not a changelog - ballot P2 item A1, carried 5-0.

Phil, 2026-10-21: the startup read cost ~36k tokens a session, 28k of it this one file at 112 KB.
The cap test is the part that matters: without it the file grows back, which is exactly how it got
to 112 KB in the first place.
"""

from pathlib import Path

LIMIT = 8192
DOCS = Path(__file__).resolve().parents[1] / "docs"


def test_live_status_stays_under_the_cap():
    size = (DOCS / "STATUS.md").stat().st_size
    assert size <= LIMIT, (
        f"docs/STATUS.md is {size} bytes; the cap is {LIMIT}. Move history into STATUS-ARCHIVE.md - "
        "every seat pays for this file at startup, on every session.")


def test_the_archive_keeps_the_history_verbatim():
    archive = DOCS / "STATUS-ARCHIVE.md"
    assert archive.exists(), "STATUS-ARCHIVE.md is missing; the split must not lose history"
    text = archive.read_text(encoding="utf-8")
    assert len(text) > 50_000, "the archive is too small - history was not actually moved"
    assert len(text.splitlines()) > 300
    assert "## " in text
