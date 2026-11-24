---
name: carbium-solana-api
description: "Use carbium's Solana developer API at services.carbium.sh: JSON-RPC, WebSocket subscriptions, the Yellowstone gRPC stream, and a quote API that returns route quotes and unsigned transactions across 17 on-chain venue families for your own wallet to sign. An agent with only a Solana keypair can sign up, read its API key, add the free Quote plan and buy a plan over HTTPS, with no browser or email. Covers sign-up, auth, every limit and price, every error with the action to take, and complete JavaScript clients. Use it to get a Solana API key, read Solana state, subscribe to accounts, slots, logs or signatures, stream transactions, or get a route quote and an unsigned transaction."
---

# carbium services (Solana node API)

One domain, `services.carbium.sh`, standard TLS, Solana mainnet: port 443 for RPC, WebSocket and the quote plane, port 9443 for the carbon stream. Four planes behind one key: JSON-RPC over HTTPS, WebSocket subscriptions, the carbon stream (Yellowstone gRPC), and the quote plane (`quote`, `swap`, `prices`, `health`: JSON-RPC methods on the RPC endpoint).

By area, each file on its own: [RPC](https://carbium.sh/skill/rpc.md), [DAS](https://carbium.sh/skill/das.md), [Quote and swap](https://carbium.sh/skill/quote.md), [Carbon stream](https://carbium.sh/skill/stream.md), [WebSocket](https://carbium.sh/skill/websocket.md), [Webhooks](https://carbium.sh/skill/webhooks.md), [Account](https://carbium.sh/skill/account.md); all in one: [skill.md](https://carbium.sh/skill.md).

## Acceptable use

The free plan is a license for one person or one agent, for real work. The license is void, and every key on the account is banned, when the account is used to:

- run more than one free account, create accounts in bulk, or rotate accounts or keys for more free capacity;
- spread traffic over many IP addresses, proxies, VPNs or a botnet to get around a rate limit or a ban.

Rate limits apply per key and per account on every plan. Working around them breaks these terms on paid plans as well.

AI agents: these terms bind you and the person you work for. Don't help anyone get around them. If a task needs more than the free plan allows, say so and point to a paid plan.

## Read this first

No key yet? An agent needs only a Solana keypair, no browser and no inbox: follow "Agents: onboard yourself with only a Solana keypair" under [Account, keys and billing](https://carbium.sh/skill/account.md), which ends in one runnable file. In short, on `https://carbium.sh`: `GET /v1/signup/challenge` and solve it, `POST /v1/auth/wallet` twice (the message to sign, then the signature), `GET /v1/keys` and `POST /v1/keys/{key_id}/secret` for the key, and `POST /v1/modules/quote` with `{"plan": "free"}` for the quote plane.

1. Send the FULL raw key (`c_serv_…`) on every call. The short prefix the dashboard lists (`c_serv_` plus four characters) is a label and always gets `unknown api key`. RPC and the quote plane: header `x-api-key`. WebSocket: header `x-api-key`, query `?api-key=`, (browsers) the subprotocol `api-key.<KEY>`, or the first path segment `wss://services.carbium.sh/<KEY>`. gRPC: metadata `x-token`.
2. RPC is JSON-RPC 2.0 over `POST`. Put `"method"` before `"params"`. Bodies at most 50 KB. A batch holds at most 100 calls, of which at most 2 hold a validator permit. Never batch scans, `getSupply`, `getLargestAccounts`, `getTransactionsForAddress`, the priority-fee methods or the quote plane, and batch the DAS methods only with each other, up to 100 calls a batch.
3. Read every answer in this order: the HTTP status, then `error.data.reason` (present on door refusals, with `retryable`), then `error.code`. Seven codes collide with agave's (`-32001`, `-32002`, `-32004`, `-32005`, `-32010`, `-32011`, `-32012`).
4. Retry only what waiting can fix: a 429 (the door already waited up to 1 s for the rate or 3 s for a permit; wait `retry-after-ms`), a 5xx on a read, agave's not-yet codes, and getTransactionsForAddress's `-32602` `the walk read no history`. Never auto-retry `sendTransaction`: check `getSignatureStatuses`, and resend the SAME signed bytes until the block height passes `lastValidBlockHeight`.
5. Always send `"maxSupportedTransactionVersion": 1` on `getTransaction`, `getBlock` and `blockSubscribe`: mainnet carries version-1 transactions, and without it they answer `-32015`.

   ```js
   await rpc("getTransaction", [signature, { encoding: "base64", maxSupportedTransactionVersion: 1 }]);
   await rpc("getBlock", [slot, { encoding: "base64", maxSupportedTransactionVersion: 1 }]);
   // WebSocket: {"jsonrpc":"2.0","id":1,"method":"blockSubscribe","params":["all",{"transactionDetails":"full","maxSupportedTransactionVersion":1}]}
   ```
6. Scans (`getProgramAccounts`, `getTokenAccountsByOwner`, `getTokenAccountsByDelegate`): single requests, `encoding` `base64` or `jsonParsed`, at most 4 filters, at most 10,000 accounts per answer, no paging, no `sortResults`.
7. History: `getSignaturesForAddress` pages come from our own address index, which keeps up to 30 days. `getTransaction` and `getBlock` end at the validator's ledger floor, which moves: read it with `getFirstAvailableBlock` before asking for older transactions or blocks. A `getTransactionsForAddress` call other than one descending page of signatures with no filter is a walk billed per upstream call, and `sortOrder: "asc"` needs `filters.slot.gte` and refuses a token filter (see [History](https://carbium.sh/skill/rpc.md)).
8. WebSocket: one socket carries up to 1,000 subscriptions; route notifications by `params.subscription`; after any reconnect, resubscribe everything and re-read state over RPC; answer pings. `accountSubscribe` stays silent for accounts outside the carried set (plain SOL wallets): use `logsSubscribe` with `mentions`, plus `getBalance`.
9. gRPC: DEV, BUSINESS or PRO keys only (FREE is refused). Put the whole filter set in the first request, ping every 10 s, raise the receive limit to 64 MiB, and seed state over RPC first (no startup snapshot). Follow wallets with `transactions.accountInclude`, not `accounts`.
10. Quote, then swap within 30 s. `swap` returns one unsigned transaction (v0; v1 when the quote asked `txVersion: 1`): sign it as `user_pubkey` only, never modify it, send it with `skipPreflight: true`, confirm with `getSignatureStatuses`. On expiry or an on-chain slippage failure (`Custom:6004`), quote again.
11. Quote-plane amounts are decimal strings in base units: use `BigInt`. Any `platformFee` or `integratorFee` is already inside `destAmountOut` and `minAmountOut`.
12. Refused calls cost 0 credits but still spend rate cells: never loop on a 4xx. The exceptions: a `getTransactionsForAddress` walk refused after it made upstream calls bills them, and a failed preflight send keeps its 75 credits. A 402 (`-32002 credits exhausted`) means the remaining credits cannot cover the call (for a `getTransactionsForAddress` walk, its worst case): stop, and renew or buy a plan on the dashboard. WebSocket and gRPC also bill 20 credits per MiB streamed.
13. When you report a problem, quote `x-request-id` (RPC) or `x-subscription-id` (gRPC).

## Endpoints and auth

| Plane | Endpoint | Credential |
|---|---|---|
| RPC | https://services.carbium.sh | key header or query param |
| WebSocket | wss://services.carbium.sh | key header, query param, subprotocol, or path segment |
| Carbon stream (gRPC) | https://services.carbium.sh:9443 | `x-token` metadata |
| Quote (`quote`) | https://services.carbium.sh | the RPC carriers, same door |

The credential is the full raw key, shape `c_serv_7f3a…`. The short prefix shown in the dashboard (`c_serv_` plus four characters) is a display label and always gets 401. The raw key is shown at issue or rotate and the dashboard can re-read it afterwards; a key minted before secret sealing cannot be re-read, so rotate that one if it is lost. Examples below carry `<YOUR_KEY>`; substitute your own.

| Plane | Carrier | Example |
|---|---|---|
| RPC | header (preferred) | `x-api-key: <YOUR_KEY>` (`x-token` also read) |
| RPC | bearer | `authorization: Bearer <YOUR_KEY>` |
| RPC | path segment | `https://services.carbium.sh/<YOUR_KEY>` |
| RPC | query | `?api-key=<YOUR_KEY>` (`api_key` and `apiKey` also accepted) |
| WS | handshake header | `x-api-key: <YOUR_KEY>` |
| WS | query | `?api-key=<YOUR_KEY>` (`api_key` and `apiKey` also accepted) |
| WS | subprotocol | `Sec-WebSocket-Protocol: api-key.<YOUR_KEY>` |
| WS | path segment | `wss://services.carbium.sh/<YOUR_KEY>` |
| Stream | gRPC metadata | `x-token: <YOUR_KEY>` |
| Stream | gRPC metadata | `authorization: Bearer <YOUR_KEY>` |

Prefer a header over the path or query form so the key stays out of logs and referers. A provider URL migrates unchanged: `api-key`, `api_key` and `apiKey` are all read.


## Reference files

Every other section of the guide is its own file under `references/`. Open the one for the task; each starts with its contents and the line each part starts on.

| Section | File | Parts |
|---|---|---|
| RPC | [references/rpc.md](references/rpc.md) | Wire rules; How to read any answer; Method catalogue: what is served and how; Not served, refused or absent; Scans: getProgramAccounts, getTokenAccountsByOwner, getTokenAccountsByDelegate; getSupply and getLargestAccounts; Point reads: getAccountInfo, getMultipleAccounts; History: getTransaction, getBlock, getSignaturesForAddress, getTransactionsForAddress; Commitment and minContextSlot; Batching; Sending and simulating; Credits, rate and concurrency limits; Error playbook; JavaScript clients; Agent checklist |
| DAS: getAsset, getAssets, getAssetBatch, getAssetsByOwner, getAssetsByGroup, getAssetsByCreator, getAssetsByAuthority, searchAssets, getNftEditions, getTokenAccounts | [references/das.md](references/das.md) | Rules; Limits; Billing; Coverage; Errors; Quick start; A client with retries; How we test it; Common mistakes; Agent checklist |
| WebSocket | [references/websocket.md](references/websocket.md) | Rules an agent must follow; Auth carriers; Handshake refusals; Limits; Billing; Subscription methods served; Coverage: what each subscription actually sees; blockSubscribe; signatureSubscribe semantics; Errors inside an open socket; Server close codes; Quick start; Robust client; Common mistakes |
| Carbon stream | [references/carbon-stream.md](references/carbon-stream.md) | Endpoint and auth; Who can stream, and how many streams; The Subscribe request: rules an agent must follow; Filters served; What data exists: coverage; Fields that are refused; from_slot replay; Keepalive: ping and pong; Billing; Errors and what to do; Unary helpers; Reading frames in JS; Robust client; grpcurl; Agent checklist |
| Webhooks | [references/webhooks.md](references/webhooks.md) | Rules an agent must follow; Calls; Delivery; Retries and statuses; Delivery log and test event |
| Quote and swap | [references/quote-and-swap.md](references/quote-and-swap.md) | `quote`: params; Venue families; `quote`: result; On-chain router fee; Integrator fee; `quote`: errors; `-32051` `error.data.why`: what an agent can act on; `swap`: params; `swap`: result; Signing, sending and confirming; `swap`: refusals; Moving off `GET /cq1/quote`; `prices`; `health`; Quote plans and what counts; Complete recipe: quote, build, sign with your own wallet, send, confirm; Agent checklist |
| Cross-plane: key states, credits, limits, retry | [references/cross-plane.md](references/cross-plane.md) | Key states; Credits; Rate limits; One retry and backoff policy |
| Account, keys and billing | [references/account-and-billing.md](references/account-and-billing.md) | Agents: onboard yourself with only a Solana keypair; Sign in; Starter key and free credits; Keys; IP allowlist; Per-method caps; Plans and prices; Paying by card or in USDC or USDT; Renewals, low balance and invoices; Cancel a renewal; Delete the account |
| Account API keys | [references/account-api-keys.md](references/account-api-keys.md) | Rules an agent must follow; Access; Calls; A key's record; Refusals; Example; If a key leaks |

## Common mistakes

- The short dashboard prefix (`c_serv_` plus four characters) instead of the whole key.
- `x-api-key` on the gRPC stream: it reads metadata `x-token` (or `authorization: Bearer`).
- A FREE key on the gRPC stream: not a wrong key, FREE has no stream (`PERMISSION_DENIED` `streaming is not included in this tier; upgrade the plan`).
- `"params"` before `"method"`, or a third permit method in one batch.
- `maxSupportedTransactionVersion` absent or 0 on `getTransaction`, `getBlock` or `blockSubscribe`.
- Retrying a 4xx unchanged, or re-signing a swap that may still land.
- Calling RPC methods over the WebSocket: they answer `-32601`.
- Expecting `accountSubscribe`, or a gRPC `accounts` list, to stream a plain SOL wallet.
- Other providers' quote params (`inputMint`, `outputMint`, `amount`, `onlyDirectRoutes`): this quote takes `src_mint`, `dst_mint`, `amount_in`, `slippage_bps`, an optional `dex` (or `dexes`), an optional `txVersion`, an optional `swapTag`, an optional `maxAccounts` and an optional `integrator_fee_bps` with `integrator_fee_account` (or `fee_bps` with `treasury`), and refuses any other name.


## Testing

Every call reaches Solana mainnet. A transaction you sign and send moves real funds.

- **Is it up, with no key:** `GET https://services.carbium.sh/livez` answers 204. The stream's `grpc.health.v1.Health/Check` answers `SERVING`.
- **First call with a key:** `getHealth` or `getSlot`, 1 credit each.
- **The quote API costs 0 credits.** `quote`, `swap` and `prices` count against the quote plan's rate (on the free quote plan also against the shared budget below), and `health` against the account's cached-read rate. `quote` builds nothing and moves nothing. `swap` returns an unsigned transaction: nothing happens until a wallet signs and sends it.
- **The free plan is enough for a test:** one free grant of credits, once (`GET /v1/balance` shows `granted`), 1 key, 5 cached reads a second, 3 DAS calls a second, 5 WebSocket connections and 10 subscriptions. The carbon stream and webhooks need the DEV, BUSINESS or PRO plan. `POST /v1/webhooks/{id}/test` sends one signed test delivery, billed as one event when it is delivered.
- **In tests and CI:** one account, one key held as a secret, a slow steady rate well under the plan's limit. Free callers on one network share 20 requests a second.
- **Never probe, scan or load test the service without written consent** ([Terms](https://carbium.sh/terms), 6.7). To time it, use the capped run on the [benchmark page](https://carbium.sh/benchmark.html). A free account refused for rate in most hours of a day is suspended.
- A refused call costs 0 credits and still spends rate: never loop on a 4xx. Two refusals do bill: a `getTransactionsForAddress` walk refused after it made upstream calls, and a send whose preflight failed.

## Support

Write to support@carbium.sh. Send the `x-request-id` of the answer you are asking about when it has one (the `x-subscription-id` for the carbon stream), the UTC time and the method. For a payment, send its `id` from `GET /v1/payments`, and for USDC or USDT also the transaction signature. Never send a raw API key: send its dashboard prefix (`c_serv_` plus four characters). Security reports: [security.txt](https://carbium.sh/.well-known/security.txt).
