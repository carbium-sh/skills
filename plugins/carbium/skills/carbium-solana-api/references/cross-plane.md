## Cross-plane: key states, credits, limits, retry

Contents, with the line each part starts on in this file:

- Key states (all `-32001`; `error.data.reason` names the state): line 10
- Credits: line 31
- Rate limits: line 41
- One retry and backoff policy (all planes): line 45

### Key states (all `-32001`; `error.data.reason` names the state)

| Message (exact) | HTTP (RPC/quote) | WS handshake | gRPC status | reason | What to do |
|---|---|---|---|---|---|
| `unknown api key` | 401 | 401 | UNAUTHENTICATED | `UNKNOWN_KEY` | Fix the carrier or send the whole key. A rotated key is unknown. Do not retry. |
| `api key suspended: the plan term ended; renew on the dashboard` | 401 | 401 | UNAUTHENTICATED | `KEY_SUSPENDED` (+`status_reason:"term_ended"`) | Rare: a key issued after a paid term ended, before the account moved to Free. Renew on the dashboard; once the account is on Free, its keys work at Free limits. |
| `api key suspended; contact support` | 401 | 401 | UNAUTHENTICATED | `KEY_SUSPENDED` | Stop and contact support. |
| `api key revoked` | 401 | 401 | UNAUTHENTICATED | `KEY_REVOKED` | The key was revoked or deleted. Stop and issue a new key. |
| `api key disabled; contact support` | 401 | 401 | UNAUTHENTICATED | `KEY_BANNED` | Stop and contact support. |
| `api key is not enabled for rpc` / `websocket` / `grpc` / `quote` / `das` | 401 | **403** (websocket) | UNAUTHENTICATED | `SCOPE_RPC_MISSING` / `SCOPE_WS_MISSING` / `SCOPE_GRPC_MISSING` / `SCOPE_QUOTE_MISSING` / `SCOPE_DAS_MISSING` | Add the scope to the key on the dashboard. |
| `client ip address is not on this api key's allowlist; add it on the dashboard or with PATCH /v1/keys/{id}/allowlist` | **403** | **403** | PERMISSION_DENIED | `IP_NOT_ALLOWED` | Call from an address on the key's IP allowlist, or add this one (up to 16 addresses or CIDRs; an empty list admits any address). |
| `session expired` | 401 | 401 | UNAUTHENTICATED | `EXPIRED_SESSION` | Dashboard session tokens only: sign in again. |
| `missing api key` (WS only) | n/a | 401 | n/a | n/a | Attach a carrier. |
| `streaming is not included in this tier; upgrade the plan` | n/a | n/a | PERMISSION_DENIED | n/a | FREE has no gRPC stream. Upgrade the plan. |

A key that is revoked, rotated, suspended or banned, or whose account is deleted, also ends its open connections within about 2 s: a WebSocket closes with `1008 key_revoked`, `key_suspended` or `key_banned`, and a Carbon stream ends UNAUTHENTICATED with the message above (a rotated key's stream reads `api key revoked`).

Scopes are per key: `rpc`, `ws`, `grpc`, `quote`, `das`. Change them on the dashboard. The 10 DAS methods need `das`, which a new key has unless you leave it out. Quote-plane verbs need only `quote` and are never batched. The account must also hold the quote module, or calls get 403 `-32050 "module not enabled for this account"`.

RPC body shape: `{"jsonrpc":"2.0","id":<your id>,"error":{"code":-32001,"message":"unknown api key","data":{"reason":"UNKNOWN_KEY","retryable":false}}}`. `error.data.retryable` is true exactly for the pressure band (429). A reply to an admitted call carries `x-request-id`; quote it to support. The WS handshake refusal body is `{"error":{"message":"..."}}`, not JSON-RPC.

### Credits

- `402`, `-32002`, `"credits exhausted"`, reason `CREDITS_EXHAUSTED`, `retryable:false`, `Retry-After: 1`. A 402 means the account's remaining credits cannot cover the call. On WS the handshake does not check credits: a subscribe answers `-32002` inside the socket, and a live socket whose streamed bytes cannot be paid closes with **1008 `credits_exhausted`**. On gRPC it is `RESOURCE_EXHAUSTED` `credits exhausted` (`consumer_credits_exhausted` on an open stream): do not retry. On RPC and WS do not retry either (after a 1008 close, reconnect once after about 5 s): buy a plan or upgrade on the dashboard (each month of an RPC plan adds its credits; a Quote plan adds none). Near the end of a balance a node can answer 402 while the last credits sit reserved at other nodes; they return within minutes.
- `429`, `-32005`, `"credits for this account are still loading on this node; retry after Retry-After"`, reason `CREDITS_PENDING`, `retryable:true`, `Retry-After: 1`, `retry-after-ms: 1000`. The account has credits, but this node has not loaded them yet (a new account's first calls, a burst that spent this node's share, or just after a node restart). It is not a 402: wait and send it again. On WS it is a subscribe reply `-32005` with `data.retryAfterMs` 1000, and the socket stays open; on gRPC it is `RESOURCE_EXHAUSTED` with that message and `retry-after: 1`. A live stream can end on it too: a WS socket closes `1013 credits_pending` (reconnect after about 1 s and re-subscribe), and a gRPC stream ends `UNAVAILABLE` with that message and `retry-after: 1` (resubscribe after it); the bytes already sent are billed.
- Refused calls cost 0 credits, except a getTransactionsForAddress walk refused after it made upstream calls, which bills those calls, and a failed preflight send, which keeps its 75 credits.
- What spends credits:
  - **RPC**: each method's credits, in the Credits column of the [RPC method catalogue](https://carbium.sh/skill/rpc.md). Token scans also bill per row returned, and a getTransactionsForAddress walk per upstream call it makes, as their catalogue rows show.
  - **WS and gRPC**: 5 per slot/root/signature subscription, 25 per account/logs-mentions/slotsUpdates subscription (gRPC: an `accounts` filter with an `account` list, or a `transactions` filter narrowed by account), 200 per program/logs-all/block subscription (gRPC: an `accounts` filter with `owner`, `blocks`, `blocksMeta`, `entry` or a transaction firehose), plus 20 per MiB delivered. A gRPC stream that delivers no data books 0 credits.
  - **Quote plane**: 0 credits; calls count against the account's quote plan. They are answered even when the account's credits are spent: a call that costs 0 credits is never refused for credits.

### Rate limits

Rates are per account (all its keys share one bucket), in cells per second; every method's cells and the plan rates are in the [RPC method catalogue](https://carbium.sh/skill/rpc.md). On RPC and the quote plane, a call over its plan rate that fits within 1 s waits and is served, and a call short of a concurrency slot waits up to 3 s for one; only then comes the 429. WebSocket and gRPC refuse at once. A 429 has `-32005` and one of these messages: `rate limit exceeded` (`RATE_LIMITED`), `heavy-class rate limit exceeded` (`HEAVY_CLASS_LIMITED`), `blocking-slot capacity exceeded: <pool> pool`, `scan-index lane capacity exceeded: chot_lane`, `DAS lane capacity exceeded: das_lane`, `quote lane capacity exceeded: quote_lane` or `free quote plan at capacity: ...` (`SLOT_CAP_EXCEEDED`), `overloaded` (`LOAD_SHED`), or, on the Free plan and the free quote plan, `free tier limit for your network reached: ...` (`FREE_SUBNET_LIMITED`: all free keys calling from one network share one budget) and `free tier at capacity on this node: ...` (`FREE_TIER_BUSY`), and `credits for this account are still loading on this node; retry after Retry-After` (`CREDITS_PENDING`: the node has not loaded the account's credits yet, as on a new account's first calls, after a burst that spent this node's share, or just after a node restart). The one 429 with another code is `-32010` `scan index temporarily unavailable, retry` (`CHOT_INDEX_UNAVAILABLE`). Every 429 on RPC and the quote plane carries `Retry-After` in whole seconds and `retry-after-ms`, which is exact; prefer the ms header (a browser can read only `Retry-After`). On gRPC the status is `RESOURCE_EXHAUSTED` with `retry-after` metadata in seconds. On a WS handshake it is 429 with `Retry-After`, and the messages include `connection or subscription cap exceeded` and `overloaded or draining`.

### One retry and backoff policy (all planes)

Backoff means: wait the larger of the server's hint (`retry-after-ms`, else `Retry-After` × 1000) and `250 ms × 2^(attempt−1)` capped at 4 s, plus 0 to 250 ms of random jitter. Never cut a server hint to 4 s. Stop after 4 attempts unless the row says otherwise.

| Error class | Where | Retry? | How | When to stop |
|---|---|---|---|---|
| 400 / -32600 / -32602 (malformed, bad params, batch refused, body over 50 KB with HTTP 413) | RPC, quote, swap, prices | No (getTransactionsForAddress's `-32602` `the walk read no history`: yes, as a 429) | Fix the request. | Immediately. |
| -32601 `method not found` / `method not served` (HTTP 200) | RPC | No | Use a served method. | Immediately. |
| 401 / -32001, 403 / -32001 `IP_NOT_ALLOWED`, WS 401/403, gRPC UNAUTHENTICATED | all | No | Fix or renew the key, add the scope, or call from an allowed address. | Immediately. |
| 403 / -32050 `module not enabled for this account` | quote, swap, prices, health | No | Add it with `POST https://carbium.sh/v1/modules/quote`, your session or a Full control account API key, and the JSON body `{"plan": "free"}` (the free plan), or on the dashboard's MODULES page. | Immediately. |
| gRPC PERMISSION_DENIED | gRPC | No | Act on the message (see the [gRPC error table](https://carbium.sh/skill/stream.md)): `streaming is not included in this tier` means upgrade the plan, the allowlist message means call from a listed address, and the rest mean fix the filter or the request. | Immediately. |
| 402 / -32002, WS subscribe `-32002` | RPC, WS | No | Buy a plan or upgrade. | Immediately. |
| WS close 1008 `credits_exhausted` | WS | Once | Reconnect once after about 5 s and re-subscribe; if the subscribes answer `-32002`, buy a plan or upgrade; if they answer `-32005` `CREDITS_PENDING`, wait `retryAfterMs` and resend. | After that one reconnect. |
| WS close 1013 `credits_pending`, gRPC UNAVAILABLE `credits for this account are still loading on this node; retry after Retry-After` | WS, gRPC | Yes | Reconnect after about 1 s (gRPC: after the `retry-after`) and re-subscribe; do not buy anything. | Back off after 3 failed reconnects. |
| gRPC RESOURCE_EXHAUSTED `credits exhausted` / `consumer_credits_exhausted` | gRPC | No | Buy a plan or upgrade. | Immediately. |
| 429 / -32005 (including the Free network limits and, on calls that cost credits, `CREDITS_PENDING`), gRPC RESOURCE_EXHAUSTED (rate, or `credits for this account are still loading on this node; retry after Retry-After`) | all | Yes | Back off, honouring `retry-after-ms`. Lower concurrency (quote: at most 8 in flight per key). | 4 attempts, then lower your request rate. |
| 429 / -32010 `CHOT_INDEX_UNAVAILABLE` (scan index behind) | RPC scans | Yes | Back off from 100 ms (100, 200, 400 ... capped at 5 s), honouring `retry-after-ms`. | About 6 tries, then surface the error. |
| 503 / -32011 and other 503s (breaker, upstream down, `cooling down`, `stale`) | RPC, quote, swap, prices | Yes | Back off, honouring `Retry-After`. | 4 attempts. For a swap, quote again if more than 30 s have passed since the quote. |
| 504 (scan over its deadline) | RPC | Yes, once | Narrow the request. | 1 retry. |
| Network error or timeout, no response | all | Yes | Back off. | 4 attempts. A `sendTransaction` with no response may have landed: check the signature status before sending again. |
| 200 / -32051 `no route`, -32054 | quote | No (see the [why table](https://carbium.sh/skill/quote.md)) | Change the pair or size, or wait the named window. | Do not loop faster than every 30 s. |
| 200 / -32055 | quote, swap | Only with a changed ask | Raise `maxAccounts` (at most 64), lower `amount_in`, or quote without `maxAccounts` and `swapTag`. | Once per change. |
| 200 / -32053 | quote | Only with a much smaller amount | The engine already tried the part under `error.data.max_amount_in`: quote again well under it. | If `why` is `partial_below_fee`, or `max_amount_in` is 0, stop. |
| 400 / -32095, -32074; 200 / -32081, -32082, -32083, -32096; 200 / -32093 | swap | Quote again | Get a new `quote`, then `swap`. | 3 rounds. |
| 200 / -32098 | swap | No | The wallet must hold `gate_min` of `gate_mint`. | Immediately. |
| 200 / -32099 | swap | No | Stop for this token. | Immediately. |
| On-chain `Custom:6004` (under the slippage floor) | after send | Quote again | Quote, swap, sign, send again. | 3 rounds. |
| On-chain, any other `Custom` code | after send | No | It is the venue's own error (see [Signing, sending and confirming](https://carbium.sh/skill/quote.md)). | Immediately. |
| Blockhash expired (block height > `lastValidBlockHeight`, not landed) | after send | Quote again | Never re-sign the old message. | 3 rounds. |
| WS close 1013 `slow_consumer` / `delivery_overload_retry` | WS | Yes | Reconnect with backoff, read faster, subscribe to less. | Back off further after 3 closes in a row. |
| WS close 1012 `draining` / `stream_gap_reseed_required` | WS | Yes | Reconnect at once with jitter and re-subscribe everything; re-read state you may have missed. | Back off after 3 failed reconnects. |
| WS close 1001 `idle_timeout` (900 s idle) / `no_pong` (300 s without a pong) | WS | Yes | Reconnect. Answer server pings (sent every 30 s); a pong counts as traffic. | Fix the client. |
| gRPC RESOURCE_EXHAUSTED `consumer_lagged: your stream fell behind the ring; reduce filters or read faster` | gRPC | Yes | Wait `retry-after` (2 s); reduce filters. | Back off after 3 in a row. |
| gRPC UNAVAILABLE / DEADLINE_EXCEEDED | gRPC | Yes | Back off and resubscribe. | 4 attempts, then 30 s waits. |
| gRPC OUT_OF_RANGE `gap: re-seed required` (`fromSlot` too old, or a gap in the upstream feed) | gRPC | Yes, after a re-seed | Reload state over RPC, then resubscribe with no `fromSlot` (or with `fromSlot >= firstAvailable`). | Back off after 3 in a row. |
| gRPC INVALID_ARGUMENT | gRPC | No | Fix the request. | Immediately. |

