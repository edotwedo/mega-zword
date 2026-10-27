"""Linux UI startup must not load Windows workspace or camera dependencies."""
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows startup contract")
def test_dashboard_and_cli_skip_windows_dependencies():
    result = subprocess.run([sys.executable, "-c", '''
import importlib.abc
import sys
from pathlib import Path

class BlockWindows(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"megazword.workspace", "megazword.workspace_terminal",
                        "winpty", "cv2", "numpy"}:
            raise AssertionError("Windows dependency imported: " + fullname)
sys.meta_path.insert(0, BlockWindows())
import megazword.cli
import megazword.dashboard
assert not any(name == "winpty" or name.startswith("winpty.") for name in sys.modules)
from megazword.cli import main
assert main(["--help"]) == 0
'''], capture_output=True, text=True)
    # argparse exits successfully after displaying help.
    assert result.returncode == 0, result.stderr

    result = subprocess.run([sys.executable, "-c", '''
import importlib.abc
import sys
from pathlib import Path
class BlockWindows(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"megazword.workspace", "megazword.workspace_terminal",
                        "winpty", "cv2", "numpy"}:
            raise AssertionError("Windows dependency imported: " + fullname)
sys.meta_path.insert(0, BlockWindows())
from megazword import dashboard, cmdc_quota
from megazword.face_identity import OwnerCamera, enroll, watch
app = dashboard.AppState()
assert not any(name == "winpty" or name.startswith("winpty.") for name in sys.modules)
camera = OwnerCamera(Path("/unused"))
assert camera.read() is False
assert camera.frame() == (None, [])
camera.close()
assert enroll(Path("/unused")) == 0
assert watch(Path("/unused")) == 0
assert cmdc_quota.read_quota() is None
app.shutdown()
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
