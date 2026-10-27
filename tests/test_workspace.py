import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from megazword import workspace as w


def test_named_native_cli_is_discovered_despite_appserver_source(tmp_path, monkeypatch):
    codex = tmp_path / '.codex'
    codex.mkdir()
    with sqlite3.connect(codex / 'state_5.sqlite') as db:
        db.execute('CREATE TABLE threads(id,cwd,model,rollout_path,source,created_at)')
        db.executemany('INSERT INTO threads VALUES (?,?,?,?,?,?)', [
            ('named-live', str(tmp_path), 'model', 'log', 'vscode', 1),
            ('named-closed', str(tmp_path), 'model', 'log', 'vscode', 2),
            ('desktop-unregistered', str(tmp_path), 'model', 'log', 'vscode', 3),
            ('regular-cli', str(tmp_path), 'model', 'log', 'cli', 4)])
    registry = tmp_path / 'AppData/Local/MegaZword/CodexNames/designations.sqlite'
    registry.parent.mkdir(parents=True)
    with sqlite3.connect(registry) as db:
        db.execute('CREATE TABLE names(thread_id,name)')
        db.executemany('INSERT INTO names VALUES (?,?)', [('named-live', 'Briar-17'), ('named-closed', 'Clover-17')])
    monkeypatch.setattr(w, 'session_locked', lambda sid, user_home: sid != 'named-closed')
    rows = w.discover(tmp_path)
    assert [r['session'] for r in rows] == ['named-live', 'regular-cli']
    assert rows[0]['title'] == rows[0]['designation'] == 'Briar-17'
    snapshot = w.merge_snapshot({}, rows)
    assert snapshot['tabs'][0]['title'] == 'Briar-17'


def test_missing_name_registry_does_not_promote_desktop_sessions(tmp_path, monkeypatch):
    codex = tmp_path / '.codex'
    codex.mkdir()
    with sqlite3.connect(codex / 'state_5.sqlite') as db:
        db.execute('CREATE TABLE threads(id,cwd,model,rollout_path,source,created_at)')
        db.execute('INSERT INTO threads VALUES (?,?,?,?,?,?)', ('desktop', str(tmp_path), 'model', 'log', 'vscode', 1))
    monkeypatch.setattr(w, 'session_locked', lambda *args: pytest.fail('unregistered desktop row must not be tested as native CLI'))
    assert w.discover(tmp_path) == []
from megazword.workspace_terminal import ReturnQueue, escape_input
from megazword.face_identity import matches


def test_all_six_saved_tabs_launch_in_one_fresh_window(tmp_path, monkeypatch):
    rows = [dict(tab(), session=f'seat-{i}', cwd=str(tmp_path), title=f'Seat {i}') for i in range(6)]
    w.save(tmp_path / 'snapshot.json', {'tabs': rows})
    monkeypatch.setattr(w, 'session_locked', lambda _: False)
    monkeypatch.setattr(w, 'command', lambda _: ['fake-cli'])
    calls = []
    monkeypatch.setattr(w, 'desktop', lambda _: calls.append('desktop') or 2)
    monkeypatch.setattr(w.subprocess, 'run', lambda args, **kw: calls.append((args, kw)))
    plans = w.restore(tmp_path)
    assert len(plans) == 6
    assert calls[0] == 'desktop' and len(calls) == 2
    args, options = calls[1]
    assert args[:3] == ['wt.exe', '-w', 'new']
    assert args.count('new-tab') == 6 and args.count(';') == 5
    assert args.count('--tabColor') == 6
    assert options['check'] is True
    assert options['creationflags'] == getattr(w.subprocess, 'CREATE_NO_WINDOW', 0)
    manifest = plans[0][-1]
    assert all(plan[-2:] == ['--manifest', manifest] for plan in plans)
    # A timer snapshot cannot change the sessions or index order of a pending batch.
    w.save(tmp_path / 'snapshot.json', {'tabs': list(reversed(rows))})
    assert [t['session'] for t in w.load(manifest)['tabs']] == [f'seat-{i}' for i in range(6)]
    assert w.load(tmp_path / 'restore-status.json')['requested'] == [f'seat-{i}' for i in range(6)]
    assert w.load(tmp_path / 'restore-status.json')['opened'] == []
    assert args.count('--') == 6


def test_owner_return_does_not_repeat_an_unconfirmed_launch(tmp_path, monkeypatch):
    w.save(tmp_path / 'snapshot.json', {'tabs': [dict(tab(), cwd=str(tmp_path))]})
    monkeypatch.setattr(w, 'session_locked', lambda _: False)
    monkeypatch.setattr(w, 'command', lambda _: ['fake-cli'])
    calls = []
    monkeypatch.setattr(w, 'desktop', lambda _: 2)
    monkeypatch.setattr(w.subprocess, 'run', lambda *a, **kw: calls.append(a))
    assert len(w.restore(tmp_path, automatic=True)) == 1
    assert w.restore(tmp_path, automatic=True) == []
    assert w.restore(tmp_path, automatic=True) == []
    assert len(calls) == 1
    assert 'previous launch unconfirmed' in w.load(tmp_path / 'restore-status.json')['skipped'][0]['reason']
    assert len(w.restore(tmp_path)) == 1  # explicit Restore Hive retries
    assert len(calls) == 2


def test_launch_failure_is_not_retried_by_owner_camera(tmp_path, monkeypatch):
    w.save(tmp_path / 'snapshot.json', {'tabs': [dict(tab(), cwd=str(tmp_path))]})
    monkeypatch.setattr(w, 'session_locked', lambda _: False)
    monkeypatch.setattr(w, 'command', lambda _: ['fake-cli'])
    monkeypatch.setattr(w, 'desktop', lambda _: 2)
    def broken(*a, **kw):
        raise OSError('launch failed')
    monkeypatch.setattr(w.subprocess, 'run', broken)
    with pytest.raises(OSError):
        w.restore(tmp_path, automatic=True)
    assert w.restore(tmp_path, automatic=True) == []


def test_missing_seat_does_not_prevent_other_saved_seats_restoring(tmp_path, monkeypatch):
    rows = [dict(tab(), session='missing', cwd=str(tmp_path / 'gone')),
            dict(tab(), session='valid', cwd=str(tmp_path))]
    w.save(tmp_path / 'snapshot.json', {'tabs': rows})
    monkeypatch.setattr(w, 'session_locked', lambda _: False)
    monkeypatch.setattr(w, 'command', lambda _: ['fake-cli'])
    monkeypatch.setattr(w, 'desktop', lambda _: 1)
    monkeypatch.setattr(w.subprocess, 'run', lambda *a, **kw: None)
    assert len(w.restore(tmp_path)) == 1
    status = w.load(tmp_path / 'restore-status.json')
    assert status['requested'] == ['valid']
    assert status['skipped'] == [{'session': 'missing', 'reason': 'folder missing'}]


def test_dedicated_desktop_does_not_reuse_ai_workshop(tmp_path, monkeypatch):
    monkeypatch.setattr(w.os, "name", "nt")
    class Function:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    calls = []
    def name(index, buffer, size):
        buffer.value = [b'Main', b'ai workshop'][index]
        return 0
    dll = SimpleNamespace(
        GetDesktopCount=Function(lambda: 2), GetDesktopName=Function(name),
        CreateDesktop=Function(lambda: calls.append('create') or 2),
        SetDesktopName=Function(lambda i, name: calls.append((i, name)) or 0),
        GetCurrentDesktopNumber=Function(lambda: 2),
        GoToDesktopNumber=Function(lambda i: calls.append(('switch', i)) or 0))
    monkeypatch.setattr(w.ctypes, 'CDLL', lambda _: dll)
    assert w.desktop(tmp_path) == 2
    assert calls == ['create', (2, b'Hive'), ('switch', 2)]


def test_stale_pid_after_boot_cannot_hide_a_saved_session(monkeypatch):
    import sys
    process = SimpleNamespace(is_running=lambda: True, create_time=lambda: 2000,
                              name=lambda: 'grok.exe')
    monkeypatch.setitem(sys.modules, 'psutil', SimpleNamespace(
        Process=lambda _: process, boot_time=lambda: 1900, Error=OSError))
    assert not w.alive(123, started=1000, name='grok.exe')
    assert not w.runtime_alive({'pid': 123, 'ready': 1000})
    assert w.alive(123, started=2000, name='grok.exe')
    assert not w.alive(123, started=2000, name='claude.exe')


def test_login_restores_before_starting_owner_watcher(tmp_path, monkeypatch):
    from megazword import face_identity
    calls = []
    monkeypatch.setattr(w, 'snapshot', lambda root: calls.append('snapshot'))
    monkeypatch.setattr(w, 'restore', lambda root: calls.append('restore') or [[], []])
    monkeypatch.setattr(face_identity, 'watch', lambda root: calls.append('watch') or 0)
    assert w.boot(tmp_path) == 0
    assert calls == ['snapshot', 'restore', 'watch']
    status = w.load(tmp_path / 'boot-status.json')
    assert status['state'] == 'launch requested' and status['tabs_requested'] == 2


def test_login_can_use_saved_roster_when_snapshot_refresh_fails(tmp_path, monkeypatch):
    from megazword import face_identity
    def broken(_):
        raise OSError('native registry not ready')
    monkeypatch.setattr(w, 'snapshot', broken)
    attempts = []
    def restore(_):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError('Explorer not ready')
        return [[]]
    monkeypatch.setattr(w, 'restore', restore)
    delays = []
    monkeypatch.setattr(w.time, 'sleep', delays.append)
    monkeypatch.setattr(face_identity, 'watch', lambda root: 0)
    assert w.boot(tmp_path) == 0
    assert len(attempts) == 2 and delays == [10]
    status = w.load(tmp_path / 'boot-status.json')
    assert status['state'] == 'launch requested'
    assert 'native registry' in status['warnings'][0]


def test_boot_command_dispatches_without_an_interactive_test(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'home', lambda: tmp_path)
    calls = []
    monkeypatch.setattr(w, 'boot', lambda root: calls.append(root) or 0)
    assert w.main(['boot']) == 0
    assert calls == [tmp_path]


def tab(client='codex'):
    return dict(client=client, session='abc-123', cwd='folder', title='My work',
                model='chosen-model', color='#123456', active=True)


def test_snapshot_retains_closed_sessions_order_and_colors():
    one, two = tab(), dict(tab('grok'), session='second')
    result = w.merge_snapshot({'tabs': [two, one]}, [dict(one, model='new-model')])
    assert [t['session'] for t in result['tabs']] == ['second', 'abc-123']
    assert result['tabs'][0]['active'] is False
    assert result['tabs'][1]['model'] == 'new-model'
    assert result['tabs'][1]['color'] == '#123456'


def test_snapshot_empty_discovery_does_not_erase_reboot_roster(tmp_path, monkeypatch):
    w.save(tmp_path / 'snapshot.json', {'tabs': [tab()]})
    monkeypatch.setattr(w, 'discover', lambda: [])
    assert w.snapshot(tmp_path)['tabs'][0]['session'] == 'abc-123'
    assert json.loads((tmp_path / 'snapshot.json').read_text())['tabs'][0]['active'] is False


def test_import_preserves_existing_launcher_without_executing_it(tmp_path):
    script = tmp_path / 'legacy.ps1'
    script.write_text("throw 'never execute this'\n"
                      "@{ cli = 'claude'; dir = 'folder'; session = '11111111-2222-3333-4444-555555555555'; title = 'Existing seat' }\n")
    w.save(tmp_path / 'snapshot.json', {'tabs': [tab()]})
    assert w.import_legacy(tmp_path, script) == 1
    rows = w.load(tmp_path / 'snapshot.json')['tabs']
    assert [r['client'] for r in rows] == ['claude', 'codex']
    assert rows[0]['title'] == 'Existing seat'


@pytest.mark.parametrize('client,prefix', [('codex', ['resume']), ('claude', ['--resume']), ('grok', ['--resume'])])
def test_resume_uses_exact_id_model_and_bounded_prompt(monkeypatch, client, prefix):
    monkeypatch.setattr(w.shutil, 'which', lambda name: f'/bin/{name}')
    args = w.command(tab(client))
    assert args[1:3] == prefix + ['abc-123']
    assert args[3:5] == ['--model', 'chosen-model']
    assert args[-1] == w.PROMPT
    assert '--last' not in args and '--continue' not in args


def test_native_idle_requires_completed_turn(tmp_path):
    path = tmp_path / 'log.jsonl'
    data = tab()
    data['log'] = str(path)
    def event(kind):
        return json.dumps({'type': 'event_msg', 'payload': {'type': kind}}) + '\n'
    path.write_text('\n' + event('task_complete') + event('task_started'))
    assert w.native_idle(data) is False
    with path.open('a') as f:
        f.write(event('task_complete'))
    assert w.native_idle(data) is True
    data['log'] = str(tmp_path / 'missing')
    assert w.native_idle(data) is False


def test_return_queue_waits_for_turn_and_preserves_typed_input():
    q = ReturnQueue(1)
    q.last_output = q.last_key = 0
    q.observe(2)
    assert not q.ready(False, 10)
    q.key('x', 10)
    assert not q.ready(True, 20)
    q.key('\r', 20)
    assert not q.ready(True, 21)
    assert q.ready(True, 24)
    q.pending = 0
    q.observe(2)
    assert q.pending == 0  # a single return cannot loop


@pytest.mark.parametrize('sequence', ['\x1b[1;1R', '\x1b[?1;2c', '\x1b[>0;10;1c', '\x1b]10;rgb:aaaa/bbbb/cccc\x07'])
def test_terminal_protocol_replies_are_not_typed_drafts(sequence):
    buffer = ''
    for char in sequence:
        buffer, user_key = escape_input(buffer, char)
        assert not user_key
    assert buffer == ''


def test_history_up_arrow_is_user_input():
    buffer = ''
    for char in '\x1b[A':
        buffer, user_key = escape_input(buffer, char)
    assert user_key and not buffer


def test_restore_skips_live_writer_without_launching(tmp_path, monkeypatch):
    row = tab()
    row['cwd'] = str(tmp_path)
    w.save(tmp_path / 'snapshot.json', {'tabs': [row]})
    monkeypatch.setattr(w, 'session_locked', lambda _: True)
    monkeypatch.setattr(w, 'desktop', lambda _: pytest.fail('must not switch desktop'))
    assert w.restore(tmp_path) == []


def test_windowless_launcher_opens_a_console_python_only_inside_terminal(tmp_path, monkeypatch):
    row = tab()
    row['cwd'] = str(tmp_path)
    w.save(tmp_path / 'snapshot.json', {'tabs': [row]})
    monkeypatch.setattr(w, 'session_locked', lambda _: False)
    monkeypatch.setattr(w.shutil, 'which', lambda _: '/bin/codex.exe')
    monkeypatch.setattr(w.sys, 'executable', str(tmp_path / 'pythonw.exe'))
    plan = w.restore(tmp_path, preview=True)[0]
    assert str(tmp_path / 'python.exe') in plan
    assert str(tmp_path / 'pythonw.exe') not in plan
    assert '--tabColor' in plan and '#123456' in plan


def test_unmatched_or_missing_face_cannot_trigger_owner_return():
    assert not matches([])
    assert not matches([.1, .3, .49])
    assert matches([.1, .65])


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_face_template_roundtrips_with_user_protection():
    from megazword.face_identity import user_protect
    plaintext = b'[[0.2, 0.8]]'
    encrypted = user_protect(plaintext)
    assert plaintext not in encrypted
    assert user_protect(encrypted, decrypt=True) == plaintext
