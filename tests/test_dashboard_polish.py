"""Dashboard polish: notifications, copy buttons, keyboard shortcuts.

The JS is run in Node with small stubs (no real browser)."""

import re
import shutil
import subprocess
from importlib import resources

import pytest

HTML = resources.files("megazword").joinpath("dashboard.html").read_text(encoding="utf-8")
SCRIPT = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))
node = shutil.which("node")


def function_source(name: str) -> str:
    start = SCRIPT.index(f"function {name}(")
    depth, i = 0, SCRIPT.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(SCRIPT[i], 0)
        i += 1
        if depth == 0:
            return SCRIPT[start:i]


def run_js(body: str) -> str:
    program = (function_source("askNotifyOnce") + "\n" + function_source("notifyDone") + "\n" +
               "const made = []; let asked = 0;\n"
               "class Notification { constructor(t, o) { made.push([t, o.body]); }"
               " static requestPermission() { asked++; return Promise.resolve('granted'); } }\n"
               "const window = {Notification, focus() {}};\n" + body)
    return subprocess.run([node, "-e", program], capture_output=True, text=True, check=True,
                          timeout=30).stdout.strip()


@pytest.mark.skipif(not node, reason="node not installed")
def test_notifies_only_when_hidden_and_granted():
    job = r"({id: 'j1', code: 0, label: 'hi', out: '=== a · 1s ===\npong\n', err: ''})"
    out = run_js(
        "let document = {hidden: true}; Notification.permission = 'granted';"
        f"notifyDone({job}); document = {{hidden: false}}; notifyDone({job});"
        "Notification.permission = 'denied'; document = {hidden: true};"
        f"notifyDone({job}); console.log(JSON.stringify(made));")
    assert out == r'[["Mega Zword: done","hi\npong"]]'


@pytest.mark.skipif(not node, reason="node not installed")
def test_permission_asked_once_only_when_undecided():
    out = run_js("Notification.permission = 'default'; askNotifyOnce();"
                 "Notification.permission = 'granted'; askNotifyOnce();"
                 "Notification.permission = 'denied'; askNotifyOnce(); console.log(asked);")
    assert out == "1"


def test_every_answer_has_a_copy_button():
    # Past answers, plain job output, and each compare column.
    assert HTML.count('<button class="copy"') == 3
    assert "navigator.clipboard.writeText" in SCRIPT and 'execCommand("copy")' in SCRIPT


def test_keyboard_shortcuts_are_wired():
    handler = SCRIPT[SCRIPT.index('// Keyboard: "/" jumps'):][:900]
    assert 'e.key === "/"' in handler and '$("prompt").focus()' in handler
    assert 'e.key === "Escape"' in handler and '"/api/cancel"' in handler
    assert "typing" in handler  # "/" isn't hijacked while typing in a box
