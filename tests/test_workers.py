import os
import sys
import pytest

from megazword import briefing, config, mcp_hive, workers, workspace as ws


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'HOME', tmp_path)
    monkeypatch.setattr(ws, 'discover', lambda _: [])
    monkeypatch.setattr(mcp_hive, '_worker_seat', '')
    monkeypatch.delenv('CODEX_THREAD_ID', raising=False)
    monkeypatch.delenv('MEGAZWORD_SESSION', raising=False)
    return tmp_path


def test_saved_working_report_does_not_fake_a_connected_worker():
    briefing.publish({'seat': 'bramble-16', 'doing': 'old task'})
    worker, = workers.roster()
    assert not worker['connected'] and not worker['reachable']
    with pytest.raises(ValueError, match='No connected worker'):
        workers.send('bramble-16', 'Who are you?')


def test_launcher_designation_labels_native_worker_without_faking_reachability(monkeypatch):
    monkeypatch.setattr(ws, 'discover', lambda _: [
        {'client': 'codex', 'session': 'named-session', 'designation': 'Briar-17'}])
    worker, = workers.roster()
    assert worker['seat'] == 'Briar-17'
    assert worker['connected'] and not worker['reachable']


def test_two_codex_workers_do_not_overwrite_each_other():
    one = workers.connect('codex', 'session-one')
    two = workers.connect('codex', 'session-two')
    assert one != two
    rows = workers.roster()
    assert {w['session'] for w in rows} == {'session-one', 'session-two'}
    assert all(w['reachable'] for w in rows)


def test_basic_install_without_workspace_extra_keeps_hive_usable(monkeypatch):
    workers.connect('existing')
    monkeypatch.setitem(sys.modules, 'psutil', None)
    assert workers.connect('new') == ''
    assert not workers.roster()[0]['reachable']
    assert mcp_hive.hive_say({'author': 'new', 'text': 'Still works'}) == '[new] Still works'


def test_connected_mcp_worker_receives_message_in_actual_read_response():
    mcp_hive.hive_status({'seat': 'testlog-14', 'session': 'session-a', 'doing': 'fix workers'})
    worker, = workers.roster()
    assert worker['connected'] and worker['reachable'] and worker['session'] == 'session-a'
    assert workers.send('testlog-14', 'Which chat is yours?')['queued'] == ['testlog-14']
    text = mcp_hive.hive_read({})
    assert '[Phil to testlog-14] Which chat is yours?' in text
    assert 'Which chat is yours?' not in mcp_hive.hive_read({})
    assert workers.pending('testlog-14') is None


def test_pid_reuse_and_dead_server_cannot_receive(isolated, monkeypatch):
    workers.connect('old')
    path = isolated / 'workers' / 'old.json'
    item = ws.load(path)
    ws.save(path, {**item, 'process_started': item['process_started'] - 100})
    assert not workers.roster()[0]['connected']
    with pytest.raises(ValueError):
        workers.send('old', 'test')


def test_native_sessions_display_distinct_identities_and_require_new_relay(isolated, monkeypatch):
    monkeypatch.setattr(ws, 'discover', lambda _: [
        {'client': 'codex', 'session': 'one'}, {'client': 'codex', 'session': 'two'}])
    briefing.publish({'seat': 'testlog-14', 'session': 'one', 'doing': 'testing'})
    import psutil
    runtime = {'pid': os.getpid(), 'process_started': psutil.Process().create_time()}
    ws.save(isolated / 'workspace' / 'tab-one.json', {**runtime, 'inbox_version': 1})
    ws.save(isolated / 'workspace' / 'tab-two.json', runtime)
    rows = {w['session']: w for w in workers.roster()}
    assert rows['one']['seat'] == 'testlog-14' and rows['one']['reachable']
    assert rows['two']['connected'] and not rows['two']['reachable']
    assert workers.send('*', 'identify yourself')['queued'] == ['testlog-14']
    message = workers.pending('codex-one')
    assert message['text'] == 'identify yourself'
    workers.acknowledge('codex-one', message['id'])
    assert workers.pending('codex-one') is None


def test_broadcast_queues_only_connected_workers_and_preserves_order():
    workers.connect('first')
    workers.connect('second')
    briefing.publish({'seat': 'offline'})
    assert workers.send('*', 'one')['queued'] == ['first', 'second']
    workers.send('first', 'two')
    assert workers.receive('first') == ['one', 'two']
    assert workers.receive('second') == ['one']
    with pytest.raises(ValueError):
        workers.pending('../escape')
