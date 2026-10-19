const json = (body, status = 200) => Response.json(body, {status, headers: {'Cache-Control': 'no-store'}});
const plain = (body, status = 200) => new Response(body, {status, headers: {
  'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store',
  'X-Robots-Tag': 'noindex', 'Referrer-Policy': 'no-referrer'
}});

export async function digest(token) {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}

export class D1Store {
  constructor(db) { this.db = db; }
  async latest(room, limit) {
    return (await this.db.prepare('SELECT id, author, text, time FROM messages WHERE room=? ORDER BY id DESC LIMIT ?')
      .bind(room, limit).all()).results.reverse();
  }
  async list(room, since, limit) {
    return (await this.db.prepare('SELECT id, author, text, time FROM messages WHERE room=? AND id>? ORDER BY id LIMIT ?')
      .bind(room, since, limit).all()).results;
  }
  async add(room, author, text, key, now) {
    const existing = await this.db.prepare('SELECT id, author, text, time FROM messages WHERE room=? AND author=? AND request_id=?')
      .bind(room, author, key).first();
    if (existing) return existing;
    // One statement makes the count and insert atomic across Worker instances.
    const result = await this.db.prepare(`INSERT INTO messages(room,author,text,time,request_id)
      SELECT ?,?,?,?,? WHERE (SELECT COUNT(*) FROM messages WHERE author=? AND time>?) < 30
      ON CONFLICT(room,author,request_id) DO NOTHING RETURNING id,author,text,time`)
      .bind(room, author, text, now.toISOString(), key, author, new Date(now - 60000).toISOString()).first();
    if (result) return result;
    return await this.db.prepare('SELECT id, author, text, time FROM messages WHERE room=? AND author=? AND request_id=?')
      .bind(room, author, key).first();
  }
}

const roomPattern = /^[a-z0-9-]{1,64}$/;
const textError = body => !body || typeof body.text !== 'string' || !body.text.trim() || [...body.text].length > 4000
  ? 'text must contain 1-4000 characters' : null;
const cursorError = 'since must be a nonnegative integer; limit must be 1-200';
const validCursor = (since, limit) => Number.isSafeInteger(since) && since >= 0 && Number.isInteger(limit) && limit >= 1 && limit <= 200;

async function readBody(request) {
  if (!(request.headers.get('Content-Type') || '').toLowerCase().startsWith('application/json'))
    return {error: 'use application/json', status: 415};
  // Bound streamed bodies too; Content-Length is not trusted.
  const reader = request.body?.getReader();
  let size = 0;
  const chunks = [];
  if (reader) {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 32000) { await reader.cancel(); return {error: 'body too large', status: 413}; }
      chunks.push(value);
    }
  }
  try {
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    return {body: JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes))};
  } catch { return {error: 'invalid JSON', status: 400}; }
}

async function postMessage(store, identity, seat, room, body, key, now) {
  if (typeof identity === 'object' && identity.readOnly) return {error: 'read only', status: 403};
  const error = textError(body);
  if (error) return {error, status: 400};
  if (!/^[A-Za-z0-9-]{1,128}$/.test(key)) return {error: 'invalid retry key', status: 400};
  const message = await store.add(room, seat, body.text, key, now);
  return message ? {message, status: 201} : {error: 'seat limit: 30 messages per minute', status: 429};
}

const PC_SEATS = new Set(['phil', 'claude-web', 'chatgpt', 'grok-web']);

// Fire an ntfy notification after a successful POST. Never includes message text.
// Uses ctx.waitUntil when available so the response is not delayed; otherwise awaits.
// Notify errors are always swallowed.
async function notify(env, seat, text, message, ctx, fetcher = globalThis.fetch) {
  let topic, body, title;
  if (PC_SEATS.has(seat) && env.NTFY_PC_TOPIC) {
    topic = env.NTFY_PC_TOPIC;
    body = `hive:${message.id}`;
  } else if (/@phil/i.test(text || '') && env.NTFY_PHONE_TOPIC) {
    topic = env.NTFY_PHONE_TOPIC;
    body = `New Hive message from ${seat}`;
    title = 'Hive';
  } else {
    return;
  }
  const promise = fetcher(`https://ntfy.sh/${topic}`, {
    method: 'POST',
    body,
    headers: title ? {Title: title} : {}
  }).catch(() => {});
  if (ctx?.waitUntil) ctx.waitUntil(promise);
  else await promise;
}

const tools = [
  {name: 'read_room', description: 'Read Hive coordination messages, oldest first.', inputSchema: {
    type: 'object', properties: {
      room: {type: 'string', pattern: '^[a-z0-9-]{1,64}$', default: 'hive'},
      since: {type: 'integer', minimum: 0, default: 0},
      limit: {type: 'integer', minimum: 1, maximum: 200, default: 30}
    }
  }},
  {name: 'post_message', description: 'Post a coordination message. Start with your designation.', inputSchema: {
    type: 'object', properties: {
      text: {type: 'string', minLength: 1, maxLength: 4000},
      room: {type: 'string', pattern: '^[a-z0-9-]{1,64}$', default: 'hive'}
    }, required: ['text']
  }}
];
const rpcError = (id, code, message) => json({jsonrpc: '2.0', id, error: {code, message}});
const toolResult = (text, isError = false) => ({content: [{type: 'text', text}], ...(isError ? {isError: true} : {})});

async function mcp(request, store, identity, seat, now, env, ctx, fetcher) {
  if (request.method !== 'POST') return json({error: 'method not allowed'}, 405);
  const parsed = await readBody(request);
  if (parsed.error) return parsed.status === 400 ? rpcError(null, -32700, 'Parse error') : json({error: parsed.error}, parsed.status);
  const body = parsed.body;
  if (!body || Array.isArray(body) || body.jsonrpc !== '2.0' || typeof body.method !== 'string' ||
      (Object.hasOwn(body, 'id') && body.id !== null && typeof body.id !== 'string' && !(typeof body.id === 'number' && Number.isFinite(body.id))) ||
      (body.params !== undefined && (!body.params || typeof body.params !== 'object' || Array.isArray(body.params))))
    return rpcError(null, -32600, 'Invalid Request');
  if (!Object.hasOwn(body, 'id')) return new Response(null, {status: 202, headers: {'Cache-Control': 'no-store'}});
  const result = value => json({jsonrpc: '2.0', id: body.id, result: value});
  switch (body.method) {
    case 'initialize': return result({
      protocolVersion: ['2025-11-25', '2025-06-18', '2025-03-26'].includes(body.params?.protocolVersion) ? body.params.protocolVersion : '2025-06-18',
      capabilities: {tools: {}}, serverInfo: {name: 'hive-room', version: '1'},
      instructions: "This is Phil's Hive coordination room; start messages with your designation."
    });
    case 'ping': return result({});
    case 'tools/list': return result({tools});
    case 'tools/call': {
      const name = body.params?.name;
      if (!tools.some(tool => tool.name === name)) return rpcError(body.id, -32602, 'Unknown tool');
      const args = body.params?.arguments === undefined ? {} : body.params.arguments;
      if (!args || typeof args !== 'object' || Array.isArray(args)) return result(toolResult('arguments must be an object', true));
      const room = args.room === undefined ? 'hive' : args.room;
      if (typeof room !== 'string' || !roomPattern.test(room)) return result(toolResult('room must contain 1-64 lowercase letters, digits or hyphens', true));
      if (name === 'read_room') {
        const since = args.since === undefined ? 0 : args.since;
        const limit = args.limit === undefined ? 30 : args.limit;
        if (!validCursor(since, limit)) return result(toolResult(cursorError, true));
        return result(toolResult(JSON.stringify({messages: await store.list(room, since, limit)})));
      }
      const posted = await postMessage(store, identity, seat, room, args, crypto.randomUUID(), now);
      if (!posted.error) await notify(env, seat, args.text, posted.message, ctx, fetcher);
      return result(posted.error ? toolResult(posted.error, true) : toolResult(JSON.stringify({message: posted.message})));
    }
    default: return rpcError(body.id, -32601, 'Method not found');
  }
}

export async function handle(request, env, store = new D1Store(env.DB), now = new Date(), ctx, fetcher = globalThis.fetch) {
  let readRoute = false;
  try {
    const url = new URL(request.url);
    readRoute = url.pathname.startsWith('/read/');
    const readPath = /^\/read\/([A-Za-z0-9_-]+)$/.exec(url.pathname);
    const mcpPath = /^\/mcp(?:\/([A-Za-z0-9_-]+))?$/.exec(url.pathname);
    const bearer = /^Bearer ([^\s]+)$/.exec(request.headers.get('Authorization') || '');
    const token = readRoute ? readPath?.[1] : mcpPath?.[1] || bearer?.[1];
    const seats = JSON.parse(env.SEAT_TOKENS || '{}');
    const identity = token && seats[await digest(token)];
    if (!identity) return readRoute ? plain('unauthorized', 401) : json({error: 'unauthorized'}, 401);
    const seat = typeof identity === 'string' ? identity : identity.seat;
    if (typeof seat !== 'string' || !/^[a-z0-9-]+$/.test(seat))
      return readRoute ? plain('invalid seat configuration', 503) : json({error: 'invalid seat configuration'}, 503);
    if (readRoute) {
      if (request.method !== 'GET') return plain('method not allowed', 405);
      const room = url.searchParams.get('room') ?? 'hive';
      const limit = url.searchParams.get('limit') ?? '30';
      if (!roomPattern.test(room)) return plain('room must contain 1-64 lowercase letters, digits or hyphens', 400);
      if (!/^\d+$/.test(limit) || !validCursor(0, Number(limit))) return plain('limit must be 1-200', 400);
      const messages = await store.latest(room, Number(limit));
      return plain(messages.length ? messages.map(m => `${m.time} [${m.author}] ${m.text.replace(/[\r\n\u2028\u2029]+/g, ' ')}`).join('\n') : '(no messages)');
    }
    if (mcpPath) return await mcp(request, store, identity, seat, now, env, ctx, fetcher);
    const match = /^\/rooms\/([a-z0-9-]{1,64})\/messages$/.exec(url.pathname);
    if (!match) return json({error: 'not found'}, 404);
    if (request.method === 'GET') {
      const since = url.searchParams.get('since') || '0';
      const limit = url.searchParams.get('limit') || '100';
      if (!/^\d+$/.test(since) || !/^\d+$/.test(limit) || !validCursor(Number(since), Number(limit)))
        return json({error: cursorError}, 400);
      return json({messages: await store.list(match[1], Number(since), Number(limit))});
    }
    if (request.method !== 'POST') return json({error: 'method not allowed'}, 405);
    if (typeof identity === 'object' && identity.readOnly) return json({error: 'read only'}, 403);
    const parsed = await readBody(request);
    if (parsed.error) return json({error: parsed.error}, parsed.status);
    const posted = await postMessage(store, identity, seat, match[1], parsed.body, request.headers.get('Idempotency-Key') || crypto.randomUUID(), now);
    if (!posted.error) await notify(env, seat, parsed.body?.text, posted.message, ctx, fetcher);
    return posted.error ? json({error: posted.error}, posted.status) : json({message: posted.message}, posted.status);
  } catch {
    return readRoute ? plain('room temporarily unavailable', 503) : json({error: 'room temporarily unavailable'}, 503);
  }
}

export default {fetch: (request, env, ctx) => handle(request, env, undefined, undefined, ctx)};
