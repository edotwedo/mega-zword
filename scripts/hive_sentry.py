#!/usr/bin/env python3
"""Hive room sentry for all seats.

Usage:
    python scripts/hive_sentry.py [--seat SEAT] [--interval SECONDS]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from megazword import sentry

if __name__ == "__main__":
    raise SystemExit(sentry.main())
