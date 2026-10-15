import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from megazword import workspace as w
from megazword.workspace_terminal import ReturnQueue, escape_input
from megazword.face_identity import matches


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
