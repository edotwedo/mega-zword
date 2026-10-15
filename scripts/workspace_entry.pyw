"""Windowless entry point for shortcuts and scheduled tasks in this checkout."""
import os
from pathlib import Path
import sys

source = str(Path(__file__).resolve().parents[1] / 'src')
sys.path.insert(0, source)
os.environ['PYTHONPATH'] = source

if __name__ == '__main__':
    from megazword.workspace import main, home, save
    try:
        raise SystemExit(main())
    except Exception as exc:
        import time
        save(home() / 'last-error.json', {'time': time.time(), 'error': str(exc)})
        raise SystemExit(1)
