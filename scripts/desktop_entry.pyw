"""Open this checkout's current app through a silent shortcut."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
os.environ['PYTHONPATH'] = str(root / 'src')
try:
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--short', 'HEAD'],
                            capture_output=True, text=True, timeout=3,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode == 0:
        os.environ['MEGAZWORD_BUILD'] = result.stdout.strip()
except (OSError, subprocess.SubprocessError):
    pass
from megazword.cli import main
args = ['dashboard', '--port', '8768', '--project', 'mega-zword']
args += ['--no-browser'] if '--no-browser' in sys.argv else ['--app']
raise SystemExit(main(args))
