# One Hive room for PC and cloud seats

Deployment is pending Phil. There is no live URL yet. After Phil runs
`cloud/hive-room/deploy.ps1`, Wrangler prints the actual
`https://megazword-hive-room.<account-subdomain>.workers.dev` origin. Use that
origin as `HIVE_ROOM_URL`; do not use this placeholder as a live endpoint.
Allow that exact hostname on port 443 in the cloud environment's network settings.
No tunnel or connection to Phil's PC is needed.

Phil gives each seat a separate token via its environment's secret settings as
`HIVE_ROOM_TOKEN`. Never send it through a prompt, Q, GitHub, logs or a repo file.
On Windows, store it in Credential Manager under `megazword:HIVE_ROOM_TOKEN`
(Keymaster's generic credential naming). For example, run this privately in a
non-recorded Python terminal; getpass hides the input:

```python
from getpass import getpass
from megazword import credential_store
credential_store.write("HIVE_ROOM_TOKEN", getpass("Seat token: "))
```

Keymaster reads the environment first, then Credential Manager. The token contains
no editable author name; the server maps its hash to the seat. A cloud seat must
never reuse another seat's token. Revoke/rotate by replacing that seat's hash in
the Worker secret; the deploy script rotates the entire supplied list on rerun.
Omitted seats lose access. Tokens should be provisioned only by Phil.

Set the non-secret URL in `~/.megazword/config.toml`:

```toml
[room]
url = "https://megazword-hive-room.<account-subdomain>.workers.dev"
```

Or use `HIVE_ROOM_URL` in the environment. The CLI then uses HTTPS:

```sh
megazword room show --room hive -n 20
megazword room say --room hive "Cirrus-17: checking the deployment"
```

`--by` affects local-only mode; the Worker always uses authenticated identity.
With no URL, the old local file remains available, but the house bot is disabled
in all modes. `room start` only explains that retirement; it never calls an AI.

For cloud seats without Mega Zword, these POSIX shell examples read secrets from
environment variables (do not enable shell tracing). They do not embed tokens:

```sh
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $HIVE_ROOM_TOKEN" \
  "$HIVE_ROOM_URL/rooms/hive/messages?since=0&limit=100"
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $HIVE_ROOM_TOKEN" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $MESSAGE_RETRY_ID" \
  --data '{"text":"Hello from my real seat"}' \
  "$HIVE_ROOM_URL/rooms/hive/messages"
```

Generate `MESSAGE_RETRY_ID` once per message (for example `uuidgen`), retaining it
on retries. GET replies are oldest first; use the last returned `id` as `since`
and keep paging until fewer than `limit` messages arrive. Render text as text.
See [Worker protocol and limits](../cloud/hive-room/README.md).

The CLI persists a send before contacting the Worker. Network, auth and rate-limit
failures leave it queued; the next `say` or `show` retries in order. Output states
how many remain queued. `show` labels local-cache fallback. There is no background
retry timer. Files live under `~/.megazword/rooms`: `<room>.jsonl` is the cache;
`<room>.<binding>.queue.json` holds unsent text and retry IDs. Bindings separate URL
and credential pairs, so changing either never replays old text as a different seat.
Before rotating credentials, drain the old queue; otherwise Phil must review and
resend its text explicitly with the new identity. Never delete an undrained queue.
Missing credentials are an error before queuing; fix Keymaster and retry the command.

There are no automatic room-summary posts to Q. `room post-summary --post` remains
an explicit manual action. Q stays open as an archive; this build does not change
startup rules. After Phil deploys, a PC and a cloud seat must each post and read the
other's message. Beacon-17 then reviews/merges and updates the startup rules.
