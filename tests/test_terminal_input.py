"""Exercise relay bytes, including chunked replies, without opening desktop windows."""
import os
import json
import sys
import time

import pytest

from megazword.terminal_input import InputFilter, OutputFilter, key_text
from megazword.workspace_terminal import ReturnQueue


def test_backspace_is_character_erase_and_ctrl_backspace_is_word_erase():
    assert key_text(8, '\b') == '\x7f'
    assert key_text(8, '\x7f', state=8) == '\b'
    assert key_text(8, '\b', repeat=3) == '\x7f' * 3


def test_modifiers_and_unicode_survive_keyboard_translation():
    assert key_text(37, state=8) == '\x1b[1;5D'
    assert key_text(39, state=0x10) == '\x1b[1;2C'
    assert key_text(9, '\t', state=0x10) == '\x1b[Z'
    assert key_text(67, '\x03', state=8) == '\x03'
    assert key_text(69, '€', state=9) == '€'
    assert key_text(88, 'x', state=2) == '\x1bx'


@pytest.mark.parametrize('reply', [
    '\x1b[?61;4;6;7;14;21;22;23;24;28;32;42;52c',
    '\x1b]10;rgb:cccc/cccc/cccc\x1b\\',
    '\x1b]11;rgb:0c0c/0c0c/0c0c\x07',
    '\x1b[2;5R', '\x1b[?2026;0$y', '\x1b[?0u',
])
def test_protocol_never_leaks_even_when_split_at_every_byte(reply):
    incoming = InputFilter()
    forwarded = []
    for char in reply:
        forwarded.extend(incoming.feed(char))
    assert forwarded == []
    assert incoming.feed('hello\x7f\r') == list('hello\x7f\r')


def test_actual_keys_and_paste_are_not_discarded():
    incoming = InputFilter()
    text = '\x1b[A\x1b[1;5D\x1b[200~literal\x1b[2;5R\x1b[201~'
    assert ''.join(incoming.feed(text)) == text
    assert not incoming.paste
    incoming.feed('\x1b')
    assert incoming.stream.escape(incoming.stream.since + .1) == '\x1b'


def test_child_queries_are_answered_without_exposing_them_to_outer_terminal():
    outgoing = OutputFilter(cursor=lambda: (7, 12))
    queries = '\x1b[c\x1b[>c\x1b[6n\x1b]10;?\x1b\\\x1b]11;?\x07\x1b[?u\x1b[?2026$p'
    display, replies = '', []
    for char in queries:
        visible, answers = outgoing.feed(char)
        display += visible
        replies += answers
    assert display == ''
    assert replies == ['\x1b[?1;2c', '\x1b[>0;0;0c', '\x1b[7;12R',
                       '\x1b]10;rgb:cccc/cccc/cccc\x1b\\',
                       '\x1b]11;rgb:0c0c/0c0c/0c0c\x1b\\',
                       '\x1b[?0u', '\x1b[?2026;0$y']
    rendering = '\x1b[31mhello\x1b[0m\x1b[?2004h'
    assert outgoing.feed(rendering) == (rendering, [])
    assert outgoing.bracketed
    outgoing.feed('\x1b[?2004l')
    assert not outgoing.bracketed


def test_return_during_initial_or_automatic_summary_does_not_queue_a_second():
    queue = ReturnQueue(1, summary_inflight=True)
    queue.observe(2)
    assert queue.seen == 2 and queue.pending == 0
    queue.summary_inflight = False
    queue.observe(3)
    assert queue.pending == 3
    queue.sent()
    queue.observe(4)
    assert queue.seen == 4 and queue.pending == 0
    queue.summary_inflight = False
    queue.observe(5)
    queue.key('\x03', 10)
    assert queue.pending == 0


@pytest.mark.skipif(os.name != 'nt', reason='Windows console events')
def test_owned_private_console_reads_actual_backspace_without_any_ui(tmp_path):
    from winpty import PtyProcess
    result = tmp_path / 'keys.json'
    script = tmp_path / 'console_probe.py'
    script.write_text(
        'import json, time\n'
        'from pathlib import Path\n'
        'from megazword.terminal_input import ConsoleInput\n'
        'with ConsoleInput() as console:\n'
        '    print("PROBE_READY", flush=True)\n'
        '    text = ""\n'
        '    deadline = time.monotonic() + 10\n'
        '    while time.monotonic() < deadline:\n'
        '        text += console.read()\n'
        '        if text.endswith("\\r"):\n'
        '            break\n'
        '        time.sleep(.01)\n'
        f'    Path({str(result)!r}).write_text(json.dumps(text))\n'
    )
    env = dict(os.environ)
    from pathlib import Path
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    child = PtyProcess.spawn([sys.executable, str(script)], env=env)
    try:
        output = ''
        while 'PROBE_READY' not in output:
            output += child.read(4096)
            if '\x1b[6n' in output:
                child.write('\x1b[1;1R')
        child.write('abc\x7f\r')
        deadline = time.monotonic() + 10
        while not result.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert result.exists(), output
        assert json.loads(result.read_text()).endswith('abc\x7f\r')
    finally:
        if child.isalive():
            child.terminate(force=True)


@pytest.mark.skipif(os.name != 'nt', reason='Windows ConPTY relay')
@pytest.mark.parametrize('automatic', [False, True])
def test_real_relay_filters_queries_and_delivers_character_backspace(tmp_path, automatic):
    """Two private ConPTYs, actual run_tab, fake native client; zero AI calls."""
    from pathlib import Path
    from threading import Thread
    from winpty import PtyProcess
    from megazword import workspace as ws
    result = tmp_path / 'received.json'
    status = tmp_path / 'native-status.txt'
    client = tmp_path / 'client.py'
    client.write_text(
        'import ctypes, json, os\n'
        'from ctypes import wintypes as w\n'
        'from pathlib import Path\n'
        'api = ctypes.WinDLL("kernel32", use_last_error=True)\n'
        'api.GetStdHandle.argtypes = [w.DWORD]\n'
        'api.GetStdHandle.restype = w.HANDLE\n'
        'api.SetConsoleMode.argtypes = [w.HANDLE, w.DWORD]\n'
        'api.SetConsoleMode(api.GetStdHandle(w.DWORD(-10).value), 0x200)\n'
        'print("\\x1b[c\\x1b]10;?\\x07CLIENT_READY", flush=True)\n'
        f'Path({str(status)!r}).write_text("idle")\n'
        'data = b""\n'
        'while not data.endswith(b"\\r"):\n'
        '    data += os.read(0, 4096)\n'
        f'Path({str(result)!r}).write_text(json.dumps(data.decode()))\n'
    )
    ws.save(tmp_path / 'snapshot.json', {'tabs': [
        {'session': 'fake-probe', 'client': 'test', 'cwd': str(tmp_path), 'log': str(status)}]})
    if automatic:
        ws.save(tmp_path / 'worker-inbox' / 'test-fake-probe' / 'message.json',
                {'id': 'message', 'text': 'Identify your worker session', 'state': 'queued'})
    relay = tmp_path / 'relay.py'
    relay.write_text(
        'from pathlib import Path\n'
        'from megazword import workspace as ws\n'
        'from megazword import config\n'
        'from megazword.workspace_terminal import run_tab\n'
        f'config.HOME = Path({str(tmp_path)!r})\n'
        'ws.native_idle = lambda tab: True\n'
        f'ws.command = lambda tab: [{sys.executable!r}, {str(client)!r}]\n'
        f'run_tab(0, Path({str(tmp_path)!r}))\n'
    )
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    child = PtyProcess.spawn([sys.executable, str(relay)], env=env)
    output = []

    def drain():
        try:
            while child.isalive():
                data = child.read(4096)
                output.append(data)
                # ConPTY's own initial cursor query is outside our relay.
                if '\x1b[6n' in data:
                    child.write('\x1b[1;1R')
        except (EOFError, OSError):
            pass

    Thread(target=drain, daemon=True).start()
    try:
        deadline = time.monotonic() + 15
        while 'CLIENT_READY' not in ''.join(output) and time.monotonic() < deadline:
            time.sleep(.02)
        assert 'CLIENT_READY' in ''.join(output), ''.join(output)
        # The outer ConPTY emits its own DA query before Python starts.
        assert '\x1b]10;?' not in ''.join(output)
        if not automatic:
            child.write('abc\x7f\r')
        while not result.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert result.exists(), ''.join(output)
        received = json.loads(result.read_text())
        if automatic:
            assert 'Identify your worker session' in received
            assert ws.load(tmp_path / 'worker-inbox' / 'test-fake-probe' / 'message.json')['state'] == 'delivered'
        else:
            assert received.endswith('abc\x7f\r'), repr(received)
        assert received.count('\x1b[?1;2c') == 1
        assert received.count('\x1b]10;rgb:cccc/cccc/cccc\x1b\\') == 1
    finally:
        if child.isalive():
            child.terminate(force=True)
