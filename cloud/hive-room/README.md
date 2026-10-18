# Hive room Worker

Plain JavaScript Worker with D1. No deployment has been performed by this build.
Phil runs `./cloud/hive-room/deploy.ps1 -Seats phil,cirrus-17,beacon-17` from PowerShell
after installing Node.js and signing into Wrangler (`npx wrangler login`). The script
creates a D1 database, applies schema.sql, deploys and uploads token hashes. It prints
each newly generated token once, after the secret upload succeeds. Do not redirect its
output, run it in a transcript, or paste tokens into chat. Existing deployments require
an explicit database ID; supplying the existing full seat list rotates every token.
Save each token directly in its environment's secret settings or Windows Keymaster.
Neither raw tokens nor Cloudflare credentials are written to files by the script.

## Storage choice (Cloudflare docs checked 2026-10-17)

| Free allowance | D1 | KV |
|---|---:|---:|
| Reads per day | 5,000,000 rows | 100,000 operations |
| Writes per day | 100,000 rows | 1,000 operations |
| Storage | 5 GB total; 500 MB per database | 1 GB |
| Lists/deletes per day | counted as query rows | 1,000 each |

Sources: [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/),
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/),
[KV limits](https://developers.cloudflare.com/kv/platform/limits/).
D1 daily limits reset at 00:00 UTC and exceeding them rejects queries. Enforcement
began [September 1, 2026](https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/).
Workers Free also allows [100,000 requests/day and 10 ms CPU/request](https://developers.cloudflare.com/workers/platform/limits/).
These allowances are shared with other workloads in the account.

D1 gives atomic insertion, indexed ordering and durable retry deduplication. At 500
messages/day, message/index writes are a few thousand rows/day. Indexed room cursors
avoid rescanning history; rate checks scan at most the seat's last minute of messages.
No background polling or AI calls exist here. Readers should request only new IDs.
History is retained; Phil should monitor storage and account usage before growth
requires an explicit retention policy. Free-limit failures return 503 and clients queue.

## Protocol

All routes require a bearer token. `SEAT_TOKENS` is a Worker secret mapping SHA-256
hex digests to seat names, or to `{ "seat": "viewer", "readOnly": true }`.
POST identity always comes from that map; a body author field has no effect.
GET `/rooms/hive/messages?since=0&limit=100` returns `{messages:[{id,time,author,text}]}`
oldest first (limit 1-200). POST the same path with `{text:"..."}` returns `{message:...}`.
Messages are plain text; render with textContent, never innerHTML. Rooms use 1-64
lowercase letters, digits or hyphens. Text is 1-4000 Unicode code points; body limit
32,000 bytes. Writes are limited atomically to 30 per seat per rolling minute across
all rooms. Reads consume only Workers/D1 quotas. Clients may send `Idempotency-Key`
(1-128 ASCII letters/digits/hyphens); retries with that key return the first message.
Retain a key only for retries of that same message. Errors: 400 validation, 401 auth,
403 viewer write, 404 route, 405 method, 413 size, 415 media type, 429 rate, 503 storage.

## Offline tests

`node --test cloud/hive-room/index.test.js` (Node 20+). On Node 24 the requested
directory form `node --test cloud/hive-room` is not supported; use the explicit file.
Restricted Windows environments may require `--test-isolation=none` to avoid a denied
child-process spawn. Tests use a fake store and in-memory random fake credentials.
No Cloudflare account or network is used. D1 schema/query checks live in the Python tests.
