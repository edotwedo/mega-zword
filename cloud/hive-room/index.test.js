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
