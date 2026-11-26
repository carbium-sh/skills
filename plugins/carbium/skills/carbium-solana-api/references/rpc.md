## RPC (JSON-RPC 2.0 over HTTPS)

Contents, with the line each part starts on in this file:

- Wire rules (follow all of them): line 23
- How to read any answer (decision order): line 42
- Method catalogue: what is served and how: line 50
- Not served, refused or absent: line 104
- Scans: getProgramAccounts, getTokenAccountsByOwner, getTokenAccountsByDelegate: line 123
- getSupply and getLargestAccounts (aggregate cache): line 160
- Point reads: getAccountInfo, getMultipleAccounts: line 167
- History: getTransaction, getBlock, getSignaturesForAddress, getTransactionsForAddress: line 173
- Commitment and minContextSlot: line 194
- Batching: line 199
- Sending and simulating: line 206
- Credits, rate and concurrency limits: line 216
- Error playbook: line 234
- JavaScript clients: line 317
- Agent checklist: line 439

Endpoint: `POST https://services.carbium.sh` (port 443). One request is one JSON object, or a JSON array of up to 100 objects for a batch. Every answer is JSON-RPC 2.0, and `id` echoes yours. "The door" below is the gateway at this address.

### Wire rules (follow all of them)

| Rule | Value | If broken |
|---|---|---|
| HTTP method | `POST` only. `GET`/`HEAD /livez` is the keyless health check (bodiless 204). `GET /cq1/quote` is the old quote path: use the `quote` method (see [Quote and router](https://carbium.sh/skill/quote.md)). Any other non-POST gets a bodiless 404. `OPTIONS` is the CORS preflight (204). | 404 or 405 |
| Credential | The full raw key (`c_serv_...`). Carriers, in read order: `x-api-key` header, `authorization: Bearer <key>`, first path segment `https://services.carbium.sh/<key>`, query `?api-key=` / `?api_key=` / `?apiKey=`, then `x-token` header. No key: `quote`, `swap`, `prices`, `health`, `getHealth`, `getVersion`, `getSlot`, `getBlockHeight`, `getEpochInfo`, `getLatestBlockhash`, `isBlockhashValid`, `getGenesisHash` only, 30 calls a minute per IP address (IPv6: per /56) in all, then 429 `PUBLIC_LIMITED`; batch calls each count, a batch over 30 gets 401 `KEY_REQUIRED`. | 401 `-32001` |
| Body size | at most 50 KB (1 KB = 1,024 bytes) | HTTP 413, `-32600` `request body exceeds the byte cap` |
| Key order | `"method"` must come BEFORE `"params"` in each request object, and must sit within the first 1,024 bytes of the object. A single `"method"` key per object. | HTTP 400 `-32600` `params before method` / `method beyond position cap` / `duplicate method key` |
| `params` | A JSON array (positional), as agave expects. The exceptions take an object: `getPriorityFeeEstimate` and `qn_estimatePriorityFees` (or a one-element array holding it), the ten DAS methods (`getAsset` also takes `["<id>"]`), and `quote`, `swap` and `prices`. | 200 `-32602` `invalid params` |
| Batch | 1 to 100 elements. An empty array `[]` is malformed. | 400 `-32600` `batch exceeds the cardinality cap` / `malformed json-rpc body` |
| Compression | Send `accept-encoding: gzip` (or `zstd`). Bodies of 1,400 bytes or more come back compressed. Node `fetch` decodes gzip by itself. | (none) |
| Connection | Reuse one keep-alive connection. The door holds idle connections for 600 s. | (none) |
| CORS (browser) | Allowed request headers: `content-type, x-api-key, x-token, authorization, solana-client`. Readable response headers: `x-request-id, retry-after` only. A browser cannot read `retry-after-ms`. | (none) |

Response headers to use:
- `x-request-id`: present on every admitted call. Quote it when you report a problem.
- `retry-after` (whole seconds) and `retry-after-ms` (exact ms) on door refusals that waiting can fix. Prefer `retry-after-ms`.
- `cache-control: public, max-age=31536000, s-maxage=31536000, immutable` on finalized `getBlock`/`getTransaction`/`getBlockTime` answers. Those results never change, so cache them yourself.

### How to read any answer (decision order)

1. A non-200 HTTP status means the door refused or the upstream failed. Act on the status and `error.code` (playbook below).
2. HTTP 200 with `error` is a method-level answer. Agave, the door's local index, or a door policy produced it.
3. `error.data.reason` (an UPPER_SNAKE string) is present only on door refusals. With `error.data.retryable: true`, waiting can change the answer. With `false`, it cannot: fix the request or stop.
4. Seven codes collide with agave's numbering (`-32001`, `-32002`, `-32004`, `-32005`, `-32010`, `-32011`, `-32012`). Tell them apart by HTTP status and `data.reason`, never by the code alone.
5. Refusals and error answers cost 0 credits, with two exceptions: a `getTransactionsForAddress` walk refused after it made upstream calls bills those calls (see History), and a `sendTransaction` whose preflight simulation failed keeps its 75 credits. Every admitted call spends rate cells, including one that errors.

### Method catalogue: what is served and how

Cells are the admission charge against your rate bucket. Credits are the billing charge: each method's base weight plus 5 credits for each blocking permit it holds; token scans add a charge per row, and a `getTransactionsForAddress` walk one per upstream call (their rows below). Req/s = the plan's cells/s ÷ the method's cells (floored). Rates are per ACCOUNT: all of an account's keys share one bucket per class.

| Methods | Cells per call | FREE | DEV | BUSINESS | PRO (req/s per account) |
|---|---|---|---|---|---|
| getHealth getVersion getSlot getBlockHeight getEpochInfo getBalance getLatestBlockhash getEpochSchedule getFeeForMessage getFirstAvailableBlock getGenesisHash getAgGenesisCert getHighestSnapshotSlot getIdentity getInflationGovernor getInflationRate getMaxRetransmitSlot getMaxShredInsertSlot getMinimumBalanceForRentExemption getSlotLeader getStakeMinimumDelegation getTransactionCount isBlockhashValid minimumLedgerSlot getBlockCommitment | 1 | 5 | 30 | 100 | 500 |
| getBlockProduction getBlockTime getLeaderSchedule getRecentPerformanceSamples getRecentPrioritizationFees getSignatureStatuses getSlotLeaders getPriorityFeeEstimate qn_estimatePriorityFees | 5 | 1 | 6 | 20 | 100 |
| getVoteAccounts getInflationReward | 50 | 0.1 | 0.6 | 2 | 10 |
| getClusterNodes | 100 | 0.05 | 0.3 | 1 | 5 |
| getAccountInfo getMultipleAccounts getTokenAccountBalance getTokenSupply | 10 | 0.5 | 15 | 50 | 400 |
| getBlocks getBlocksWithLimit | 50 | 0.5 | 3 | 5 | 20 |
| getTransaction getTransactionsForAddress | 50 | 0.24 | 1.2 | 5 | 25 |
| getSignaturesForAddress | 50 | 0.24 | 1.2 | 100 | 500 |
| getBlock | 250 | 0.048 | 0.24 | 1 | 5 |
| sendTransaction `skipPreflight: true` | 20 | 0.25 | 1.5 | 5 | 25 |
| sendTransaction with preflight | 70 | 0.071 | 0.428 | 1.4 | 7.1 |
| simulateTransaction | 50 | 0.5 | 1.2 | 1.5 | 5 |
| getProgramAccounts (provisioned program) | 500 | 0.004 | 0.03 | 50 | 100 |
| getTokenAccountsByOwner getTokenAccountsByDelegate | 200 | 0.01 | 0.075 | 125 | 250 |
| getLargestAccounts getSupply | 200 | 0.005 | 0.005 | 100 | 250 |
| getAsset getAssets getAssetBatch getAssetsByOwner getAssetsByGroup getAssetsByCreator getAssetsByAuthority searchAssets getNftEditions getTokenAccounts | 1 | 3 | 15 | 75 | 150 |

Where each method is served and what it costs in credits:

| Method(s) | Served by | Credits per call |
|---|---|---|
| getHealth getVersion getSlot getBlockHeight getEpochInfo getBalance getLatestBlockhash isBlockhashValid getMinimumBalanceForRentExemption getGenesisHash getAgGenesisCert getIdentity getTransactionCount getBlockCommitment getFeeForMessage getStakeMinimumDelegation getInflationGovernor getInflationRate getEpochSchedule getSlotLeader getHighestSnapshotSlot getMaxRetransmitSlot getMaxShredInsertSlot minimumLedgerSlot getFirstAvailableBlock | door cache (150 ms per-slot TTL, 1 s near-constant TTL) or validator | 1 |
| getSignatureStatuses getRecentPerformanceSamples getRecentPrioritizationFees getBlockProduction getBlockTime getPriorityFeeEstimate qn_estimatePriorityFees | validator / door | 5 |
| getLeaderSchedule getSlotLeaders | validator (1 permit) | 10 |
| getInflationReward | validator (1 permit) | 55 |
| history getSignatureStatuses | validator (1 permit) | 10 a signature + 5 |
| getVoteAccounts | validator, cached 150 ms | 5 |
| getClusterNodes | validator, cached 1 s | 5 |
| getAccountInfo getTokenAccountBalance getTokenSupply | local hot index for write-hot accounts, otherwise validator (1 permit) | 15 |
| getMultipleAccounts | same as above; 10 cells per pubkey | 10 per pubkey + 5 |
| getBlocks getBlocksWithLimit | validator (1 permit) | 55 |
| getSignaturesForAddress | our own address index (up to 30 days), otherwise validator (1 permit) | 55 |
| getTransaction | validator (1 permit) | 55 |
| getTransactionsForAddress | validator (1 permit) | 55 for one descending page of signatures with no filter; any other call is a walk, 55 plus 50 per upstream call after the first (see History) |
| getBlock | validator (getBlock pool, 2 node-wide) | 70 |
| sendTransaction `skipPreflight: true` | validator, no permit | 20 |
| sendTransaction with preflight | validator (compute permit) | 75 |
| simulateTransaction | validator (compute permit) | 55 |
| getProgramAccounts (provisioned program) | local program index | 505 |
| getTokenAccountsByOwner / ByDelegate | local token index | 205 for up to 20 rows, then +10 per row (max 100,005) |
| getSupply getLargestAccounts | door aggregate cache only | 200 |
| getAsset getAssets getAssetBatch getAssetsByOwner getAssetsByGroup getAssetsByCreator getAssetsByAuthority searchAssets getNftEditions | our own DAS index | 1 |
| getTokenAccounts (the DAS method) | local token index | 1 |

The scan and walk rows (getProgramAccounts, the token scans, getSupply and getLargestAccounts) show sustained rates. Those served from our own index also draw a per-account ceiling on index-heavy work, and the table gives the lower of the two. The getSignaturesForAddress row is for a single call our address index answers. A batch, or a page the index misses, runs at the getTransaction row's rate.

Bursts: each class bucket holds max(1,024 cells, one second of the plan's rate), 32,000 cells for PRO account reads and 150 cells for the DAS methods on every plan. An empty bucket refills at the plan rate, for one-cell calls 5 / 30 / 100 / 500 req/s (FREE / DEV / BUSINESS / PRO). On FREE the shared network budget (see Credits, rate and concurrency limits) can stop a burst before the bucket is empty; sustained, the plan rate above binds first.

### Not served, refused or absent

| Call | Answer | Agent action |
|---|---|---|
| `requestAirdrop` | 200 `-32601` `method not served`, reason `METHOD_NOT_SERVED` | Mainnet only, no faucet. Stop. |
| `getProgramAccountsV2` | 200 `-32601` `method not served` | Use `getProgramAccounts` with filters. There is no pagination cursor. |
| `getTokenLargestAccounts` | 200 `-32601` `method not served` | Not served on any plane. Do not emulate it with an unfiltered scan. |
| DAS proof and signature methods (`getAssetProof`, `getAssetProofBatch`, `getAssetProofs`, `getAssetSignatures`, `getSignaturesForAsset`) | 200 `-32601` `method not found`, reason `UNKNOWN_METHOD` | Not served: compressed NFTs are not indexed, so there is no proof or asset signature list to give. A final answer that costs nothing; do not retry or loop over them. |
| Compressed NFTs (Bubblegum) | absent from every DAS answer | Not indexed. No DAS method returns them; do not page looking for them. |
| Any unknown name | 200 `-32601` `method not found`, reason `UNKNOWN_METHOD` | Check the spelling. The answer is final and costs nothing, so retrying the same name never changes it. |
| `getLargestAccounts` with `filter: circulating\|nonCirculating` | 501 `-32004`, reason `UNSUPPORTED_SHAPE`, message begins `getLargestAccounts filter=circulating\|nonCirculating is not served` | Use the unfiltered form, or `getSupply` for the circulating and non-circulating totals. |
| Enhanced-transactions REST, Metis REST paths | absent | Read `getTransaction`, `getSignaturesForAddress` or `getTransactionsForAddress`. For push, use WSS, the gRPC stream or a webhook (see [Webhooks](https://carbium.sh/skill/webhooks.md)). |

Vendor-compatible extras that ARE served (single requests only):
- `getPriorityFeeEstimate` (Helius shape). Params are `[{accountKeys?: string[] (≤128), transaction?: string, options?: {priorityLevel?: "Min"|"Low"|"Medium"|"High"|"VeryHigh"|"UnsafeMax", includeAllPriorityFeeLevels?: bool, recommended?: bool, lookbackSlots?: n (≤150), transactionEncoding?: "base58"|"base64"}}]`. It answers `{"priorityFeeEstimate":n,"priorityFeeLevels":{min,low,medium,high,veryHigh,unsafeMax}}` in micro-lamports per compute unit. The levels are percentiles 0/25/50/75/95/100. The default estimate is `medium`, and `recommended: true` returns `high`.
- `qn_estimatePriorityFees` (QuickNode shape). Params are `{last_n_blocks?, account?, api_version?}`. It answers `{context:{slot}, per_compute_unit:{extreme,high,medium,low,percentiles{25,50,75,95,99}}, per_transaction:{...}, recommended}`.
- Both fee methods are derived from this door's `getRecentPrioritizationFees` over up to 150 slots, cached 2 s. Bad params get 400 `-32602` with one of these messages: `params must be an object, or a one-element array holding one`, `accountKeys must be at most 128 base58 32-byte pubkeys`, `priorityLevel must be Min, Low, Medium, High, VeryHigh or UnsafeMax`, `this method is not batchable`.
- `getTransactionsForAddress` (Helius shape): see History.

### Scans: getProgramAccounts, getTokenAccountsByOwner, getTokenAccountsByDelegate

Rules:
- Send scans as single requests. In a batch they get 400 `-32600` `scan index method is not batchable; send it as a single request` (`SCAN_NOT_BATCHABLE`).
- Always set `encoding` to `base64`, `base64+zstd` or `jsonParsed`. With base58, any account over 128 bytes (every 165-byte token account, for example) gets 200 `-32600` `Encoded binary (base 58) data should be less than 128 bytes, please use Base64 encoding.`
- A result holds at most 10,000 accounts. Over that, the answer is 200 `-32012` `result exceeds this tier's 10000-account cap. 10000 is the page ceiling, not the program's total ...`. Narrow with `dataSize`/`memcmp` filters (gPA) or a `mint` filter (token scans). `dataSlice` does not reduce the row count. There is no paging.
- Program index lag: 429 `-32010` `scan index temporarily unavailable, retry`, reason `CHOT_INDEX_UNAVAILABLE`, `retryable: true`, `retry-after-ms: 100`. Retry with exponential backoff (100 ms, 200, 400 ... capped at 5 s) for up to about 6 tries, then surface the error.

Accepted config keys (anything else is dropped silently, as agave does):

| Method | Config keys |
|---|---|
| getProgramAccounts `[programId, config]` | `commitment`, `encoding`, `dataSlice {offset, length}` (both integers, both required), `minContextSlot`, `filters`, `withContext` |
| getTokenAccountsByOwner/ByDelegate `[owner\|delegate, filter, config]` | `filter` = exactly one of `{"mint": <pubkey>}` or `{"programId": <pubkey>}`. Config keys: `commitment`, `encoding`, `dataSlice`, `minContextSlot`. The answer always carries `context`. |

Filters (gPA): at most 4 entries in total, at most one `{"dataSize": n}`, and any number of `{"memcmp": {"offset": n, "bytes": "<string>", "encoding"?: "base58"|"base64"}}`. `bytes` must decode to 128 bytes or fewer, and the default encoding is base58.

| Request | Answer |
|---|---|
| 5+ filters, bad offset, undecodable or over-128-byte `bytes`, malformed `dataSlice` | 200 `-32602` `invalid params` |
| `sortResults` (any value, null included) | 501 `-32004` `sortResults is not served for getProgramAccounts; omit it`, data `{"reason":"UNSUPPORTED_SHAPE","field":"sortResults","served":[]}` |
| `commitment` other than processed/confirmed/finalized | 501 `-32004` `commitment 'root' is not served for getProgramAccounts; use processed, confirmed or finalized`, data includes `"value":"root","served":[...]` |
| `encoding` binary/json | 501 `-32004` naming the served set `base58, base64, base64+zstd, jsonParsed` |
| `jsonParsed` together with `dataSlice` | 501 `-32004`, served `base58, base64, base64+zstd` |
| memcmp `bytes` as a number array, a second `dataSize`, any other filter type, memcmp keys other than offset/bytes/encoding | 501 `-32004` `filters '<what>' is not served for getProgramAccounts; use one dataSize or memcmp with base58 or base64 string bytes` |
| Token scan with no usable mint/programId | 200 `-32010` `program not provisioned for scan; contact support to request provisioning for this program`, reason `CLASSIC_SPL_SCAN` |

How to read the 501 answer: `error.data.field` names what to change, `error.data.served` lists the accepted values (`[]` means remove the field), and `error.data.value` is what you sent. Fix the request and resend once. Never retry it unchanged.

`withContext: true` returns `{context:{slot, apiVersion}, value:[{pubkey, account}]}`. Without it, the answer is a bare array.

Provisioned programs (served from the local index): `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` (SPL Token, filter it by `dataSize: 165` plus `memcmp` owner at offset 32 or mint at offset 0), `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` (Token-2022), `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL`, `AddressLookupTab1e1111111111111111111111111`, `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`, `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`, `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`, `5quBtoiQqxF9Jv6KYKctB59NT3gtJD2Y65kdnB1Uev3h`, `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`, `DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1`, `9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP`, `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`, `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`, `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ`, `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB`, `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG`, `24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi`, `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN`, `2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3c`, `PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY`, `REALQqNEomY6cQGZJUGwywTBD2UmDT32rZcNnfxQ5N2`, `ALPHAQmeA7bjrVuccPsYPiCvsi428SNwte66Srvs4pHA`, `9H6tua7jkLhdm3w8BvgpTn5LZNU7g4ZynDmCiNN3q6Rp`, `MNFSTqtC93rEfYHB6hF82sKdZpUDFWkViLByLd1k1Ms`, `HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq`, `goonuddtQRrWqqn5nFyczVKaie28f3kDkHWkHtURSLE`, `SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy`, `SP12tWFxD9oJsVWNavTTBZvMbA6gkAmxtVgxdqvyvhY`, `SPMBzsVUuoHA4Jm6KunbsotaahvVikZs1JyTW6iJvbn`, `5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx`, `voTpe3tHQ7AjQHMapgSue2HJFAh2cGsdokqN3XqmVSj`, `LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj` (Raydium LaunchLab).

A scan the local index does not answer gets 200 `-32010` `this method is not served from the validator on this host; only the local index answers it`, or, for a program outside the validator's own index, `<program> excluded from account secondary indexes; this RPC method unavailable for key`. Do not retry; contact support to provision the program.

Token scans are billed by rows: 205 credits cover the first 20 rows, then 10 credits per extra row (10,000 rows = 100,005 credits). The extra is taken before the body is sent. If the account cannot cover it, the call gets 402 `-32002` `credits exhausted` unserved, and the base charge is refunded; when this node has not loaded enough of the account's credits yet, it gets 429 `CREDITS_PENDING` the same way: wait `retry-after-ms` and send it again.

### getSupply and getLargestAccounts (aggregate cache)

- They are served only from the door's cache, never by a live whole-ledger walk on your request. Send them as single requests. In a batch they get 400 `-32600` `getSupply and getLargestAccounts are not batchable; send them as single requests`.
- Cold entry (for example after a restart, or for a new param combination): 503 `-32005` `served from cache only; the cache is filling, retry after Retry-After`, with `Retry-After` up to 30 s. Your call starts one background fill. Wait the `Retry-After` it gives and retry; expect success within 1 to 3 retries. Where the door cannot fill the cache at all, it answers 200 `-32010` `this method is not served from the validator on this host; only the local index answers it`: do not retry. Where the cache is copied from our other host and that copy was refused, the call gets 200 `-32010` `this method is served from the peer door's cache only, and the peer refused the copy (...); asked again after the hold`: retry after about 20 s, and contact support if it repeats. Each distinct `commitment` / `excludeNonCirculatingAccountsList` combination is its own cache entry.
- Freshness: an entry is served at any age and refreshes at most once every 600 s. `context.slot` can lag the tip by minutes, so treat the values as approximate. With `minContextSlot` above the cached slot, the call answers 200 `-32016` with `data.contextSlot` and starts a refresh. That answer can repeat for up to about 10 minutes.
- Accepted keys: getSupply `commitment`, `excludeNonCirculatingAccountsList`, `minContextSlot`. getLargestAccounts `commitment`, `minContextSlot`; `filter` gets the 501 described earlier.

### Point reads: getAccountInfo, getMultipleAccounts

- Config keys: `commitment`, `encoding` (`base58`, `base64`, `base64+zstd`, `jsonParsed`), `dataSlice`, `minContextSlot`.
- getMultipleAccounts: the validator caps it at 300 pubkeys, and each pubkey costs 10 cells. A call must fit your burst bucket (1,024 cells on FREE/DEV/BUSINESS, so 100 pubkeys or fewer per call; 32,000 on PRO).
- Concurrency: on FREE and DEV, one index-served read is in flight per key. Validator-served reads allow 2 in flight per key and 4 node-wide. Beyond that, the door waits up to 3 s for a free slot and then answers 429 `SLOT_CAP_EXCEEDED` (`blocking-slot capacity exceeded: external pool`) or `scan-index lane capacity exceeded: chot_lane`, with `retry-after-ms: 100`.

### History: getTransaction, getBlock, getSignaturesForAddress, getTransactionsForAddress

- Retention: `getSignaturesForAddress` pages come from our own address index, which keeps up to 30 days. A page the index cannot answer goes to the validator, one at a time for all callers on this host; while another page holds that turn the call gets 429 `SLOT_CAP_EXCEEDED` `one getSignaturesForAddress at a time reaches this host's validator and the turn stayed taken; retry` with `Retry-After: 1`.
- `getTransaction` and `getBlock` end at the validator's ledger floor. Read it live with `getFirstAvailableBlock` or `minimumLedgerSlot` (1 credit each); it moves continuously. There is no archive behind it, so a signature listed from the index can be older than any transaction you can fetch.
- Below the floor, `getBlock` answers 200 `-32001` `Block <slot> cleaned up, does not exist on node. First available block: <slot>`. Do not retry.
- Always send `"maxSupportedTransactionVersion": 1` on `getTransaction` and `getBlock` (and `blockSubscribe`). Mainnet carries version-1 transactions. With the key absent or 0, the answer is 200 `-32015` `Transaction version (1) is not supported by the requesting client. Please try the request again with the following configuration parameter: "maxSupportedTransactionVersion": 1`. The door passes your value through unchanged.
- getBlock config: `commitment`, `encoding`, `transactionDetails` (`full`, `accounts`, `signatures`, `none`), `rewards`, `maxSupportedTransactionVersion`. Use `transactionDetails: "signatures"` or `"none"` and `rewards: false` when you do not need bodies; a full block is several MB.
- getTransaction config: `commitment`, `encoding`, `maxSupportedTransactionVersion`.
- getSignaturesForAddress: `[address, {limit ≤1000, before, until, commitment, minContextSlot}]`, standard agave semantics. Page with `before` set to the last signature you received.
- getTransactionsForAddress (Helius shape). Params: `[address, {limit 1..1000 (default 1000), transactionDetails: "signatures"|"full", sortOrder: "desc"|"asc", paginationToken, commitment, minContextSlot, encoding, maxSupportedTransactionVersion, filters: {slot:{gte,gt,lte,lt,eq}, blockTime:{...}, status:"succeeded"|"failed"|"any", tokenAccounts:"none"|"balanceChanged"|"all", tokenTransfer:{with, mint, direction:"in"|"out"|"any", amount:{gte,...}}}}]`.
  - Result: `{"data":[...], "paginationToken": <string|null>, "historyFloor": <slot>}`. `historyFloor` is the ledger floor, as `getFirstAvailableBlock` reads it, and is left out when the door has not read it within the last 2 minutes. `paginationToken: null` means done. Pass a non-null token back to get the next page.
  - In `full` mode, rows are `{slot, transactionIndex, blockTime, transaction, meta, version}`, and `droppedRows` counts bodies that could not be fetched.
  - One call examines at most 25,000 signatures (`limit` with a token filter) and stops paging after 45 s (in `full` mode its body fetch can run to 67.5 s), then answers what it found, which can be fewer rows than `limit` or none, with a live `paginationToken`. Keep paging until `paginationToken` is null.
  - Price: one descending page of signatures with no filter is one upstream call, 55 credits. Any other call (`transactionDetails: "full"`, `sortOrder: "asc"` or any filter) is a walk: 55 credits plus 50 for each upstream call after the first that answers (each page of up to 1,000 signatures, and each transaction fetched for `full` or a token filter). The door holds the walk's worst case before its first call and gives back the unused part: 25 pages for an ascending walk, or for one with a slot, blockTime or status filter but no token filter (otherwise 1 page), plus one fetch per row of `limit` for `full` or a token filter, so 1,255 credits for 25 pages and up to 51,255 at `limit` 1000. An account whose credits cannot cover that worst case gets 402 `credits exhausted`, unserved: lower `limit` when the walk fetches bodies, otherwise buy a plan or upgrade. A 429 `CREDITS_PENDING` means this node has not loaded the credits yet: wait `retry-after-ms` and send it again.
  - `sortOrder: "asc"` without a lower slot bound gets 200 `-32602` `sortOrder "asc" requires a lower slot bound (filters.slot.gte, .gt or .eq): ...`.
  - `sortOrder: "asc"` with a token filter (`filters.tokenAccounts` or `filters.tokenTransfer`) gets 200 `-32602` `sortOrder "asc" is not supported with a token filter ...` and costs 0 credits. Page descending instead.
  - An ascending walk that cannot reach its slot floor within 45 s or 25,000 signatures, or meets a page the validator does not answer, gets 200 `-32602` `this ascending walk did not reach its slot floor: ...` and is billed for the upstream calls it made. Raise `filters.slot.gte` and send it again (with `filters.slot.eq`, page descending instead); never resend it unchanged.
  - A walk that read no history gets 200 `-32602` `the walk read no history: ...`, billed only for upstream calls that answered. Retry it; if it repeats, check the address and `paginationToken`.
  - `filters.signature` gets 200 `-32602` `filters.signature is not supported: ...`. Use `filters.slot` or `filters.blockTime` instead.
  - Not batchable.

### Commitment and minContextSlot

- `processed`, `confirmed` and `finalized` are accepted everywhere. The deprecated aliases (`recent`, `single`, `singleGossip`, `root`, `max`) pass through to the validator on ordinary methods but get 501 on scans. Use `confirmed` for reads and `finalized` for history you will cache.
- An unmet `minContextSlot` answers HTTP 200 `-32016` `Minimum context slot has not been reached` with `error.data.contextSlot` (the slot the node is at). Retry after about 220 ms per missing slot, or lower your floor.

### Batching

- At most 100 elements; the whole batch's cells are charged in one check.
- Any element that is refused refuses the whole batch: every element comes back with the same error and its own `id`. Upstream method errors stay per element.
- At most 2 elements per batch may hold a validator permit: `getAccountInfo`, `getMultipleAccounts`, `getTokenAccountBalance`, `getTokenSupply`, `getTransaction`, `getSignaturesForAddress`, `getTransactionsForAddress`, `getBlocks`, `getBlocksWithLimit`, `getLeaderSchedule`, `getSlotLeaders`, `getInflationReward` and a history `getSignatureStatuses`. A third returns 429 `-32005` `blocking-slot capacity exceeded: external pool` (`SLOT_CAP_EXCEEDED`, `retryable: true`). In a batch it is permanent: split the batch.
- Never batch: `getProgramAccounts`, `getTokenAccountsByOwner`, `getTokenAccountsByDelegate`, `getSupply`, `getLargestAccounts`, `getTransactionsForAddress`, `getPriorityFeeEstimate`, `qn_estimatePriorityFees`, `quote`, `swap`, `prices`, `health`.

### Sending and simulating

- `sendTransaction [base64Tx, {encoding: "base64", skipPreflight, preflightCommitment, maxRetries, minContextSlot}]`. Both v0 and v1 transactions are accepted (v1 can be up to 4,096 bytes).
- `skipPreflight: true` costs 20 credits and has the higher send rate. Preflight costs 75 credits, allows one in flight per key, and shares a node-wide compute pool. A failed preflight answers 200 `-32002` `Transaction simulation failed: ...` with agave's `data` (`err`, `logs`, `unitsConsumed`) and keeps its 75 credits, as `simulateTransaction` bills the same failure. That `data` has no `reason`, which tells it apart from the door's 402.
- The door forwards a send exactly once, with no retries, and the upstream write deadline is 30 s. On 502, 503 or 504 after a send, the transaction may already have landed. Do not re-sign. Poll `getSignatureStatuses`, and resend the SAME signed bytes (same signature, which cannot execute twice) until `getBlockHeight` passes the blockhash's `lastValidBlockHeight`. Only then build a new transaction with a fresh blockhash.
- `simulateTransaction [base64Tx, {encoding: "base64", sigVerify, replaceRecentBlockhash, commitment, accounts, innerInstructions}]` costs 55 credits. One is in flight per key, and simulations are limited node-wide (a heavy pool shared by all customers), so 429 `HEAVY_CLASS_LIMITED` can happen at low volume: honor `retry-after-ms`. An undecodable transaction gets 200 `-32602` `failed to deserialize solana_transaction::versioned::VersionedTransaction: ...`.
- Confirming: `getSignatureStatuses [[sig, ...]]` (5 credits per call, up to 256 signatures) returns `confirmationStatus` `processed`/`confirmed`/`finalized` and `err`. Or use `signatureSubscribe` on WSS. Get a blockhash with `getLatestBlockhash [{commitment: "confirmed"}]` (1 credit, cached 150 ms).
- Fees: `getRecentPrioritizationFees [[writableAccounts]]`, `getPriorityFeeEstimate`, or `qn_estimatePriorityFees`. All are in micro-lamports per compute unit.
- 0-RTT: when a send or simulate arrives as TLS early data, the door answers 425 `-32600` `early data not permitted for non-idempotent method`. Resend after the handshake completes.

### Credits, rate and concurrency limits

| Limit | FREE | DEV | BUSINESS | PRO |
|---|---|---|---|---|
| Rate bucket burst (cells), per class | max(1,024, one second of the class rate); DAS 150 | max(1,024, one second of the class rate); DAS 150 | max(1,024, one second of the class rate); DAS 150 | max(1,024, one second of the class rate); 32,000 for account reads; DAS 150 |
| Index-served reads in flight per key (account reads, getSignaturesForAddress, scans, walks) | 1 | 1 | 24 | 48 |
| Validator permit reads in flight per key | 2 | 2 | 2 | 2 |
| Simulate / preflight send in flight per key | 1 | 1 | 1 | 1 |
| Validator gPA (unprovisioned program) in flight per key | 1 | 1 | 1 | 1 |

Node-wide limits apply as well: index lane 32, validator permits 4, getBlock 2, compute 6, validator scans 2. Validator-heavy work (simulate, unprovisioned gPA) is capped at 250 cells/s per key with a 600-cell burst, and at 300 cells/s node-wide (about 6 simulations/s for all customers together).

- A call over its plan rate that can be served within 1 s waits in the door once and is then served, with no 429. Only a longer shortfall is refused.
- 429 body: `{"code":-32005,"message":"rate limit exceeded","data":{"reason":"RATE_LIMITED","retryable":true}}`, with `Retry-After` (seconds, rounded up) and `retry-after-ms`. Wait `retry-after-ms` plus jitter. If a request is larger than the whole burst it can never fit, and it gets 429 with `retry-after-ms` 1000 every time: split it.
- 402 body: `{"code":-32002,"message":"credits exhausted","data":{"reason":"CREDITS_EXHAUSTED","retryable":false}}` with `Retry-After: 1`. Do not retry: stop and tell the user to buy or renew a plan on the dashboard. A funded account whose credits this node has not loaded is answered 429 `CREDITS_PENDING` instead (below). Near the end of a balance a node can answer 402 while the last credits sit reserved at other nodes; they return within minutes.
- 429 body while this node has not loaded a funded account's credits yet: `{"code":-32005,"message":"credits for this account are still loading on this node; retry after Retry-After","data":{"reason":"CREDITS_PENDING","retryable":true}}` with `Retry-After: 1` and `retry-after-ms: 1000`. Wait `retry-after-ms` and send it again; it costs 0 credits.
- FREE keys, and quote calls (`quote`, `swap`, `prices`, `health`) on the free quote plan at any plan, also share two budgets by client address. Every free caller from one IPv4 /24 (IPv6 /56) shares 20 requests/s with a burst of 20, and each call in a batch counts. All free traffic on the door shares 1,000 requests/s. Over the first: 429 `-32005` `free tier limit for your network reached: all free keys calling from one subnet share one request budget; retry after Retry-After, or upgrade for a limit of your own`, reason `FREE_SUBNET_LIMITED`. Over the second: 429 `-32005` `free tier at capacity on this node: all free traffic shares one budget; retry after Retry-After, or upgrade`, reason `FREE_TIER_BUSY`. Wait `retry-after-ms`, or move to a paid plan (a paid quote plan, for quote calls), which neither budget touches.

### Error playbook

Door refusals (admission). Every one carries `error.data.reason` and `retryable`:

| HTTP | code | message | reason | Do |
|---|---|---|---|---|
| 401 | -32001 | `unknown api key` | UNKNOWN_KEY | Send the full key in a header. The prefix the dashboard shows (`c_serv_` plus four characters) is a label. Stop. |
| 401 | -32001 | `api key is not enabled for rpc` | SCOPE_RPC_MISSING | Enable RPC on the key. Stop. |
| 401 | -32001 | `api key suspended: the plan term ended; renew on the dashboard` (+`status_reason`) | KEY_SUSPENDED | Rare: the paid term just ended. The account moves to Free shortly and the key works again at Free limits; renew on the dashboard to keep the plan. |
| 401 | -32001 | `api key is not enabled for quote` | SCOPE_QUOTE_MISSING | The account has the quote module, but this key's scope lacks quote. Turn quote on in this key's scope on the dashboard (Keys, Key scope) or with `PATCH /v1/keys/{id}/scope`, or use a key that has it. Stop. |
| 401 | -32001 | `api key is not enabled for das` | SCOPE_DAS_MISSING | The 10 DAS methods need `das` in this key's scope. Turn das on in the key's scope on the dashboard (Keys, Key scope) or with `PATCH /v1/keys/{id}/scope`, or use a key that has it. Stop. |
| 401 | -32001 | `session expired` | EXPIRED_SESSION | A `Bearer` value with a dot is read as a dashboard session, and it has expired. Sign in again, or send the API key. Stop. |
| 403 | -32001 | `client ip address is not on this api key's allowlist; add it on the dashboard or with PATCH /v1/keys/{id}/allowlist` | IP_NOT_ALLOWED | Call from an address on the key's list, or add this one. Do not retry. |
| 401 | -32001 | `api key suspended; contact support` | KEY_SUSPENDED | Contact support. Stop. |
| 401 | -32001 | `api key revoked` | KEY_REVOKED | Mint a new key. Stop. |
| 401 | -32001 | `api key disabled; contact support` | KEY_BANNED | Contact support. Stop. |
| 400 | -32600 | `malformed json-rpc body` / `params before method` / `duplicate method key` / `method beyond position cap` / `batch exceeds the cardinality cap` | MALFORMED_BODY / PARAMS_BEFORE_METHOD / DUPLICATE_METHOD_KEY / METHOD_POSITION_CAP / BATCH_TOO_LARGE | Fix the body. |
| 400 | -32600 | `scan index method is not batchable; send it as a single request` / `quote is not batchable` | SCAN_NOT_BATCHABLE / QUOTE_NOT_BATCHABLE | Send it single. |
| 200 | -32601 | `method not found` / `method not served` | UNKNOWN_METHOD / METHOD_NOT_SERVED | Stop. Do not probe. |
| 200 | -32010 | `program not provisioned for scan; contact support to request provisioning for this program` | PROGRAM_NOT_PROVISIONED / CLASSIC_SPL_SCAN | Add a mint/programId filter (token scans), or ask support. Do not retry. |
| 402 | -32002 | `credits exhausted` | CREDITS_EXHAUSTED | Do not retry: buy a plan or upgrade. |
| 429 | -32005 | `credits for this account are still loading on this node; retry after Retry-After` | CREDITS_PENDING | The account has credits, but this node has not loaded them yet (a new account's first calls, a burst that spent this node's share, or just after a node restart). Wait `retry-after-ms` (1000) and send it again; do not buy anything. |
| 403 | -32050 | `module not enabled for this account` | MODULE_NOT_ENABLED | Quote/swap/prices/health need the quote module. Add it with `POST https://carbium.sh/v1/modules/quote`, your session or a Full control account API key, and the JSON body `{"plan": "free"}` (the free plan), or on the dashboard's MODULES page. |
| 429 | -32005 | `rate limit exceeded` | RATE_LIMITED | Wait `retry-after-ms` plus jitter. |
| 429 | -32005 | `heavy-class rate limit exceeded` | HEAVY_CLASS_LIMITED | Wait `retry-after-ms`. Shared with other customers for simulate. |
| 429 | -32005 | `blocking-slot capacity exceeded: <external\|compute\|scan\|get_block> pool`, `scan-index lane capacity exceeded: chot_lane`, `DAS lane capacity exceeded: das_lane` | SLOT_CAP_EXCEEDED | Lower your concurrency and retry after 100 ms. Split a batch with more than 2 permit methods. |
| 429 | -32005 | `overloaded` | LOAD_SHED | Back off 1 to 5 s. |
| 429 | -32005 | `free tier limit for your network reached: ...` | FREE_SUBNET_LIMITED | FREE plan, or quote calls on the free quote plan: every free caller on your network shares one budget. Wait `retry-after-ms`, or upgrade (the quote plan, for quote calls). |
| 429 | -32005 | `free tier at capacity on this node: ...` | FREE_TIER_BUSY | FREE plan, or quote calls on the free quote plan: all free traffic shares one budget. Wait `retry-after-ms`, or upgrade (the quote plan, for quote calls). |
| 429 | -32010 | `scan index temporarily unavailable, retry` | CHOT_INDEX_UNAVAILABLE | Exponential backoff from 100 ms, about 6 tries. |
| 501 | -32004 | `<field> '<value>' is not served for <method>; use ...` (+`field`, `value`, `served`) | UNSUPPORTED_SHAPE | Change the field per `served`. Do not retry unchanged. |
| 501 | -32004 | `getLargestAccounts filter=circulating\|nonCirculating is not served: ...` | UNSUPPORTED_SHAPE | Drop `filter`, or use getSupply. |

Door transport and local answers (no `data.reason`):

| HTTP | code | message | Do |
|---|---|---|---|
| 413 | -32600 | `request body exceeds the byte cap` | Keep the body ≤ 50 KB; split the batch or gMA. |
| 200 | -32602 | `invalid params` | Fix the param types and arity (see scans). |
| 200 | -32602 | `the walk read no history: ...` | getTransactionsForAddress only: retry with backoff; if it repeats, check the address and `paginationToken`. |
| 200 | -32602 | `this ascending walk did not reach its slot floor: ...` | getTransactionsForAddress only: raise `filters.slot.gte` and send it again (with `filters.slot.eq`, page descending), never unchanged. Billed for the upstream calls it made. |
| 503 | -32005 | `served from cache only; the cache is filling, retry after Retry-After` | Wait `Retry-After` (up to 30 s) and retry. |
| 200 | -32010 | `this method is not served from the validator on this host; only the local index answers it` | The local index cannot answer this scan or aggregate here. Do not retry; use a provisioned program or contact support. |
| 200 | -32010 | `this method is served from the peer door's cache only, and the peer refused the copy (...); asked again after the hold` | getSupply or getLargestAccounts only: the copy from our other host was refused. Retry after about 20 s; if it repeats, contact support. |
| 503 | -32005 | `overloaded` (Retry-After 1) | Retry after Retry-After with jitter. |
| 503 | -32011 | `upstream RPC unavailable, retry later` (Retry-After 2) | The validator is failing, so calls to it are paused for a moment. Back off 2, 4, 8 s. |
| 504 | -32000 | `gateway timeout` (95 s) | Retry idempotent reads once. For sends, check status first. |
| 504 | -32000 | `upstream_slow` (Retry-After 90) | The validator scan exceeded 90 s or 64 MiB. Narrow the query. |
| 502 | -32603 | `upstream unavailable` / `upstream response error` / `upstream omitted required context` | Retry idempotent reads with backoff. For sends, check status first. |
| 425 | -32600 | `early data not permitted for non-idempotent method` | Resend after the TLS handshake. |
| 200 | -32012 | `result exceeds this tier's 10000-account cap. ...` | Narrow the filters. Never retry unchanged. |
| 200 | -32016 | `Minimum context slot has not been reached` + `data.contextSlot` | Wait, or lower minContextSlot. |
| 200 | -32600 | `Encoded binary (base 58) data should be less than 128 bytes, please use Base64 encoding.` | Use base64. |

Validator answers (HTTP 200, agave's codes, passed through):

| code | meaning | Do |
|---|---|---|
| -32001 | `Block N cleaned up, does not exist on node. First available block: M` | Below the ledger floor. Stop. |
| -32002 | `Transaction simulation failed: ...` (preflight) | Fix the transaction (read `data.logs`). Do not resend unchanged. |
| -32003 | signature verification failure | Re-sign. |
| -32004 | block not available for slot | Not produced or confirmed yet. Retry in 1 to 2 s. |
| -32005 | node unhealthy / behind | Retry with backoff. |
| -32007 / -32009 | slot skipped / missing in long-term storage | No block at that slot. Move on. |
| -32010 | `<key> excluded from account secondary indexes; this RPC method unavailable for key` | Program not indexed. Contact support. |
| -32013 | signature length mismatch | Fix the transaction. |
| -32014 | block status not yet available | Retry in 1 s. |
| -32015 | `Transaction version (1) is not supported ...` | Send `maxSupportedTransactionVersion: 1`. |
| -32016 | min context slot not reached (+`data.contextSlot`) | Wait, or lower the floor. |
| -32602 | invalid params (agave's text) | Fix the params. |

Code collisions for clients ported from another provider:

| code | elsewhere | here |
|---|---|---|
| -32001 | agave: block cleaned up | also any key refusal (HTTP 401, or 403 for the IP allowlist) |
| -32002 | agave: preflight failed | also credits exhausted (HTTP 402) |
| -32004 | agave: block not available | also unsupported shape (HTTP 501) |
| -32005 | agave: node unhealthy | also rate, heavy, slot, overload, the free budgets, credits still loading on this node (429) and the cache filling (503) |
| -32010 | agave: key excluded from index | also scan not provisioned (200), a scan this door does not send to the validator (200) and index lag (429, retry) |
| -32011 | agave: transaction history not available; QuickNode: method rate limit | here: upstream unavailable (503) |
| -32012 | agave: scan error | here: a scan result over the 10,000-account cap (200). Narrow the filters; never retry unchanged |

### JavaScript clients

Fetch wrapper (Node 18+, no dependencies). It honors `retry-after-ms` and retries only what waiting can fix:

```js
// carbium-rpc.mjs
const ENDPOINT = "https://services.carbium.sh";
const KEY = process.env.CARBIUM_KEY; // full raw key, c_serv_...
let nextId = 0;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class RpcError extends Error {
  constructor(http, error) {
    super(`${error.code}: ${error.message}`);
    this.http = http;
    this.code = error.code;
    this.data = error.data;
    this.reason = error.data?.reason; // set only on door refusals
  }
}

function delayMs(res, attempt) {
  const ms = Number(res.headers.get("retry-after-ms"));
  if (ms > 0) return ms;
  const s = Number(res.headers.get("retry-after"));
  if (s > 0) return s * 1000;
  return Math.min(200 * 2 ** attempt, 5000);
}

// write: true for sendTransaction / simulateTransaction: never auto-retried on 5xx.
export async function rpc(method, params = [], { write = false, maxRetries = 5 } = {}) {
  const body = JSON.stringify({ jsonrpc: "2.0", id: ++nextId, method, params }); // method before params
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": KEY },
      body,
    });
    const j = await res.json().catch(() => ({ error: { code: -32700, message: `HTTP ${res.status}, non-JSON body` } }));
    if (!j.error && res.ok) return j.result;
    const e = j.error;
    const retry =
      (res.status === 429 && e.data?.retryable !== false) ||
      (!write && (res.status === 502 || res.status === 503 || (res.status === 504 && e.message !== "upstream_slow"))) ||
      (res.status === 200 && (e.code === -32004 || e.code === -32005 || e.code === -32014)) ||
      (res.status === 200 && e.code === -32602 && e.message?.startsWith("the walk read no history"));
    if (!retry || attempt >= maxRetries) throw new RpcError(res.status, e);
    await sleep(delayMs(res, attempt) + Math.floor(Math.random() * 250));
  }
}

// Batch: up to 100 calls, at most 2 permit methods, no scans or aggregates. Returns results or RpcError per element, in order.
export async function rpcBatch(calls) {
  const body = JSON.stringify(calls.map(([method, params = []], id) => ({ jsonrpc: "2.0", id, method, params })));
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": KEY },
    body,
  });
  const out = await res.json();
  if (!Array.isArray(out)) throw new RpcError(res.status, out.error); // whole-batch refusal, id null
  const byId = new Map(out.map((r) => [r.id, r]));
  return calls.map((_, id) => {
    const r = byId.get(id);
    return r?.error ? new RpcError(res.status, r.error) : r?.result;
  });
}

// examples
const slot = await rpc("getSlot", [{ commitment: "confirmed" }]);
const tx = await rpc("getTransaction", [sig, { encoding: "base64", maxSupportedTransactionVersion: 1 }]);
const owned = await rpc("getTokenAccountsByOwner", [owner, { mint }, { encoding: "jsonParsed" }]);
const pools = await rpc("getProgramAccounts", [
  "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
  { encoding: "base64", withContext: true, filters: [{ dataSize: 653 }, { memcmp: { offset: 101, bytes: mint } }] },
]);
```

Send and confirm (with the wrapper above; `wire` is your signed transaction as base64):

```js
const { value: { blockhash, lastValidBlockHeight } } = await rpc("getLatestBlockhash", [{ commitment: "confirmed" }]);
// ...build the transaction with `blockhash`, sign it, serialize it to base64 `wire`...
const send = () => rpc("sendTransaction", [wire, { encoding: "base64", skipPreflight: true, maxRetries: 0 }], { write: true });
const sig = await send();
for (;;) {
  const [st] = (await rpc("getSignatureStatuses", [[sig]])).value;
  if (st?.err) throw new Error("failed on chain: " + JSON.stringify(st.err));
  if (st?.confirmationStatus === "confirmed" || st?.confirmationStatus === "finalized") break;
  if ((await rpc("getBlockHeight", [{ commitment: "confirmed" }])) > lastValidBlockHeight) throw new Error("expired: rebuild with a fresh blockhash");
  await sleep(2000);
  await send().catch(() => {}); // same bytes, same signature: safe to rebroadcast
}
```

@solana/web3.js v1:

```js
import { Connection, PublicKey } from "@solana/web3.js";
const KEY = process.env.CARBIUM_KEY;
const connection = new Connection("https://services.carbium.sh", {
  commitment: "confirmed",
  httpHeaders: { "x-api-key": KEY }, // key stays out of the URL
  wsEndpoint: "wss://services.carbium.sh/?api-key=" + KEY, // web3.js derives ws from http, so set it
});
const slot = await connection.getSlot();
const info = await connection.getAccountInfo(new PublicKey("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"));
```

web3.js retries 429 on its own (500 ms doubling, ignoring Retry-After). Pass `disableRetryOnRateLimit: true` if you use your own backoff. For `getTransaction`/`getBlock` that can return version-1 transactions, use the raw `rpc()` above with `maxSupportedTransactionVersion: 1`; the SDK's typed decoders may reject version 1.

@solana/kit:

```js
import { createSolanaRpc, address } from "@solana/kit";
const rpc = createSolanaRpc("https://services.carbium.sh", { headers: { "x-api-key": process.env.CARBIUM_KEY } });
const slot = await rpc.getSlot({ commitment: "confirmed" }).send(); // bigint
const { value: lamports } = await rpc.getBalance(address("vines1vzrYbzLMRdu58ou5XTby4qAqVRLmqo36NKPTg")).send();
```

Kit returns u64 values as `bigint`. Kit builds `{id, jsonrpc, method, params}`, so the key order is already right.

### Agent checklist

1. Put `"method"` before `"params"`. Keep the body ≤ 50 KB and batches ≤ 100 calls with ≤ 2 permit methods.
2. Send `maxSupportedTransactionVersion: 1` on getTransaction and getBlock.
3. Scans: single request, `encoding: "base64"` or `"jsonParsed"`, narrow filters (at most 4, one dataSize), no `sortResults`, a 10,000-row cap, no paging.
4. Expect 503 with `Retry-After` on a cold getSupply/getLargestAccounts, and wait that long.
5. Branch on HTTP status, then `error.data.reason`, then `error.code`. Retry only 429s, the 5xx reads, agave's not-yet codes and getTransactionsForAddress's `-32602` `the walk read no history`, waiting `retry-after-ms`.
6. Never auto-retry a send on 5xx: check `getSignatureStatuses`, then rebroadcast the same bytes until the blockhash expires.
7. getSignaturesForAddress reaches back up to 30 days; getTransaction and getBlock end at the ledger floor. Read `getFirstAvailableBlock` instead of assuming older transactions exist.

