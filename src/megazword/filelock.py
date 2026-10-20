"""A small cross-process lock for Mega Zword's data files (stdlib only).

The dashboard runs jobs in parallel, so several megazword processes can
append to the same JSON-lines file while one of them trims it. Holding
`locked(path)` around every append/trim/rewrite keeps lines from being lost
or torn. The lock lives in a sidecar file (`<name>.lock`).

It never hangs forever: after `timeout` seconds it gives up waiting, prints a
warning and carries on unlocked (a rare lost log line beats a stuck run).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_TIMEOUT = 10.0
_POLL = 0.02

if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def locked(path: Path, timeout: float = DEFAULT_TIMEOUT) -> Iterator[bool]:
    """Hold an exclusive lock for `path`. Yields True if the lock was taken,
    False if the wait timed out and the caller is running unlocked."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    got = False
    try:
        deadline = time.monotonic() + timeout
        while not (got := _try_lock(fd)):
            if time.monotonic() >= deadline:
                print(f"[megazword] couldn't lock {path.name} within {timeout:.0f}s; "
                      "writing anyway", file=sys.stderr)
                break
            time.sleep(_POLL)
        yield got
    finally:
        if got:
            try:
                _unlock(fd)
            except OSError:
                pass
        os.close(fd)


def write_atomic(path: Path, text: str) -> None:
    """Replace a file in one step so readers never see half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # pid + thread: the dashboard's threads may write the same file at once (e.g. the meter cache).
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    # Windows refuses a replace while another writer or reader has the file open
    # ("Access is denied"); that clears in milliseconds, so retry for up to ~2s.
    for attempt in range(100):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 99:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(_POLL)
