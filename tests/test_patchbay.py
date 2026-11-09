"""Delivery contracts: bounded routing, durable recovery, and reviewed writes."""
import threading

import pytest

from megazword.patchbay import PatchBay


def agent(bay, name):
    return bay.add(dict(kind='agent', title=name, provider='fake', tab_id=name, role='writer'))['id']


def finish(bay):
    thread = bay._thread
    if thread:
        thread.join(5)
        assert not thread.is_alive()
    return bay.view()


def test_peer_delivery_and_explicit_hub_apply(tmp_path):
    calls = []
    def send(node, prompt):
        calls.append((node['title'], prompt))
        return 'first draft' if len(calls) == 1 else 'reviewed document\n'
    bay = PatchBay(tmp_path / 'state', send)
    a, b = agent(bay, 'Writer'), agent(bay, 'Reviewer')
    document = tmp_path / 'doc.md'
    document.write_text('original\n')
    h = bay.add(dict(kind='hub', title='Document', root=str(tmp_path), file='doc.md'))['id']
    bay.connect(a, b)
    bay.connect(h, a)
    bay.connect(b, h)
    bay.start(a, 'Improve the document', 2)
    state = finish(bay)
    assert [x[0] for x in calls] == ['Writer', 'Reviewer']
    assert 'original\n' in calls[0][1]
    assert 'first draft' in calls[1][1] and 'Message from Writer' in calls[1][1]
    assert state['runs'][0]['state'] == 'complete'
    artifact = next(m for m in state['messages'] if m['state'] == 'artifact')
    assert document.read_text() == 'original\n'
    preview = bay.preview(artifact['id'])
    document.write_text('someone else edited\n')
    with pytest.raises(ValueError, match='File changed'):
        bay.apply(artifact['id'], preview['sha256'])
    document.write_text('original\n')
    bay.apply(artifact['id'], preview['sha256'])
    assert document.read_text() == 'reviewed document\n'
    with pytest.raises(ValueError, match='unapplied'):
        bay.apply(artifact['id'], preview['sha256'])


def test_cycle_is_bounded_and_queue_survives_restart(tmp_path):
    bay = PatchBay(tmp_path, lambda *_: 'response')
    a, b = agent(bay, 'A'), agent(bay, 'B')
    bay.connect(a, b)
    bay.connect(b, a)
    bay.start(a, 'discuss', 3)
    state = finish(bay)
    assert state['runs'][0]['used'] == 3
    assert state['runs'][0]['state'] == 'limit'
    again = PatchBay(tmp_path, lambda *_: pytest.fail('must not call on restart'))
    assert again.view()['messages'] == state['messages']
    with pytest.raises(ValueError, match='queued work'):
        again.remove(dict(id=a))
    again.control('discard')
    again.remove(dict(id=a))


def test_pause_finishes_current_turn_and_cross_instance_cannot_recover(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def send(node, prompt):
        calls.append(node['id'])
        entered.set()
        assert release.wait(5)
        return 'hello peer'
    bay = PatchBay(tmp_path, send)
    a, b = agent(bay, 'A'), agent(bay, 'B')
    bay.connect(a, b)
    bay.start(a, 'hello', 2)
    assert entered.wait(3)
    other = PatchBay(tmp_path, send)
    try:
        with pytest.raises(ValueError, match='Another dashboard'):
            other.control('resume')
        bay.control('pause')
    finally:
        release.set()
    assert finish(bay)['runs'][0]['state'] == 'paused'
    assert calls == [a]
    bay.control('resume')
    assert finish(bay)['runs'][0]['state'] == 'complete'
    assert calls == [a, b]


def test_failure_is_visible_and_never_automatically_replayed(tmp_path):
    def fail(*_):
        raise RuntimeError('provider unavailable')
    bay = PatchBay(tmp_path, fail)
    a = agent(bay, 'A')
    bay.start(a, 'hello', 2)
    state = finish(bay)
    assert state['messages'][0]['state'] == 'failed'
    assert 'provider unavailable' in state['messages'][0]['error']
    bay.control('resume')
    assert finish(bay)['runs'][0]['used'] == 1


@pytest.mark.parametrize('path', ['../outside', '/etc/passwd', '.env', 'folder/.secret'])
def test_hub_scope(tmp_path, path):
    bay = PatchBay(tmp_path / 'state', lambda *_: '')
    with pytest.raises(ValueError):
        bay.add(dict(kind='hub', title='Bad', root=str(tmp_path), file=path))


def test_interrupted_turn_is_not_replayed(tmp_path):
    bay = PatchBay(tmp_path, lambda *_: pytest.fail('cannot replay unknown outcome'))
    a = agent(bay, 'A')
    bay.launch = lambda: None
    bay.start(a, 'hello', 2)
    with bay.db() as db:
        db.execute("UPDATE messages SET state='running'")
        db.execute('UPDATE runs SET used=1')
    bay.control('resume')
    assert finish(bay)['messages'][0]['state'] == 'interrupted'


def test_shared_account_floor_blocks_provider_alias(tmp_path, monkeypatch):
    from megazword import config, dashboard
    from megazword.usage_sources import PlanUsage, Window
    monkeypatch.setattr(config, 'HOME', tmp_path)
    usage = dashboard.Usage(lambda: [PlanUsage('cmdc', [Window('5-hour', 90, None)], 'test')])
    app = dashboard.App(config.Config(), 'test', usage, {})
    monkeypatch.setattr(app, 'tabs_send', lambda *_: pytest.fail('quota floor must stop dispatch'))
    with pytest.raises(ValueError, match='allowance'):
        app.patchbay_send(dict(provider='cmdc-glm', tab_id='fake'), 'hello')
