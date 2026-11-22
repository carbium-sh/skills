## WebSocket (JSON-RPC 2.0 subscriptions over WSS)

Contents, with the line each part starts on in this file:

- Rules an agent must follow: line 22
- Auth carriers (handshake): line 36
- Handshake refusals (HTTP, before the upgrade): line 50
- Limits: line 72
- Billing (credits): line 94
- Subscription methods served: line 117
- Coverage: what each subscription actually sees: line 163
- blockSubscribe: line 201
- signatureSubscribe semantics: line 215
- Errors inside an open socket (JSON-RPC replies to your request): line 223
- Server close codes: line 265
- Quick start: line 286
- Robust client (Node, `npm i ws`): line 330
- Common mistakes: line 524

Endpoint: `wss://services.carbium.sh` on port 443, the same domain and key as RPC. The wire protocol is Solana's (agave) pubsub: send `xSubscribe`, get back a numeric subscription id, then receive `xNotification` frames until you send `xUnsubscribe` or the socket closes.

### Rules an agent must follow

1. Authenticate with the **full raw key** (`c_serv_…`). The short prefix the dashboard shows (`c_serv_` plus four characters) gets `401 unknown api key`.
2. Open **one socket and reuse it** for many subscriptions: up to 1,000 per socket. Open another socket only past that, and stay inside your plan's connection cap (see Limits).
3. **Wait for each subscribe's reply** before you count the subscription as live. The reply's `result` is the subscription id. The server always sends that reply before the first notification for the id.
4. Route notifications by `params.subscription`, not by your request `id`.
5. Subscription ids are **not stable across connections**. After any reconnect, re-send every subscribe and map the new ids.
6. Nothing is replayed. After any disconnect, re-read the state you care about over HTTPS RPC (`getAccountInfo`, `getSignatureStatuses`, …).
7. Your client must answer server pings. Browsers, Node 22+ global `WebSocket` and the `ws` package do this automatically. Do not block the event loop for long stretches.
8. Read fast. A socket whose outbound queue fills is closed with `1013 slow_consumer`.
9. A `signatureSubscribe` ends itself after its one notification. Never unsubscribe it afterwards. If you do, the answer is `-32602 "Invalid subscription id."`, which is harmless.
10. Send subscribes at no more than 500 per second per account. Keep about 32 unanswered requests in flight per socket. That is advice, not a server limit; the server closes a socket that leaves more than 64 replies unread with `1013 slow_consumer`.
11. Only the subscribe/unsubscribe methods below and `getVersion` work over the socket. Every other JSON-RPC method answers `-32601 "method not found"`, so send it to `https://services.carbium.sh` over HTTPS.

### Auth carriers (handshake)

The server reads the first of these that is present:

| Order | Carrier | Example | Use when |
|---|---|---|---|
| 1 | header `x-api-key` | `x-api-key: <KEY>` | Node (`ws` package), any client that can set headers. Preferred. |
| 2 | query param `api-key`, `api_key` or `apiKey` | `wss://services.carbium.sh/?api-key=<KEY>` | Node 22 global WebSocket, web3.js, Kit, provider-URL migrations |
| 3 | subprotocol `Sec-WebSocket-Protocol: api-key.<KEY>` | `new WebSocket("wss://services.carbium.sh", ["api-key." + key])` | Browsers. This keeps the key out of the URL. |
| 4 | first path segment | `wss://services.carbium.sh/<KEY>` | QuickNode-style URLs |

- The subprotocol carrier reads the **last** comma-separated token, with `api-key.` stripped. If you offer other subprotocols too, put `api-key.<KEY>` last. The server echoes a non-key token when you offered one; if the key token is the only one offered, it echoes that.
- `authorization: Bearer` and `x-token` are **not** read on the WebSocket plane. They work only on RPC and gRPC.

### Handshake refusals (HTTP, before the upgrade)

These come back as a plain HTTP response with the body `{"error":{"message":"<text>"}}`. There is no JSON-RPC code and no `error.data` here. Browsers and the Node global `WebSocket` cannot see the status: they report an `error` event and then a close with code `1006`. The `ws` package exposes the status through its `unexpected-response` event.

| HTTP | `error.message` | Retry-After | Meaning | What to do |
|---|---|---|---|---|
| 401 | `missing api key` | no | No carrier found | Attach the key. Do not retry unchanged. |
| 401 | `unknown api key` | `1` | No key matched (typo, the prefix instead of the full key, or a rotated key) | Fix the key. Stop. |
| 401 | `api key suspended: the plan term ended; renew on the dashboard` | `1` | Plan term ended | Renew. Stop. |
| 401 | `api key suspended; contact support` | `1` | Suspended for another reason | Contact support. Stop. |
| 401 | `api key revoked` | `1` | Key revoked | Mint a new key. Stop. |
| 401 | `api key disabled; contact support` | `1` | Key banned | Contact support. Stop. |
| 403 | `api key is not enabled for websocket` | no | The key does not carry the WebSocket plane | Enable WebSocket on the key in the dashboard. Stop. |
| 403 | `client ip address is not on this api key's allowlist; add it on the dashboard or with PATCH /v1/keys/{id}/allowlist` | no | The key has an IP allowlist and your address is not on it | Add the address on the dashboard or with `PATCH /v1/keys/{id}/allowlist`, or connect from a listed address. Stop. |
| 429 | `rate limit exceeded` | ≥ `1` s | More than 500 handshakes/s per account (burst 1024) | Wait Retry-After, then retry with jittered backoff. |
| 429 | `connection or subscription cap exceeded` | `1` | The account already holds its tier's connection count (table below) | Close an unused socket, then retry with backoff. After an unclean drop the server keeps the old socket's slot until it detects the dead peer (up to about 5.5 minutes, the no-pong limit), so keep retrying with backoff. |
| 429 | `overloaded or draining` | `1` | The server is restarting or shedding load | Retry with jittered backoff (1–5 s). |
| 429 | `free tier limit for your network reached: all free keys calling from one subnet share one request budget; retry after Retry-After, or upgrade for a limit of your own` | ≥ `1` s | Free plan only: all free keys calling from your network (subnet) share one budget, and each handshake and each subscribe spends from it | Wait Retry-After, then retry with jittered backoff, or upgrade for a limit of your own. |
| 429 | `free tier at capacity on this node: all free traffic shares one budget; retry after Retry-After, or upgrade` | ≥ `1` s | Free plan only: all free traffic on the server shares one budget | Wait Retry-After, then retry with jittered backoff, or upgrade. |

Any GET without `Upgrade: websocket` is routed to the RPC plane and is not a WebSocket answer. Measured live: `404`.

### Limits

| Limit | Value |
|---|---|
| Concurrent connections, and subscriptions across them, per account (all keys of the account combined) | 5 / 150 / 250 / 1,000 connections and 10 / 5,000 / 20,000 / 50,000 subscriptions (FREE / DEV / BUSINESS / PRO) |
| Subscriptions per connection, every plan | 1,000 |
| Subscribe rate per account (GCRA), every plan | 500/s, burst 1,024 |
| Handshake rate per account (GCRA, separate bucket), every plan | 500/s, burst 1,024 |

| Socket property | Value |
|---|---|
| Max inbound frame (your request) | 65,536 bytes. A larger frame drops the connection, and you see close `1006`. |
| Outbound queue per socket | 4,096 notifications. While a `blockSubscribe` is live on the socket: 8,192 frames and 8 MiB. Overflow closes `1013 slow_consumer`. |
| Unread control replies per socket | 64. Overflow closes `1013 slow_consumer`. |
| Server write stall | 10 s per write. Past that the TCP connection is dropped, and you see `1006`. |
| Upstream bind timeout per subscribe | 5 s. Past that: `-32005 "upstream subscription acceptance timed out"`, not charged. |
| Server ping interval | 30 s (first ping 30 s after open, empty payload) |
| Close if no pong | more than 300 s since your last pong, checked on each 30 s ping tick, so 300–330 s → `1001 no_pong` |
| Close if no inbound frame at all | 900 s → `1001 idle_timeout`. Pongs count as inbound frames, so a client that answers pings never hits this, and a silent client hits `no_pong` first. |

An unsubscribe frees the slot at once, and so does a signature subscription's final notification. Closing a socket frees all its subscriptions and its connection slot. Close cleanly (`ws.close(1000)`) so the slot frees immediately. This matters most on plans with few connections (see Limits).

### Billing (credits)

There are two charges, both taken from the account's credit balance:

1. **Per subscribe**, charged once when the subscribe is accepted. Unsubscribing does not refund it, with one exception: an `accountSubscribe` that never sent a notification is refunded in full when it closes (unsubscribe or socket close).
2. **Per byte streamed**: 20 credits per MiB (1,048,576 bytes) of text frames the server sends you, notifications and replies alike. Metered every second and recorded as `wsStreamBytes`.

| Subscribe | Credits |
|---|---|
| `slotSubscribe`, `rootSubscribe`, `signatureSubscribe` | 5 |
| `accountSubscribe`, `slotsUpdatesSubscribe`, `logsSubscribe` with `{"mentions":[…]}` | 25 |
| `programSubscribe`, `logsSubscribe` with `"all"` / `"allWithVotes"`, `blockSubscribe` | 200 |

Not charged:
- Subscribes refused for bad params (`-32602`).
- Subscribes refused for coverage (`-32010`), rate (`-32005`), caps (`-32005`) or credits still loading (`-32005` `CREDITS_PENDING`).
- Subscribes whose upstream bind timed out or failed.
- An `accountSubscribe` that closes without ever sending a notification (debited at subscribe, refunded at close).

Rate and cap checks still count against the subscribe rate before params are validated. If the byte meter cannot debit, the socket is closed `1008 credits_exhausted` when the account's credits are spent, and `1013 credits_pending` when the account has credits this node has not loaded yet: reconnect after about 1 s and re-subscribe.

A cold burst (the first subscribes after an idle period) is admitted against a 50,000-credit allowance until your balance is confirmed, about 1 s later. A burst worth more than 50,000 credits inside that second can be refused `-32005` `CREDITS_PENDING` on a funded account: resend after `error.data.retryAfterMs` (1000). The firehoses are heavy on bytes: a `blockSubscribe("all")` with `full` details can send MB-sized frames.

### Subscription methods served

Commitment values accepted: `processed`, `confirmed`, `finalized`. The legacy names `recent`, `single` and `max` are refused with `-32602`. When omitted, commitment defaults to `finalized`.

| Subscribe / Unsubscribe | Notification `method` | params | Options (in `params[1]`) | Credits |
|---|---|---|---|---|
| `accountSubscribe` / `accountUnsubscribe` | `accountNotification` | `[pubkey, opts?]` | `commitment`, `encoding` (`base64`, `base58`, `binary`, `jsonParsed`, `base64+zstd`), `dataSlice` `{offset,length}` (not with `jsonParsed`) | 25 |
| `programSubscribe` / `programUnsubscribe` | `programNotification` | `[programId, opts?]` | `commitment`, `encoding`, `dataSlice`, `filters` (at most 4) | 200 |
| `logsSubscribe` / `logsUnsubscribe` | `logsNotification` | `["all" \| "allWithVotes" \| {"mentions":[one address]}, opts?]` | `commitment` only | 25 mentions, 200 all |
| `signatureSubscribe` / `signatureUnsubscribe` | `signatureNotification` | `[signature, opts?]` | `commitment`; `enableReceivedNotification` only `false` | 5 |
| `slotSubscribe` / `slotUnsubscribe` | `slotNotification` | none, or `[]` | none | 5 |
| `rootSubscribe` / `rootUnsubscribe` | `rootNotification` | none, or `[]` | none | 5 |
| `slotsUpdatesSubscribe` / `slotsUpdatesUnsubscribe` | `slotsUpdatesNotification` | none, or `[]` | none | 25 |
| `blockSubscribe` / `blockUnsubscribe` | `blockNotification` | `["all" \| {"mentionsAccountOrProgram": pubkey}, opts?]` | `commitment` (`confirmed`/`finalized` only, default `finalized`), `encoding` (`json` default, `base64`, `base58`), `transactionDetails` (`full` default, `signatures`, `none`), `showRewards` (default `true`), `maxSupportedTransactionVersion` | 200 |
| `voteSubscribe` | refused: `-32601`, Alpenglow removes vote transactions from blocks | none | none | 0 |
| `getVersion` | (reply only) | none | none | 0 |

Option rules:
- Any option key not listed above is refused: `-32602 "requested subscription option is not supported"`. This covers `withContext`, `sortResults`, `enableReceivedNotification: true` and unknown keys. `blockSubscribe` answers with its own messages: `transactionDetails: "accounts"` gets `"blockSubscribe does not support transactionDetails=accounts"`, and an unknown key gets `"blockSubscribe option is not supported"`. `minContextSlot` is accepted and ignored.
- `slotSubscribe`, `rootSubscribe` and `slotsUpdatesSubscribe` take **no** params. Sending a config object, e.g. `[{"commitment":"finalized"}]`, is refused: `-32602 "subscribe takes at most 2 params"`.
- `programSubscribe` filters: each element is exactly one of `{"dataSize": <u64>}` or `{"memcmp": {"offset": <u64>, "bytes": "<string>", "encoding"?: "base58" | "base64" | "bytes"}}`. Order matters.
- Send `encoding` explicitly. `base64` is the most compact for account data.

Request and reply framing, measured live:

```json
> {"jsonrpc":"2.0","id":1,"method":"slotSubscribe"}
< {"jsonrpc":"2.0","result":719,"id":1}
< {"jsonrpc":"2.0","method":"slotNotification","params":{"subscription":719,"result":{"slot":454967396,"parent":454967395,"root":454967363}}}
> {"jsonrpc":"2.0","id":2,"method":"slotUnsubscribe","params":[719]}
< {"jsonrpc":"2.0","result":true,"id":2}
```

Notification `params.result` shapes, measured live (the JSON key order in `params` is `subscription`, then `result`):

| Notification | `params.result` |
|---|---|
| `slotNotification` | `{"slot":454967396,"parent":454967395,"root":454967363}`: one per slot, about every 220 ms |
| `rootNotification` | `454967364` (a bare number) |
| `slotsUpdatesNotification` | `{"type":"firstShredReceived","slot":454967397,"timestamp":1791572468894}`. `type` is one of agave's slot lifecycle types (`firstShredReceived`, `completed`, `createdBank`, `frozen`, `dead`, `optimisticConfirmation`, `root`), with extra fields per type. |
| `accountNotification` | `{"context":{"slot":454967398},"value":{"lamports":1169280,"data":["ZkAeGwAAAAA=","base64"],"owner":"Sysvar1111111111111111111111111111111111111","executable":false,"rentEpoch":18446744073709551615,"space":40}}`. With `jsonParsed`, `data` is `{"program":…,"parsed":{…},"space":40}`. |
| `programNotification` | `{"context":{"slot":N},"value":{"pubkey":"<base58>","account":{"lamports":2039280,"data":["<b64>","base64"],"owner":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA","executable":false,"rentEpoch":18446744073709551615,"space":165}}}` |
| `logsNotification` | `{"context":{"slot":N},"value":{"signature":"<base58>","err":null \| {…},"logs":["Program … invoke [1]", …]}}`. Failed transactions are included (`err` non-null). |
| `signatureNotification` | `{"context":{"slot":N},"value":{"err":null}}`, or `{"err":{…}}` for a failed transaction. This is the only notification: the subscription ends with it. |
| `blockNotification` | `{"context":{"slot":N},"value":{"slot":N,"err":null,"block":{"previousBlockhash","blockhash","parentSlot","transactions" or "signatures","rewards","blockTime","blockHeight"}}}` |

### Coverage: what each subscription actually sees

The socket is fed from the node's stream, not from a full validator pubsub. **Transactions are complete**, so `logsSubscribe`, `signatureSubscribe` and `blockSubscribe` see every transaction, including failed ones. Since Alpenglow, blocks carry no vote transactions, so no subscription sees votes. **Accounts are covered by owner:**

- `programSubscribe` is accepted only for these owners. Any other program answers `-32010 "filter not in v1 coverage; request provisioning"` (`data.reason` `PROGRAM_NOT_PROVISIONED`), and is not charged.

```
11111111111111111111111111111111               System (narrowed: only accounts closing to 0 lamports)
24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi
2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3c
675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8   Raydium AMM v4
6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P    Pump.fun
CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK   Raydium CLMM
CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C   Raydium CPMM
CarbeVCzypPEbtPJsdCboEkqxYxqT75nmhNUNBtyNPiz
CoREENxT6tW1HoK8ypY1SxRMZTcVPm7R94rH4PZNhX7d   Metaplex Core
Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB
LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo    Meteora DLMM (narrowed: 904-byte accounts only)
LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj    Raydium LaunchLab
PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY    Phoenix
TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA    SPL Token
TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb    Token-2022
box8cR7MyfymPsNS9QW4iEzzDZUNLer3LUDo87uGdVM
cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG    Meteora DAMM v2
dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN    Meteora DBC
dca1HQzdAnibwxoE7vMYdEmYhqggVUjADsB9YAXdDoi
iso5rbdHjynDynkosGgHxDGAD7Eks9BeHRrFLPYYjJo
isogrRJ6sEiktnfUY7QdZhDr5Sut3C8ER9HejjUqSZK
metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s    Metaplex Token Metadata
pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA    PumpSwap AMM
voTpe3tHQ7AjQHMapgSue2HJFAh2cGsdokqN3XqmVSj
whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc    Orca Whirlpool
ww3st35u7nDFdAypP8nXjyCQy9cUMp9i1cuAJq2JKgL
```

- `accountSubscribe` is **accepted for any address but notifies only for accounts the stream carries**: accounts owned by the programs above; accounts owned by these programs, which `programSubscribe` refuses: `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL`, `AddressLookupTab1e1111111111111111111111111`, `MNFSTqtC93rEfYHB6hF82sKdZpUDFWkViLByLd1k1Ms`, `SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy`, `SP12tWFxD9oJsVWNavTTBZvMbA6gkAmxtVgxdqvyvhY`, `SPMBzsVUuoHA4Jm6KunbsotaahvVikZs1JyTW6iJvbn`, `ALPHAQmeA7bjrVuccPsYPiCvsi428SNwte66Srvs4pHA`, `REALQqNEomY6cQGZJUGwywTBD2UmDT32rZcNnfxQ5N2`, `5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx`, `5quBtoiQqxF9Jv6KYKctB59NT3gtJD2Y65kdnB1Uev3h`, `9H6tua7jkLhdm3w8BvgpTn5LZNU7g4ZynDmCiNN3q6Rp`, `9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP`, `DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1`, `HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq`, `goonuddtQRrWqqn5nFyczVKaie28f3kDkHWkHtURSLE`, `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ`; the sysvars Clock, EpochSchedule, Rent, SlotHashes, SlotHistory and StakeHistory; System accounts closing to 0 lamports; and System, Stake and Vote accounts holding more than 1,000,000 SOL. For an account outside that set (a plain SOL wallet, an account owned by an uncovered program), the subscribe is acked, **no notification arrives**, and its 25 credits are refunded when the subscription closes. Measured: an account owned by `T1pyyaTNZsKv2WcRAB8oVnk93mLJw2XzjtVYqCsaHqt` changed lamports twice within 8 s over RPC and sent nothing in 15 s over WS.
- To watch a wallet's SOL balance, subscribe `logsSubscribe` with `{"mentions":["<wallet>"]}` (25 credits; it fires for every transaction that touches the wallet), then read `getBalance` over RPC. Token accounts (SPL Token, Token-2022) are covered by `accountSubscribe` directly.

### blockSubscribe

Assembled by the server from the transaction stream; not a validator passthrough. Live today. `voteSubscribe` is refused (`-32601`): Alpenglow (mainnet, from 2026-10-21) takes vote transactions out of blocks, so it would never fire.

- `blockSubscribe` filter: `"all"`, or `{"mentionsAccountOrProgram":"<pubkey>"}`. With a mentions filter, a notification is sent only for blocks that contain a matching transaction, and it carries only the matching transactions.
- **Always send `"maxSupportedTransactionVersion": 1`.** Mainnet carries version-1 transactions. With it set, each `full` transaction carries `"version"` (`"legacy"`, `0` or `1`). With `0`, a block holding a v1 transaction arrives as `{"slot":N,"block":null,"err":{"UnsupportedTransactionVersion":1}}`.
- Not served: the `processed` commitment, `jsonParsed` and `base64+zstd` encodings, and `transactionDetails: "accounts"`. Each refusal is listed below.
- Use `transactionDetails: "signatures"` or `"none"` plus `showRewards: false` unless you need full transactions. Frames are much smaller, so they cost fewer byte credits and carry less risk of `1013`.
- If the stream feeding the socket loses continuity, every socket with a live subscription of any kind (not only `blockSubscribe`) is closed `1012 stream_gap_reseed_required`.

```json
{"jsonrpc":"2.0","id":1,"method":"blockSubscribe","params":[{"mentionsAccountOrProgram":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},{"commitment":"confirmed","transactionDetails":"signatures","showRewards":false,"maxSupportedTransactionVersion":1}]}
```

### signatureSubscribe semantics

- You get one notification at the requested commitment, `{"context":{"slot":N},"value":{"err":null}}`. Then the server ends the subscription and frees its slot. The 5 credits stay charged.
- `signatureUnsubscribe` on an ended or unknown id answers `{"error":{"code":-32602,"message":"Invalid subscription id."}}`. Treat this as success. Before the notification arrives, `signatureUnsubscribe` answers `true`.
- `enableReceivedNotification: true` is refused (`-32602 "requested subscription option is not supported"`). There is no early `receivedSignature` frame.
- Subscribe **before** you send the transaction. If you subscribe after it may already have landed, or after a reconnect, also call `getSignatureStatuses` over RPC: a notification is not guaranteed for a signature that confirmed before the subscription existed.
- Bound the wait. If no notification arrives before the transaction's `lastValidBlockHeight` passes, check `getSignatureStatuses`. If it is not found, the transaction expired.

### Errors inside an open socket (JSON-RPC replies to your request)

Shape: `{"jsonrpc":"2.0","error":{"code":C,"message":"…","data":{…}?},"id":<your id>}`. Refusals that name a `data.reason` in the table below carry `data` = `{"reason":"…","retryable":bool,"retryAfterMs"?:n}`. The other errors carry no `data`.

| code | message (exact) | `data.reason` | When | What to do |
|---|---|---|---|---|
| -32005 | `rate limit exceeded` | `RATE_LIMITED` (retryable, `retryAfterMs`) | More than 500 subscribes/s per account past the 1,024 burst | Wait `retryAfterMs`, resend. Pace subscribes. |
| -32005 | `connection or subscription cap exceeded` | `SLOT_CAP_EXCEEDED` (retryable, no `retryAfterMs`) | The socket's cap (1,000) or the account's subscription cap (see Limits) is reached | Do not loop. Unsubscribe unused ids. At the socket cap, open another socket. At the account cap, upgrade. |
| -32005 | `overloaded or draining` | `LOAD_SHED` (retryable, `retryAfterMs` 1000) | Server shedding | Wait `retryAfterMs`, resend. |
| -32005 | `free tier limit for your network reached: all free keys calling from one subnet share one request budget; retry after Retry-After, or upgrade for a limit of your own` | `FREE_SUBNET_LIMITED` (retryable, `retryAfterMs`) | Free plan only: your network's shared free budget is spent | Wait `retryAfterMs`, resend, or upgrade. |
| -32005 | `free tier at capacity on this node: all free traffic shares one budget; retry after Retry-After, or upgrade` | `FREE_TIER_BUSY` (retryable, `retryAfterMs`) | Free plan only: the server's shared free budget is spent | Wait `retryAfterMs`, resend, or upgrade. |
| -32005 | `credits for this account are still loading on this node; retry after Retry-After` | `CREDITS_PENDING` (retryable, `retryAfterMs` 1000) | The server has not loaded the account's credits yet (a new account's first subscribes, a burst that spent this server's share, or just after a server restart). The socket stays open. | Wait `retryAfterMs`, resend. |
| -32001 | `client ip address is not on this api key's allowlist; add it on the dashboard or with PATCH /v1/keys/{id}/allowlist` | `IP_NOT_ALLOWED` (not retryable) | The key's allowlist changed after this socket opened and no longer holds the address it connected from | Add the address, or reconnect from a listed address. Do not resend unchanged. |
| -32005 | `upstream subscription acceptance timed out` | none | The upstream did not ack within 5 s (not charged) | Resend after 1–5 s with backoff. |
| -32005 | `upstream subscription unavailable, retry` | none | Upstream feed reconnecting (not charged) | Resend after 1–5 s with backoff. |
| -32005 | `synthesised subscription upstream is unavailable, retry` | none | Block feed not ready (not charged) | Resend after 1–5 s with backoff. |
| -32002 | `credits exhausted` | `CREDITS_EXHAUSTED` (not retryable, `retryAfterMs` 1000) | The account's remaining credits cannot cover the subscribe | Buy a plan or upgrade. |
| -32010 | `filter not in v1 coverage; request provisioning` | `PROGRAM_NOT_PROVISIONED` | `programSubscribe` owner outside coverage | Ask support to provision the program. Meanwhile use `logsSubscribe` mentions or the gRPC stream. |
| -32601 | `method not found` | none | Any method other than those listed (e.g. `getSlot`, `transactionSubscribe`) | Send RPC methods over HTTPS. Use the methods above for push. |
| -32601 | `blockSubscribe not enabled` | `METHOD_NOT_SERVED` | `blockSubscribe` is turned off on this server (it is on today) | Use the gRPC stream or RPC `getBlock`. |
| -32601 | `voteSubscribe not served: Alpenglow removes vote transactions from blocks` | `METHOD_NOT_SERVED` | `voteSubscribe` | Votes are not transactions under Alpenglow; read slot status for finality. |
| -32600 | `invalid request: no method` | none | Frame has no `method`, or is not JSON (then `id` is `null`) | Fix the frame. |
| -32600 | `invalid request` | none | `method` is not a string | Fix the frame. |
| -32602 | `params must be a JSON array` | none | `params` not an array | Fix. |
| -32602 | `subscribe requires a params selector` | none | Missing pubkey, signature or filter | Fix. |
| -32602 | `subscribe takes at most 2 params` | none | More than 2 params, or any params on slot/root/slotsUpdates | Fix. |
| -32602 | `subscription config must use supported field types` | none | `params[1]` not an object, or a wrong type in `dataSlice` / `filters` | Fix. |
| -32602 | `invalid base58 address or signature` | none | Selector is not a 32-byte (64-byte for signatures) base58 string | Fix. |
| -32602 | `logs filter must be "all", "allWithVotes", or {"mentions":[one address]}` | none | Bad logs filter, or more than one mention | Use exactly one address per subscription. |
| -32602 | `encoding must be binary, base58, base64, jsonParsed or base64+zstd` | none | Bad account/program encoding | Fix. |
| -32602 | `commitment must be processed, confirmed, or finalized` | none | Bad commitment | Fix. |
| -32602 | `at most 4 filters` | none | More than 4 `programSubscribe` filters | Fix. |
| -32602 | `requested subscription option is not supported` | none | Unknown option, `withContext`, `sortResults`, `enableReceivedNotification:true`, or `dataSlice` with `jsonParsed` | Remove the option. |
| -32602 | `blockSubscribe params must be a JSON array` / `blockSubscribe takes at most 2 params` / `blockSubscribe requires a filter ("all" or {mentionsAccountOrProgram})` / `blockSubscribe config must be an object` | none | Bad block params | Fix. |
| -32602 | `blockSubscribe commitment must be confirmed or finalized` / `blockSubscribe does not support the processed commitment` | none | Bad block commitment | Use `confirmed` or `finalized`. |
| -32602 | `blockSubscribe does not support jsonParsed (use json, base64, or base58)` / `blockSubscribe does not support the base64+zstd encoding (use base64, base58, or json)` / `blockSubscribe encoding must be json, base64, or base58` | none | Bad block encoding | Fix. |
| -32602 | `blockSubscribe does not support transactionDetails=accounts` / `blockSubscribe transactionDetails must be full, signatures, or none` | none | Bad details | Fix. |
| -32602 | `blockSubscribe showRewards must be a boolean` / `blockSubscribe maxSupportedTransactionVersion must be a non-negative integer` / `blockSubscribe option is not supported` | none | Bad block option | Fix. |
| -32602 | `Invalid subscription id.` | none | `signatureUnsubscribe` for an ended or unknown id | Ignore: it is already gone. |

`xUnsubscribe` for an id you do not hold (any method except signature) answers `{"result":false}`. `getVersion` answers `{"solana-core":"<version>","feature-set":0,"carbium":"csocket"}`.

### Server close codes

Every close the server starts carries a code and a reason string. Close codes are read in `onclose` / `on("close")`.

| Code | Reason | Cause | What the client must do |
|---|---|---|---|
| 1013 | `slow_consumer` | Your outbound queue overflowed: more than 4,096 queued notifications (more than 8,192 frames or 8 MiB while a `blockSubscribe` is live), or more than 64 unread replies | Reconnect with backoff, resubscribe, re-read state. Then fix the cause: do less work per message, split subscriptions over more sockets, narrow filters, use `base64` / `signatures` instead of `jsonParsed` / `full`. |
| 1013 | `delivery_overload_retry` | Server ordered-delivery capacity was exhausted. The socket is closed rather than delivering out of order. | Reconnect with jittered backoff (≥ 1 s), resubscribe, re-read state. |
| 1013 | `credits_pending` | The byte meter could not debit, but the account has credits: this node has not loaded them yet (its share here ran out before the refill, or the node re-registered). The bytes already sent are billed. | Reconnect after about 1 s and re-subscribe; do not buy anything. If the subscribes answer `-32005` `CREDITS_PENDING`, wait `retryAfterMs` and resend. |
| 1001 | `no_pong` | No pong for more than 300 s | Reconnect, resubscribe. Make sure pings are answered and the event loop is not blocked. |
| 1001 | `idle_timeout` | No inbound frame of any kind for 900 s | Reconnect, resubscribe. |
| 1001 | `server_shutdown` | Planned shutdown. Reserved: a restart today closes with `1012 draining`. | Reconnect with jitter, resubscribe, re-read state. |
| 1012 | `draining` | Server restart or redeploy | Reconnect after 250–1000 ms jitter, resubscribe, re-read state. |
| 1012 | `stream_gap_reseed_required` | The upstream feed lost continuity. Your subscriptions are gone and anything in the gap is lost. | Reconnect, resubscribe, and **re-read all derived state over RPC** before trusting new notifications. |
| 1008 | `credits_exhausted` | The per-byte meter could not debit the account | Stop streaming. Reconnect once after about 5 s: the handshake succeeds, and if the balance really is empty the subscribes answer `-32002`. Then stop, and buy a plan or upgrade. If they answer `-32005` `CREDITS_PENDING`, wait `retryAfterMs` and resend. |
| 1008 | `key_revoked` | The socket's key was revoked, rotated or deleted, or its account was deleted. Checked every second; the socket closes within about 2 s. | Stop. Reconnect only with a live key: the old one is refused at the handshake (401 `api key revoked`, or `unknown api key` after a rotate). |
| 1008 | `key_suspended` | The socket's key or its account was suspended | Stop. A reconnect is refused with the reason (see Key states): renew, or contact support. |
| 1008 | `key_banned` | The socket's key or its account was disabled | Stop and contact support. |
| 1000 | (empty) | Echo of your own close | Nothing. |
| 1006 | (no close frame) | Network drop, a frame you sent over 65,536 bytes, a server write stalled over 10 s, or a refused handshake seen from a browser or the Node global WebSocket | Reconnect with exponential backoff (0.5 s doubling to 30 s, with jitter). |

### Quick start

Node 22+ global `WebSocket` (no headers possible, so use the query carrier):

```js
const ws = new WebSocket("wss://services.carbium.sh/?api-key=" + process.env.CARBIUM_KEY);
ws.onopen = () => ws.send(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "slotSubscribe" }));
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id === 1) return m.error ? console.error(m.error) : console.log("sub id", m.result);
  if (m.method === "slotNotification") console.log(m.params.result.slot);
};
ws.onclose = (e) => console.log("closed", e.code, e.reason); // see the close-code table
```

Browser (headers cannot be set; the key rides the subprotocol, not the URL):

```js
const ws = new WebSocket("wss://services.carbium.sh", ["api-key." + key]);
```

`@solana/web3.js` v1: set `wsEndpoint` explicitly.

```js
import { Connection, PublicKey } from "@solana/web3.js";
const KEY = process.env.CARBIUM_KEY;
const conn = new Connection("https://services.carbium.sh/?api-key=" + KEY, {
  wsEndpoint: "wss://services.carbium.sh/?api-key=" + KEY,
  commitment: "confirmed",
});
const id = conn.onAccountChange(new PublicKey("SysvarC1ock11111111111111111111111111111111"), (acc, ctx) => console.log(ctx.slot, acc.lamports), { commitment: "confirmed", encoding: "base64" });
// later: await conn.removeAccountChangeListener(id);
```

`@solana/kit`:

```js
import { createSolanaRpcSubscriptions } from "@solana/kit";
const subs = createSolanaRpcSubscriptions("wss://services.carbium.sh/?api-key=" + process.env.CARBIUM_KEY);
const abort = new AbortController();
const slots = await subs.slotNotifications().subscribe({ abortSignal: abort.signal });
for await (const n of slots) console.log(n.slot); // the loop throws when the socket drops: re-create the subscription
```

### Robust client (Node, `npm i ws`)

This client reconnects with backoff and resubscribes on reconnect. It maps local handles to server ids, handles every close code and refusal above, watches the server's 30 s pings, paces subscribes, and ends signature subscriptions on their final notification. It was run against the live service.

```js
// carbium-ws.mjs: a reconnecting subscription client for wss://services.carbium.sh
// Node 18+, `npm i ws`.
import WebSocket from "ws";

const URL = "wss://services.carbium.sh";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const RETRY_REASONS = new Set(["RATE_LIMITED", "LOAD_SHED", "FREE_SUBNET_LIMITED", "FREE_TIER_BUSY", "CREDITS_PENDING"]); // -32005 with these reasons: wait data.retryAfterMs, resend

export class CarbiumWS {
  constructor(key, { onReseed = () => {}, onFatal = (e) => console.error("fatal:", e.message) } = {}) {
    this.key = key;
    this.onReseed = onReseed; // after a reconnect: notifications sent while you were away are gone; re-read state over RPC
    this.onFatal = onFatal;   // bad key, key not enabled for websocket, credits exhausted
    this.rpcId = 0;
    this.pending = new Map();    // json-rpc id -> { resolve, reject }
    this.subs = new Map();       // local handle -> { method, params, cb, serverId }
    this.byServerId = new Map(); // server subscription id -> local handle
    this.nextHandle = 0;
    this.attempt = 0;
    this.stopped = false;
    this.reconnected = false;
    this.#open();
  }

  subscribe(method, params, cb) {
    const h = ++this.nextHandle;
    this.subs.set(h, { method, params, cb, serverId: undefined });
    if (this.ws.readyState === WebSocket.OPEN) this.#bind(h).catch((e) => this.subs.delete(h) && console.error(method, e.message));
    return h; // stable across reconnects; the server id is not
  }

  async unsubscribe(h) {
    const s = this.subs.get(h);
    this.subs.delete(h);
    if (!s || s.serverId === undefined) return;
    this.byServerId.delete(s.serverId);
    try {
      await this.#call(s.method.replace("Subscribe", "Unsubscribe"), [s.serverId]);
    } catch (e) {
      if (e.code !== -32602) throw e; // -32602 "Invalid subscription id.": already ended (signature) or never held
    }
  }

  close() {
    this.stopped = true;
    if (this.ws.readyState === WebSocket.OPEN) this.ws.close(1000); // a clean close frees the connection slot at once
    else this.ws.terminate();
  }

  #open() {
    const ws = (this.ws = new WebSocket(URL, { headers: { "x-api-key": this.key } }));
    let watchdog;
    const alive = () => {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => ws.terminate(), 75_000); // the server pings every 30 s
    };

    // Refused before the upgrade (401/403/429). ws emits no 'close' after this event, so handle it here.
    ws.on("unexpected-response", (req, res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        req.destroy();
        const retryAfterMs = 1000 * Number(res.headers["retry-after"] ?? 1);
        if (res.statusCode === 401 || res.statusCode === 403) return this.#fatal(new Error(`handshake ${res.statusCode} ${body}`));
        this.reconnected = true;
        this.#retry(Math.max(retryAfterMs, this.#backoff())); // 429: rate, connection cap, draining
      });
    });
    ws.on("error", () => {}); // 'close' always follows
    ws.on("ping", alive);       // ws answers the pong itself
    ws.on("open", async () => {
      this.attempt = 0;
      alive();
      const handles = [...this.subs.keys()];
      for (let i = 0; i < handles.length; i += 32) {
        // at most 32 in flight; the account limit is 500 subscribes/s, burst 1024
        await Promise.all(handles.slice(i, i + 32).map((h) => this.#bind(h).catch((e) => console.error(e.message))));
      }
      if (this.reconnected) this.onReseed();
    });
    ws.on("message", (data) => {
      const m = JSON.parse(data);
      if (m.id != null && this.pending.has(m.id)) {
        const p = this.pending.get(m.id);
        this.pending.delete(m.id);
        return m.error ? p.reject(Object.assign(new Error(m.error.message), m.error)) : p.resolve(m.result);
      }
      if (!m.method || !m.params) return; // e.g. {"id":null,"error":...} for an unparsable frame
      const h = this.byServerId.get(m.params.subscription);
      const s = h && this.subs.get(h);
      if (!s) return;
      s.cb(m.params.result, m.method);
      if (m.method === "signatureNotification" && typeof m.params.result?.value === "object") {
        this.byServerId.delete(s.serverId); // final: the server ended it, do not unsubscribe
        this.subs.delete(h);
      }
    });
    ws.on("close", (code, reasonBuf) => {
      clearTimeout(watchdog);
      const reason = reasonBuf.toString();
      for (const p of this.pending.values()) p.reject(new Error(`socket closed ${code} ${reason}`));
      this.pending.clear();
      this.byServerId.clear();
      for (const s of this.subs.values()) s.serverId = undefined;
      if (this.stopped) return;
      // 1008 key_revoked / key_suspended / key_banned: the key is dead, so stop.
      if (code === 1008 && reason.startsWith("key_")) return this.#fatal(new Error(`socket closed ${code} ${reason}`));
      this.reconnected = true;
      // 1001 no_pong / idle_timeout, 1012 draining / stream_gap_reseed_required: reconnect soon.
      // 1013 slow_consumer / delivery_overload_retry, 1006 network: back off; 1013 credits_pending: about 1 s. 1008 credits_exhausted: one slow retry;
      // its subscribes answer -32002 if the balance is really empty, which stops the client.
      const delay = code === 1001 || code === 1012 ? 250 + Math.random() * 750 : code === 1008 ? 5000 : reason === "credits_pending" ? 1000 + Math.random() * 500 : this.#backoff();
      this.#retry(delay);
    });
  }

  #backoff() {
    const base = Math.min(30_000, 500 * 2 ** this.attempt++);
    return base / 2 + Math.random() * (base / 2);
  }

  #retry(ms) {
    setTimeout(() => !this.stopped && this.#open(), ms);
  }

  #fatal(e) {
    this.stopped = true;
    if (this.ws.readyState === WebSocket.OPEN) this.ws.close(1000);
    this.onFatal(e);
  }

  #call(method, params) {
    return new Promise((resolve, reject) => {
      if (this.ws.readyState !== WebSocket.OPEN) return reject(new Error("not connected"));
      const id = ++this.rpcId;
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify(params === undefined ? { jsonrpc: "2.0", id, method } : { jsonrpc: "2.0", id, method, params }));
    });
  }

  async #bind(h) {
    for (;;) {
      const s = this.subs.get(h);
      if (!s || s.serverId !== undefined) return;
      try {
        const id = await this.#call(s.method, s.params);
        if (!this.subs.has(h)) return void this.#call(s.method.replace("Subscribe", "Unsubscribe"), [id]).catch(() => {});
        s.serverId = id;
        this.byServerId.set(id, h);
        return;
      } catch (e) {
        if (e.code === undefined) return; // socket closed: the next 'open' rebinds
        const reason = e.data?.reason;
        if (e.code === -32005 && (RETRY_REASONS.has(reason) || reason === undefined)) {
          await sleep(e.data?.retryAfterMs ?? 1000); // reason undefined: upstream bind timed out or unavailable
          continue;
        }
        if (e.code === -32002) this.#fatal(e); // CREDITS_EXHAUSTED: buy a plan or upgrade
        throw e; // SLOT_CAP_EXCEEDED, -32602 bad params, -32601 not served, -32010 not covered: fix, do not resend
      }
    }
  }
}

// Usage
const c = new CarbiumWS(process.env.CARBIUM_KEY, {
  onReseed: () => console.log("reconnected: re-read state with getAccountInfo / getSignatureStatuses"),
});
c.subscribe("slotSubscribe", undefined, (r) => console.log("slot", r.slot));
c.subscribe("accountSubscribe", ["SysvarC1ock11111111111111111111111111111111", { encoding: "jsonParsed", commitment: "confirmed" }],
  (r) => console.log("clock", r.context.slot, r.value.data.parsed.info.unixTimestamp));
process.on("SIGINT", () => c.close());
```

Confirming a sent transaction with the client above (subscribe first, then send):

```js
function confirm(c, signature, commitment = "confirmed", ms = 90_000) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => { c.unsubscribe(h).catch(() => {}); reject(new Error("no notification: check getSignatureStatuses")); }, ms);
    const h = c.subscribe("signatureSubscribe", [signature, { commitment }], (r) => {
      clearTimeout(t);
      r.value.err ? reject(Object.assign(new Error("transaction failed"), { err: r.value.err })) : resolve(r.context.slot);
    });
  });
}
```

### Common mistakes

- Expecting `accountSubscribe` on a plain wallet to fire. It is acked but stays silent (its credits are refunded when it closes). Use `logsSubscribe` mentions and RPC `getBalance`.
- Sending `{"commitment":…}` to `slotSubscribe`, `rootSubscribe` or `slotsUpdatesSubscribe`. They take no params.
- Two addresses in one `logsSubscribe` mentions list. Use one subscription per address.
- `blockSubscribe` without `maxSupportedTransactionVersion: 1`, or with `processed` or `jsonParsed`.
- Opening a socket per subscription. That hits your plan's connection cap (see Limits).
- Reconnecting in a tight loop on `1008`, or on a 401/403 handshake. Those need a human: buy a plan, upgrade, fix the key, or enable the plane.
- Treating notifications after a `1012 stream_gap_reseed_required` as a continuation. Re-read state first.
- Calling RPC methods (`getSlot`, `getAccountInfo`) over the socket. They answer `-32601 "method not found"`, so use HTTPS.

