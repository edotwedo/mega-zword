"""The conftest guard: a test can never run a real AI CLI installed on the PC."""

import os

from megazword.backends import CLIBackend


def test_a_cli_outside_the_repo_and_temp_is_refused(monkeypatch):
    outside = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "whoami.exe")
    monkeypatch.setattr("megazword.backends.shutil.which", lambda exe: outside)
    result = CLIBackend("claude", exe="claude", args=["-p"]).run("hi")
    assert not result.ok and "test tried to run a real CLI" in result.error
