"""Real local worker connections and durable, explicitly addressed inboxes."""
import os
import hashlib
import sqlite3
import time
import uuid

from . import briefing, config, workspace as ws


def _live(item):
    try:
        return ws.runtime_alive(item)
    except ImportError:
        return False  # workspace extras are optional in a basic CLI install


def connect(seat, session=None, client=None):
    """Called by a worker's persistent MCP server, not a provider health probe."""
    try:
        import psutil
    except ImportError:
        return ''
    seat = briefing._seat(seat)
    session = session or os.getenv('MEGAZWORD_SESSION') or os.getenv('CODEX_THREAD_ID', '')
    key = seat
    previous = ws.load(config.HOME / 'workers' / f'{key}.json')
    if seat in ws.COLORS or (previous.get('pid') != os.getpid() and _live(previous)):
        suffix = hashlib.sha256(session.encode()).hexdigest()[:12] if session else str(os.getpid())
        key = f'{seat[:48]}-{suffix}'
    ws.save(config.HOME / 'workers' / f'{key}.json', {
        'id': key, 'seat': seat, 'session': session,
        'client': client or os.getenv('MEGAZWORD_CLIENT', 'MCP'),
        'pid': os.getpid(), 'process_started': psutil.Process().create_time(),
        'transport': 'mcp', 'updated': time.time()})
    return key


def roster():
    cards = {c['seat']: c for c in briefing.snapshot()['cards']}
    found = {}
    for path in (config.HOME / 'workers').glob('*.json'):
        item = ws.load(path)
        if not isinstance(item, dict) or not item.get('id'):
            continue
        live = _live(item)
        card = cards.get(item['seat'], {})
        if card.get('session') and item.get('session') != card['session']:
            card = {}
        found[item['id']] = {**item, 'connected': live, 'reachable': live,
                             'seat': item['seat'] + (f" · {item.get('session', '')[:8] or item['pid']}" if item['seat'] in ws.COLORS else ''),
                             'state': card.get('state', 'unknown'),
                             'doing': card.get('doing', ''), 'transport': 'mcp'}
    # Native writer locks/PIDs prove a session exists; a saved roster alone does not.
    try:
        native = ws.discover(config.HOME.parent)
    except (OSError, ValueError, sqlite3.Error, ImportError):
        native = []
    for tab in native:
        session = tab['session']
        if any(w.get('session') == session and w['connected'] for w in found.values()):
            continue
        runtime = ws.load(config.HOME / 'workspace' / f'tab-{session}.json')
        key = f"{tab['client']}-{session}"
        reachable = _live(runtime) and runtime.get('inbox_version') == 1
        card = next((c for c in cards.values() if c.get('session') == session), {})
        found[key] = {'id': key, 'seat': card.get('seat') or tab.get('designation') or f"{tab['client']} · {session[:8]}",
                      'session': session, 'client': tab['client'], 'connected': True,
                      'reachable': bool(reachable), 'transport': 'terminal',
                      'state': card.get('state', 'unknown'), 'doing': card.get('doing', '')}
    # Historical names stay visible but cannot masquerade as connected workers.
    linked = {w['seat'] for w in found.values()}
    for seat, card in cards.items():
        if seat not in linked:
            found[seat] = {'id': seat, 'seat': seat, 'client': '', 'session': card.get('session', ''),
                           'connected': False, 'reachable': False, 'transport': '',
                           'state': card['state'], 'doing': card['doing']}
    return sorted(found.values(), key=lambda w: (not w['connected'], w['seat']))


def pending(worker):
    worker = briefing._seat(worker)
    for path in sorted((config.HOME / 'worker-inbox' / worker).glob('*.json')):
        item = ws.load(path)
        if item.get('state') == 'queued':
            return item
    return None


def acknowledge(worker, message):
    worker, message = briefing._seat(worker), briefing._seat(message)
    path = config.HOME / 'worker-inbox' / worker / f'{message}.json'
    item = ws.load(path)
    if item:
        ws.save(path, {**item, 'state': 'delivered', 'delivered': time.time()})


def send(target, text):
    text = briefing._text(text, 'message', 4000)
    if not text:
        raise ValueError('empty worker message')
    available = [w for w in roster() if w['reachable'] and (target == '*' or w['id'] == target)]
    if not available:
        raise ValueError('No connected worker can receive this message. Reopen managed tabs or connect Hive MCP.')
    queued = []
    for worker in available:
        mid = f'{time.time_ns():020d}-{uuid.uuid4().hex}'
        ws.save(config.HOME / 'worker-inbox' / worker['id'] / f'{mid}.json', {
            'id': mid, 'text': text, 'state': 'queued', 'created': time.time(), 'author': 'phil'})
        queued.append(worker['seat'])
    return {'queued': queued, 'status': 'queued; delivered when the worker reads or its terminal is idle'}


def receive(seat):
    messages = []
    for _ in range(20):
        item = pending(seat)
        if not item:
            break
        messages.append(item['text'])
        acknowledge(seat, item['id'])
    return messages
