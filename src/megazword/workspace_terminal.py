"""An owned terminal relay: queued return prompts, never SendKeys into another app."""
import os
import re
import shutil
import sys
import threading
import time

from . import workspace as ws


def escape_input(buffer, char):
    """Keep terminal query responses out of the user's draft state."""
    buffer += char
    if buffer == '\x1b':
        return buffer, False
    if buffer.startswith('\x1b]'):
        if buffer.endswith(('\x07', '\x1b\\')):
            return '', False
        return buffer, False
    if buffer.startswith('\x1b['):
        if len(buffer) < 3 or not ('@' <= buffer[-1] <= '~'):
            return buffer, False
        protocol = re.fullmatch(r'\x1b\[[?>]?[0-9;:]*[Rcnty]', buffer)
        return '', not bool(protocol)
    return '', True


class ReturnQueue:
    def __init__(self, event=0):
        self.seen = event
        self.pending = 0
        self.dirty = False
        self.last_key = self.last_output = time.monotonic()

    def observe(self, event):
        if event > self.seen:
            self.pending = event
            self.seen = event

    def key(self, char, now):
        self.last_key = now
        self.dirty = char not in ('\r', '\n', '\x03', '\x15')

    def ready(self, idle, now):
        return (self.pending > 0 and not self.dirty and idle
                and now - max(self.last_key, self.last_output) >= 3)


def run_tab(index, root, manifest=None):
    import msvcrt
    from winpty import PtyProcess
    tabs = ws.load(manifest or root / 'snapshot.json').get('tabs', [])
    if index is None or not 0 <= index < len(tabs):
        raise ValueError('Unknown saved tab')
    tab = tabs[index]
    marker = root / f"tab-{tab['session']}.json"
    from .filelock import locked
    # Held for the whole relay lifetime; two launcher clicks cannot start two copies.
    with locked(root / f"launch-{tab['session']}", timeout=0) as acquired:
        if not acquired:
            return 0
        if tab['client'] == 'codex' and ws.session_locked(tab['session']):
            print('This conversation is already open; skipped.')
            return 0
        import psutil
        process_started = psutil.Process().create_time()
        ws.save(marker, {'pid': os.getpid(), 'started': time.time(), 'process_started': process_started})
        size = shutil.get_terminal_size()
        submitted = time.time()
        child = PtyProcess.spawn(ws.command(tab), cwd=tab['cwd'], dimensions=(size.lines, size.columns))
        queue = ReturnQueue(ws.load(root / 'return.json').get('event', 0))
        ws.save(marker, {'pid': os.getpid(), 'ready': time.time(), 'process_started': process_started})

        def output():
            while child.isalive():
                try:
                    data = child.read(8192)
                except (EOFError, OSError):
                    break
                if data:
                    queue.last_output = time.monotonic()
                    sys.stdout.write(data)
                    sys.stdout.flush()

        threading.Thread(target=output, daemon=True).start()
        old_size = size
        next_check = 0
        escape = ''
        try:
            while child.isalive():
                try:
                    if msvcrt.kbhit():
                        char = msvcrt.getwch()
                        if char in ('\x00', '\xe0'):
                            key = msvcrt.getwch()
                            char = {'H':'\x1b[A', 'P':'\x1b[B', 'M':'\x1b[C', 'K':'\x1b[D',
                                    'G':'\x1b[H', 'O':'\x1b[F', 'S':'\x1b[3~'}.get(key, '')
                        if escape or char == '\x1b':
                            escape, user_key = escape_input(escape, char)
                            if user_key:
                                queue.key(char, time.monotonic())
                        else:
                            queue.key(char, time.monotonic())
                        child.write(char)
                        if char in ('\r', '\n'):
                            submitted = time.time()
                    if time.monotonic() < next_check:
                        time.sleep(.02)
                        continue
                    next_check = time.monotonic() + .5
                    queue.observe(ws.load(root / 'return.json').get('event', 0))
                    # A completed turn must postdate the last submitted user input.
                    try:
                        fresh = os.path.getmtime(tab.get('log') or tab.get('status_file', '')) > submitted
                    except OSError:
                        fresh = False
                    if queue.pending and not escape and fresh and queue.ready(ws.native_idle(tab), time.monotonic()):
                        child.write(ws.PROMPT + '\r')
                        queue.pending = 0
                        submitted = time.time()
                    size = shutil.get_terminal_size()
                    if size != old_size:
                        child.setwinsize(size.lines, size.columns)
                        old_size = size
                    time.sleep(.03)
                except KeyboardInterrupt:
                    child.write('\x03')
        finally:
            if child.isalive():
                child.terminate(force=True)
            ws.save(marker, {'pid': None, 'stopped': time.time()})
        return child.exitstatus or 0
