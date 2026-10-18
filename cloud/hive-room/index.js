const json = (body, status = 200) => Response.json(body, {status, headers: {'Cache-Control': 'no-store'}});

export async function digest(token) {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}

export class D1Store {
  constructor(db) { this.db = db; }
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

export async function handle(request, env, store = new D1Store(env.DB), now = new Date()) {
  try {
    const bearer = /^Bearer ([^\s]+)$/.exec(request.headers.get('Authorization') || '');
    const seats = JSON.parse(env.SEAT_TOKENS || '{}');
    const identity = bearer && seats[await digest(bearer[1])];
    if (!identity) return json({error: 'unauthorized'}, 401);
    const seat = typeof identity === 'string' ? identity : identity.seat;
    if (typeof seat !== 'string' || !/^[a-z0-9-]+$/.test(seat)) return json({error: 'invalid seat configuration'}, 503);
    const url = new URL(request.url);
    const match = /^\/rooms\/([a-z0-9-]{1,64})\/messages$/.exec(url.pathname);
    if (!match) return json({error: 'not found'}, 404);
    if (request.method === 'GET') {
      const since = url.searchParams.get('since') || '0';
      const limit = url.searchParams.get('limit') || '100';
      if (!/^\d+$/.test(since) || !Number.isSafeInteger(Number(since)) || !/^\d+$/.test(limit) || Number(limit) < 1 || Number(limit) > 200)
        return json({error: 'since must be a nonnegative integer; limit must be 1-200'}, 400);
      return json({messages: await store.list(match[1], Number(since), Number(limit))});
    }
    if (request.method !== 'POST') return json({error: 'method not allowed'}, 405);
    if (typeof identity === 'object' && identity.readOnly) return json({error: 'read only'}, 403);
    if (!(request.headers.get('Content-Type') || '').toLowerCase().startsWith('application/json'))
      return json({error: 'use application/json'}, 415);
    // Bound streamed bodies too; Content-Length is not trusted.
    const reader = request.body?.getReader();
    let size = 0, chunks = [];
    if (reader) {
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 32000) { await reader.cancel(); return json({error: 'body too large'}, 413); }
        chunks.push(value);
      }
    }
    let body;
    try {
      const bytes = new Uint8Array(size); let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      body = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    } catch { return json({error: 'invalid JSON'}, 400); }
    if (!body || typeof body.text !== 'string' || !body.text.trim() || [...body.text].length > 4000)
      return json({error: 'text must contain 1-4000 characters'}, 400);
    const key = request.headers.get('Idempotency-Key') || crypto.randomUUID();
    if (!/^[A-Za-z0-9-]{1,128}$/.test(key)) return json({error: 'invalid retry key'}, 400);
    const message = await store.add(match[1], seat, body.text, key, now);
    return message ? json({message}, 201) : json({error: 'seat limit: 30 messages per minute'}, 429);
  } catch {
    return json({error: 'room temporarily unavailable'}, 503);
  }
}

export default {fetch: (request, env) => handle(request, env)};
