## Webhooks (a signed HTTPS POST per finalized transaction)

Contents, with the line each part starts on in this file:

- Rules an agent must follow: line 13
- Calls (dashboard API: session token or account API key): line 22
- Delivery: line 60
- Retries and statuses: line 110
- Delivery log and test event: line 125

Register an HTTPS address and a list of Solana addresses; each finalized transaction that touches one of them arrives there as a signed `POST`, with no socket or stream to hold open. You manage webhooks on the dashboard's own API at `https://carbium.sh` with the dashboard session (`Authorization: Bearer <session token>`, as under Account, keys and billing) or an account API key (Account API keys), never a service key. Send each JSON body with `Content-Type: application/json`.

### Rules an agent must follow

1. Plans: 0 / 5 / 25 / 50 webhooks per account, each of up to 0 / 1,000 / 25,000 / 100,000 addresses, and 0 / 10 / 50 / 200 deliveries a second per account (FREE / DEV / BUSINESS / PRO); 1 credit per delivered event. A delivered test event costs the same as a delivered event. A failed try, a failed or refused test and every other call that manages a webhook cost 0. FREE is refused.
2. Store the `secret` (`whsec_...`) from the create reply. It is shown there and in the rotate reply only, and cannot be read again; reads show `secret_hint`.
3. Verify every delivery over the RAW body bytes before any `JSON.parse`, and refuse a `webhook-timestamp` more than 300 s from your clock.
4. Answer 2xx within 15 s, then do the work. A redirect is not followed and counts as a failed try.
5. Events that are sent arrive at least once: dedupe on `webhook-id`. No order is promised.
6. Not served: parsed (enhanced) payloads, account-change webhooks, Discord, batching, sending past events.

### Calls (dashboard API: session token or account API key)

| Call | Body | Answer |
|---|---|---|
| `GET /v1/webhooks` | none | your webhooks, oldest first, without address lists |
| `POST /v1/webhooks` | the create fields | `{"webhook": {...}, "secret": "whsec_..."}` |
| `GET /v1/webhooks/{id}` | none | the webhook, with `addresses` |
| `PATCH /v1/webhooks/{id}` | any create field, or `status` | the webhook |
| `DELETE /v1/webhooks/{id}` | none | `{"deleted": true}` |
| `POST /v1/webhooks/{id}/rotate` | none | `{"secret", "secret_hint", "previous_valid_until"}`: a new secret, shown once; the old one still verifies for one day |
| `GET /v1/webhooks/{id}/deliveries` | none; `?limit=` (50, at most 200), `?before=` (a line's `cursor`, or a Unix-ms time) | the delivery log, newest first: one line per try, per dropped event and per test, kept at least 7 days |
| `POST /v1/webhooks/{id}/test` | none | `{"event_id", "ts", "outcome", "http_status", "reason", "latency_ms", "refusal"}`: one signed test event, tried once |

| Field | | Rule |
|---|---|---|
| `key_id` | required | One of the account's live API keys. Deliveries are billed under it; revoking it pauses the webhook. |
| `url` | required | `https://` on port 443, a public host name (an IP address is refused), no user, password or fragment, at most 2,048 characters. |
| `addresses` | required | base58, 1 up to the plan's cap; a program id counts as an address. On `PATCH`, the whole new list. The System, Token, Token-2022, Associated Token, ComputeBudget and Vote programs are refused: nearly every transaction names them. |
| `name` | optional | At most 48 characters. |
| `tx_status` | optional | `"all"` (default), `"success"` or `"failed"`. |
| `auth_header` | optional | At most 512 visible ASCII characters, sent as the `Authorization` header of every delivery. `""` on `PATCH` clears it, and so does a new `url` sent without one. |
| `status` | `PATCH` only | `"paused"` or `"active"`; `"active"` also switches a `disabled` webhook back on. |

An unknown field is a 400. A webhook reads as `webhook_id`, `key_id`, `name`, `url`, `status`, `status_reason`, `tx_status`, `address_count`, `addresses` (single read only), `secret_hint`, `has_auth_header`, `consecutive_failures`, `last_success_at`, `last_failure_at`, `created_at`, `updated_at`.

| HTTP | Message | What to do |
|---|---|---|
| 400 | names what was typed wrong, e.g. `url must use https`, `url host must be a name, not an IP address` | Fix the request. |
| 401 | | Sign in again, or check the account API key. |
| 404 | | The webhook or key is missing, revoked, deleted or another account's. |
| 409 | `webhooks are not on the Free plan` | Buy DEV or above. |
| 409 | `webhook limit reached: the <plan> plan allows <n>` | Delete one or move up a plan. |
| 409 | `too many addresses: the <plan> plan allows <n> per webhook` | Shorten the list or move up a plan. A list of more than 100,000 addresses is a 400 on every plan. |
| 409 | `account is not active` | Resolve the account first. |
| 409 | `a test of this webhook is in flight` | One test per webhook runs at a time. Wait for its answer. |
| 429 | `too many webhook changes` | More than 120 creates, edits, tests, rotations and deletes of one account in 10 minutes. Wait up to 10 minutes and send it again; reads are never held. |
| 503 | | The control plane, the sender or the log did not answer. Make the same call again. |

### Delivery

| Part | What |
|---|---|
| `webhook-id` | The event's id, the same on every try of it. |
| `webhook-timestamp` | Unix seconds. |
| `webhook-signature` | `v1,` plus the base64 HMAC-SHA256 of `{webhook-id}.{webhook-timestamp}.{body}` under the secret's bytes: the base64 text after `whsec_`, decoded. Two signatures, separated by a space, while a rotated secret's day runs: accept either. |
| `Authorization` | Your `auth_header`, when set. |
| Body | A JSON array of one transaction, never a batch, in the shape `getTransaction` returns: `slot`, `blockTime` (`null` while the block's time is not known), `indexWithinBlock`, `transaction`, `meta` and `version`, as a Helius raw webhook sends. An address a transaction loads from a lookup table counts. Each try is a new connection with no `User-Agent` header. One `POST` per finalized transaction that touches a listed address; vote transactions never; `tx_status` filters by result. |
| Over 64 KB | A body past 65,536 bytes arrives in a short form: `slot`, `blockTime`, `indexWithinBlock`, `signature`, `err`, `status` and `truncated: true`. Read the rest with `getTransaction`. |

Create, receive and verify (Node 18+, no package):

```
# 1 create: the dashboard's API, with the session token or an account API key (never a service key)
curl -s https://carbium.sh/v1/webhooks -H 'Authorization: Bearer <session token>' \
  -H 'Content-Type: application/json' \
  -d '{"key_id":<your key_id>,"url":"https://example.com/hook","addresses":["<base58 address>"]}'
# -> {"webhook":{"webhook_id":7,"status":"active",...},"secret":"whsec_..."}
# the secret is shown once: store it. No 2xx within 15 s: 8 tries over about 27 hours.

# 2 test, once parts 3 and 4 answer on your url: one signed event with slot 0 and "test": true, tried once
curl -s -X POST https://carbium.sh/v1/webhooks/7/test -H 'Authorization: Bearer <session token>'
# -> {"event_id":"evt_test_...","outcome":"delivered","http_status":200,"reason":"","latency_ms":102,...}

// 3 receive (node, no package; save parts 3 and 4 as receive.mjs): keep the RAW body, answer 200 at once, work after
import { createServer } from "node:http";
createServer((req, res) => {
  const parts = [];
  req.on("data", (c) => parts.push(c)).on("end", () => {
    const raw = Buffer.concat(parts);
    if (!verify(process.env.WHSEC, req.headers, raw)) return res.writeHead(401).end();
    res.writeHead(200).end();
    for (const tx of JSON.parse(raw)) console.log(tx.test ? "test" : tx.slot, tx.transaction?.signatures[0] ?? tx.signature);
  });
}).listen(8080); // behind your https name on 443

// 4 verify: HMAC-SHA256 of id.timestamp.body under the secret's bytes
import { createHmac, timingSafeEqual } from "node:crypto";
function verify(secret, h, raw) {
  if (!secret) return false;
  const id = h["webhook-id"], ts = h["webhook-timestamp"];
  if (!id || !(Math.abs(Date.now() / 1000 - Number(ts)) <= 300)) return false; // 5 minutes
  const key = Buffer.from(secret.slice("whsec_".length), "base64");
  const want = Buffer.from("v1," + createHmac("sha256", key).update(id + "." + ts + ".").update(raw).digest("base64"));
  return String(h["webhook-signature"] || "").split(" ").some((s) => { const got = Buffer.from(s);
    return got.length === want.length && timingSafeEqual(got, want); });
}
```

### Retries and statuses

A try with no 2xx within 15 s is tried again after 5 s, 5 min, 30 min, 2 h, 5 h, 10 h and 10 h: 8 tries over about 27 hours, then the event is dropped. At most 2 calls are in flight per webhook. While every try of a webhook fails its new events wait too: 5 s after the first failed batch, then 5 minutes between batches, until one delivery succeeds. Events over your plan's deliveries a second wait in the webhook's queue, and so do events while the account is out of credits; no try is spent on them. The queue holds 10,000 events or 64 MiB per webhook, and past that the oldest are dropped. A webhook takes at most 200 transactions of one slot, the first in block order; the rest of that slot are not sent. A paused webhook keeps its queue and captures nothing new; a delete or the switch-off drops the queue. After 5 days of failed tries without one success the webhook turns `disabled`. If our sender stops for longer than its feed can replay (a few hundred slots), or the chain stops finalizing for more than 1,024 slots, the transactions of that stretch are not sent and no notice follows: read them with `getSignaturesForAddress` and `getTransaction`.

| `status` | `status_reason` | What to do |
|---|---|---|
| `active` | `null` | Nothing. |
| `paused` | `null` | You paused it: `PATCH {"status": "active"}`. |
| `paused` | `key_revoked`, `key_deleted`, `key_suspended`, `key_banned` | `PATCH` a live `key_id`, or lift the key's suspension. For `key_banned`, contact support. |
| `paused` | `account_suspended`, `account_closed`, `account_banned` | The account is not active. For `account_banned`, contact support. |
| `paused` | `over_plan_limit` | The plan was lowered: the newest webhooks past its count, or a list past its addresses. Delete one, shorten the list or move up a plan. |
| `disabled` | `no success in 5 days` | Fix the receiver, then `PATCH {"status": "active"}`. |

A `paused` webhook with a reason comes back by itself once the cause is lifted.

### Delivery log and test event

`GET /v1/webhooks/{id}/deliveries` lists what happened to a webhook's events, newest first: one line per try, per dropped event and per test, each about a second after it happened, kept at least 7 days. It answers 50 lines, or `?limit=` up to 200. For the lines before, send the last line's `cursor` as `?before=`; a page shorter than the limit is the last. A webhook that is missing or another account's reads as an empty list, never a 404. It is a record to debug with, not a bill, and a line can be missing.

| Field | What |
|---|---|
| `ts` | When, in Unix milliseconds (UTC). |
| `event_id` | The `webhook-id` the receiver saw. A test's starts with `evt_test_`. Empty on a drop whose id is not known. |
| `slot` | The transaction's slot; 0 on a test. |
| `kind` | `"delivery"` or `"test"`. |
| `attempt` | The try's number, 1 to 8; on a dropped event, the tries made, 0 to 8. |
| `outcome` | `"delivered"`; `"failed"` (a delivery is tried again); `"dropped"` (given up, the event is lost); `"refused"` (a test that was not sent). |
| `http_status` | Your url's status; 0 when it never answered. |
| `reason` | failed: `timeout`, `connect`, `tls`, `http`, or `refused` (we did not call the url: its name does not resolve, or points to an address that is not public), and empty when your url answered without a 2xx. dropped: `tries_spent`, `queue_full`, `disabled` or `switched_off`. refused: the cause in words. |
| `latency_ms` | From the name lookup to the answer's first line; 0 on a drop, a refusal or a url we did not call. |
| `cursor` | This line's place in the log, for `?before=`. |

`POST /v1/webhooks/{id}/test` (no body) sends one event to the webhook's url, signed like any delivery, and makes one try that waits up to 15 s. The call answers with how that try went (`event_id`, `ts`, `outcome`, `http_status`, `reason`, `latency_ms`, `refusal`), so allow it 20 s.

1. The test's body is `[{"slot": 0, "blockTime": <unix seconds>, "indexWithinBlock": 0, "signature": "<64 ones>", "err": null, "status": {"Ok": null}, "test": true}]` and its `webhook-id` starts with `evt_test_`. Skip it before any `getTransaction`.
2. A delivered test costs the same as a delivered event and shows in usage as a `webhookDelivery` under the webhook's key. A failed or refused test costs 0.
3. A test also goes to a webhook you paused and to a `disabled` one. It changes neither `status` nor `consecutive_failures`: a delivered test does not switch a webhook back on. A webhook paused for its key or its account gets its test refused, with the cause in `reason`.
4. A test counts as one of the account's 120 changes per 10 minutes (the 429 above), also when it answers 404 or 409, and against the plan's deliveries a second. One test per webhook runs at a time; a second answers 409.
5. A test refused before it is sent still answers 200, with `"outcome": "refused"`, the cause in `reason` and its class in `refusal`: `credits` (out of credits), `rate` (over the plan's deliveries a second), `plan` (webhooks are not on the plan), `key` (the webhook's API key is revoked, suspended or unknown), `secret`, `host` or `refused`. A url we will not call is `"outcome": "failed"` with `"reason": "refused"`. Read `outcome`, never the HTTP status alone.

