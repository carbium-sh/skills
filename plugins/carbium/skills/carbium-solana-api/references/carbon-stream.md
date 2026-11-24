## Carbon stream (Yellowstone gRPC)

Contents, with the line each part starts on in this file:

- Endpoint and auth: line 23
- Who can stream, and how many streams: line 41
- The Subscribe request: rules an agent must follow: line 61
- Filters served: line 77
- What data exists: coverage: line 96
- Fields that are refused: line 141
- from_slot replay: line 153
- Keepalive: ping and pong: line 163
- Billing (credits): line 171
- Errors and what to do: line 187
- Unary helpers: line 237
- Reading frames in JS (v8): line 251
- Robust client (Node 20.18+, `@triton-one/yellowstone-grpc` v8): line 260
- grpcurl (debugging only): line 350
- Agent checklist: line 361

A Yellowstone/Dragon's Mouth compatible Geyser gRPC stream of slots, accounts, transactions, transaction statuses, blocks, block metadata and entries. Filtering happens on the server. Every stream passes the same key, rate and credit checks as RPC: one key, one domain, TLS on port 9443.

### Endpoint and auth

| Item | Value |
|---|---|
| Endpoint (URL-style clients: `@triton-one/yellowstone-grpc`, tonic, `yellowstone-grpc-client`) | `https://services.carbium.sh:9443` |
| Endpoint (host:port clients: grpcurl, raw grpc-js) | `services.carbium.sh:9443`, TLS |
| Service / method | `geyser.Geyser/Subscribe` (bidirectional stream) |
| Auth, form 1 | gRPC metadata `x-token: <FULL_KEY>` |
| Auth, form 2 | gRPC metadata `authorization: Bearer <FULL_KEY>` |
| Not accepted on the stream | `x-api-key`, `?api-key=`, or the key in the path. Those carriers only work for RPC and WebSocket |
| Key scope | The key must carry the GRPC scope. On the dashboard's Keys page, press SCOPE on the key, select GRPC and Save; it applies to that key only. Or call `PATCH /v1/keys/{id}/scope` with every plane the key should keep, e.g. `{"scope": ["rpc", "ws", "grpc", "das"]}`: the list replaces the key's scopes. A key issued on the dashboard while the account was on FREE was made without GRPC, so turn it on after you upgrade. |
| Response metadata | `x-subscription-id`: 32 hex chars, unique per Subscribe. Log it. |
| Server reflection | Not served (`UNIMPLEMENTED`). grpcurl needs the `.proto` files. |
| Compression | Server frames are sent uncompressed and metered as sent. Compressed requests (gzip, zstd) are accepted on `Subscribe` only. Send the unary helpers uncompressed. |
| Health (keyless) | `grpc.health.v1.Health/Check` answers `SERVING` with no key. Use it only as a liveness probe. |

Send the whole key. A `c_serv_xxxx` prefix is a label and is refused as `unknown api key`.

### Who can stream, and how many streams

| Limit | Value |
|---|---|
| `Subscribe` allowed | DEV, BUSINESS and PRO. FREE is refused `PERMISSION_DENIED`. |
| Concurrent streams per account (all keys of the account combined; one `Subscribe` = one stream) | 0 / 5 / 25 / 100 concurrent streams (FREE / DEV / BUSINESS / PRO) |
| Of those, heavy streams per account (the shapes below; 0 = not on the plan) | 0 / 0 / 1 / 2 (FREE / DEV / BUSINESS / PRO) |
| Subscribe attempts per account | 500/s, burst 1024, on every plan |
| Unary helpers (`GetSlot` and the others below) | 5 / 30 / 100 / 500 req/s (FREE / DEV / BUSINESS / PRO) |

Heavy fan-out streams have two limits of their own: the plan's number per account in the table above, and a node-wide ceiling of 128 open at once, shared by every customer. A Subscribe counts as heavy if it has any of the following:
- a `blocks` filter
- an `entry` filter
- a transaction firehose: `vote` or `failed` set, with no `account_include`, `account_required` or `signature`
- an `accounts` filter that names an `owner` and no `account`

A heavy Subscribe on a plan whose number is 0 is refused `PERMISSION_DENIED` `heavy streams are not included in this plan; upgrade to BUSINESS`, before any charge. One past the account's number is refused `RESOURCE_EXHAUSTED` `this account holds its share of the heavy stream slots; close one of its heavy streams first` with `retry-after: 2`. When the node's ceiling is full, a new heavy Subscribe is refused `RESOURCE_EXHAUSTED` `overloaded`, also with `retry-after: 2`. Slots, blocks_meta, transactions_status, narrowed transaction filters and account-list filters are never heavy: they open on every paying plan and count against none of this. Prefer narrow shapes.

`from_slot` does not make a stream heavy. A resume is classed by its filters, so a light stream resumes on every paying plan and uses none of the account's heavy number. Resumes have one limit of their own: the node admits at most 128 of them in any 10 s, light or heavy. One past that is refused `RESOURCE_EXHAUSTED` `too many streams are resuming from a past slot; retry shortly` with `retry-after: 2`: retry with backoff.

### The Subscribe request: rules an agent must follow

1. Put everything in the first request message. The filters, `commitment`, `accounts_data_slice` and `from_slot` in that first message fix the stream for its whole life.
   - `@triton-one/yellowstone-grpc` v5 and later (N-API): `client.subscribe(request)`, or `client.subscribe()` and then `stream.write(request)` once.
   - v1 to v4 (grpc-js): `client.subscribe()` and then `stream.write(request)` once.
   - The stream opens before the request is read. Send it at once: a stream with no request for 10 s is closed.
2. You cannot change filters mid-stream. A later request that adds, removes or changes any filter is silently ignored. The stream keeps serving the original filter, and you get no error frame. To change filters, open a new Subscribe with the new set, then close the old one. A later `from_slot` gets `INVALID_ARGUMENT` `from_slot is only supported on the initial subscribe request`.
3. The only later message that is applied is a ping (`ping: { id }` set). Any filter or commitment written with it is ignored; the stream keeps its first request. See Keepalive below.
4. With the TypeScript client, every map and list must be present (`accounts, slots, transactions, transactionsStatus, blocks, blocksMeta, entry, accountsDataSlice, blockFooter`). Empty maps are not sent on the wire. `blockFooter` must stay `{}`.
5. Filter keys are names you choose. Each update's `filters` array lists the keys it matched.
6. A request that names nothing (no filter, no ping, no `from_slot`) is not your first request yet: v8 and later send one at `client.subscribe()`, and the stream waits for the `stream.write(request)` that names the filters, within the 10 s. A stream that ends with only an empty request is refused `PERMISSION_DENIED` `filter not in v1 coverage; request provisioning`.
7. Keep each request under 4 MiB. That is the server's default decode limit (not tested live).
8. Set the client's max receive size to at least 64 MiB. Block and transaction frames can be several MiB, and the grpc-js default of 4 MiB fails on them.
   - v5 and later: `{ grpcMaxDecodingMessageSize: 64 * 1024 * 1024 }`
   - v1 to v4: `{ "grpc.max_receive_message_length": 64 * 1024 * 1024 }`

### Filters served

`commitment` is one subscription-level field: `PROCESSED = 0`, `CONFIRMED = 1`, `FINALIZED = 2`. Unset means processed. Every filter is served at the commitment you set; only `fromSlot` replay is limited to processed. Credits are charged once per Subscribe at the heaviest filter present (see Billing).

| Filter (TS key) | Fields that work | Subscribe credits | Heavy? |
|---|---|---|---|
| `slots` | `filterByCommitment`, `interslotUpdates` | 5 | no |
| `accounts` with `account: [pubkeys]` | `account`, `filters` (`memcmp` {offset, bytes / base58 / base64}, `datasize`, `tokenAccountState`, `lamports` {eq / ne / lt / gt}), `nonemptyTxnSignature`, top-level `accountsDataSlice` | 25 | no |
| `accounts` with `owner: [programs]` (no `account`) | `owner` plus the same `filters`. Every owner must be in the covered list below. | 200 | yes |
| `accounts` with both `account` and `owner` | ANDed, so it narrows the account list. The owner coverage check is skipped. | 200 | no |
| `transactions`, narrowed | `accountInclude` (any of), `accountRequired` (all of), `accountExclude`, `vote`, `failed`, or a single `signature` | 25 (5 if only `signature`) | no |
| `transactions` firehose | `vote` and/or `failed` set with no include, required or signature: `{vote:false, failed:false}` = all successful non-vote; `{vote:true}` = votes; `{failed:true}` = failed | 200 | yes |
| `transactionsStatus` | same shape as `transactions`, but each frame carries only status (slot, signature, isVote, index, err) | 25 (5 if only `signature`) | no |
| `blocksMeta` | `{}` | 200 | no |
| `blocks` | `accountInclude`, `includeTransactions`. A block frame carries only the transactions of the 9 on-chain liquidity programs listed below. `accounts` and `entries` arrive empty. | 200 | yes |
| `entry` | `{}`. Very high volume: about 20,000 frames in 4 s at processed, measured. | 200 | yes |

A bare transaction filter with nothing set (`{}`, or every field empty) is refused. Name at least one account, a signature, or set `vote`/`failed`.

### What data exists: coverage

The stream serves one shared upstream feed. A filter can only return what that feed carries.

- **Transactions are complete.** The feed carries every transaction: successful non-vote, votes and failed. Any narrowed `transactions` or `transactionsStatus` filter sees all matching transactions on any account, including wallets and programs not listed below.
- **Owner-scoped account streams** (`owner` without `account`) are sold only for these owners. Any other owner is refused `PERMISSION_DENIED` `filter not in v1 coverage; request provisioning` before any charge. Stake, Vote and every unlisted program are refused.

| Owner (program id) | Program | Carried |
|---|---|---|
| `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` | SPL Token | whole |
| `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` | Token-2022 | whole |
| `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | Raydium AMM v4 | whole |
| `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C` | Raydium CPMM | whole |
| `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | Raydium CLMM | whole |
| `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | Orca Whirlpool | whole |
| `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB` | Meteora AMM (DAMM v1) | whole |
| `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | Meteora DAMM v2 | whole |
| `24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi` | Meteora dynamic vault | whole |
| `voTpe3tHQ7AjQHMapgSue2HJFAh2cGsdokqN3XqmVSj` | Other program | whole |
| `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN` | Meteora DBC | whole |
| `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | Pump.fun bonding curve | whole |
| `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` | Pump.fun AMM | whole |
| `LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj` | Raydium LaunchLab | whole |
| `2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3c` | Lifinity v2 | whole |
| `PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY` | Phoenix | whole |
| `metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s` | Metaplex Token Metadata | whole |
| `CoREENxT6tW1HoK8ypY1SxRMZTcVPm7R94rH4PZNhX7d` | Metaplex Core | whole |
| `CarbeVCzypPEbtPJsdCboEkqxYxqT75nmhNUNBtyNPiz` | Carbium program | whole |
| `box8cR7MyfymPsNS9QW4iEzzDZUNLer3LUDo87uGdVM` | Carbium program | whole |
| `iso5rbdHjynDynkosGgHxDGAD7Eks9BeHRrFLPYYjJo` | Carbium program | whole |
| `isogrRJ6sEiktnfUY7QdZhDr5Sut3C8ER9HejjUqSZK` | Carbium program | whole |
| `ww3st35u7nDFdAypP8nXjyCQy9cUMp9i1cuAJq2JKgL` | Carbium program | whole |
| `dca1HQzdAnibwxoE7vMYdEmYhqggVUjADsB9YAXdDoi` | Carbium program | whole |
| `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | Meteora DLMM | only 904-byte accounts (LbPair) |
| `11111111111111111111111111111111` | System | only accounts closing to 0 lamports, or holding more than 1,000,000 SOL |

- **Account-list streams** (`account: [...]`) are admitted for any pubkey, but only deliver writes to accounts the feed carries:
  - accounts of the owners in the table above (for DLMM and System, only the part the Carried column names)
  - Stake and Vote accounts holding more than 1,000,000 SOL
  - the six sysvars: `SysvarC1ock…`, `SysvarEpochSchedu1e…`, `SysvarRent…`, `SysvarS1otHashes…`, `SysvarS1otHistory…`, `SysvarStakeHistory…`
  - accounts of these indexed programs: `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL`, `AddressLookupTab1e1111111111111111111111111`, `MNFSTqtC93rEfYHB6hF82sKdZpUDFWkViLByLd1k1Ms`, `SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy`, `SP12tWFxD9oJsVWNavTTBZvMbA6gkAmxtVgxdqvyvhY`, `SPMBzsVUuoHA4Jm6KunbsotaahvVikZs1JyTW6iJvbn`, `ALPHAQmeA7bjrVuccPsYPiCvsi428SNwte66Srvs4pHA`, `REALQqNEomY6cQGZJUGwywTBD2UmDT32rZcNnfxQ5N2`, `5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx`, `5quBtoiQqxF9Jv6KYKctB59NT3gtJD2Y65kdnB1Uev3h`, `9H6tua7jkLhdm3w8BvgpTn5LZNU7g4ZynDmCiNN3q6Rp`, `9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP`, `DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1`, `HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq`, `goonuddtQRrWqqn5nFyczVKaie28f3kDkHWkHtURSLE`, `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ`
- **System-owned wallets (SOL balances), Stake and Vote accounts do not stream as account updates**, except System accounts closing to 0 lamports and accounts holding more than 1,000,000 SOL. They are admitted, then stay silent. A stream that delivers no data frame books 0 credits. In a live test, 8 busy Jito tip accounts gave 0 account frames in 15 s, while a `transactions` filter on the same accounts gave 740 frames in 6 s. To follow a wallet, subscribe `transactions` with `accountInclude: [wallet]` and read `meta.preBalances`/`postBalances`, or poll `getBalance` over RPC.
- **No startup snapshot.** An account stream sends only writes made after it opens. Load the current state with RPC `getMultipleAccounts` (up to 100 keys per call on DEV and BUSINESS, 300 on PRO; see Point reads in the [RPC section](https://carbium.sh/skill/rpc.md)) first. Then apply stream updates, keeping the highest `(slot, writeVersion)` per pubkey.
- **Blocks are program-scoped.** A `blocks` frame carries only the transactions that touch these programs: `675kPX9M…`, `CAMMCzo5…`, `CPMMoo8L…`, `whirLbMi…`, `LBUZKhRx…`, `Eo7WjKq6…`, `cpamdpZC…`, `pAMMBay6…`, `PhoeNiXZ…`. `executedTransactionCount` still states the full block count. For full blocks, use RPC `getBlock` with `maxSupportedTransactionVersion: 1`.

### Fields that are refused

These fields are refused before any charge with `PERMISSION_DENIED` `token_accounts, cuckoo filters and block_footer are not supported: remove the field`:
- `transactions[*].tokenAccounts` and `transactionsStatus[*].tokenAccounts`
- any cuckoo filter (`accounts[*].cuckooAccountsFilter`, `transactions[*].cuckooAccountInclude`, `blocks[*].cuckooAccountInclude`)
- a non-empty `blockFooter`
- `entry[*].includeUpdateParent` (the message does not name this field)

Do not use the client's `CompressedAccountFilterSet` (v5 and later), because it emits a cuckoo filter. Send explicit `account` lists instead.

`subscribeDeshred` is not part of this service, and the server has no handler for it (not tested live).

### from_slot replay

- Replay works only on the first request, only at processed commitment (`commitment` unset or `PROCESSED`). Asking at confirmed or finalized is refused `PERMISSION_DENIED` `from_slot replay is available only at processed commitment`.
- The retained window is bounded by bytes, not by a slot count, so its length in slots changes with traffic. Before replaying, call the unary `SubscribeReplayInfo` (`client.subscribeReplayInfo()` → `{ firstAvailable }`) and use `fromSlot >= firstAvailable`.
- A `fromSlot` below the floor ends the stream with `OUT_OF_RANGE` `gap: re-seed required`. The 5/25/200 subscribe charge is kept for that probe.
- Replay can start one slot before `fromSlot`, and it overlaps whatever you already have. Dedupe on transaction `(slot, signature)` and account `(pubkey, slot, writeVersion)`.
- A `fromSlot` Subscribe is classed by its filters: with light filters it opens on every paying plan, with a heavy filter it is a heavy stream as above. The node admits at most 128 resumes in any 10 s; one past that is refused `too many streams are resuming from a past slot; retry shortly` with `retry-after: 2`. Retry with backoff, or open a plain Subscribe and re-seed over RPC.
- The v5 client's auto reconnect (reconnect options as the fourth constructor argument) resubscribes with `fromSlot` when it reconnects. For light filters that works on every paying plan (measured with 5.0.9 on DEV across a server restart: the stream carried on). If a refusal with a retry-after refuses the reconnect (the node's replay starts, the account's stream cap or heavy number), the server holds that refusal for its retry-after before it answers, so the client tries once every 2 s until it is admitted (measured with 5.0.9 on DEV: one try every 2 s for 20 s), then delivers its backfill. The client shows your code no error while it retries. For a heavy filter on a plan with no heavy streams the reconnect is refused `PERMISSION_DENIED` and the stream stays down: leave the option off there, reconnect yourself and re-seed over RPC.
- `uint64` values are decimal strings in the JS client: `fromSlot: "454966788"`.

### Keepalive: ping and pong

- The server sends an `update.ping` frame on every stream every 15 s (measured at 15.1 s and 30.1 s). Ignore it. Its bytes are metered like any frame on a stream that also delivers data; a stream that delivers only pings and pongs books 0 credits.
- The server also sends an HTTP/2 PING every 20 s and closes the connection if no answer comes within 10 s. Your HTTP/2 library answers it on its own; just keep reading the connection.
- Send your own ping every 10 s on the same stream: `stream.write({ ...EMPTY, ping: { id: 1 } })`. The server answers with `update.pong` `{ id }` (measured: pong about 0.1 s after the write). A ping that also carries filters gets its pong; the filters are ignored and never change the stream. A ping that carries `fromSlot` ends the stream with `INVALID_ARGUMENT`.
- The unary `Ping(count)` RPC costs 1 credit per call. Prefer in-stream pings.
- The server's bounded control queue holds 8 messages. Do not flood writes: a ping that finds the queue full ends the stream with `RESOURCE_EXHAUSTED` `cfan control backlog full`.

### Billing (credits)

The subscribe charge depends on the heaviest filter in the request:

| Subscribe class | Shapes | Credits |
|---|---|---|
| slot | `slots` only; `transactions`/`transactionsStatus` with only `signature` | 5 |
| account | `accounts` with an `account` list (no owner); `transactions`/`transactionsStatus` with `accountInclude` or `accountRequired` | 25 |
| program | any `accounts` filter with `owner`; `blocksMeta`; `entry`; `blocks`; a transaction firehose | 200 |

- **Subscribe charge:** taken once at admission. A stream that delivers no data frame (nothing, or only pings and pongs) books 0 credits: the charge is refunded and its ping bytes are not billed. A `fromSlot` gap probe is the exception and keeps the charge.
- **Egress:** 20 credits per MiB (1,048,576 bytes) of frames your client actually reads, counted as the protobuf bytes of each `SubscribeUpdate`, server pings and pongs included on a stream that delivers data. It is billed every second. Formula: `credits = floor(bytes × 20 / 1,048,576)`. Example: 10 MiB/s sustained ≈ 200 credits/s ≈ 720,000 credits/hour.
- **Unary helpers:** 1 credit per call.
- **Out of credits:** an open stream is cut with `RESOURCE_EXHAUSTED` `consumer_credits_exhausted: stream egress budget spent; buy a plan or upgrade`. A new Subscribe is refused `RESOURCE_EXHAUSTED` `credits exhausted`. A funded account whose credits the server has not loaded yet is refused `RESOURCE_EXHAUSTED` `credits for this account are still loading on this node; retry after Retry-After` (retry-after 1): retry. Its open stream ends `UNAVAILABLE` with the same message (retry-after 1) when the server cannot bill it yet: resubscribe after it; the bytes already sent are billed.
- **Refusals cost nothing:** a refused Subscribe (auth, filter, field, tier, cap) is never charged.

### Errors and what to do

How the clients surface a status:
- **grpc-js clients** (`@triton-one/yellowstone-grpc` v1 to v4): the numeric `code`, `details` and `metadata` (`retry-after`) are on the error.
- **N-API client (v5 and later):**
  - A refused key (unknown or disabled, no gRPC scope, outside its IP allowlist) makes `await client.subscribe()` throw: `message` = `failed to open subscribe stream`, `code` = `GenericFailure`.
  - Every other refusal (plan, filter, limits, credits) and every mid-stream error comes on the `error` event with `message` `subscribe stream receive failed`. Handle both.
  - In both cases, `err.cause.message` reads `gRPC status: code: '<status text>', message: "<message>"`. Map the status text: `The request does not have valid authentication credentials` = UNAUTHENTICATED, `The caller does not have permission to execute the specified operation` = PERMISSION_DENIED, `Some resource has been exhausted` = RESOURCE_EXHAUSTED, `The service is currently unavailable` = UNAVAILABLE, `Operation was attempted past the valid range` = OUT_OF_RANGE, `Client specified an invalid argument` = INVALID_ARGUMENT, `Internal error` = INTERNAL.
  - It does not expose `retry-after`, so use the values in the table. A `RESOURCE_EXHAUSTED` refusal with a retry-after reaches you about that long after your request: the server holds it for its retry-after, so a client that retries at once tries once per retry-after per stream. While an account already has many refusals held, a further one answers at once. Refusals without a retry-after (`PERMISSION_DENIED` and the rest) answer at once.

| gRPC status (code) | Message (exact) | When | retry-after | Agent action |
|---|---|---|---|---|
| UNAUTHENTICATED (16) | `unknown api key` | no key, wrong key, key in the wrong carrier, prefix only, rotated key | 2 | Stop. Send the full key as `x-token` or `authorization: Bearer`. |
| UNAUTHENTICATED (16) | `api key is not enabled for grpc` | key lacks the grpc scope | 2 | Stop. Turn on GRPC for the key (Keys page, SCOPE, select GRPC, Save; or `PATCH /v1/keys/{id}/scope`), then reconnect. |
| UNAUTHENTICATED (16) | `api key suspended: the plan term ended; renew on the dashboard` | plan term ended | 2 | Stop. Renew. |
| UNAUTHENTICATED (16) | `api key suspended; contact support` / `api key revoked` / `api key disabled; contact support` / `session expired` | key state, at Subscribe or mid-stream: an open stream ends within about 2 s of a revoke, rotate (reads `api key revoked`), suspend or ban | 2 | Stop. Mint a new key, contact support, or refresh the session. |
| PERMISSION_DENIED (7) | `streaming is not included in this tier; upgrade the plan` | FREE account | none | Stop. Upgrade to DEV, BUSINESS or PRO. |
| PERMISSION_DENIED (7) | `heavy streams are not included in this plan; upgrade to BUSINESS` | a heavy Subscribe on a plan with no heavy streams | none | Stop. Use a non-heavy shape (an `account` list instead of `owner`, a narrowed transaction filter instead of the firehose, `blocksMeta` instead of `blocks`), or upgrade. |
| PERMISSION_DENIED (7) | `filter not in v1 coverage; request provisioning` | owner not in the covered list; bare or empty transaction filter; empty request | none | Stop. Fix the filter (narrow it, or use a covered owner) or request provisioning. |
| PERMISSION_DENIED (7) | `accounts filter names no account and no owner: firehose shape, not sold in v1` | `accounts` filter with no `account` and no `owner` | none | Stop. Name accounts or a covered owner. |
| PERMISSION_DENIED (7) | `token_accounts, cuckoo filters and block_footer are not supported: remove the field` | refused field present | none | Stop. Remove the field. |
| PERMISSION_DENIED (7) | `from_slot replay is available only at processed commitment` | `fromSlot` with confirmed or finalized | none | Stop. Use processed, or drop `fromSlot`. |
| PERMISSION_DENIED (7) | `client ip address is not on this api key's allowlist; add it on the dashboard or with PATCH /v1/keys/{id}/allowlist` | the key has an IP allowlist and the caller's address is not on it (Subscribe and the unary helpers) | none | Stop. Call from a listed address, or add this one on the dashboard or with `PATCH /v1/keys/{id}/allowlist`. |
| INVALID_ARGUMENT (3) | `empty subscribe request stream` | stream half-closed before the first request | none | Fix the client: send the request. |
| DEADLINE_EXCEEDED (4) | `no subscribe request within 10 s` | stream opened and no request sent | none | Fix the client: send the request with the open or right after it. |
| INVALID_ARGUMENT (3) | `from_slot is only supported on the initial subscribe request` | `fromSlot` in a later write | none | Reconnect with `fromSlot` in the first request. |
| RESOURCE_EXHAUSTED (8) | `rate limit exceeded` | more than 500 Subscribes/s per account, or unary calls above the tier rate | ≥1 (from the limiter) | Wait the retry-after, then back off exponentially. |
| RESOURCE_EXHAUSTED (8) | `max subscription limit exceeded` | account already holds its plan's concurrent streams: 0 / 5 / 25 / 100 concurrent streams (FREE / DEV / BUSINESS / PRO) | 2 | Close idle streams, merge filters into fewer Subscribes, or upgrade. Retry only after a stream closes. |
| RESOURCE_EXHAUSTED (8) | `overloaded` | node-wide heavy fan-out ceiling (128) full | 2 | Retry with backoff from 2 s to 30 s, or switch to a non-heavy shape (an `account` list instead of `owner`, a narrowed transaction filter instead of the firehose, `blocksMeta` instead of `blocks`). |
| RESOURCE_EXHAUSTED (8) | `this account holds its share of the heavy stream slots; close one of its heavy streams first` | the account already holds its plan's number of heavy streams | 2 | Close one of the account's heavy streams, or use a non-heavy shape. Retry only after one closes. |
| RESOURCE_EXHAUSTED (8) | `too many streams are resuming from a past slot; retry shortly` | more than 128 resumes (`fromSlot`) started on the node within 10 s | 2 | Retry with backoff from 2 s, or open a plain Subscribe and re-seed over RPC. |
| RESOURCE_EXHAUSTED (8) | `credits exhausted` | the account's remaining credits cannot cover the Subscribe | 1 | Stop: buy a plan or upgrade. Do not loop. |
| RESOURCE_EXHAUSTED (8) | `credits for this account are still loading on this node; retry after Retry-After` | the server has not loaded the account's credits yet, at Subscribe or a unary call (a new account's first calls, a burst that spent this server's share, or just after a server restart) | 1 | Wait the retry-after, then retry. Not charged; do not buy anything. |
| UNAVAILABLE (14) | `credits for this account are still loading on this node; retry after Retry-After` | an open stream of an account that has credits, which the server cannot bill yet (its share here ran out before the refill, or the server re-registered); the bytes already sent are billed | 1 | Resubscribe after the retry-after. Do not buy anything. |
| RESOURCE_EXHAUSTED (8) | `consumer_credits_exhausted: stream egress budget spent; buy a plan or upgrade` | balance hit 0 mid-stream | 2 | Stop: buy a plan or upgrade. |
| RESOURCE_EXHAUSTED (8) | `consumer_lagged: your stream fell behind the ring; reduce filters or read faster` (+ metadata `x-egress-bps`) | client read too slowly | 2 | Reconnect after 2 s. Read faster: hand frames to a queue and never block the `data` handler. Or narrow the filters. |
| RESOURCE_EXHAUSTED (8) | `cfan control backlog full` | a ping arrived while the server's control queue was full; the stream ends | none | Reconnect. Ping no more than every 10 s and do not flood writes. |
| (stall cut) CANCELLED (1) `Call cancelled` in grpc-js; INTERNAL `Unexpected EOF decoding stream.` in v8 | (client-side text) | the client took no frame for 10 s, so the server closed the stream. Measured: the stalled reader saw this, not `consumer_lagged`. | none | Same as `consumer_lagged`: reconnect after 2 s and fix the slow reader. |
| OUT_OF_RANGE (11) | `gap: re-seed required` | `fromSlot` below the retained floor, or the upstream feed had a gap or source cutover | none | Reload state over RPC, then resubscribe with no `fromSlot` (or with `fromSlot >= firstAvailable`). |
| UNAVAILABLE (14) | `server shutting down, reconnect` | server restart or deploy; open streams drain within 10 s | 2 | Reconnect with backoff from 2 s. With processed commitment, resume with `fromSlot` = last seen slot. |
| UNAVAILABLE (14) | `cfan downstream unavailable` | upstream feed not reachable at open (subscribe charge refunded) | none | Retry with jittered backoff from 2 s to 30 s. |
| UNAVAILABLE (14) | `stream closed with updates undelivered, reconnect` | stream closed while frames were still queued | none | Reconnect. The tail was not delivered and not billed, so re-seed if you need it. |
| UNAVAILABLE (14) | `warm start: filling` | upstream feed just restarted | none | Retry after 2 s or more. |
| UNAVAILABLE (14) (HTTP 503 at the edge) | (empty or edge text) | stream backend down between restarts | none | Retry with jittered backoff. |
| OK / clean end | — | the server ended the stream | — | Reconnect after 1 s or more. Treat it as a possible gap. |
| UNIMPLEMENTED (12) | — | method not served (reflection, `SubscribeDeshred`) | none | Stop. Use `Subscribe` and the unary helpers below. |
| INVALID_ARGUMENT (3) | `invalid commitment N` | unary call with a commitment other than 0, 1 or 2 | none | Fix the request. |

Refusals are checked in this order: key (its state, the GRPC scope, then its IP allowlist), then filter shape, then the subscribe rate, then the FREE bar, then for a heavy shape the plan's bar, the account's heavy number and the node's ceiling, then for a resume the node's replay starts, then the stream cap, then credits. A FREE key with a bad filter therefore sees the filter error first.

### Unary helpers

Same endpoint and metadata, 1 credit per call, at 5 / 30 / 100 / 500 req/s (FREE / DEV / BUSINESS / PRO).

| RPC (JS v8 method) | Returns (sample) |
|---|---|
| `GetSlot` (`getSlot(commitment)`) | `{ slot: "454966888" }` |
| `GetBlockHeight` (`getBlockHeight(commitment)`) | `{ blockHeight: "433004140" }` |
| `GetLatestBlockhash` (`getLatestBlockhash(commitment)`) | `{ slot, blockhash, lastValidBlockHeight }` |
| `IsBlockhashValid` (`isBlockhashValid(hash, commitment)`) | `{ slot, valid: true }` |
| `GetVersion` (`getVersion()`) | JSON string with the server, proto and Solana versions |
| `Ping` (`ping(count)`) | `{ count }` |
| `SubscribeReplayInfo` (`subscribeReplayInfo()`) | `{ firstAvailable: "454966574" }` (the replay floor) |

### Reading frames in JS (v8)

- Each update has a `filters: string[]` field and exactly one payload field: `slot`, `account`, `transaction`, `transactionStatus`, `block`, `blockMeta`, `entry`, `ping` or `pong`.
- `uint64` values are decimal strings. Use `BigInt(...)` for arithmetic.
- Pubkeys, signatures and account data are `Uint8Array` or Buffer. Get base58 with `getBase58Decoder().decode(bytes)` from `@solana/kit`.
- `update.slot.status` values: `0` PROCESSED, `1` CONFIRMED, `2` FINALIZED, `3` FIRST_SHRED_RECEIVED, `4` COMPLETED, `5` CREATED_BANK, `6` DEAD (`SlotStatus` enum).
- `update.account.account`: `{ pubkey, lamports, owner, executable, rentEpoch, data, writeVersion, txnSignature }`, plus `update.account.slot`.
- `update.transaction.transaction`: `{ signature, isVote, transaction, meta, index }`. `meta.err` is set on failed transactions. Every transaction version is carried, and the stream has no `maxSupportedTransactionVersion` parameter.

### Robust client (Node 20.18+, `@triton-one/yellowstone-grpc` v8)

```js
// npm i @triton-one/yellowstone-grpc@8 @solana/kit
import Client, { CommitmentLevel } from "@triton-one/yellowstone-grpc";
import { getBase58Decoder } from "@solana/kit";

const ENDPOINT = "https://services.carbium.sh:9443";
const KEY = process.env.CARBIUM_KEY;              // full key, never the c_serv_xxxx prefix
const b58 = getBase58Decoder();

// Every map and list must be present (the TS type requires it); empty ones are not sent on the wire.
const EMPTY = { accounts: {}, slots: {}, transactions: {}, transactionsStatus: {}, blocks: {},
                blocksMeta: {}, entry: {}, accountsDataSlice: [], blockFooter: {} };

const REQUEST = {
  ...EMPTY,
  commitment: CommitmentLevel.CONFIRMED,
  slots: { s: { filterByCommitment: true } },
  transactions: { dex: { vote: false, failed: false, accountExclude: [], accountRequired: [],
    accountInclude: ["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"] } },
};

// Pull "<status text>" and "<message>" out of either client generation.
const STATUS = { "valid authentication credentials": "UNAUTHENTICATED", "does not have permission": "PERMISSION_DENIED",
  "resource has been exhausted": "RESOURCE_EXHAUSTED", "currently unavailable": "UNAVAILABLE",
  "past the valid range": "OUT_OF_RANGE", "invalid argument": "INVALID_ARGUMENT", "not implemented": "UNIMPLEMENTED",
  "was cancelled": "CANCELLED", "Internal error": "INTERNAL", "data loss": "DATA_LOSS", "Deadline expired": "DEADLINE_EXCEEDED" };
const NUM = { 1: "CANCELLED", 3: "INVALID_ARGUMENT", 4: "DEADLINE_EXCEEDED", 7: "PERMISSION_DENIED", 8: "RESOURCE_EXHAUSTED",
  11: "OUT_OF_RANGE", 12: "UNIMPLEMENTED", 13: "INTERNAL", 14: "UNAVAILABLE", 15: "DATA_LOSS", 16: "UNAUTHENTICATED" };
function grpcError(e) {
  if (typeof e?.code === "number") return { code: NUM[e.code] ?? String(e.code), msg: e.details ?? "" };
  const text = String(e?.cause?.message ?? e?.message ?? e);
  const code = Object.entries(STATUS).find(([k]) => text.includes(k))?.[1] ?? "UNKNOWN";
  return { code, msg: (text.match(/message: "(.*)"$/) ?? [])[1] ?? text };
}

// What to do with a terminal status. "stop" = fix the request, key or plan; do not retry.
function decide({ code, msg }) {
  if (code === "UNAUTHENTICATED" || code === "PERMISSION_DENIED" || code === "INVALID_ARGUMENT" || code === "UNIMPLEMENTED") return "stop";
  if (code === "OUT_OF_RANGE") return "reseed";                        // gap: re-seed required
  if (msg.startsWith("consumer_credits_exhausted") || msg === "credits exhausted") return "stop"; // buy a plan or upgrade first
  return "retry";                                                     // rate, overloaded, lag, credits loading, restart, transport
}

let backoffMs = 2000;                                                 // the server's retry-after is 1-2 s; start at 2 s
let lastSlot = 0n;

async function runOnce() {
  const client = new Client(ENDPOINT, KEY, { grpcMaxDecodingMessageSize: 64 * 1024 * 1024 });
  await client.connect();
  const stream = await client.subscribe(REQUEST);                    // a refused key throws here; other refusals end the stream
  const pinger = setInterval(() => stream.write({ ...EMPTY, ping: { id: 1 } }), 10_000);
  return new Promise((resolve) => {
    const done = (how) => { clearInterval(pinger); stream.destroy(); resolve(how); };
    stream.on("data", (u) => {
      backoffMs = 2000;                                               // healthy again
      if (u.ping || u.pong) return;                                   // server ping every 15 s; pong answers ours
      if (u.slot) lastSlot = BigInt(u.slot.slot);
      if (u.transaction) {
        const t = u.transaction.transaction;
        console.log("tx", u.transaction.slot, b58.decode(t.signature), t.meta?.err ? "failed" : "ok");
      }
    });
    stream.on("error", (e) => done(grpcError(e)));
    stream.on("end", () => done({ code: "OK", msg: "server ended the stream" }));
  });
}

for (;;) {
  let how;
  try { how = await runOnce(); } catch (e) { how = grpcError(e); }
  const action = decide(how);
  console.error(new Date().toISOString(), how.code, how.msg, "->", action);
  if (action === "stop") process.exit(1);
  if (action === "reseed") { /* reload state over RPC (getMultipleAccounts / getSignaturesForAddress) before resuming */ }
  await new Promise((r) => setTimeout(r, backoffMs + Math.random() * 1000));
  backoffMs = Math.min(backoffMs * 2, 30_000);
}
```

Notes on the client:
- **Keep the handler fast.** Keep the `data` handler non-blocking (push to a queue). A reader that takes no frame for 10 s is disconnected.
- **grpc-js client (v1 to v4):**
  - `const stream = await client.subscribe(); stream.write(REQUEST);`
  - Omit `blockFooter` from the request.
  - Pass `{ "grpc.max_receive_message_length": 64 * 1024 * 1024 }` as channel options.
  - Errors carry a numeric `code`, `details` and `metadata.get("retry-after")`.
- **Resuming without loss at processed commitment:** on reconnect, call `subscribeReplayInfo()`. If `lastSlot >= BigInt(firstAvailable)`, set `fromSlot: String(lastSlot)` in the request and dedupe the overlap. Otherwise re-seed over RPC.

### grpcurl (debugging only)

There is no reflection, so pass the proto files from the `rpcpool/yellowstone-grpc` repo (`yellowstone-grpc-proto/proto/geyser.proto` and `solana-storage.proto`):

```bash
grpcurl -import-path ./proto -proto geyser.proto \
  -H "x-token: $CARBIUM_KEY" \
  -d '{"slots":{"s":{}}}' \
  services.carbium.sh:9443 geyser.Geyser/Subscribe
```

### Agent checklist

- Use a DEV, BUSINESS or PRO key with the grpc scope, sent as `x-token`. Never use a FREE key, the key prefix, or `x-api-key`.
- Put one complete request in the first message. To change filters, open a new stream and then close the old one.
- Every `owner` must come from the covered list. For wallets (System-owned) use `transactions.accountInclude`, not `accounts`.
- Use narrow shapes (`account` lists, `accountInclude`) for anything long-lived: they cost 25 credits, not 200, open on every paying plan and never count against the heavy limits.
- Seed state over RPC first. The stream sends no snapshot.
- Ping every 10 s, read promptly, and set the max receive size to at least 64 MiB.
- Retry only on RESOURCE_EXHAUSTED (except credits), UNAVAILABLE, CANCELLED, INTERNAL and a clean end. Start at 2 s, double up to 30 s, add jitter. Stop on UNAUTHENTICATED, PERMISSION_DENIED, INVALID_ARGUMENT and credit exhaustion.
- On `gap: re-seed required`, reload state over RPC before trusting the stream again.
- Budget egress at 20 credits per MiB read, plus the 5 / 25 / 200 subscribe fee.

