## Account API keys (run the account by API)

Contents, with the line each part starts on in this file:

- Rules an agent must follow: line 15
- Access: line 24
- Calls: line 38
- A key's record: line 127
- Refusals: line 131
- Example: line 144
- If a key leaks: line 167

An account API key lets a script or an agent run the account on `https://carbium.sh` without a session: it creates and retires service keys, sets their policies, manages webhooks and reads usage. It cannot buy, upgrade or cancel anything. It starts with `c_acct_`, is shown once, and calls made with it cost no credits. A service key (`c_serv_...`) is refused on these calls, and an account API key is refused on every plane of `services.carbium.sh`.

### Rules an agent must follow

1. Send `Authorization: Bearer <c_acct_ key>` on every call, and `Content-Type: application/json` with a JSON body.
2. Start with `GET /v1/api-key`. It answers the key's own record, so you know its `access`, `scopes` and `expires_at` before you act. Every answer to a live key also carries `x-api-key-expires`: an RFC 3339 time, or `never`. A 401 carries none.
3. A key cannot make, list or revoke account API keys. A person makes one on the dashboard's ACCOUNT page (Create API key, also in the user menu), or a session does: `POST /v1/account/api-keys` with `{"name": "ci-agent", "access": "full", "expires_in_days": 90, "ip_allow": []}`. `name` and `access` are required. `access` is `"full"` or `"read"`; `expires_in_days` is 30, 90 or 365, and `null` or left out means no expiry; `ip_allow` holds up to 16 IPv4 or IPv6 addresses or CIDRs (left out: any address), and a call from any other address answers 403. The answer holds `raw_key` once: store it and never print it. An agent that signed in with its wallet makes a key for its automation this way and keeps the wallet out of it.
4. One key may make 600 calls in each 10-minute window; past that a call answers 429 with `Retry-After`, the seconds left in the window. An address that sends 20 wrong keys in 10 minutes (an IPv6 caller counts by its /64) gets 429 `too many wrong keys from this address` for the rest of that window, its right key included: never guess or cycle keys. An account holds 5 live account API keys, on every plan.
5. Store a service key's `raw_key` when you create or rotate it. A key cannot read it again: `POST /v1/keys/{id}/secret` takes a session.
6. Payments, plan changes, renewals and removing a module are closed to a key and answer 401. Do not retry them: tell the person.

### Access

| | Full control (`"access": "full"`) | Read only (`"access": "read"`) |
|---|---|---|
| Service keys | create, rename, rotate, revoke, delete | list |
| A key's policies | planes, per-method caps, IP allowlist, connection and in-flight limits | read |
| Webhooks | create, change, pause, resume, test, rotate the secret, delete; the delivery log | list, read, the delivery log |
| Usage and telemetry | read | read |
| The account | plan, status, credits, payments and modules: read; add a free module plan | read |

A key's `scopes` list what it holds: `keys:read`, `keys:write`, `webhooks:read`, `webhooks:write`, `usage:read`, `account:read`, `modules:write`. Read only holds the four that end in `:read`.

Never, with any account API key: buy or upgrade a plan or a paid module; open the billing portal; cancel or resume a renewal; remove a module; make, list or revoke account API keys; link a wallet, log out or delete the account; read a service key's stored value; fetch an invoice document.

### Calls

**service keys · keys:read**

| Call | Request | Answer |
|---|---|---|
| `GET /v1/keys` | none | your service keys, oldest first, revoked ones included: key_id, prefix, name, tier, scope, status, per_method_caps, max_connections, max_inflight, ip_allow, created_at, rotated_at, revoked_at (allow_domains and allow_ips are old lists the doors do not use). Never a key's value |

**service keys and their policies · keys:write**

| Call | Request | Answer |
|---|---|---|
| `POST /v1/keys` | {name, scope}, both optional: name up to 48 characters, scope a list of rpc, ws, grpc, quote and das (rpc, ws, grpc and das when left out; quote needs the Quote module) | {key_id, prefix, raw_key, name}: the key's value, shown here once and mailed to the account's email address when it has one. 409 at your plan's count of service keys, or for quote without the module |
| `POST /v1/keys/{id}/rotate` | none | {prefix, raw_key}: a new value for the same key, mailed like a new key's; the old one is refused at once |
| `POST /v1/keys/{id}/revoke` | none | {applied}: true the first time, false on a repeat; every door refuses the key at once, and the first revoke mails a notice |
| `DELETE /v1/keys/{id}` | none | {deleted}: the key is gone from the list, and a live one is refused at every door; a repeat is 404 |
| `POST /v1/keys/{id}/name` | {name}: up to 48 characters, "" clears it | {name} |
| `PATCH /v1/keys/{id}/scope` | {scope}: the whole new list of planes (rpc, ws, grpc, quote, das), at least one; a plane left out is removed | {key_id, scope}; the doors follow within a second |
| `PATCH /v1/keys/{id}/caps` | {per_method_caps}: the whole new list of {method_class, rps_ceiling (0 or left out: no ceiling), allow (true when left out)}; [] clears every cap. method_class is o1_cached, bounded_read, bounded_slot, write_send, compute, bounded_disk, range, scan, gpa or das (the 10 DAS methods together) | the stored list; the doors follow at once |
| `PATCH /v1/keys/{id}/allowlist` | {ip_allow}: the whole new list of IPv4 or IPv6 addresses and CIDRs, 16 at most; [] admits any address | {key_id, ip_allow}; a call from any other address is 403 at the door |
| `PATCH /v1/keys/{id}/limits` | {max_connections, max_inflight}: 0 to 10,000 each; 0 or left out is the plan's own number, and both are replaced together | {max_connections, max_inflight}; the WebSocket and stream doors follow within 5 minutes |

**webhooks · webhooks:read**

| Call | Request | Answer |
|---|---|---|
| `GET /v1/webhooks` | none | your webhooks, without their address lists |
| `GET /v1/webhooks/{id}` | none | the webhook with its addresses |
| `GET /v1/webhooks/{id}/deliveries` | none; ?limit=, ?before= | its delivery log, newest first |

**webhooks · webhooks:write (fields and answers: Webhooks)**

| Call | Request | Answer |
|---|---|---|
| `POST /v1/webhooks` | the create fields | {webhook, secret}: the signing secret, shown here once |
| `PATCH /v1/webhooks/{id}` | any create field, status | the webhook |
| `DELETE /v1/webhooks/{id}` | none | {"deleted": true} |
| `POST /v1/webhooks/{id}/rotate` | none | {secret, secret_hint, previous_valid_until} |
| `POST /v1/webhooks/{id}/test` | none | how one signed test event went |

**usage and telemetry · usage:read**

| Call | Request | Answer |
|---|---|---|
| `GET /v1/usage` | none; ?from= and ?to= as YYYY-MM-DD, given together, both days included (the last 7 days when left out; over 90 days is 400), ?key_id=, ?group=key | [{utc_day, method, method_class, call_count, credits_charged}], oldest day first; with group=key each row also carries its key_id (null for calls made before a key was rotated, or by a key since deleted). A key_id that is not yours is 404, and an answer of more than 50,000 rows is 400: narrow the range or name a key. Answers are kept 15 s |
| `GET /v1/keys/usage` | none | {period_start, period_end, account_credits, keys: [{key_id, credits, calls}]}: this calendar month (UTC) per service key, revoked ones included. Calls made before a key was rotated, or by a key since deleted, count in account_credits only; account_credits is null when the read failed |
| `GET /v1/keys/load` | none | [{key_id, rps_current, class_rps}]: calls a second over the last 20 s for each live key, in all and per method class |
| `GET /v1/usage/hourly` | none; ?from= and ?to= as RFC 3339 times, given together (the last 24 hours when left out; over 7 days is 400), ?key_id= | [{hour, key_id, method_class, calls, credits_charged, errors, resp_bytes}], kept 90 days; the newest hour can be two hours behind. Answers are kept 60 s |
| `GET /v1/usage/latency` | none; the same ?from=, ?to= and ?key_id= | [{hour, key_id, method_class, calls, p50_ms, p95_ms, p99_ms}]: milliseconds with up to 3 decimals, kept 90 days. Answers are kept 60 s |

**the account · account:read**

| Call | Request | Answer |
|---|---|---|
| `GET /v1/account` | none | {account_id, email, wallet, status, created_at, tier, term, payments}: the plan and its term, and the last 24 payments |
| `GET /v1/balance` | none | {granted, used, remaining}, in credits |
| `GET /v1/invoices` | none | [{period_start, period_end, granted, used, current}]: credits per month, the running month first |
| `GET /v1/payments` | none | your payments, newest first, 1,000 at most: id, amount_minor, currency, status, method, tier or module and plan, months, credits_granted, reference, paid_at |
| `GET /v1/modules` | none | every module with its plans and what the account holds of it |
| `GET /v1/billing/crypto-intent/{id}` | none | one on-chain payment of yours and its status: open, paid, held or expired |

**modules · modules:write**

| Call | Request | Answer |
|---|---|---|
| `POST /v1/modules/{module}` | {plan}, or {} for the cheapest: a plan with no price (a priced one is 400 "plan '<name>' must be purchased") | the module as the account now holds it; 409 "module not available yet", 429 past the change limit |

**the key itself · any account API key**

| Call | Request | Answer |
|---|---|---|
| `GET /v1/api-key` | none | the calling key's own record |

**what a key did · a session, or the key for its own id**

| Call | Request | Answer |
|---|---|---|
| `GET /v1/account/api-keys/{id}/activity` | none; ?limit= (50, at most 200), ?before= (a Unix-ms time) | [{ts, action, request_id, detail}]: what the key changed, newest first; another key's id is 404 |

**making and revoking account API keys · dashboard session only**

| Call | Request | Answer |
|---|---|---|
| `POST /v1/account/api-keys` | {name, access, expires_in_days, ip_allow}: name 1 to 48 characters and access "full" or "read", both required; expires_in_days 30, 90 or 365 (null or left out: no expiry); ip_allow up to 16 addresses or CIDRs (left out: any address) | the new key's record with its raw_key, this once; 409 at 5 live keys, 403 while the account is not active |
| `GET /v1/account/api-keys` | none | the live keys' records, newest first |
| `DELETE /v1/account/api-keys/{id}` | none | {api_key_id, revoked}; a repeat answers the same |

The bodies and answers of the service-key and webhook calls are the ones under "Account, keys and billing" and "Webhooks" above. `key_id` is the service key's own id, as `GET /v1/keys` lists it, or `null` for calls made before a key was rotated or by a key since deleted: the ledger names a key by its value's hash. Times in the usage reads are UTC.

### A key's record

`{"api_key_id": 12, "name": "ci-agent", "prefix": "c_acct_AbCd", "access": "full", "scopes": ["keys:read", "keys:write", "webhooks:read", "webhooks:write", "usage:read", "account:read", "modules:write"], "ip_allow": [], "created_at": "2026-11-18T15:10:00Z", "expires_at": "2027-02-16T15:10:00Z", "last_used_at": null}`. `expires_at` is `null` for a key with no expiry. The create answer adds `raw_key`.

### Refusals

| HTTP | Message | What to do |
|---|---|---|
| 401 | `authentication required` | The key is unknown, revoked or expired, was made on the other dashboard name, or the call is closed to account API keys. |
| 403 | `this key is read only` | Use a Full control key. |
| 403 | `this key may not be used from this address` | Call from an address on the key's list. |
| 403 | `account is not active` | The account is suspended, banned or closed. The person sees the dashboard or contacts support. |
| 409 | `account API key limit reached (5)` | On create: revoke a key first. |
| 429 | | The key's 600 calls of this 10-minute window are spent. Wait `Retry-After` seconds, then send the call again. |
| 429 | `too many wrong keys from this address` | Wait until the window ends, then send the right key. |
| 429 | `too many key changes` | More than 120 service-key changes of the account in 10 minutes (webhooks: `too many webhook changes`). Wait, then send it again. |

### Example

```
# 1 who am I: the key's own record (name, access, scopes, expiry)
curl -s https://carbium.sh/v1/api-key -H 'Authorization: Bearer <c_acct_ key>'
# -> {"api_key_id":12,"name":"ci-agent","access":"full","scopes":["keys:read","keys:write",...],"expires_at":"2027-02-16T15:10:00Z",...}

# 2 make a service key for one app, RPC and WebSocket only, then lock it to the app's address
#   (FREE holds one service key: there this answers 409 until the starter key is revoked)
curl -s https://carbium.sh/v1/keys -H 'Authorization: Bearer <c_acct_ key>' \
  -H 'Content-Type: application/json' -d '{"name":"indexer","scope":["rpc","ws"]}'
# -> {"key_id":13,"prefix":"c_serv_AbCd","raw_key":"c_serv_...","name":"indexer"}   the value is shown once: store it
curl -s -X PATCH https://carbium.sh/v1/keys/13/allowlist -H 'Authorization: Bearer <c_acct_ key>' \
  -H 'Content-Type: application/json' -d '{"ip_allow":["203.0.113.7"]}'

# 3 watch it: this month's calls and credits per key, then the last day by hour
curl -s https://carbium.sh/v1/keys/usage -H 'Authorization: Bearer <c_acct_ key>'
curl -s 'https://carbium.sh/v1/usage/hourly?key_id=13' -H 'Authorization: Bearer <c_acct_ key>'

# 4 retire it: every door refuses the key at once
curl -s -X POST https://carbium.sh/v1/keys/13/revoke -H 'Authorization: Bearer <c_acct_ key>'
```

### If a key leaks

The person revokes it on the ACCOUNT page, and its next call answers 401. Until then its holder can do what the key's access allows: with Full control, revoke or rotate service keys, make new ones and spend the account's credits through them, and re-point or delete webhooks. It cannot spend money, cancel anything, get a session, delete the account, read a service key, a signing secret or a webhook's Authorization header that is in use, or make another key. Every change a key makes is kept under the key: `GET /v1/account/api-keys/{id}/activity`, which a session reads for any key and a key for its own id.

