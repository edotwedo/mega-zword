"""An owned terminal relay: queued return prompts, never SendKeys into another app."""
import os
import re
import shutil
import sys
import threading
import time

from . import workspace as ws
from .terminal_input import ConsoleInput, InputFilter, OutputFilter


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
    def __init__(self, event=0, summary_inflight=False):
        self.seen = event
        self.pending = 0
        self.dirty = False
        self.summary_inflight = summary_inflight
        self.last_key = self.last_output = time.monotonic()

    def observe(self, event):
        if event > self.seen:
            if not self.summary_inflight:
                self.pending = event
            self.seen = event

    def key(self, char, now):
        self.last_key = now
        self.dirty = char not in ('\r', '\n', '\x03', '\x15')
        if char == '\x03':
            self.pending = 0

    def sent(self):
        self.pending = 0
        self.summary_inflight = True

    def ready(self, idle, now):
        return (self.pending > 0 and not self.summary_inflight and not self.dirty and idle
                and now - max(self.last_key, self.last_output) >= 3)


def run_tab(index, root, manifest=None):
    if os.name != "nt":
        raise OSError("The Windows console relay is unavailable")
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
        env = dict(os.environ, MEGAZWORD_SESSION=tab['session'], MEGAZWORD_CLIENT=tab['client'])
        child = PtyProcess.spawn(ws.command(tab), cwd=tab['cwd'], env=env, dimensions=(size.lines, size.columns))
        queue = ReturnQueue(ws.load(root / 'return.json').get('event', 0), summary_inflight=True)
        ws.save(marker, {'pid': os.getpid(), 'ready': time.time(), 'process_started': process_started,
                         'inbox_version': 1})
        from . import workers
        worker_id = f"{tab['client']}-{tab['session']}"
        writer = threading.RLock()
        try:
            with ConsoleInput() as console:
                incoming = InputFilter()
                outgoing = OutputFilter(console.cursor)

                def output():
                    while child.isalive():
                        try:
                            data = child.read(8192)
                            if data:
                                queue.last_output = time.monotonic()
                                display, replies = outgoing.feed(data)
                                sys.stdout.write(display)
                                sys.stdout.flush()
                                with writer:
                                    for reply in replies:
                                        child.write(reply)
                        except (EOFError, OSError):
                            break

                threading.Thread(target=output, daemon=True).start()
                old_size, next_check = size, 0
                while child.isalive():
                    # Drain this console before considering an automatic submission.
                    while console.pending():
                        tokens = incoming.feed(console.read())
                        with writer:
                            for token in tokens:
                                queue.key(token, time.monotonic())
                                child.write(token)
                                if token in ('\r', '\n'):
                                    submitted = time.time()
                    escape = incoming.stream.escape(time.monotonic())
                    if escape:
                        queue.key(escape, time.monotonic())
                        with writer:
                            child.write(escape)
                    if time.monotonic() >= next_check:
                        next_check = time.monotonic() + .5
                        queue.observe(ws.load(root / 'return.json').get('event', 0))
                        try:
                            fresh = os.path.getmtime(tab.get('log') or tab.get('status_file', '')) > submitted
                        except OSError:
                            fresh = False
                        idle = fresh and ws.native_idle(tab)
                        now = time.monotonic()
                        if idle and now - queue.last_output >= 3:
                            queue.summary_inflight = False
                        message = workers.pending(worker_id)
                        safe = (not queue.dirty and not queue.summary_inflight and idle
                                and now - max(queue.last_key, queue.last_output) >= 3)
                        if (not console.pending() and not incoming.stream.buffer and not incoming.paste
                                and (queue.ready(idle, now) or (message and safe))):
                            prompt = (f"Phil sent this to your existing worker session: {message['text']}\n"
                                      "Reply in Hive with hive_say if available; otherwise reply here."
                                      if message else ws.PROMPT)
                            if outgoing.bracketed:
                                prompt = '\x1b[200~' + prompt + '\x1b[201~'
                            with writer:
                                child.write(prompt + '\r')
                                if message:
                                    workers.acknowledge(worker_id, message['id'])
                                queue.sent()
                                submitted = time.time()
                        size = shutil.get_terminal_size()
                        if size != old_size:
                            child.setwinsize(size.lines, size.columns)
                            old_size = size
                    time.sleep(.02)
        finally:
            if child.isalive():
                child.terminate(force=True)
            ws.save(marker, {'pid': None, 'stopped': time.time()})
        return child.exitstatus or 0
