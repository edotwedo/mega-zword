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


def test_http_patchbay_requires_token_for_mutations(tmp_path, monkeypatch):
    import json
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from megazword import config, dashboard
    monkeypatch.setattr(config, 'HOME', tmp_path)
    app = dashboard.App(config.Config(), 'test', dashboard.Usage(lambda: []), {})
    server = ThreadingHTTPServer(('127.0.0.1', 0), dashboard.make_handler(app, 0))
    # Host validation must use the actual ephemeral port.
    server.RequestHandlerClass = dashboard.make_handler(app, server.server_port)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        page = urllib.request.urlopen(base + '/patchbay').read().decode()
        assert app.token in page and '__MZ_TOKEN__' not in page
        payload = json.dumps(dict(action='add', kind='hub', title='Document', root=str(tmp_path), file='doc.txt')).encode()
        req = urllib.request.Request(base + '/api/patchbay', data=payload, headers={'Content-Type': 'application/json'})
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(req)
        assert denied.value.code == 403
        req.add_header('X-MZ-Token', app.token)
        hub = json.load(urllib.request.urlopen(req))
        state = json.load(urllib.request.urlopen(base + '/api/patchbay'))
        assert state['nodes'][0]['id'] == hub['id']
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)


def test_pause_on_last_turn_still_lets_hub_output_resume_without_extra_turns(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def send(node, prompt):
        calls.append(node['id'])
        entered.set()
        assert release.wait(5)
        return 'final document\n'
    bay = PatchBay(tmp_path / 'state', send)
    a, b = agent(bay, 'Writer'), agent(bay, 'Reviewer')
    (tmp_path / 'doc.md').write_text('old\n')
    h = bay.add(dict(kind='hub', title='Document', root=str(tmp_path), file='doc.md'))['id']
    bay.connect(a, h)
    bay.connect(a, b)
    bay.start(a, 'write it', 1)
    assert entered.wait(3)
    bay.control('pause')
    release.set()
    paused = finish(bay)
    assert paused['runs'][0]['state'] == 'paused' and paused['runs'][0]['used'] == 1
    bay.control('resume')
    state = finish(bay)
    assert calls == [a], 'resume must not buy the Reviewer a turn past the budget'
    assert any(m['state'] == 'artifact' and m['target'] == h for m in state['messages'])
    assert state['runs'][0]['state'] == 'limit'


def _app(tmp_path, monkeypatch):
    from megazword import config, dashboard
    monkeypatch.setattr(config, 'HOME', tmp_path)
    app = dashboard.App(config.Config(), 'test', dashboard.Usage(lambda: []), {})
    return app, dashboard


def test_agent_tab_closed_and_reused_is_not_sent_to(tmp_path, monkeypatch):
    from megazword import tabs
    app, _ = _app(tmp_path, monkeypatch)
    first = tabs.create('fake', None, 'Writer')
    node = app.patchbay.add(dict(kind='agent', title='Writer', provider='fake', tab_id=first['id'], tab_created=first['created']))
    monkeypatch.setattr(app, 'tabs_send', lambda body: {'ok': True, 'answer': 'hi'})
    assert app.patchbay_send(node, 'hello') == 'hi'
    tabs.close(first['id'])
    with pytest.raises(ValueError, match='closed or replaced'):
        app.patchbay_send(node, 'hello')
    other = tabs.create('other-ai', None, 'Someone else')
    assert other['id'] == first['id'], 'tab ids are reused; that is the hazard'
    monkeypatch.setattr(app, 'tabs_send', lambda *_: pytest.fail('must not reach the replacement tab'))
    with pytest.raises(ValueError, match='closed or replaced'):
        app.patchbay_send(node, 'hello')


def test_removing_an_agent_closes_its_tab_but_removing_a_wire_does_not(tmp_path, monkeypatch):
    from megazword import tabs
    app, _ = _app(tmp_path, monkeypatch)
    t1, t2 = tabs.create('fake', None, 'A'), tabs.create('fake', None, 'B')
    a = app.patchbay.add(dict(kind='agent', title='A', provider='fake', tab_id=t1['id'], tab_created=t1['created']))
    b = app.patchbay.add(dict(kind='agent', title='B', provider='fake', tab_id=t2['id'], tab_created=t2['created']))
    app.patchbay.connect(a['id'], b['id'])
    wire = app.patchbay.view()['wires'][0]['id']
    app.patchbay_action(dict(action='remove', wire=wire))
    assert {t['id'] for t in tabs.list_tabs()} == {t1['id'], t2['id']}
    app.patchbay_action(dict(action='remove', id=a['id']))
    assert {t['id'] for t in tabs.list_tabs()} == {t2['id']}
