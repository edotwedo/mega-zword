"""Local Windows Terminal session snapshots. Snapshotting never invokes an AI."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time

from .filelock import locked, write_atomic

PROMPT = ("Phil is back. Give a short catch-up, at most 80 words: what we are working on, "
          "what you just completed, any blocker, and the next step. Use this conversation's "
          "actual state. Do not start work, run tools, edit files, or message other agents.")
COLORS = {'codex': '#65A8E8', 'claude': '#DE9973', 'grok': '#B094E8', 'gemini': '#70BD91'}


def home():
    return Path.home() / '.megazword' / 'workspace'


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path) as acquired:
        if not acquired:
            raise OSError(f'Could not lock {path.name}')
        write_atomic(path, json.dumps(data, indent=2) + '\n')


def session_locked(session_id, user_home=None):
    """A stale Codex lock file alone does not mean its writer is alive."""
    path = (user_home or Path.home()) / '.codex/thread-writer-locks' / f'{session_id}.lock'
    if not path.exists() or os.name != 'nt':
        return False
    import msvcrt
    try:
        with path.open('rb') as f:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBRLCK, 1)
            except OSError:
                return True
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        return True  # unknown/access denied: do not open a second writer
    return False


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    import psutil
    try:
        return psutil.Process(int(pid)).is_running()
    except (psutil.Error, TypeError, ValueError):
        return False


def discover(user_home=None):
    """Read native registries, not chat contents. Only CLI Codex writers qualify."""
    user_home = user_home or Path.home()
    found = []
    db = user_home / '.codex/state_5.sqlite'
    if db.exists():
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2) as c:
            for sid, cwd, model, rollout in c.execute(
                    "SELECT id,cwd,model,rollout_path FROM threads WHERE source='cli' ORDER BY created_at"):
                if session_locked(sid, user_home):
                    found.append(dict(client='codex', session=sid, cwd=cwd.removeprefix('\\\\?\\'),
                                      model=model, log=rollout, active=True))
    for item in load(user_home / '.grok/active_sessions.json', []):
        if alive(item.get('pid')):
            sid, cwd = item['session_id'], item['cwd']
            from urllib.parse import quote
            folder = user_home / '.grok/sessions' / quote(cwd, safe='') / sid
            meta = load(folder / 'summary.json')
            found.append(dict(client='grok', session=sid, cwd=cwd,
                              model=meta.get('current_model_id'), log=str(folder / 'updates.jsonl'),
                              active=True, pid=item['pid']))
    for path in (user_home / '.claude/sessions').glob('*.json'):
        item = load(path)
        if item.get('kind') == 'interactive' and alive(item.get('pid')):
            found.append(dict(client='claude', session=item['sessionId'], cwd=item['cwd'],
                              active=True, pid=item['pid'], status_file=str(path)))
    return found


def merge_snapshot(previous, current):
    """Keep closed tabs for reboot recovery; refresh live IDs and retain chosen order/colors."""
    rows = [dict(r, active=False) for r in previous.get('tabs', [])]
    by_id = {(r['client'], r['session']): r for r in rows}
    for item in current:
        key = item['client'], item['session']
        if key in by_id:
            by_id[key].update(item)
        else:
            row = dict(item)
            row['title'] = f"{item['client']} - {Path(item['cwd']).name}"
            row['color'] = COLORS.get(item['client'], '#777777')
            rows.append(row)
            by_id[key] = row
    return dict(version=1, saved_at=time.time(), tabs=rows)


def import_legacy(root, script):
    """Import literal roster rows from Phil's existing launcher; never execute it."""
    rows = []
    for line in Path(script).read_text(encoding='utf-8').splitlines():
        fields = dict(re.findall(r"\b(cli|dir|session|title)\s*=\s*'([^']*)'", line))
        if set(fields) != {'cli', 'dir', 'session', 'title'} or fields['cli'] not in COLORS:
            continue
        if not re.fullmatch(r'[a-fA-F0-9-]{36}', fields['session']):
            continue
        rows.append(dict(client=fields['cli'], cwd=fields['dir'], session=fields['session'],
                         title=fields['title'], color=COLORS[fields['cli']], active=False))
    if rows:
        previous = load(root / 'snapshot.json')
        combined = merge_snapshot({'tabs': rows}, previous.get('tabs', []))
        save(root / 'snapshot.json', combined)
    return len(rows)


def snapshot(root=None):
    root = root or home()
    path = root / 'snapshot.json'
    # Serialize read/merge/write, so parallel task/manual invocations cannot lose a tab.
    root.mkdir(parents=True, exist_ok=True)
    with locked(root / 'snapshot-update') as acquired:
        if not acquired:
            raise OSError('Another snapshot is still running')
        result = merge_snapshot(load(path), discover())
        save(path, result)
    return result


def command(tab, catch_up=True):
    client, sid = tab['client'], str(tab['session'])
    if client not in COLORS or not re.fullmatch(r'[a-zA-Z0-9_-]+', sid):
        raise ValueError('Unsupported client or invalid session ID')
    exe = shutil.which(client + '.exe') or shutil.which(client + '.cmd') or shutil.which(client)
    if not exe:
        raise ValueError(f'{client} is not installed')
    if client == 'codex' and exe.lower().endswith('.cmd'):
        candidates = list((Path(exe).parent / 'node_modules/@openai/codex/node_modules').glob(
            '@openai/codex-win32-x64/vendor/*/bin/codex.exe'))
        if not candidates:
            raise ValueError('Cannot find the native Codex executable behind its npm shim')
        exe = str(candidates[0])
    args = [exe, 'resume', sid] if client == 'codex' else [exe, '--resume', sid]
    if tab.get('model'):
        args += ['--model', tab['model']]
    if catch_up:
        args.append(PROMPT)
    return args


def native_idle(tab):
    """Fail closed. A quiet screen is not proof an agent finished its turn."""
    if tab['client'] == 'claude':
        item = load(tab.get('status_file', ''))
        return item.get('status') == 'idle'
    path = Path(tab.get('log', ''))
    try:
        with path.open('rb') as f:
            offset = max(0, path.stat().st_size - 131072)
            f.seek(offset)
            rows = f.read().decode('utf-8', errors='replace').splitlines()
            if offset:
                rows = rows[1:]
        for line in reversed(rows):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if tab['client'] == 'codex' and row.get('type') == 'event_msg':
                kind = row.get('payload', {}).get('type')
                if kind in ('task_started', 'task_complete', 'turn_aborted'):
                    return kind != 'task_started'
            if tab['client'] == 'grok':
                kind = row.get('params', {}).get('update', {}).get('sessionUpdate')
                if kind in ('turn_started', 'turn_completed'):
                    return kind == 'turn_completed'
                if kind in ('agent_thought_chunk', 'agent_message_chunk', 'tool_call'):
                    return False
    except OSError:
        pass
    return False


def desktop(root):
    """Use the local, pinned VirtualDesktopAccessor helper; never download at launch."""
    dll = ctypes.CDLL(str(root / 'VirtualDesktopAccessor.dll'))
    dll.GetDesktopCount.restype = ctypes.c_int
    dll.GetDesktopName.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
    dll.SetDesktopName.argtypes = [ctypes.c_int, ctypes.c_char_p]
    count = dll.GetDesktopCount()
    if count < 1:
        raise OSError('Virtual desktop helper is incompatible with this Windows build')
    target = None
    for i in range(count):
        name = ctypes.create_string_buffer(256)
        dll.GetDesktopName(i, name, 256)
        if name.value.lower() in (b'hive', b'ai workshop'):
            target = i
            break
    if target is None:
        target = dll.CreateDesktop()
        if target < 0:
            raise OSError('Could not create the Hive desktop')
        if dll.SetDesktopName(target, b'Hive') < 0:
            raise OSError('Could not name the Hive desktop')
    if dll.GoToDesktopNumber(target) < 0:
        raise OSError('Could not switch to the Hive desktop')
    return target


def restore(root=None, preview=False):
    root = root or home()
    tabs = load(root / 'snapshot.json').get('tabs', [])
    if not tabs:
        raise ValueError('No saved terminal sessions. Run workspace snapshot first.')
    plans = []
    for i, tab in enumerate(tabs):
        # Check again at launch. Never resume over a live writer.
        active = (session_locked(tab['session']) if tab['client'] == 'codex'
                  else alive(tab.get('pid')))
        runtime = load(root / f"tab-{tab['session']}.json")
        if active or alive(runtime.get('pid')):
            continue
        if not Path(tab['cwd']).is_dir():
            continue
        command(tab)  # validate availability before switching desktop
        args = ['wt.exe', '-w', 'Hive', 'new-tab', '--title', tab['title'],
                '--suppressApplicationTitle', '--tabColor', tab['color'], '-d', tab['cwd'],
                str(Path(sys.executable).with_name('python.exe')) if Path(sys.executable).name.lower() == 'pythonw.exe' else sys.executable,
                '-m', 'megazword.workspace', 'tab', str(i)]
        plans.append(args)
    if not preview and plans:
        desktop(root)
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        for args in plans:
            subprocess.run(args, env=env, check=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return plans


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'restore', 'status', 'tab', 'watch', 'enroll', 'catch-up'])
    parser.add_argument('index', nargs='?', type=int)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args(argv)
    root = home()
    if args.action == 'snapshot':
        print(f"Saved {len(snapshot(root)['tabs'])} sessions")
    elif args.action == 'restore':
        plans = restore(root, args.preview)
        print(json.dumps(plans, indent=2) if args.preview else f'Restored {len(plans)} tabs; already-open sessions skipped')
    elif args.action == 'status':
        for tab in load(root / 'snapshot.json').get('tabs', []):
            print(tab['title'], tab['session'], tab.get('model', 'client default'), tab['cwd'])
    elif args.action == 'catch-up':
        save(root / 'return.json', {'event': time.time()})
    elif args.action == 'tab':
        from .workspace_terminal import run_tab
        return run_tab(args.index, root)
    else:
        from .face_identity import enroll, watch
        return enroll(root) if args.action == 'enroll' else watch(root)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        save(home() / 'last-error.json', {'time': time.time(), 'error': str(exc)})
        if sys.stderr:
            print(exc, file=sys.stderr)
        raise SystemExit(1)
