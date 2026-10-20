import {test, beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {handle, digest} from './index.js';
globalThis.crypto ??= webcrypto;

// Fake credentials are generated in memory, never stored in fixtures.
const token = crypto.randomUUID(), viewer = crypto.randomUUID();
const env = {SEAT_TOKENS: JSON.stringify({[await digest(token)]: 'cirrus-17', [await digest(viewer)]: {seat: 'viewer', readOnly: true}})};
class FakeStore {
  rows = [];
  async list(room, since, limit) { return this.rows.filter(m => m.room === room && m.id > since).slice(0, limit); }
  async latest(room, limit) { return this.rows.filter(m => m.room === room).sort((a, b) => b.id - a.id).slice(0, limit).reverse(); }
  async add(room, author, text, key, now) {
    const old = this.rows.find(m => m.room === room && m.author === author && m.key === key);
    if (old) return old;
    if (this.rows.filter(m => m.author === author && new Date(m.time) > now - 60000).length >= 30) return null;
    const row = {id: this.rows.length + 1, room, author, text, key, time: now.toISOString()};
    this.rows.push(row); return row;
  }
}
let store;
beforeEach(() => { store = new FakeStore(); });
const call = (method = 'GET', path = '/rooms/hive/messages', body, headers = {}) => handle(new Request('https://room.example' + path, {
  method, headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...headers},
  ...(body === undefined ? {} : {body: JSON.stringify(body)})
}), env, store);

test('all routes require authentication', async () => {
  assert.equal((await call('GET', '/missing', undefined, {Authorization: ''})).status, 401);
  assert.equal((await call('POST', undefined, {text: 'hi'}, {Authorization: 'Bearer invalid'})).status, 401);
});
test('server chooses author, preserves plain text and emoji', async () => {
  const res = await call('POST', undefined, {text: '<b>hello</b> 😀', author: 'phil'});
  assert.equal(res.status, 201);
  const {message} = await res.json();
  assert.equal(message.author, 'cirrus-17'); assert.equal(message.text, '<b>hello</b> 😀');
});
test('cursor, rooms and limit keep oldest-first order', async () => {
  for (let i = 0; i < 3; i++) await call('POST', undefined, {text: String(i)});
  await call('POST', '/rooms/other/messages', {text: 'other'});
  const data = await (await call('GET', '/rooms/hive/messages?since=1&limit=1')).json();
  assert.deepEqual(data.messages.map(m => m.id), [2]);
});
test('invalid rooms, methods and cursors fail', async () => {
  for (const path of ['/rooms/UPPER/messages', '/rooms/a_b/messages', '/rooms/../messages']) assert.equal((await call('GET', path)).status, 404);
  for (const query of ['since=-1', 'since=NaN', 'limit=0', 'limit=201', 'since=9007199254740992']) assert.equal((await call('GET', '/rooms/hive/messages?' + query)).status, 400);
  assert.equal((await call('DELETE')).status, 405);
});
test('text validation and body limits', async () => {
  for (const body of [null, [], {text: 1}, {text: ' '}, {text: 'a'.repeat(4001)}]) assert.equal((await call('POST', undefined, body)).status, 400);
  assert.equal((await call('POST', undefined, {text: '😀'.repeat(4000)})).status, 201);
  assert.equal((await call('POST', undefined, {text: 'a'.repeat(32001)})).status, 413);
  assert.equal((await call('POST', undefined, {text: 'hi'}, {'Content-Type': 'text/plain'})).status, 415);
});
test('read only tokens cannot write', async () => {
  const headers = {Authorization: `Bearer ${viewer}`};
  assert.equal((await call('GET', undefined, undefined, headers)).status, 200);
  assert.equal((await call('POST', undefined, {text: 'hi'}, headers)).status, 403);
});
test('retry key prevents duplicate messages', async () => {
  const headers = {'Idempotency-Key': crypto.randomUUID()};
  await call('POST', undefined, {text: 'hi'}, headers);
  await call('POST', undefined, {text: 'hi'}, headers);
  assert.equal(store.rows.length, 1);
});
test('seat rate is shared across rooms; retries still work at cap', async () => {
  for (let i = 0; i < 30; i++) assert.equal((await call('POST', undefined, {text: 'hi'}, {'Idempotency-Key': String(i)})).status, 201);
  assert.equal((await call('POST', '/rooms/other/messages', {text: 'hi'})).status, 429);
  assert.equal((await call('POST', undefined, {text: 'hi'}, {'Idempotency-Key': '0'})).status, 201);
});
test('bad JSON and storage failures return safe errors', async () => {
  const req = new Request('https://room.example/rooms/hive/messages', {method: 'POST', headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'}, body: '{'});
  assert.equal((await handle(req, env, store)).status, 400);
  store.list = () => { throw new Error('private details'); };
  const res = await call(); assert.equal(res.status, 503); assert.ok(!(await res.text()).includes('private details'));
});

const readPage = (query = '', key = token, method = 'GET') => call(method, '/read/' + key + query, undefined, {Authorization: ''});

test('web read returns newest N oldest first and flattens message newlines', async () => {
  const now = new Date('2026-10-18T12:00:00Z');
  for (const text of ['old', 'second\r\nline', '<b>new</b>\nlast'])
    await store.add('hive', 'reader', text, crypto.randomUUID(), now);
  const res = await readPage('?limit=2');
  assert.equal(res.status, 200);
  assert.equal(await res.text(), '2026-10-18T12:00:00.000Z [reader] second line\n2026-10-18T12:00:00.000Z [reader] <b>new</b> last');
});

test('web read defaults to latest 30 messages in hive', async () => {
  for (let i = 0; i < 35; i++) await store.add('hive', 'seat-' + i, String(i), String(i), new Date());
  await store.add('other', 'other', 'separate', 'other', new Date());
  const lines = (await (await readPage()).text()).split('\n');
  assert.equal(lines.length, 30);
  assert.match(lines[0], /\[seat-5\] 5$/);
  assert.match(lines.at(-1), /\[seat-34\] 34$/);
});

test('web read selects room and reports an empty room', async () => {
  await store.add('other', 'reader', 'separate', 'other', new Date());
  assert.match(await (await readPage('?room=other')).text(), /\[reader\] separate$/);
  assert.equal(await (await readPage()).text(), '(no messages)');
  for (const room of ['', 'UPPER', 'a_b', 'a'.repeat(65)])
    assert.equal((await readPage('?room=' + room)).status, 400);
});

test('web read rejects invalid tokens without falling back to bearer auth', async () => {
  for (const key of ['bad', 'bad.key', '']) {
    const res = await call('GET', '/read/' + key);
    assert.equal(res.status, 401);
    assert.equal(await res.text(), 'unauthorized');
    assert.equal(res.headers.get('Content-Type'), 'text/plain; charset=utf-8');
  }
});

test('web read validates limit and accepts its boundaries', async () => {
  for (const limit of ['', '0', '201', '-1', '1.5', 'NaN', '1e2', '9007199254740992'])
    assert.equal((await readPage('?limit=' + limit)).status, 400);
  for (const limit of ['1', '200']) assert.equal((await readPage('?limit=' + limit)).status, 200);
});

test('web read allows read-only seats and rejects other methods without writing', async () => {
  assert.equal((await readPage('', viewer)).status, 200);
  for (const method of ['POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
    assert.equal((await readPage('', viewer, method)).status, 405);
  assert.equal(store.rows.length, 0);
});

test('web read supplies privacy headers on success and errors and hides storage failures', async () => {
  const responses = [await readPage(), await readPage('', 'bad'), await readPage('?limit=0'), await readPage('', token, 'POST')];
  store.latest = () => { throw new Error('private storage details'); };
  const failed = await readPage();
  assert.equal(failed.status, 503);
  assert.equal(await failed.text(), 'room temporarily unavailable');
  for (const res of [...responses, failed]) {
    assert.equal(res.headers.get('Content-Type'), 'text/plain; charset=utf-8');
    assert.equal(res.headers.get('Cache-Control'), 'no-store');
    assert.equal(res.headers.get('X-Robots-Tag'), 'noindex');
    assert.equal(res.headers.get('Referrer-Policy'), 'no-referrer');
  }
});

const rpc = (method, params, id = 1, path = '/mcp', headers = {}) =>
  call('POST', path, {jsonrpc: '2.0', id, method, ...(params === undefined ? {} : {params})}, headers);
const invoke = (name, args = {}, headers = {}) => rpc('tools/call', {name, arguments: args}, 1, '/mcp', headers);

test('second different claim by the same designation is refused regardless of lane', async () => {
  assert.equal((await call('POST', undefined, {text: 'Beacon-17: claiming #3'})).status, 201);
  const res = await call('POST', undefined, {text: 'beacon-17: claiming #4'});
  assert.equal(res.status, 409);
  assert.deepEqual(await res.json(), {error: "Beacon-17 has open claim '#3'; post 'Beacon-17: releasing #3' first"});
  assert.equal(store.rows.length, 1);
  // Repeating the same claim (including a retry) does not claim different work.
  assert.equal((await call('POST', undefined, {text: 'Beacon-17: claiming #3'})).status, 201);
});

test('another designation cannot claim the same numbered item', async () => {
  await call('POST', undefined, {text: 'Beacon-17: claiming #3 server'});
  assert.equal((await call('POST', undefined, {text: 'Birch-18: claiming item 3 tests'})).status, 409);
  assert.equal((await call('POST', undefined, {text: 'Birch-18: claiming #30'})).status, 201);
});

test('release then claim succeeds, including another seats numbered completion', async () => {
  for (const release of ['releasing #3', 'released #3', 'dropping #3', 'dropped #3',
    'landed #3', 'done #3', 'complete #3', 'completed #3', 'merged #3', 'shipped #3', 'pushed #3', 'fixed #3']) {
    store = new FakeStore();
    await call('POST', undefined, {text: 'Beacon-17: claiming #3'});
    await call('POST', undefined, {text: `Beacon-17: ${release}`});
    assert.equal((await call('POST', undefined, {text: 'Beacon-17: claiming #4'})).status, 201, release);
  }
  store = new FakeStore();
  await call('POST', undefined, {text: 'Beacon-17: claiming #3'});
  await call('POST', undefined, {text: 'Birch-18: completed #3'});
  assert.equal((await call('POST', undefined, {text: 'Beacon-17: claiming #4'})).status, 201);
});

test('negated or unrelated completion does not release a claim', async () => {
  await call('POST', undefined, {text: 'Beacon-17: claiming #3'});
  for (const body of ['#3 is not done yet', '#3 hasnt shipped', 'done #4']) {
    await call('POST', undefined, {text: `Beacon-17: ${body}`});
    assert.equal((await call('POST', undefined, {text: 'Birch-18: claiming #3'})).status, 409);
  }
});

test('claims older than 24 hours are ignored', async () => {
  await store.add('hive', 'a-lane', 'Beacon-17: claiming #3', 'old', new Date(Date.now() - 86400001));
  assert.equal((await call('POST', undefined, {text: 'Beacon-17: claiming #4'})).status, 201);
  assert.equal((await call('POST', undefined, {text: 'Birch-18: claiming #3'})).status, 201);
});

test('lane labels are parsed and designation comes only from text', async () => {
  await call('POST', undefined, {text: 'Beacon-17 (claude-pc): claiming #3'});
  const res = await call('POST', undefined, {text: 'Beacon-17 (chatgpt): claiming #4'});
  assert.equal(res.status, 409);
  assert.match((await res.json()).error, /^Beacon-17 has open claim/);
  assert.equal((await call('POST', undefined, {text: 'Birch-18 (claude-pc): claiming #4'})).status, 201);
});

test('MCP post_message shares the REST claim check and returns a tool error', async () => {
  await invoke('post_message', {text: 'Beacon-17: claiming #3'});
  const {result} = await (await invoke('post_message', {text: 'Birch-18: claiming #3'})).json();
  assert.equal(result.isError, true);
  assert.equal(result.content[0].text, "Beacon-17 has open claim '#3'; post 'Beacon-17: releasing #3' first");
  assert.equal(store.rows.length, 1);
});

test('--force bypasses checks and the newest claim replaces the old claim', async () => {
  await call('POST', undefined, {text: 'Beacon-17: claiming #3'});
  assert.equal((await call('POST', undefined, {text: 'Beacon-17: claiming --force #4'})).status, 201);
  assert.equal((await call('POST', undefined, {text: 'Birch-18: claiming #3'})).status, 201);
  assert.equal((await call('POST', undefined, {text: 'Cedar-19: claiming #4'})).status, 409);
  const {result} = await (await invoke('post_message', {text: 'Cedar-19: claiming --force #4'})).json();
  assert.ok(!result.isError);
});

test('claim parsing matches ownership verbs, first line and first sentence rules', async () => {
  for (const verb of ['claim', 'claiming', 'take', 'taking', 'reserve', 'reserving', 'grab', 'grabbing', 'owning']) {
    store = new FakeStore();
    await call('POST', undefined, {text: `Beacon-17: ${verb} #3. Also landed #4\n#5`});
    assert.equal((await call('POST', undefined, {text: 'Birch-18: claiming #3'})).status, 409, verb);
    assert.equal((await call('POST', undefined, {text: 'Cedar-19: claiming #5'})).status, 201, verb);
  }
});

test('normal posts do not read claims and claim history is scoped to the latest 200 in the room', async () => {
  const latest = store.latest.bind(store);
  store.latest = () => { throw new Error('must not read for non-claims'); };
  for (const text of ['hi', 'Beacon-17: taking conductor', 'claiming #3', 'Beacon-17: note\nclaiming #3'])
    assert.equal((await call('POST', undefined, {text})).status, 201);
  store.latest = async (room, limit) => {
    assert.equal(room, 'hive'); assert.equal(limit, 200);
    return latest(room, limit);
  };
  await store.add('other', 'lane', 'Beacon-17: claiming #3', 'other', new Date());
  await store.add('hive', 'lane', 'Beacon-17: claiming #3', 'old', new Date());
  for (let i = 0; i < 200; i++) await store.add('hive', `lane-${i}`, 'ordinary note', String(i), new Date());
  assert.equal((await call('POST', undefined, {text: 'Beacon-17: claiming #4'})).status, 201);
});

test('MCP initialize negotiates supported versions and defaults', async () => {
  for (const version of ['2025-06-18', '2025-03-26', 'unknown']) {
    const res = await rpc('initialize', {protocolVersion: version});
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.jsonrpc, '2.0'); assert.equal(data.id, 1);
    assert.equal(data.result.protocolVersion, version === 'unknown' ? '2025-06-18' : version);
    assert.deepEqual(data.result.capabilities, {tools: {}});
    assert.deepEqual(data.result.serverInfo, {name: 'hive-room', version: '1'});
    assert.match(data.result.instructions, /designation/);
  }
});
test('MCP notifications return empty 202 and never run tools', async () => {
  for (const body of [
    {jsonrpc: '2.0', method: 'notifications/initialized'},
    {jsonrpc: '2.0', method: 'tools/call', params: {name: 'post_message', arguments: {text: 'hi'}}}
  ]) {
    const res = await call('POST', '/mcp', body);
    assert.equal(res.status, 202); assert.equal(await res.text(), '');
  }
  assert.equal(store.rows.length, 0);
});
test('MCP lists tools and answers ping and unknown methods', async () => {
  const {result} = await (await rpc('tools/list')).json();
  assert.deepEqual(result.tools.map(t => t.name), ['read_room', 'post_message']);
  assert.deepEqual((await (await rpc('ping')).json()).result, {});
  assert.equal((await (await rpc('missing')).json()).error.code, -32601);
  assert.equal((await (await invoke('missing')).json()).error.code, -32602);
});
test('MCP read_room defaults and cursor filtering match REST', async () => {
  for (let i = 0; i < 32; i++) await store.add('hive', 'other-' + i, String(i), String(i), new Date());
  await store.add('other', 'other', 'separate', 'other', new Date());
  const read = async args => JSON.parse((await (await invoke('read_room', args)).json()).result.content[0].text).messages;
  assert.equal((await read({})).length, 30);
  assert.deepEqual((await read({since: 1, limit: 1})).map(m => m.id), [2]);
  assert.equal((await read({room: 'other'}))[0].text, 'separate');
});
test('MCP post_message uses seat identity, preserves text and random retry keys', async () => {
  const args = {text: '<b>hi</b> ??', author: 'phil'};
  const {result} = await (await invoke('post_message', args)).json();
  const {message} = JSON.parse(result.content[0].text);
  assert.equal(message.author, 'cirrus-17'); assert.equal(message.room, 'hive');
  assert.equal(message.text, args.text);
  await invoke('post_message', args);
  assert.equal(store.rows.length, 2); assert.notEqual(store.rows[0].key, store.rows[1].key);
});
test('MCP accepts path and header tokens and rejects missing or bad tokens', async () => {
  assert.equal((await rpc('ping')).status, 200);
  assert.equal((await rpc('ping', undefined, 1, '/mcp/' + token, {Authorization: ''})).status, 200);
  for (const [path, auth] of [['/mcp', ''], ['/mcp', 'Bearer bad'], ['/mcp/bad', ''], ['/mcp/bad', `Bearer ${token}`]]) {
    const res = await rpc('ping', undefined, 1, path, {Authorization: auth});
    assert.equal(res.status, 401); assert.deepEqual(await res.json(), {error: 'unauthorized'});
  }
});
test('MCP refuses read-only writes with a tool error and allows reads', async () => {
  const headers = {Authorization: `Bearer ${viewer}`};
  const {result} = await (await invoke('post_message', {text: 'hi'}, headers)).json();
  assert.equal(result.isError, true); assert.equal(result.content[0].text, 'read only');
  assert.equal(store.rows.length, 0);
  assert.ok(!(await (await invoke('read_room', {}, headers)).json()).result.isError);
});
test('MCP GET and DELETE are not allowed for either auth route', async () => {
  for (const method of ['GET', 'DELETE']) for (const path of ['/mcp', '/mcp/' + token])
    assert.equal((await call(method, path)).status, 405);
});
test('MCP validation, batch rejection and body limits', async () => {
  for (const args of [{text: ''}, {text: ' '}, {text: 1}, {text: 'x'.repeat(4001)}, {text: 'hi', room: 'UPPER'}])
    assert.equal((await (await invoke('post_message', args)).json()).result.isError, true);
  for (const args of [{room: ''}, {since: -1}, {since: 0.5}, {since: '1'}, {limit: 0}, {limit: 201}, {limit: null}])
    assert.equal((await (await invoke('read_room', args)).json()).result.isError, true);
  for (const body of [[], [{jsonrpc: '2.0', id: 1, method: 'ping'}], null, {method: 'ping'}, {jsonrpc: '2.0', method: 'ping', id: {}}])
    assert.equal((await (await call('POST', '/mcp', body)).json()).error.code, -32600);
  assert.equal((await invoke('post_message', {text: 'a'.repeat(32001)})).status, 413);
  const malformed = new Request('https://room.example/mcp', {method: 'POST', headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'}, body: '{'});
  assert.equal((await (await handle(malformed, env, store)).json()).error.code, -32700);
});
test('MCP shares the REST seat rate across rooms and returns tool errors', async () => {
  for (let i = 0; i < 30; i++) await call('POST', undefined, {text: 'hi'});
  const res = await invoke('post_message', {room: 'other', text: 'hi'});
  assert.equal(res.status, 200);
  const {result} = await res.json();
  assert.equal(result.isError, true); assert.match(result.content[0].text, /30 messages per minute/);
  assert.equal(store.rows.length, 30);
});

test('MCP rejects non-object arguments and hides storage failures', async () => {
  for (const args of [null, [], 'text'])
    assert.equal((await (await invoke('read_room', args)).json()).result.isError, true);
  store.list = () => { throw new Error('private storage details'); };
  const res = await invoke('read_room');
  assert.equal(res.status, 503);
  assert.deepEqual(await res.json(), {error: 'room temporarily unavailable'});
});

// ntfy pings (2026-10-18): Phil's lanes wake the PC; @phil pings his phone. Never the text.
const philToken = crypto.randomUUID();
const pingEnv = {...env, NTFY_PC_TOPIC: 'pc-topic', NTFY_PHONE_TOPIC: 'phone-topic',
  SEAT_TOKENS: JSON.stringify({...JSON.parse(env.SEAT_TOKENS), [await digest(philToken)]: 'phil'})};
const pings = [];
const fakeFetch = async (url, init) => { pings.push({url, ...init}); return new Response('ok'); };
const post = (tok, text, e = pingEnv, path = '/rooms/hive/messages') => handle(new Request('https://room.example' + path, {
  method: 'POST', headers: {Authorization: `Bearer ${tok}`, 'Content-Type': 'application/json'},
  body: JSON.stringify(path === '/mcp' ? {jsonrpc: '2.0', id: 1, method: 'tools/call',
    params: {name: 'post_message', arguments: {text}}} : {text})}), e, store, new Date(), undefined, fakeFetch);
beforeEach(() => { pings.length = 0; });

test('a post from one of Phil\'s lanes pings the PC topic with only the id', async () => {
  assert.equal((await post(philToken, 'secret tax stuff')).status, 201);
  assert.equal(pings.length, 1);
  assert.equal(pings[0].url, 'https://ntfy.sh/pc-topic'); assert.equal(pings[0].body, 'hive:1');
  assert.ok(!JSON.stringify(pings).includes('secret'));
});
test('MCP posts from Phil\'s lanes ping too', async () => {
  assert.equal((await post(philToken, 'status?', pingEnv, '/mcp')).status, 200);
  assert.equal(pings.length, 1); assert.equal(pings[0].url, 'https://ntfy.sh/pc-topic');
});
test('a bot @phil pings the phone without the text; plain bot posts ping nothing', async () => {
  await post(token, 'routine note');
  assert.equal(pings.length, 0);
  await post(token, '@Phil done: private detail');
  assert.equal(pings.length, 1);
  assert.equal(pings[0].url, 'https://ntfy.sh/phone-topic');
  assert.equal(pings[0].body, 'New Hive message from cirrus-17');
  assert.ok(!JSON.stringify(pings).includes('private'));
});
test('no topics configured means no pings, and a failing ntfy never fails the post', async () => {
  assert.equal((await post(philToken, 'hi', {...pingEnv, NTFY_PC_TOPIC: ''})).status, 201);
  assert.equal(pings.length, 0);
  const res = await handle(new Request('https://room.example/rooms/hive/messages', {method: 'POST',
    headers: {Authorization: `Bearer ${philToken}`, 'Content-Type': 'application/json'}, body: JSON.stringify({text: 'x'})}),
    pingEnv, store, new Date(), undefined, async () => { throw new Error('down'); });
  assert.equal(res.status, 201);
});

for (const lane of ['claude-web', 'chatgpt']) test(`${lane} does not wake the PC`, async () => {
  const webToken = crypto.randomUUID();
  const webEnv = {...env, NTFY_PC_TOPIC: 'pc-topic', NTFY_PHONE_TOPIC: 'phone-topic',
    SEAT_TOKENS: JSON.stringify({...JSON.parse(env.SEAT_TOKENS), [await digest(webToken)]: lane})};
  assert.equal((await post(webToken, 'routine note', webEnv)).status, 201);
  assert.equal(pings.length, 0);
});

test('a post from the phone lane pings the PC topic so seats wake', async () => {
  const phoneToken = crypto.randomUUID();
  const phoneEnv = {...env, NTFY_PC_TOPIC: 'pc-topic',
    SEAT_TOKENS: JSON.stringify({...JSON.parse(env.SEAT_TOKENS), [await digest(phoneToken)]: 'phone'})};
  assert.equal((await post(phoneToken, 'Broadcast: check in', phoneEnv)).status, 201);
  assert.equal(pings.length, 1);
  assert.equal(pings[0].url, 'https://ntfy.sh/pc-topic');
});

test('the phone app page is served only under a valid key', async () => {
  const ok = await call('GET', '/app/' + token);
  assert.equal(ok.status, 200);
  assert.match(ok.headers.get('content-type'), /text\/html/);
  assert.equal(ok.headers.get('x-robots-tag'), 'noindex');
  assert.match(ok.headers.get('content-security-policy'), /connect-src 'self'/);
  const html = await ok.text();
  assert.match(html, /<title>Hive<\/title>/);
  assert.match(html, /id="badge"/);
  assert.match(html, /localStorage/);
  assert.ok(!html.includes(token), 'the key must not be baked into the page');
  assert.equal((await call('GET', '/app/not-a-real-key')).status, 401);
  assert.equal((await call('POST', '/app/' + token)).status, 405);
});

for (const path of ['/rooms/hive/messages', '/mcp']) {
  test(`Phil's grok-web lane wakes the PC through ${path} without exposing text`, async () => {
    const grokToken = crypto.randomUUID();
    const grokEnv = {...pingEnv, SEAT_TOKENS: JSON.stringify({
      ...JSON.parse(pingEnv.SEAT_TOKENS), [await digest(grokToken)]: 'grok-web'})};
    const res = await post(grokToken, 'private test content', grokEnv, path);
    assert.equal(res.status, path === '/mcp' ? 200 : 201);
    assert.equal(pings.length, 1);
    assert.equal(pings[0].url, 'https://ntfy.sh/pc-topic');
    assert.match(pings[0].body, /^hive:\d+$/);
    assert.ok(!JSON.stringify(pings).includes('private test content'));
  });
}
