"""Windows AI CLIs must not flash a console from the windowless app."""

import os
import subprocess

from megazword.backends import process_group


def test_process_group_hides_console_on_windows():
    flags = process_group()
    if os.name == "nt":
        hidden = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        assert flags["creationflags"] == hidden
    else:
        assert flags.get("start_new_session") is True
