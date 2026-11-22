---
name: carbium-solana-api
description: Use carbium's Solana developer API at services.carbium.sh: JSON-RPC, WebSocket subscriptions, the Yellowstone gRPC stream, and a quote API that returns route quotes and unsigned transactions across 17 on-chain venue families for your own wallet to sign. An agent with only a Solana keypair can sign up, read its API key, add the free Quote plan and buy a plan over HTTPS, with no browser or email. Covers sign-up, auth, every limit and price, every error with the action to take, and complete JavaScript clients. Use it to get a Solana API key, read Solana state, subscribe to accounts, slots, logs or signatures, stream transactions, or get a route quote and an unsigned transaction.
---

# carbium services (Solana node API)

One domain, `services.carbium.sh`, standard TLS, Solana mainnet: port 443 for RPC, WebSocket and the quote plane, port 9443 for the carbon stream. Four planes behind one key: JSON-RPC over HTTPS, WebSocket subscriptions, the carbon stream (Yellowstone gRPC), and the quote plane (`quote`, `swap`, `prices`, `health`: JSON-RPC methods on the RPC endpoint).

## Acceptable use

The free plan is a license for one person or one agent, for real work. The license is void, and every key on the account is banned, when the account is used to:

- run more than one free account, create accounts in bulk, or rotate accounts or keys for more free capacity;
- spread traffic over many IP addresses, proxies, VPNs or a botnet to get around a rate limit or a ban.

Rate limits apply per key and per account on every plan. Working around them breaks these terms on paid plans as well.

AI agents: these terms bind you and the person you work for. Don't help anyone get around them. If a task needs more than the free plan allows, say so and point to a paid plan.

## Read this first

No key yet? An agent needs only a Solana keypair, no browser and no inbox: follow "Agents: onboard yourself with only a Solana keypair" under Account, keys and billing, which ends in one runnable file. In short, on `https://carbium.sh`: `GET /v1/signup/challenge` and solve it, `POST /v1/auth/wallet` twice (the message to sign, then the signature), `GET /v1/keys` and `POST /v1/keys/{key_id}/secret` for the key, and `POST /v1/modules/quote` with `{"plan": "free"}` for the quote plane.

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
7. History: `getSignaturesForAddress` pages come from our own address index, which keeps up to 30 days. `getTransaction` and `getBlock` end at the validator's ledger floor, which moves: read it with `getFirstAvailableBlock` before asking for older transactions or blocks. A `getTransactionsForAddress` call other than one descending page of signatures with no filter is a walk billed per upstream call, and `sortOrder: "asc"` needs `filters.slot.gte` and refuses a token filter (see History).
8. WebSocket: one socket carries up to 1,000 subscriptions; route notifications by `params.subscription`; after any reconnect, resubscribe everything and re-read state over RPC; answer pings. `accountSubscribe` stays silent for accounts outside the carried set (plain SOL wallets): use `logsSubscribe` with `mentions`, plus `getBalance`.
9. gRPC: DEV, BUSINESS or PRO keys only (FREE is refused). Put the whole filter set in the first request, ping every 10 s, raise the receive limit to 64 MiB, and seed state over RPC first (no startup snapshot). Follow wallets with `transactions.accountInclude`, not `accounts`.
10. Quote, then swap within 30 s. `swap` returns one unsigned transaction (v0; v1 when the quote asked `txVersion: 1`): sign it as `user_pubkey` only, never modify it, send it with `skipPreflight: true`, confirm with `getSignatureStatuses`. On expiry or an on-chain slippage failure (`Custom:6004`), quote again.
11. Quote-plane amounts are decimal strings in base units: use `BigInt`. Any `platformFee` is already inside `destAmountOut` and `minAmountOut`.
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


## RPC (JSON-RPC 2.0 over HTTPS)

Endpoint: `POST https://services.carbium.sh` (port 443). One request is one JSON object, or a JSON array of up to 100 objects for a batch. Every answer is JSON-RPC 2.0, and `id` echoes yours. "The door" below is the gateway at this address: it checks every call's key, rate and credits before anything serves it.

### Wire rules (follow all of them)

| Rule | Value | If broken |
|---|---|---|
| HTTP method | `POST` only. `GET`/`HEAD /livez` is the keyless health check (bodiless 204). Any other non-POST gets a bodiless 404. `OPTIONS` is the CORS preflight (204). | 404 or 405 |
| Credential | The full raw key (`c_serv_...`). Carriers, in the order the door reads them: `x-api-key` header, `authorization: Bearer <key>`, first path segment `https://services.carbium.sh/<key>`, query `?api-key=` / `?api_key=` / `?apiKey=`, then `x-token` header. Prefer the header. | 401 `-32001` |
| Body size | at most 50 KB (1 KB = 1,024 bytes) | HTTP 413, `-32600` `request body exceeds the byte cap` |
| Key order | `"method"` must come BEFORE `"params"` in each request object, and must sit within the first 1,024 bytes of the object. A single `"method"` key per object. | HTTP 400 `-32600` `params before method` / `method beyond position cap` / `duplicate method key` |
| `params` | A JSON array (positional), as agave expects. The only exceptions are `getPriorityFeeEstimate`, `qn_estimatePriorityFees`, `quote`, `swap` and `prices`, which take an object. | 200 `-32602` `invalid params` |
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
| getBlockProduction getBlockTime getInflationReward getLeaderSchedule getRecentPerformanceSamples getRecentPrioritizationFees getSignatureStatuses getSlotLeaders getPriorityFeeEstimate qn_estimatePriorityFees | 5 | 1 | 6 | 20 | 100 |
| getVoteAccounts | 50 | 0.1 | 0.6 | 2 | 10 |
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
| getLeaderSchedule getSlotLeaders getInflationReward | validator (1 permit) | 10 |
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
| Enhanced-transactions REST, Metis REST paths | absent | Read `getTransaction`, `getSignaturesForAddress` or `getTransactionsForAddress`. For push, use WSS, the gRPC stream or a webhook (see Webhooks). |

Vendor-compatible extras that ARE served (single requests only):
- `getPriorityFeeEstimate` (Helius shape). Params are `[{accountKeys?: string[] (≤128), transaction?: string, options?: {priorityLevel?: "Min"|"Low"|"Medium"|"High"|"VeryHigh"|"UnsafeMax", includeAllPriorityFeeLevels?: bool, recommended?: bool, lookbackSlots?: n (≤150), transactionEncoding?: "base58"|"base64"}}]`. It answers `{"priorityFeeEstimate":n,"priorityFeeLevels":{min,low,medium,high,veryHigh,unsafeMax}}` in micro-lamports per compute unit. The levels are percentiles 0/25/50/75/95/100. The default estimate is `medium`, and `recommended: true` returns `high`.
- `qn_estimatePriorityFees` (QuickNode shape). Params are `{last_n_blocks?, account?, api_version?}`. It answers `{context:{slot}, per_compute_unit:{extreme,high,medium,low,percentiles{25,50,75,95,99}}, per_transaction:{...}, recommended}`.
- Both fee methods are derived from this door's `getRecentPrioritizationFees` over up to 150 slots, cached 2 s. Bad params get 400 `-32602` with one of these messages: `params must be an object, or a one-element array holding one`, `accountKeys must be at most 128 base58 32-byte pubkeys`, `priorityLevel must be Min, Low, Medium, High, VeryHigh or UnsafeMax`, `this method is not batchable`.
- `getTransactionsForAddress` (Helius shape): see History.

### DAS: getAsset, getAssets, getAssetBatch, getAssetsByOwner, getAssetsByGroup, getAssetsByCreator, getAssetsByAuthority, searchAssets, getNftEditions, getTokenAccounts

The ten Digital Asset Standard methods are JSON-RPC calls on the RPC endpoint, `POST https://services.carbium.sh`, with the same key. Answers come from our own index of the chain's finalized state, in the field names and answer shapes of the Helius DAS API, so a DAS client switches by its URL alone: `https://services.carbium.sh/?api-key=<KEY>`, or the key in the `x-api-key` header.

#### Rules

1. Send the Helius field names. `options` and `displayOptions` are the same. A display flag at the top level of `params` is an unknown field. `getAsset` also takes `params: ["<id>"]`. An unknown field gets `-32602` `unknown field ..., expected one of ...`. With the Metaplex Umi DAS plugin (2.1.1), set `dasApi({ heliusCompatibility: true })`. Without it, the plugin's `getNftEditions` and `getTokenAccounts` send `mintAddress` and `ownerAddress`, and those calls are refused.
2. Page deep lists by cursor. Leave `page` out and pass the last answer's `cursor` until a page holds fewer than `limit` items. `cursor` goes alone. `before` and `after` set id bounds and can go together. None of the three goes with `page`, and without `page` only `sortBy` `id` works.
3. `limit` goes up to 1,000, the default. `page` starts at 1, and `page` × `limit` stays at or under 500,000. `sortBy` takes `id`, `created`, `updated`, `recent_action` or `none`, with `sortDirection` `asc` or `desc`, and defaults to `id` `desc`. `created` and `none` return id order, as the index holds no creation time. `updated` and `recent_action` sort by the newest slot that wrote the asset.
4. In a list answer, `total` counts the items on this page. `showGrandTotal` adds `grand_total`, the full count, on the `getAssetsBy*` lists and `searchAssets`, but not on one that includes fungibles; `getTokenAccounts` and `getNftEditions` carry none. `cursor` is the last item's id. It is absent on an empty page, in page mode (the answer carries `page`) and when you paged by `before` or `after`. `last_indexed_slot` is the newest finalized slot the index holds.
5. `getAssets` and `getAssetBatch` are one call. They take at most 1,000 `ids`, repeats allowed, and return a positional array with `null` where an id is not held. An id that is not a valid address refuses the whole call with `-32602` `Pubkey Validation Err: <v> is invalid`.
6. Batch DAS calls only with each other. A DAS batch answers HTTP 200 with an array in request order, each element with its own `id` and its own result or error. A batch takes all its cells at once, one per call plus one for each 4 KB of body past the first, so a full batch of 100 calls fits the 150-cell burst. It holds one place in flight, and its calls run one after another under one 5 s limit. A call still waiting at the limit comes back as `-32011` `das upstream timed out`, uncharged: send it again. A batch that mixes DAS with any other served method gets 400 `-32602` `this method is not batchable`, and a batch that holds an unknown name, a proof or signature method included, gets one 200 `-32601` `method not found` for the whole batch.
7. `getAssetsByGroup` does not read `groupKey`: `groupValue` names a collection whatever the key says. The same holds for a `searchAssets` `grouping` in any of its forms: `["collection", v]`, `{"collection": v}` or `{"group_key": k, "group_value": v}`.
8. `searchAssets` serves `ownerAddress`, `creatorAddress` with `creatorVerified`, `authorityAddress`, `grouping`, `interface`, `tokenType`, `frozen`, `delegate` and `burnt`. `tokenType` needs `ownerAddress` beside it and goes with neither `interface` nor `compressed`. `delegate` needs `ownerAddress` or `grouping`. Every other filter is refused by name with `-32602` ``this index does not serve the `<name>` filter``: `negate` (other than `false`), `conditionType` (other than `"all"`), `ownerType`, `supply`, `supplyMint`, `compressible`, `royaltyTargetType`, `royaltyTarget`, `royaltyAmount`, `jsonUri`, `not`, `name`, `collections`, `createdAt`, `collectionNft`, `isAgent`, `agentToken` and `assetSigner`. Apply those on your side.
9. A `searchAssets` with no `ownerAddress`, `authorityAddress`, `creatorAddress` or `grouping` reaches its first 10,000 items by `page`; go on by `cursor`. It also refuses `showGrandTotal`, `sortBy` `updated` or `recent_action`, `burnt: true` and `interface` `MplCoreGroup`. Name one of the four to use them.
10. `showNativeBalance` on `getAssetsByOwner`, and on `searchAssets` with `ownerAddress`, adds `nativeBalance: {"lamports": <balance>}`, with no `price_per_sol` or `total_price`. When the balance read takes more than 1 s, or a batch's 5 s limit runs out first, the answer comes without it. `showFungible` (getAssetsByOwner only; on searchAssets use `tokenType`), `showZeroBalance`, `showCollectionMetadata` and `showGrandTotal` change the answer, and `showUnverifiedCollections` adds `verified: true` to each grouping. `showRawData`, `requireFullIndex`, `showSystemMetadata`, `showClosedAccounts` and `showInscription` are accepted and change nothing.
11. `getTokenAccounts` takes `owner`, `mint` or both, sorts by account address, and its `cursor` is the last account's address. With `mint` alone it lists any number of holders by `cursor`, and `page` reaches the first 10,000. An owner with more than 10,000 token accounts is refused with `-32012`, and so is a fungible list of that owner (`showFungible`, or `searchAssets` `tokenType` `all` or `fungible`). Name both an owner and a mint instead.
12. `getNftEditions` takes `mint`, `limit` and `page` only, and sorts by edition number. A `cursor` is refused as an unknown field, so page by `page`. `max_supply` is `null` when the supply is unlimited.

#### Limits

Each DAS call costs 1 credit and 1 cell, plus 1 cell for each 4 KB of body past the first, at 3 / 15 / 75 / 150 req/s (FREE / DEV / BUSINESS / PRO), counted per account, so all of an account's keys share one bucket, with a 150-cell burst on every plan. Each key holds 1 / 2 / 4 / 8 DAS calls in flight (FREE / DEV / BUSINESS / PRO), and a batch holds one place. A call over the rate waits for its turn when that comes within 1 s, and a call with no place in flight waits up to 3 s. One still not admitted gets 429.

| Size or time | Limit |
|---|---|
| Request body | 50 KB |
| Batch | 100 calls |
| `limit` | 1,000, also the default |
| `ids` on getAssets and getAssetBatch | 1,000 |
| `page` × `limit` | 500,000; 10,000 on a searchAssets with no owner, creator, authority or grouping, and on getTokenAccounts by mint |
| Token accounts per owner | 10,000 |
| Answer | 8 MiB per call, or per whole batch |
| Time | 5 s per call, and one 5 s limit for a whole batch |

#### Billing

Each served call costs 1 credit, and each served element of a batch costs 1, so a batch of three costs 3. These cost nothing: an error answer, a batch element that fails, times out or goes over the answer cap, a call refused before it runs (key, rate, credits, size) and the `nativeBalance` read. Every admitted call spends its rate cell, one that ends in an error included.

#### Coverage

The index holds:
- Token Metadata NFTs (`V1_NFT`), programmable NFTs (`ProgrammableNFT`), fungibles (`FungibleToken`, `FungibleAsset`), Core assets, collections and groups (`MplCoreAsset`, `MplCoreCollection`, `MplCoreGroup`), and mints with no metadata account (`Custom`), on SPL Token and Token-2022, the Token-2022 metadata extension included. Mint extensions appear in `mint_extensions`.
- For Core: plugins, external plugins, `mpl_core_info` (`num_minted`, `current_size`), parent groups and `asset_signer`.
- Editions. A master reports its print supply and maximum, and a print its `edition_number` and `master_edition_mint`.
- Burnt assets. `getAsset` answers a burnt asset that has a metadata account with `burnt: true`, and a burnt mint with none answers not found. The `getAssetsBy*` lists leave burnt assets out, except burnt Core assets. `searchAssets` lists them unless `burnt` picks one side, except a token NFT burnt before the index began with no holder seen, which it never lists.
- Mints with no metadata account. `getAsset` answers one with an empty `content`, as `Custom`, or as `FungibleToken` or `FungibleAsset` for a fungible mint. It appears in lists only among an owner's held fungibles. It shows the supply, decimals and extensions on chain. `getAsset` answers its `ownership.owner` as `""`, and an owner's held-fungibles list shows that owner and the state of their account.

The index does not hold:
- Compressed NFTs. They are absent from every answer. `compressed: true`, `tree` (with `ownerAddress` or `grouping`) and `tokenType` `compressedNft` (with `ownerAddress`) answer an empty page. The proof and signature methods (`getAssetProof`, `getAssetProofBatch`, `getAssetProofs`, `getAssetSignatures`, `getSignaturesForAsset`) answer `-32601`.
- The off-chain JSON document. `content.json_uri` is its address only and is never fetched, so `content.files` is `[]`, `content.links` is `{}`, and `content.category` and the off-chain keys are absent. Fetch the document yourself when you need it.
- Prices. `token_info` carries no `price_info`.
- These fixed fields: `uses` is `null`, `royalty.target` is `null`, `royalty.locked` is `false`, and `compression` reads as uncompressed. A collection grouping appears only when the collection is verified. Plain list items leave out `mint_authority` and `freeze_authority`, which `getAsset` carries.
- On `searchAssets`, `interface` `V1_PRINT` or `LEGACY_NFT` matches nothing.

#### Errors

Errors from the index come with HTTP 200 and their own code. A call refused before it runs comes with its own HTTP status. Decide by the code: the message can carry your own values, and an index error that arrives with no message reads `das upstream refused the request` under the same code.

| HTTP | Code | Message | What to do |
|---|---|---|---|
| 200 | `-32000` | `Database Error: RecordNotFound Error: Asset Not Found` | The index holds no such asset (getAsset) or no such master edition (getNftEditions). Do not retry at once. |
| 401, 403 | `-32001` | the key messages | Fix the key, its scope or the calling address. Do not retry. |
| 402 | `-32002` | `credits exhausted` | Buy a plan or upgrade. Do not retry. |
| 429 | `-32005` | `rate limit exceeded` (`RATE_LIMITED`) | Wait `retry-after-ms`, then retry. Lower your rate if it repeats. |
| 429 | `-32005` | `DAS lane capacity exceeded: das_lane` (`SLOT_CAP_EXCEEDED`) | Too many calls in flight. Wait `retry-after-ms`, retry, and send fewer at once. |
| 502 | `-32011` | `das upstream unreachable`, `das upstream error`, `das upstream read failed` | Retry with backoff. |
| 502 | `-32011` | `das upstream response too large` | The answer is over 8 MiB. Ask for a smaller `limit` or fewer `ids`, or split the batch. Do not resend it unchanged. |
| 503 | `-32011` | `compat verbs not initialised` | Retry with backoff a few times, then stop. |
| 504, or 200 inside a batch | `-32011` | `das upstream timed out` | No answer within 5 s. Retry. For a list, ask for a smaller `limit`. In a batch, send that element again. |
| 200 | `-32012` | `token accounts refused: the subject holds more than the hot store's 10000-account cap; name an owner and a mint` | Name both an owner and a mint. Do not retry. |
| 200 | `-32012` | `showFungible refused: the owner holds more than the hot store's 10000 token accounts; list without it` | On getAssetsByOwner, list without `showFungible`. On searchAssets, ask for `tokenType` `nonFungible`. |
| 200 | `-32021` | `index is behind the chain, retry` | The index trails the chain by more than 32 slots. Retry with backoff. |
| 200 | `-32022` | `index is repairing a gap, retry later` | Retry later with long waits. Do not loop. |
| 200 | `-32023` | `index is not built yet` | Retry later. |
| 200 | `-32024` | `token accounts refused: the hot store deferred the read; retry` | Retry with backoff. |
| 200 | `-32026` | `index is busy, retry`, `hot store is busy, retry` | Retry with jittered backoff. |
| 413 | `-32600` | `request body exceeds the byte cap` | The body is over 50 KB. Split it. |
| 400 | `-32600` | `batch exceeds the cardinality cap` | The batch has more than 100 calls. Split it. |
| 400 | `-32600` | `malformed json-rpc body`, `duplicate method key`, `params before method`, `method beyond position cap` | Fix the body. Put `"method"` before `"params"`, within the first 1 KB. |
| 200 | `-32601` | `method not found` | The method name is unknown, the proof and signature methods included. Do not retry. |
| 400 | `-32602` | `this method is not batchable` | Batch DAS calls only with DAS calls. |
| 200 | `-32602` | `missing field ...`, `unknown field ..., expected one of ...`, `invalid type: ...`, `invalid value: ...`, `unknown variant ...`, `Pubkey Validation Err: <v> is invalid`, `Validation Error: Invalid pubkey <v>`, `Cursor Validation Err: <v> is invalid`, `invalid params: ...`, `Validation Error: Must provide either 'owner' or 'mint'`, `Validation Error: Must provide 'mint'` | Fix the params. Do not retry. |
| 200 | `-32602` | `Pagination Error. Limit should not be greater than 1000.`, `Pagination Error. Only one pagination parameter supported per query.`, `Pagination Error. No Pagination Method Selected.` (`page: 0`), `Pagination Sorting Error. Only sorting based on id is supported for this pagination option.`, `Batch Size Error. Batch size should not be greater than 1000.`, `Paginating beyond 500000 items is not supported. ...`, `Paginating beyond 10000 items of a search with no ... is not supported. ...`, `Paginating beyond 10000 token accounts of a mint is not supported. ...` | Fix the paging. Past a window, go on by `cursor`. |
| 200 | `-32602` | ``this index does not serve the `<name>` filter``, ``this index serves the `delegate` filter only with `ownerAddress` or `grouping` ``, ``this index serves <what> on searchAssets only with `ownerAddress`, `authorityAddress`, `creatorAddress` or `grouping` ``, and the `token_type` and `tree` validation errors | Drop the filter and apply it on your side, or name an owner, creator, authority or grouping. |
| 200 | `-32603` | `the index could not finish this read in time` | Narrow the request with a smaller `limit` or a named owner, creator, authority or grouping, then send it. |
| 200 | `-32603` | `Internal error`, `das upstream refused the request` | Retry with backoff a few times, then stop. |
| 200 | `-32700` | `Parse error` | Send valid JSON-RPC 2.0: an object or array, `"jsonrpc": "2.0"`, an `id`, and params as an object or array. |

#### Quick start

```bash
URL="https://services.carbium.sh"   # CARBIUM_KEY holds the full raw key
# one asset
curl -s "$URL" -H 'content-type: application/json' -H "x-api-key: $CARBIUM_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getAsset","params":{"id":"<ASSET_ID>"}}'

# a wallet's assets, page by page
curl -s "$URL" -H 'content-type: application/json' -H "x-api-key: $CARBIUM_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getAssetsByOwner","params":{"ownerAddress":"<OWNER>","limit":1000}}'
# next page: the same body plus "cursor":"<result.cursor>"; stop at a page of fewer than 1000 items

# a search anchored on an owner
curl -s "$URL" -H 'content-type: application/json' -H "x-api-key: $CARBIUM_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"searchAssets","params":{"ownerAddress":"<OWNER>","tokenType":"nonFungible","limit":100}}'

# every holder of a token, page by page
curl -s "$URL" -H 'content-type: application/json' -H "x-api-key: $CARBIUM_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getTokenAccounts","params":{"mint":"<MINT>","limit":1000}}'
# next page: the same body plus "cursor":"<result.cursor>"

# a DAS batch of two: HTTP 200, an array in request order
curl -s "$URL" -H 'content-type: application/json' -H "x-api-key: $CARBIUM_KEY" \
  -d '[{"jsonrpc":"2.0","id":1,"method":"getAsset","params":{"id":"<ASSET_ID>"}},
       {"jsonrpc":"2.0","id":2,"method":"getAssetsByGroup","params":{"groupKey":"collection","groupValue":"<COLLECTION>","limit":10}}]'
```

#### A client with retries (Node 18+, global fetch)

```js
// carbium-das.mjs
const URL = "https://services.carbium.sh";
const KEY = process.env.CARBIUM_KEY; // full raw key

// Codes that waiting can fix. -32022 and -32023 need a later run: do not loop on them. Every other code is final, and so are
// two messages that ask for a smaller request.
const RETRY = new Set([-32005, -32011, -32021, -32024, -32026, -32603]);
const LATER = new Set([-32022, -32023]);
const NARROW = new Set(["das upstream response too large", "the index could not finish this read in time"]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class DasError extends Error {
  constructor(status, e) {
    super(`HTTP ${status} ${e?.code} ${e?.message}`);
    Object.assign(this, { status, code: e?.code, later: LATER.has(e?.code) });
  }
}

export async function das(method, params, { maxAttempts = 4 } = {}) {
  const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }); // method before params
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(URL, { method: "POST", headers: { "content-type": "application/json", "x-api-key": KEY }, body });
    const j = await res.json().catch(() => ({ error: { code: -32700, message: `HTTP ${res.status}, non-JSON body` } }));
    if (!j.error) return j.result;
    const e = j.error;
    const retry = RETRY.has(e.code) && !NARROW.has(e.message);
    if (!retry || attempt >= maxAttempts) throw new DasError(res.status, e);
    const hint = Number(res.headers.get("retry-after-ms")) || Number(res.headers.get("retry-after")) * 1000 || 0;
    await sleep(Math.max(hint, Math.min(250 * 2 ** (attempt - 1), 4000)) + Math.random() * 250);
  }
}

// Every item of a list, by cursor. getTokenAccounts answers token_accounts; the other lists answer items.
export async function* walk(method, params, limit = 1000) {
  let cursor;
  for (;;) {
    const r = await das(method, { ...params, limit, ...(cursor && { cursor }) });
    const rows = r.items ?? r.token_accounts;
    yield* rows;
    if (rows.length < limit || !r.cursor) return;
    cursor = r.cursor;
  }
}

// examples
const asset = await das("getAsset", { id: "<ASSET_ID>" });
for await (const a of walk("getAssetsByOwner", { ownerAddress: "<OWNER>" })) console.log(a.id, a.interface);
let holders = 0;
for await (const t of walk("getTokenAccounts", { mint: "<MINT>" })) if (t.amount > 0) holders++;
```

#### How we test it

1. Pick real subjects of every kind the index holds: Token Metadata NFTs, programmable NFTs, master and print editions, Core assets and collections, Token-2022 mints with extensions, and fungibles. Add wallets, creators, authorities and collections to list. Our two sets hold 1,251 requests across the ten methods, naming 1,000 assets, and 167 collection requests, with paging, display options and bad inputs.
2. Send every request to the reference DAS API once, one call at a time, and keep the answers.
3. Send the same bodies to `https://services.carbium.sh`, one call at a time. Compare every field exactly by its JSON path, leaving out `last_indexed_slot` and `price_info` on both sides. Compare lists as the set of ids (`address` for token accounts, `mint` for editions) and their order. Compare errors by code, and by message with your own values cut out.
4. Set aside the fields of the off-chain document behind `json_uri`, since the index does not fetch it. For any other difference, read the account on chain at `finalized` to see which answer the chain holds.
5. Walk whole collections with `getAssetsByGroup` (`limit` 1000, `sortBy` id ascending) on both sides. Then ask for each collection's hashlist by id through `getAssetBatch`, 1,000 ids at a time, and compare the id sets. An id only the reference returns should be one it marks `burnt: true`.
6. Walk every holder of a token with `getTokenAccounts` by `mint` and `cursor`, on both sides. Read any account found on one side only with `getMultipleAccounts` at `finalized`. It should be closed or empty.
7. Send the exact bodies the Metaplex Umi DAS plugin 2.1.1 and the Helius SDK 3.5.0 send, the request bodies from the reference docs, 21 bad inputs and a batch. Compare HTTP status, error code and message, answer shape and row count.
8. Compare `last_indexed_slot` with `getSlot` at `finalized`, many times over, to see how far the index trails the chain.

Results, measured 2026-11-21:
- 10,382 of 10,386 compared assets (99.96%) equal on every on-chain field.
- Every live asset found and none extra across three Core collections walked whole (5,561, 2,222 and 374 assets) and a 6,202-asset hashlist asked by id.
- Every holder with a balance returned once, for a token with more than 11,500 token accounts.
- The same status, code, message and answer shape on every request form of the ten methods, with `nativeBalance` in lamports.
- The index within 16 slots of the finalized chain on 99.99% of 101,252 readings over six hours.

#### Common mistakes

- Paging deep with `page`. Past 500,000 items it is refused, and past 10,000 on an unanchored searchAssets or on a mint's token accounts. Walk by `cursor`.
- Reading `total` as the full count. It counts this page only. Ask for `showGrandTotal`.
- Expecting images, attributes, `content.files` or `content.links` from the off-chain JSON. Fetch `content.json_uri` yourself.
- Sorting by `created` and expecting creation order. It returns id order.
- Mixing DAS and other RPC methods in one batch.
- Using the Umi DAS plugin without `heliusCompatibility: true`.
- Retrying a `-32602`, or looping on `-32022`.
- Sending more calls at once than the plan's in-flight cap allows. Queue them per key.

#### Agent checklist

- Call `https://services.carbium.sh` with the full key in `x-api-key` or `?api-key=`.
- Send the Helius field names, and put `"method"` before `"params"`.
- Walk lists by `cursor` with `limit` 1000 until a page comes back short.
- Keep calls in flight per key within your plan; a batch counts as one. Batch DAS calls only with each other, up to 100 a batch.
- Retry `-32005`, `-32011`, `-32021`, `-32024`, `-32026` and `-32603` with jittered backoff, and honour `retry-after-ms`; narrow the request instead on `response too large` and `could not finish this read in time`. Retry `-32022` and `-32023` later. Stop on every other code.
- Apply unserved `searchAssets` filters on your side. Name an owner, creator, authority or grouping before you use `showGrandTotal`, `burnt: true`, `interface` `MplCoreGroup` or the `updated` and `recent_action` sorts.
- Fetch off-chain JSON yourself, and expect no prices and no compressed NFTs.
- Budget 1 credit per served call.

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
- At most 2 elements per batch may hold a validator permit. The permit methods are `getAccountInfo`, `getMultipleAccounts`, `getTokenAccountBalance`, `getTokenSupply`, `getTransaction`, `getSignaturesForAddress`, `getTransactionsForAddress`, `getBlocks`, `getBlocksWithLimit`, `getLeaderSchedule`, `getSlotLeaders` and `getInflationReward`. A third returns 429 `-32005` `blocking-slot capacity exceeded: external pool` (`SLOT_CAP_EXCEEDED`, `retryable: true`). For a batch this refusal is permanent: split it and do not retry it as is.
- Never batch: `getProgramAccounts`, `getTokenAccountsByOwner`, `getTokenAccountsByDelegate`, `getSupply`, `getLargestAccounts`, `getTransactionsForAddress`, `getPriorityFeeEstimate`, `qn_estimatePriorityFees`, `quote`, `swap`, `prices`, `health`.
- Good batch material: the 1-cell and 5-cell reads plus up to 2 permit methods.

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
| 429 | -32005 | `blocking-slot capacity exceeded: <external\|compute\|scan\|get_block> pool`, `scan-index lane capacity exceeded: chot_lane`, `DAS lane capacity exceeded: das_lane` | SLOT_CAP_EXCEEDED | Lower your concurrency and retry after 100 ms. A batch with more than 2 permit methods never fits: split it. |
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

## WebSocket (JSON-RPC 2.0 subscriptions over WSS)

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

## Carbon stream (Yellowstone gRPC)

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
- **No startup snapshot.** An account stream sends only writes made after it opens. Load the current state with RPC `getMultipleAccounts` (up to 100 keys per call on DEV and BUSINESS, 300 on PRO; see Point reads in the RPC section) first. Then apply stream updates, keeping the highest `(slot, writeVersion)` per pubkey.
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

### Robust client (Node 18+, `@triton-one/yellowstone-grpc` v8)

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

## Webhooks (a signed HTTPS POST per finalized transaction)

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

## Quote and swap (`quote`, `swap`, `prices`, `health`)

The quote plane uses JSON-RPC 2.0 over HTTPS at `POST https://services.carbium.sh`, on the same endpoint and with the same key carriers as RPC. It has four verbs: `quote`, `swap`, `prices` and `health`. There are no REST paths: `POST /quote` is not an endpoint, so put the method name in the JSON body.

Rules an agent must follow:
- Send one quote-plane call per HTTP request. A batch that contains `quote`, `swap` or `prices` is refused whole with HTTP 400 `-32600 "quote is not batchable"`, and each element of the batch gets that error. A batch that contains `health` is refused with HTTP 400 `-32602 "quote is not batchable"` and `id: null`.
- Params are snake_case, except `txVersion` and `swapTag`. You can send them positionally (`"params":[{...}]`) or by name (`"params":{...}`). Results are camelCase.
- Every amount is a decimal string in base units (atoms or lamports). Parse amounts with `BigInt`, never `Number`.
- Do not treat HTTP 200 as success: several answers about the pair itself (no route, no live pool, an input larger than the pool can pay, some swap refusals) come back as HTTP 200 with an `error`. Read `error.code` and the HTTP status together: `-32093` means quote again at HTTP 200 and retry with backoff at HTTP 503.
- An unknown parameter name is refused and never ignored silently. The one exception is `fft`, in any letter case, which is accepted and dropped by both `quote` and `swap`.

### `quote`: params

| Param | Type | Rule |
|---|---|---|
| `src_mint` | base58 string | The input mint. Must decode to exactly 32 bytes. |
| `dst_mint` | base58 string | The output mint. Must differ from `src_mint`. |
| `amount_in` | u64, as a JSON number or a decimal string | The input amount, in base units. Must be non-zero. Use a string above 2^53. |
| `slippage_bps` | integer 0 to 5000 | Sets `minAmountOut`: 50 means 0.5%. Values above 5000 are refused. |
| `dex` (optional; `dexes` is an alias) | a label string, or an array of 1 to 17 labels | Restricts the quote to these venue families, one hop from `src_mint` to `dst_mint` (it may split across their pools); a pair with no such route answers `-32051` with why `no_route_in_pinned_dex`, never another venue's route. Each label is at most 32 characters from `[A-Za-z0-9._-]` and matches case-insensitively. Send `dex` or `dexes`, never both. Omit it to search every family, multi-hop and split. |
| `txVersion` (optional) | number, 0 or 1 | 0 (default): a v0 transaction with address lookup tables, at most 1,232 B. 1: a v1 transaction with every address inline (no lookup tables), at most 4,096 B, for routes v0 cannot fit. v1 lifts the byte limit, not the 64-account limit: a route that needs more than 64 accounts is refused in both versions. The swap built from the quote is the version the quote names. v1 is built for every family; it has not yet been landed on `r-cpmm`, `m-dbc` or `m-dbc-hook` routes. Any other value is refused: `-32602` `txVersion must be 0 or 1`. |
| `swapTag` (optional) | number, 0 or 1 | 0 (default): the router picks the form of the swap instruction. 1: the plain form: its data starts with tag `0x01` and has no middle block, and each middle token account is created by its own idempotent instruction, paid and owned by your wallet and left open. Route, price, fee and floor are the same. v0 only: with `txVersion: 1` the quote is refused `-32602` `the quote upstream refused the request` with `error.data.code` `swap_tag_format`. The swap built from the quote is the tagged one, and the quote and the swap both answer `swapTag: 1`. Any other value is refused: `-32602` `swapTag must be 0 or 1`. |

Wrapped SOL is `So11111111111111111111111111111111111111112`. Use it for SOL at either end.

### Venue families (`dex` labels)

| Label | Venue |
|---|---|
| `r-amm` | Raydium AMM v4 |
| `r-cpmm` | Raydium CPMM |
| `r-clmm` | Raydium CLMM |
| `r-lpad` | Raydium LaunchLab |
| `o-whirlpool` | Orca Whirlpool |
| `o-orca-v1` | Orca legacy pools (token-swap v1) |
| `o-orca-v2` | Orca legacy pools (token-swap v2) |
| `m-dlmm` | Meteora DLMM |
| `m-damm` | Meteora DAMM v1 |
| `m-damm-v2` | Meteora DAMM v2 |
| `m-dbc` | Meteora Dynamic Bonding Curve |
| `m-dbc-hook` | Meteora DBC, Token-2022 transfer-hook mints |
| `pump-curve` | pump.fun bonding curve |
| `pump-amm` | PumpSwap |
| `manifest` | Manifest |
| `pancakeswap-v3` | PancakeSwap v3 |
| `byreal` | Byreal CLMM |

Pin one family with `"dex":"o-whirlpool"` or several with `"dex":["o-whirlpool","r-clmm"]`. The same labels appear in `routePlan[].swapInfo.label`. A pin takes only the labels the `-32602` `dex must name venue families: …` message lists; any other label is refused before the search. An unpinned quote searches every family the engine serves, so `routePlan` can name a family you cannot pin yet.

Bonding-curve pools: `quote` serves a token on its curve and, after it migrates, on its pool (for example `pump-curve`, then `pump-amm`); no extra parameter is needed. When a curve has just completed, `quote` waits briefly for the pool that replaces it (250 ms on `pump-curve`, 600 ms on `r-lpad` and `m-dbc` curves) and answers from that pool. If the pool is not serving yet, `quote` answers HTTP 503 `-32011` `quote upstream stale` with `error.data.why` = `graduating`. Nothing retries for you: retry after `Retry-After`. A `dex` pin to `pump-curve` on a migrated token answers `-32051` with why `no_route_in_pinned_dex`: drop the pin, or pin `pump-amm`. A chain of pump hops (a PumpSwap pool or a SOL curve, then curves quoted in each other) is quoted and lands as ONE pump multi_hop_swap step: `routePlan` still lists each hop, with the one-step amounts (the protocol fee at the SOL-end hop, nothing on the curves in between, and the creator fee at the hop farthest from SOL (the last hop when SOL is the input, the first when SOL is the output), plus the LP fee when that hop is a `pump-amm` pool).

### `quote`: result

| Field | Type | Meaning |
|---|---|---|
| `srcAmountIn` | string | The input amount, gross: what the wallet is debited. On a partial fill it is the part that fills. |
| `destAmountOut` | string | The amount received, net of `platformFee` and of any Token-2022 transfer fee on the route's mints. Do not subtract that fee again. |
| `minAmountOut` | string | The floor `swap` lays, exactly, rounded down. When the fee comes off the input (SOL in, SOL to USDC or USDT included, or a route with no SOL end whose destination is not USDC or USDT) it is `floor(destAmountOut × (10000 − slippageBps) / 10000)`. When the fee comes off the output (SOL out, or USDC or USDT out with no SOL in) the slippage is taken on the gross output (`destAmountOut + platformFee.amount`), `G = floor(gross × (10000 − slippageBps) / 10000)`, then the fee, `G − floor(G × feeBps / 10000)`. |
| `slippageBps` | number | Your slippage. |
| `swapMode` | string | Always `"BaseIn"` (exact in). |
| `inputMint`, `outputMint` | base58 | The pair. |
| `routePlan[]` | array | One entry per leg: `{hop, percent, swapInfo:{ammKey, label, inputMint, outputMint, inAmount, outAmount}}`. `hop` is the depth: 0 is the first stage, 1 spends the output of hop 0, and so on. `percent` is a string giving that leg's share of its hop's input. Legs in the same hop are a split. |
| `quoteId` | 32 lowercase hex | The handle `swap` takes. It is valid for 30 s, can be evicted sooner under load and is forgotten when the service restarts. You can reuse it within 30 s, for example to rebuild with a different priority price. |
| `platformFee` | object, present only when a fee is charged | `{amount, feeBps, mint}`: the router fee, already inside `destAmountOut` and `minAmountOut` (see On-chain router fee). |
| `txVersion` | number, present only on a v1 quote | `1` when the quote asked `txVersion: 1`: the swap built from it is v1. Absent on v0. |
| `swapTag` | number, present only on a tagged quote | `1` when the quote asked `swapTag: 1`: the swap built from it is the plain form. Absent otherwise. |
| `partial`, `requestedAmountIn` | `true`, string; present only on a partial fill | Only part of your `amount_in` can fill: an input past what its one pool can pay (any venue family; the part is that bound less 3%), or a route with SOL in that cannot fill it whole (why `first_hop_unfilled`; asked again at half the amount, up to 6 times, down to 1/64, and the first part that fills is served). `srcAmountIn` is that part, `requestedAmountIn` is what you asked for, and `swap` builds the part. |

Live example (2026-10-09), quoting 0.01 SOL to USDC:
```json
{"srcAmountIn":"10000000","destAmountOut":"1092857","minAmountOut":"1087392","slippageBps":50,"swapMode":"BaseIn",
 "inputMint":"So11111111111111111111111111111111111111112","outputMint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
 "routePlan":[{"hop":0,"percent":"100","swapInfo":{"ammKey":"HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR","label":"m-dlmm",
   "inputMint":"So11111111111111111111111111111111111111112","outputMint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
   "inAmount":"9995000","outAmount":"1092857"}}],
 "quoteId":"4579cc7e1b1ec3ead63e9c1cbbfe8e19",
 "platformFee":{"amount":"5000","feeBps":5,"mint":"So11111111111111111111111111111111111111112"}}
```

### On-chain router fee (`platformFee`)

The router fee is 5 bps (0.05%): an on-chain fee inside the transaction your software signs and sends. With SOL at either end it is taken in SOL, off the input on SOL in and off the output on SOL out. Otherwise it is taken in USDC/USDT from the output when the destination is USDC or USDT, else in the input token before the swap; `destAmountOut` is what you receive.

| Route | Fee | How the quote shows it |
|---|---|---|
| SOL in (`src_mint` = wSOL) | `floor(amount_in × 5 / 10000)` lamports, taken before the route | `srcAmountIn` = `amount_in` (gross). The hop-0 `inAmount` values add up to `amount_in − fee`. Example: 10,000,000 in gives a fee of 5,000 and the leg routes 9,995,000. |
| SOL out (`dst_mint` = wSOL) | `floor(gross_out × 5 / 10000)` lamports | `destAmountOut` and `minAmountOut` are net of the fee. The last leg's `outAmount` is gross. Example: leg out 9,144,480, fee 4,572, `destAmountOut` 9,139,908. |
| USDC or USDT out (no wSOL at either end) | `floor(gross_out × 5 / 10000)` in `dst_mint` | `platformFee.mint` is `dst_mint`; `destAmountOut` and `minAmountOut` are net of the fee. Example: 5 USDC -> USDT, gross 5,004,236, fee 2,502, `destAmountOut` 5,001,734. |
| Any other token route (no wSOL at either end, destination not USDC or USDT) | `floor(amount_in × 5 / 10000)` in `src_mint`, taken before the route | `platformFee.mint` is `src_mint`. `srcAmountIn` = `amount_in` (gross); the hop-0 `inAmount` values add up to `amount_in − fee`. |

The fee is 0, and the quote carries no `platformFee`, in two cases: when it rounds down to 0 atoms (a fee base under 2,000 atoms at 5 bps: `amount_in` when the fee comes off the input, the gross output when it comes off the output), and on a route with no wSOL at either end and a destination other than USDC or USDT, when the input is a Token-2022 mint with a transfer hook program set (an empty hook still pays), frozen by default, or non-transferable. With SOL at either end, or USDC or USDT out, such a token still pays the fee.

The fee is paid inside the router instruction of the built transaction, at the quoted bps; there is no separate transfer instruction for it. On SOL out, and on USDC or USDT out with no SOL in, it is a share of the output the route actually delivers, so a fill better than the quote pays slightly more than `platformFee.amount` and a worse one (slippage, or a reroute) slightly less.

### `quote`: errors

| HTTP | code | message (exact) | What to do |
|---|---|---|---|
| 400 | -32602 | `params must carry src_mint, dst_mint, amount_in, slippage_bps` | Fix the request. |
| 400 | -32602 | `src_mint and dst_mint must be base58 32-byte pubkeys` | Fix the mints. |
| 400 | -32602 | `src_mint and dst_mint must differ` | Fix the pair. |
| 400 | -32602 | `amount_in must be a non-zero u64 in base units` | Send base units, greater than 0 and at most 2^64−1. |
| 400 | -32602 | `slippage_bps must be 0 to 5000` | Fix the slippage. |
| 400 | -32602 | `params accepts only src_mint, dst_mint, amount_in, slippage_bps, txVersion, swapTag, and one of dex or dexes` | Remove the extra params (other providers' `onlyDirectRoutes` and similar are refused). |
| 400 | -32602 | `dex must be a venue-family label, or an array of them, matching [A-Za-z0-9._-]` | Fix the shape: 1 to 17 labels, each at most 32 characters. |
| 400 | -32602 | `dex must name venue families: r-amm, r-cpmm, r-clmm, r-lpad, o-whirlpool, o-orca-v1, o-orca-v2, m-dlmm, m-damm, m-damm-v2, m-dbc, m-dbc-hook, pump-amm, pump-curve, pancakeswap-v3, manifest, byreal` | Use a label from the venue table. |
| 400 | -32602 | `send dex or dexes, not both` | Send one of them. |
| 400 | -32602 | `txVersion must be 0 or 1` | Send 0, 1, or leave it out. |
| 400 | -32602 | `the quote upstream refused the request` | The engine refused this exact request. `error.data` = `{status, code, why, min_out_atoms?, min_amount_in?}`. For `code:"dust_amount"` the amount is too small: send at least `error.data.min_amount_in`, or a clearly larger amount. Change the request; do not resend it unchanged. |
| 400 | -32052 | `dex names a venue family the quote upstream does not have` | That family is not loaded right now. Pin another family or leave out `dex`. |
| 400 | -32600 | `quote is not batchable` | Send one quote per request. |
| 401 | -32001 | `unknown api key` / `api key is not enabled for quote` / other key states (see Key states) | Fix the key. Do not retry. |
| 403 | -32050 | `module not enabled for this account` | The account lacks the quote module. Add it with `POST https://carbium.sh/v1/modules/quote`, your session or a Full control account API key, and the JSON body `{"plan": "free"}` (the free plan), or on the dashboard's MODULES page. Do not retry until it is added. |
| 429 | -32005 | `rate limit exceeded` | Over your rate. A call that fits within 1 s waits and is served instead of getting this. Wait `retry-after-ms` (or `Retry-After`), then retry. |
| 429 | -32005 | `quote lane capacity exceeded: quote_lane` | More than 8 quote-plane calls were in flight on this key (32 node-wide) and none finished within 3 s. Lower your concurrency, wait `retry-after-ms` (100), then retry. |
| 429 | -32005 | `free tier limit for your network reached: all free keys calling from one subnet share one request budget; retry after Retry-After, or upgrade for a limit of your own` | Free quote plan only: all free callers on one /24 network (/56 on IPv6) share 20 req/s. Wait `Retry-After`, or buy a quote plan. |
| 429 | -32005 | `free tier at capacity on this node: all free traffic shares one budget; retry after Retry-After, or upgrade` | Free quote plan only: all free traffic on this host shares 1000 req/s. Wait `Retry-After`, or buy a quote plan. |
| 429 | -32005 | `free quote plan at capacity: free quotes share a fixed part of the quote lane; retry after Retry-After, or upgrade the quote plan` | Free quote plan only: free quotes share 8 of the node's quote-lane slots. Wait `Retry-After`, or buy a quote plan. |
| 200 | -32051 | `no route` | No path for this pair and size. `error.data` = `{reason, why, direct_why?, message?}`; act on `why` (table below). `message` is the engine's reason in one plain sentence, for logs. |
| 200 | -32053 | `sell exceeds what the curve can pay` | `error.data` = `{code:"sell_exceeds_real_sol", why?, requested?, max_amount_in?, max_out?, real_sol_reserves?, real_quote_reserves?, quote_mint?}`. An input past what its one pool can pay, any venue family. The engine has already tried the part the pool can pay (`max_amount_in` less 3%), which normally answers ok as a `partial` quote, so this error means that part failed too. `max_out` is the most it pays at `max_amount_in`. If `why` is `partial_below_fee`, that part pays less than the swap costs to land: stop. If `max_amount_in` is 0, nothing pays: stop. With no `why`, that part did not route or the bound moved: quote again well under `max_amount_in`, or stop. |
| 200 | -32054 | `token has no live pool` | Nothing routes this token (engine `why:"no_live_pool"`). Stop polling it; check again after minutes, not seconds. |
| 503 | -32011 | `quote upstream stale` | A momentary decline (a feed is reloading). `error.data.why` is one of `stale_pool`, `family_head_dead`, `tick_window_moved`, `pool_keys_missing`, `graduating` (a bonding curve has completed and the pool that replaces it is not serving yet), or `direct_why` is one of `stale_stamp`, `row_fresh_dist`, `row_fresh_dead_head`, `feed_gap`, `no_reserve`. Retry after `Retry-After` with backoff. |
| 503 | -32011 | `quote upstream refused` | The engine declined. `error.data` (when given) = `{status:503, code, why}` with code `builder_cold`, `snapshot_unavailable`, `redis_unavailable`, `overloaded`, `rpc_unavailable` or `snapshot_declined`, or `{reason, why}` with why `dlmm_window_moved` (a Meteora DLMM price window moved): retry with backoff. |
| 503 | -32011 | `quote upstream cooling down` | The quote breaker is open after 3 consecutive transport faults. Wait `Retry-After` (about 1 s), then retry. |
| 503 | -32011 | `quote upstream timed out` / `quote upstream unreachable` / `quote upstream error` / `quote upstream response shape` / `quote upstream response too large` / `quote upstream read failed` | The quote is bounded at 2 s. Retry with jittered backoff and honour `Retry-After`. Stop after 4 tries. |
| 503 | -32011 | `quote upstream not configured` | This endpoint has no quote service behind it. Stop. |

#### `-32051` `error.data.why`: what an agent can act on

| why | Meaning | What to do |
|---|---|---|
| `hook_launch_window` | The token's transfer hook admits only allowlisted wallets for now; each hook program sets its own window. | Retry later, no faster than every 30 s, or stop. |
| `hook_market_closed` | The token's transfer hook allows transfers only on a schedule its issuer sets, in both directions. | Retry when the schedule allows. |
| `hook_sells_only` | The token's transfer hook allows routes out of the token only. | Do not quote into this token; routes out of it may still be served. |
| `hook_sell_refused` | The token's transfer hook refuses routes out of the token. | Stop: this direction has no route. |
| `hook_not_tradable`, `hook_program_refused`, `hook_program_not_admitted` | The token's hook program is not supported by this router. | Stop. |
| `below_floor` | Every indexed pool for the mint is valued under the liquidity floor (USD 500). | Stop. |
| `route_below_floor` | The only route runs through a pool valued under that floor. | Try another pair, or stop. |
| `no_way_back` | A route into SOL whose only pools (m-dlmm) cannot pay a leg's cost at this size or at any tenth of it. | Stop. |
| `leg_one_way` | A non-SOL route whose leg back through SOL does not price. | Try another pair. The engine holds this answer for 2 s for the same mint, side and amount, so do not re-ask it inside 2 s. |
| `pair_unknown` | No pool is known for this pair (`direct_why:"no_body"` is the common form). | Check the mints and try another pair. Retry no faster than every 30 s. |
| `no_candidate`, `hub_refused`, `hub_none_fits`, `hub_leg_too_wide`, `partner_no_liquidity`, `via_sol_unchained` | No path at this size right now. | Try a smaller `amount_in` once. Otherwise retry no faster than every 30 s, or stop. |
| `first_hop_unfilled`, `tail_unfilled`, `curve_room_exceeded` | The route cannot fill this amount (`curve_room_exceeded`: the amount is more than the bonding curve has left before it completes). With SOL in, the engine has already asked again at half the amount, down to 1/64, and serves any part that fills as a `partial` quote, so there `first_hop_unfilled` means no part filled, or the part that filled spends less SOL than the swap's fee. | With SOL in, quote under 1/64 of this `amount_in` or stop for this pair. Otherwise quote a smaller `amount_in`. |
| `transaction_too_large`, `legs_over_cap`, `trace_too_long` | The route does not fit in one transaction. | Quote a smaller `amount_in`, or pin fewer families with `dex`. For `transaction_too_large`, also try `txVersion: 1`. |
| `pool_dead` | The route needs a pool that is held out for 30 s after a failed build. | Retry after 30 s, or try another pair. |
| `no_route_in_pinned_dex` | No one-hop route from `src_mint` to `dst_mint` in the families you pinned; a pin never falls back to another venue. | Drop the pin, or pin other families. |
| `dust_gate` | Every pool for this token holds under 0.001 SOL on its SOL side; a route into this token would drain it. `direct_why` names the pool and its reserve (`pool <address> sol_reserve <n> lamports`). | Stop for this token; check again after minutes, not seconds. |
| `dust_reserve` | The pool for this pair is under the USD 500 liquidity floor, whatever the size: its SOL, USDC or USDT side, valued twice, is under USD 500. On Meteora DAMM v2 a route into the token is judged on the token side the pool pays out, valued at the pool's price and doubled. A smaller `amount_in` does not help. | Stop for this pair; check again after minutes, not seconds. |
| `t22_unadmitted` | A Token-2022 mint whose extensions the engine has not judged yet. | Retry after a few minutes, once the engine's next table build has judged it: the mint then quotes, or answers `t22_void` or `t22_fee_over_cutoff`. |
| `t22_fee_over_cutoff`, `t22_void`, `lpad_t22_drop`, `unregistered_quote_mint`, `quote_mint_on_curve` | The engine's safeguards: a Token-2022 mint it does not admit (a transfer fee over the cutoff, or a mint LaunchLab does not support), a pump curve quoted in a mint pump has not registered, or a bonding curve that is not chainable. | Stop for this pair. |
| any other value | No path. | Treat it as `pair_unknown`. |

### `swap`: params

| Param | Type | Rule |
|---|---|---|
| `quote_id` | 32 lowercase hex | The `quoteId` from a `quote` less than 30 s old. |
| `user_pubkey` | base58, 32 bytes | The wallet that signs, pays fees and owns the token accounts. |
| `compute_unit_price_micro_lamports` | whole JSON number 0 to 300000, optional (`null` means absent) | The priority price per compute unit. When you omit it, `swap` sets it from the network: the 75th percentile of recent priority fees on the pools the router serves most, refreshed every 10 s, kept between 10,000 and 300,000 micro-lamports per compute unit, and 10,000 when the sample is more than 60 s old. A value you pass always wins. A string, a fraction, a duplicate key or a value above 300000 is refused with `-32602` `compute_unit_price_micro_lamports must be a whole number from 0 to 300000`, never clamped. |

### `swap`: result

| Field | Type | Meaning |
|---|---|---|
| `transaction` | base64 string | One unsigned transaction: v0 (with lookup tables) by default, v1 (no lookup tables) when the quote asked `txVersion: 1`. `user_pubkey` is the fee payer and the only signer (1 signature). |
| `blockhash` | string | The blockhash it was built on. |
| `lastValidBlockHeight` | number | The transaction is dead once the block height (commitment `confirmed`) passes this value. |
| `minAmountOut` | string | The floor the transaction enforces. It equals the quote's `minAmountOut`, after a reroute too. |
| `computeUnitLimit` | number | The compute limit set in the transaction. |
| `priorityFeeLamports` | string | The priority fee the transaction pays: `computeUnitLimit × price / 1,000,000`, rounded up on v0 and down on v1 (a v1 transaction carries the fee in lamports in its config). The price is yours, or the network price when you sent none. Example: 161,000 CU at 10,000 micro-lamports per CU is 1,610 lamports. |
| `rentLamports` | string or null | An upper bound on the rent for the token accounts the swap creates (refundable when they are closed). `null` when unknown. |
| `ataCreates` | number | How many token accounts it creates. |
| `txVersion` | number, present only on a v1 build | `1` on a v1 build; absent on v0. |
| `routeRerouted` | object, present only after a reroute | `{why, deadPool, quotedOut, reroutedOut, floor}`, the three amounts as strings; see Reroute. |
| `swapTag` | number, present only on a tagged build | `1` when the quote asked `swapTag: 1`; absent otherwise. A route that has no plain form is refused `-32093` with `error.data.code` `swap_tag_unroutable`: pin `dex`, change the amount, or quote without `swapTag`. |

**Reroute.** If a pool on the quoted route is gone at build time (closed, a pump curve migrated, or its keys or a fee recipient's token account missing), `swap` holds that pool out of every quote for 30 s. If the transaction would be too large, it holds that route shape out for 60 s. Either way it quotes again once, with the same `srcAmountIn`, `dex` or `dexes` selection, `txVersion` and `compute_unit_price_micro_lamports`, and builds the new route only if that quote keeps the same `srcAmountIn`, avoids the held pool or route and pays at least the original `minAmountOut`. The transaction then no longer follows `routePlan` and can deliver less than `destAmountOut`, never less than `minAmountOut`. The answer then carries `routeRerouted`: `why` is the build refusal that set it off (`pool_state_missing`, `pool_keys_missing`, `fee_recipient_ata_missing`, `pcurve_graduated` or `transaction_too_large`), `deadPool` the pool held out (absent when the route was too large), `quotedOut` the quote's `destAmountOut`, `reroutedOut` the new route's expected out, `floor` the floor held (the same as `minAmountOut`). Treat `minAmountOut` as the guarantee and `reroutedOut` as the estimate. If the new quote finds no route, pays less, changes the amount or does not build, `swap` answers the first build's refusal at HTTP 200: `-32081` for `pool_state_missing`, `-32083` for `transaction_too_large`, or `-32093` with `error.data` = `{status: 422, code}` for the other three. Quote again: the held pool or route stays out of new quotes until its hold ends.

Live example (2026-10-09, when the default was a fixed 10,000) with the price absent: `{"transaction":"AQAA…(708 b64 chars)","blockhash":"2QpLj7ntb9aAeZLM5ByDz2QJqWJtMCWNtJuq5TC4BSnD","lastValidBlockHeight":433003717,"minAmountOut":"1081632","computeUnitLimit":161000,"priorityFeeLamports":"1610","rentLamports":"1488440","ataCreates":1}`. The decoded transaction (v0) had 3 instructions: ComputeBudget SetComputeUnitLimit, ComputeBudget SetComputeUnitPrice, and the router swap on program `cqXpiki8fwAWY72xtzqPLmstzf3MZ4kjJBhRatZrWMs`. Some builds add an idempotent token-account create, for 4.

The wallet needs: the input amount (if the input is SOL), the 5,000-lamport signature fee, `priorityFeeLamports` and `rentLamports`.

### Signing, sending and confirming

1. Decode `transaction` from base64 as a **VersionedTransaction (v0 or v1, the version the quote asked for)**. For v1 the wire order is the message, then the signatures, so sign it with a v1-capable SDK (web3.js 3.0, kit 8.4). Sign it with the `user_pubkey` keypair only. Do not change the message, the blockhash or the instructions; if you do, the floor and the fee are no longer the quoted ones.
2. Send it with `sendTransaction`, on the same endpoint or through any other Solana RPC: `[base64, {"encoding":"base64","skipPreflight":true}]`. On this endpoint it costs 20 cells and 20 credits. Without `skipPreflight:true` the call is priced as a preflight send (70 cells) and runs slower.
3. Confirm by polling `getSignatureStatuses([[sig]])` until `confirmationStatus` is `confirmed` or `finalized`, or until `err` is non-null. Alternatively, subscribe with `signatureSubscribe` over WSS (one notification, then the subscription closes). For full detail, call `getTransaction(sig, {"encoding":"base64","maxSupportedTransactionVersion":1,"commitment":"confirmed"})`. Mainnet carries v1 transactions: with the version option absent or 0 you get `-32015`.
4. Expiry: while you are not confirmed, read `getBlockHeight({commitment:"confirmed"})`. Once it is above `lastValidBlockHeight`, make one last status check with `searchTransactionHistory:true`. If the transaction still has not landed, it never will. **Quote again**; do not re-sign the old message.
5. Resending the *same signed bytes* before expiry is safe because it has the same signature and cannot execute twice. Never re-sign a rebuilt transaction while the first one might still land.
6. On-chain failure `{"InstructionError":[i,{"Custom":6004}]}` is the router's own error: the output was under the slippage floor (the price moved). Quote again, and widen `slippage_bps` only if you mean to. Any other `Custom` code comes from the venue program the route calls: quote again and resend. An insufficient-funds error means you should stop and fund the wallet.

### `swap`: refusals

| code | HTTP | message (exact) | What to do |
|---|---|---|---|
| -32602 | 400 | `params must carry quote_id and user_pubkey` / `params accepts only quote_id, user_pubkey, compute_unit_price_micro_lamports` / `user_pubkey must be a base58 32-byte pubkey` / `quote_id must be the 32-character quoteId of a served quote` / `compute_unit_price_micro_lamports must be a whole number from 0 to 300000` | Fix the request. |
| -32600 | 400 | `quote is not batchable` | Send one swap per request. |
| -32095 | 400 | `swap quote_id is unknown or expired; request a new quote` | Quote again. |
| -32074 | 400 | `swap quote route carries a leg family the builder refuses` | Quote again, pinning other families with `dex`. |
| -32081 | 200 | `swap route pool state is not loaded upstream` | Quote again. |
| -32082 | 200 | `swap route mint is not resolvable on chain` | Quote again. If it repeats, stop for this pair. |
| -32083 | 200 | `swap transaction exceeds the size limit` | Quote again, with a smaller size or with `dex` pinned to fewer families (fewer legs). |
| -32096 | 200 | `swap route has a leg the on-chain router cannot execute` | Quote again, pinning other families. |
| -32098 | 200 | `swap route's token hook admits only a wallet holding its gate token` | `error.data` = `{code:"hook_token_gate", gate_mint, gate_min, holding, gate_decimals}`. `gate_min` and `holding` are in base units of `gate_mint`. This is final for this wallet: hold at least `gate_min` of `gate_mint`, then quote again. |
| -32099 | 200 | `swap route has a hook account the builder cannot derive` | Final for this quote. Do not retry it; stop for this token. |
| -32093 | 200 or 503 | `swap upstream refused for an unmapped reason` | `error.data` = `{status, code}`. At HTTP 200, quote again. At HTTP 503, retry with backoff. |
| -32094 | 503 | `swap upstream returned a floor that is not the one sent` | Retry once with backoff. If it repeats, quote again. |
| -32060 … -32073, -32075 … -32080 | 503 | for example `swap quote carries no floor` (-32063), `swap quote route leg amounts do not sum to amount_in` (-32078), `swap upstream refused the user pubkey` (-32080) | The builder disagrees with its own quote. Quote again. |
| -32084 … -32092, -32097 | 503 | for example `swap upstream cannot reach its validator RPC` (-32084), `swap upstream cannot reach its pool store` (-32085), `swap upstream build failed` (-32086), `swap upstream has its on-chain router switched off` (-32097) | Retry with backoff and honour `Retry-After`. Quote again if more than 30 s have passed since the quote. |
| -32011 | 503 | `swap upstream timed out` (5 s bound) / `swap upstream unreachable` / `swap upstream response shape` / `swap upstream status disagrees with its body` / `swap upstream response too large` / `swap upstream read failed` / `swap upstream not configured` | Retry with backoff. Stop after 4 tries. |
| -32001 / -32050 / -32005 | 401 / 403 / 429 | as for `quote` | as for `quote` |

### `prices`

The params are none, `{}`, or `{"mints":[...]}` with at most 64 base58 mints. The result is `{solUsd, builtUnix, priced, stale, noroute, total, rows}`. Each row is `[mint, priceUsd | null, tvlUsd, quoteMint]`. A mint the table does not carry is simply absent from `rows`; that is not an error. The table is periodic, not a per-call price oracle: it is cached for 30 s. Poll it on a timer and never call it once per swap. Each call counts as one quote. Errors:

| HTTP | code | message | What to do |
|---|---|---|---|
| 400 | -32602 | `params accepts only mints, or no params at all` | Fix the request. |
| 400 | -32602 | `mints must be an array of at most 64 base58 32-byte pubkeys` | Send at most 64, or omit `mints` to get the whole table. |
| 400 | -32600 | `quote is not batchable` | Send it unbatched. |
| 503 | -32011 | `prices upstream unreachable` / `timed out` / `read failed` / `response too large` (4 MiB ceiling) / `prices upstream response shape` / `prices upstream row shape` | Retry with backoff. |

### `health`

There are no params. The result is `{ok, quoteUpstream, canBuild, families[], poolStore, chainRpc, priced, total, stale, tableAgeSecs, quote_refusal_ratio}`, cached for 2 s. It reports the quote plane's own readiness. `getHealth` is the validator's liveness, which is a different question. A dependency that is down shows up as `ok:false` with its own fields zeroed, never as a 503. It costs 1 cell at your subscription tier's cached-read rate, 5 / 30 / 100 / 500 req/s (FREE / DEV / BUSINESS / PRO), and needs the quote module and the QUOTE scope. **It is advisory.** Do not gate a swap on `canBuild`; call `swap` and act on its answer. Errors: 400 `-32602 "quote is not batchable"` (in a batch); 503 `-32011 "quote plane upstream not configured"`.

### Quote plans and what counts

Each `quote`, `swap` and `prices` call is one quote (60 cells) against the account's quote plan. The plan is shared by all the account's keys and is the same at every subscription tier.

| Quote plan | Price | Quotes per account (burst: one second of it) |
|---|---|---|
| FREE | $0 | 10 / s |
| STARTER | see `GET /v1/plans` `quote[]` | 50 / s |
| PRO | see `GET /v1/plans` `quote[]` | 150 / s |
| ELITE | see `GET /v1/plans` `quote[]` | 500 / s |

- Concurrency: at most **8 quote-plane calls in flight per key** and 32 node-wide. Beyond that a call waits up to 3 s for a slot, then gets 429.
- Free quote plan: calls also share the free budgets: 20 req/s for all free callers on one /24 network (/56 on IPv6), 1000 req/s for all free traffic on this host, and 8 of the node's quote-lane slots. Past any of them the call gets 429 `-32005` (see `quote`: errors). A paid quote plan has none of these.
- Quote-plane calls cost **0 credits**; the plan is the meter, so they are answered even when the account's credits are spent. The `sendTransaction`, `getSignatureStatuses` and `getBlockHeight` calls in the swap flow are ordinary RPC and spend credits and RPC rate.
- A refused call still spends its rate cells, so a retry loop on a 400 burns your quote rate.

## Cross-plane: key states, credits, limits, retry

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

RPC body shape: `{"jsonrpc":"2.0","id":<your id>,"error":{"code":-32001,"message":"unknown api key","data":{"reason":"UNKNOWN_KEY","retryable":false}}}`. `error.data.retryable` is true exactly for the pressure band (429). Every reply carries `x-request-id`; quote it to support. The WS handshake refusal body is `{"error":{"message":"..."}}`, not JSON-RPC.

### Credits

- `402`, `-32002`, `"credits exhausted"`, reason `CREDITS_EXHAUSTED`, `retryable:false`, `Retry-After: 1`. A 402 means the account's remaining credits cannot cover the call. On WS the handshake does not check credits: a subscribe answers `-32002` inside the socket, and a live socket whose streamed bytes cannot be paid closes with **1008 `credits_exhausted`**. On gRPC it is `RESOURCE_EXHAUSTED` `credits exhausted` (`consumer_credits_exhausted` on an open stream): do not retry. On RPC and WS do not retry either (after a 1008 close, reconnect once after about 5 s): buy a plan or upgrade on the dashboard (each month of an RPC plan adds its credits; a Quote plan adds none). Near the end of a balance a node can answer 402 while the last credits sit reserved at other nodes; they return within minutes.
- `429`, `-32005`, `"credits for this account are still loading on this node; retry after Retry-After"`, reason `CREDITS_PENDING`, `retryable:true`, `Retry-After: 1`, `retry-after-ms: 1000`. The account has credits, but this node has not loaded them yet (a new account's first calls, a burst that spent this node's share, or just after a node restart). It is not a 402: wait and send it again. On WS it is a subscribe reply `-32005` with `data.retryAfterMs` 1000, and the socket stays open; on gRPC it is `RESOURCE_EXHAUSTED` with that message and `retry-after: 1`. A live stream can end on it too: a WS socket closes `1013 credits_pending` (reconnect after about 1 s and re-subscribe), and a gRPC stream ends `UNAVAILABLE` with that message and `retry-after: 1` (resubscribe after it); the bytes already sent are billed.
- Refused calls cost 0 credits, except a getTransactionsForAddress walk refused after it made upstream calls, which bills those calls, and a failed preflight send, which keeps its 75 credits.
- What spends credits:
  - **RPC**: each method's credits, in the Credits column of the RPC method catalogue. Token scans also bill per row returned, and a getTransactionsForAddress walk per upstream call it makes, as their catalogue rows show.
  - **WS and gRPC**: 5 per slot/root/signature subscription, 25 per account/logs-mentions/slotsUpdates subscription (gRPC: an `accounts` filter with an `account` list, or a `transactions` filter narrowed by account), 200 per program/logs-all/block subscription (gRPC: an `accounts` filter with `owner`, `blocks`, `blocksMeta`, `entry` or a transaction firehose), plus 20 per MiB delivered. A gRPC stream that delivers no data books 0 credits.
  - **Quote plane**: 0 credits; calls count against the account's quote plan. They are answered even when the account's credits are spent: a call that costs 0 credits is never refused for credits.

### Rate limits

Rates are per account (all its keys share one bucket), in cells per second; every method's cells and the plan rates are in the RPC method catalogue. On RPC and the quote plane, a call over its plan rate that fits within 1 s waits and is served, and a call short of a concurrency slot waits up to 3 s for one; only then comes the 429. WebSocket and gRPC refuse at once. A 429 has `-32005` and one of these messages: `rate limit exceeded` (`RATE_LIMITED`), `heavy-class rate limit exceeded` (`HEAVY_CLASS_LIMITED`), `blocking-slot capacity exceeded: <pool> pool`, `scan-index lane capacity exceeded: chot_lane`, `DAS lane capacity exceeded: das_lane`, `quote lane capacity exceeded: quote_lane` or `free quote plan at capacity: ...` (`SLOT_CAP_EXCEEDED`), `overloaded` (`LOAD_SHED`), or, on the Free plan and the free quote plan, `free tier limit for your network reached: ...` (`FREE_SUBNET_LIMITED`: all free keys calling from one network share one budget) and `free tier at capacity on this node: ...` (`FREE_TIER_BUSY`), and `credits for this account are still loading on this node; retry after Retry-After` (`CREDITS_PENDING`: the node has not loaded the account's credits yet, as on a new account's first calls, after a burst that spent this node's share, or just after a node restart). The one 429 with another code is `-32010` `scan index temporarily unavailable, retry` (`CHOT_INDEX_UNAVAILABLE`). Every 429 on RPC and the quote plane carries `Retry-After` in whole seconds and `retry-after-ms`, which is exact; prefer the ms header (a browser can read only `Retry-After`). On gRPC the status is `RESOURCE_EXHAUSTED` with `retry-after` metadata in seconds. On a WS handshake it is 429 with `Retry-After`, and the messages include `connection or subscription cap exceeded` and `overloaded or draining`.

### One retry and backoff policy (all planes)

Backoff means: wait the larger of the server's hint (`retry-after-ms`, else `Retry-After` × 1000) and `250 ms × 2^(attempt−1)` capped at 4 s, plus 0 to 250 ms of random jitter. Never cut a server hint to 4 s. Stop after 4 attempts unless the row says otherwise.

| Error class | Where | Retry? | How | When to stop |
|---|---|---|---|---|
| 400 / -32600 / -32602 (malformed, bad params, batch refused, body over 50 KB with HTTP 413) | RPC, quote, swap, prices | No (getTransactionsForAddress's `-32602` `the walk read no history`: yes, as a 429) | Fix the request. | Immediately. |
| -32601 `method not found` / `method not served` (HTTP 200) | RPC | No | Use a served method. | Immediately. |
| 401 / -32001, 403 / -32001 `IP_NOT_ALLOWED`, WS 401/403, gRPC UNAUTHENTICATED | all | No | Fix or renew the key, add the scope, or call from an allowed address. | Immediately. |
| 403 / -32050 `module not enabled for this account` | quote, swap, prices, health | No | Add it with `POST https://carbium.sh/v1/modules/quote`, your session or a Full control account API key, and the JSON body `{"plan": "free"}` (the free plan), or on the dashboard's MODULES page. | Immediately. |
| gRPC PERMISSION_DENIED | gRPC | No | Act on the message (see the gRPC error table): `streaming is not included in this tier` means upgrade the plan, the allowlist message means call from a listed address, and the rest mean fix the filter or the request. | Immediately. |
| 402 / -32002, WS subscribe `-32002` | RPC, WS | No | Buy a plan or upgrade. | Immediately. |
| WS close 1008 `credits_exhausted` | WS | Once | Reconnect once after about 5 s and re-subscribe; if the subscribes answer `-32002`, buy a plan or upgrade; if they answer `-32005` `CREDITS_PENDING`, wait `retryAfterMs` and resend. | After that one reconnect. |
| WS close 1013 `credits_pending`, gRPC UNAVAILABLE `credits for this account are still loading on this node; retry after Retry-After` | WS, gRPC | Yes | Reconnect after about 1 s (gRPC: after the `retry-after`) and re-subscribe; do not buy anything. | Back off after 3 failed reconnects. |
| gRPC RESOURCE_EXHAUSTED `credits exhausted` / `consumer_credits_exhausted` | gRPC | No | Buy a plan or upgrade. | Immediately. |
| 429 / -32005 (including the Free network limits and, on calls that cost credits, `CREDITS_PENDING`), gRPC RESOURCE_EXHAUSTED (rate, or `credits for this account are still loading on this node; retry after Retry-After`) | all | Yes | Back off, honouring `retry-after-ms`. Lower concurrency (quote: at most 8 in flight per key). | 4 attempts, then lower your request rate. |
| 429 / -32010 `CHOT_INDEX_UNAVAILABLE` (scan index behind) | RPC scans | Yes | Back off from 100 ms (100, 200, 400 ... capped at 5 s), honouring `retry-after-ms`. | About 6 tries, then surface the error. |
| 503 / -32011 and other 503s (breaker, upstream down, `cooling down`, `stale`) | RPC, quote, swap, prices | Yes | Back off, honouring `Retry-After`. | 4 attempts. For a swap, quote again if more than 30 s have passed since the quote. |
| 504 (scan over its deadline) | RPC | Yes, once | Narrow the request. | 1 retry. |
| Network error or timeout, no response | all | Yes | Back off. | 4 attempts. A `sendTransaction` with no response may have landed: check the signature status before sending again. |
| 200 / -32051 `no route`, -32054 | quote | No (see the why table) | Change the pair or size, or wait the named window. | Do not loop faster than every 30 s. |
| 200 / -32053 | quote | Only with a much smaller amount | The engine already tried the part under `error.data.max_amount_in`: quote again well under it. | If `why` is `partial_below_fee`, or `max_amount_in` is 0, stop. |
| 400 / -32095, -32074; 200 / -32081, -32082, -32083, -32096; 200 / -32093 | swap | Quote again | Get a new `quote`, then `swap`. | 3 rounds. |
| 200 / -32098 | swap | No | The wallet must hold `gate_min` of `gate_mint`. | Immediately. |
| 200 / -32099 | swap | No | Stop for this token. | Immediately. |
| On-chain `Custom:6004` (under the slippage floor) | after send | Quote again | Quote, swap, sign, send again. | 3 rounds. |
| On-chain, any other `Custom` code | after send | No | It is the venue's own error (see Signing, sending and confirming). | Immediately. |
| Blockhash expired (block height > `lastValidBlockHeight`, not landed) | after send | Quote again | Never re-sign the old message. | 3 rounds. |
| WS close 1013 `slow_consumer` / `delivery_overload_retry` | WS | Yes | Reconnect with backoff, read faster, subscribe to less. | Back off further after 3 closes in a row. |
| WS close 1012 `draining` / `stream_gap_reseed_required` | WS | Yes | Reconnect at once with jitter and re-subscribe everything; re-read state you may have missed. | Back off after 3 failed reconnects. |
| WS close 1001 `idle_timeout` (900 s idle) / `no_pong` (300 s without a pong) | WS | Yes | Reconnect. Answer server pings (sent every 30 s); a pong counts as traffic. | Fix the client. |
| gRPC RESOURCE_EXHAUSTED `consumer_lagged: your stream fell behind the ring; reduce filters or read faster` | gRPC | Yes | Wait `retry-after` (2 s); reduce filters. | Back off after 3 in a row. |
| gRPC UNAVAILABLE / DEADLINE_EXCEEDED | gRPC | Yes | Back off and resubscribe. | 4 attempts, then 30 s waits. |
| gRPC OUT_OF_RANGE `gap: re-seed required` (`fromSlot` too old, or a gap in the upstream feed) | gRPC | Yes, after a re-seed | Reload state over RPC, then resubscribe with no `fromSlot` (or with `fromSlot >= firstAvailable`). | Back off after 3 in a row. |
| gRPC INVALID_ARGUMENT | gRPC | No | Fix the request. | Immediately. |

### Complete recipe: quote, build, sign with your own wallet, send, confirm (Node 18+, `npm i @solana/web3.js`)

Pass `dryRun: true` to sign and simulate (`simulateTransaction` with `sigVerify:true`) instead of sending. Leave `cuPrice` unset for the default priority price; set it to pay your own.

```js
// carbium-swap.mjs
import { VersionedTransaction } from "@solana/web3.js";

const DOOR = "https://services.carbium.sh";
const KEY = process.env.CARBIUM_KEY; // the FULL raw key, never the short c_serv_ prefix the dashboard lists
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// One JSON-RPC call. Retries ONLY 429 and 503 (and network errors), honouring retry-after-ms / Retry-After, max `tries`.
// Every other answer is returned or thrown at once: branch on error.code, never on the HTTP status alone.
export async function call(method, params, { tries = 4 } = {}) {
  for (let i = 1; ; i++) {
    let r, j = null;
    try {
      r = await fetch(DOOR, {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": KEY },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      });
      j = await r.json().catch(() => null);
    } catch (netErr) {
      if (i >= tries) throw netErr;
    }
    if (j && "result" in j && !j.error) return j.result;
    const status = r ? r.status : 0;
    const e = j?.error ?? { code: status, message: "HTTP " + status + " without a JSON-RPC body" };
    const retryable = status === 0 || status === 429 || status === 503 || (status >= 500 && !j?.error);
    if (!retryable || i >= tries) {
      throw Object.assign(new Error(`${method} ${e.code}: ${e.message}`), { http: status, code: e.code, data: e.data });
    }
    const hinted = Number(r?.headers.get("retry-after-ms")) || Number(r?.headers.get("retry-after")) * 1000 || 0;
    const backoff = Math.min(250 * 2 ** (i - 1), 4000);
    await sleep(Math.max(hinted, backoff) + Math.random() * 250); // jitter
  }
}

// Swap answers that mean "this quote is dead, quote again".
const REQUOTE = new Set([-32095, -32074, -32081, -32082, -32083, -32096]);

// Poll until confirmed, failed, or the blockhash expires (block height past lastValidBlockHeight).
export async function confirm(sig, lastValidBlockHeight, pollMs = 1000) {
  for (;;) {
    const { value: [st] } = await call("getSignatureStatuses", [[sig]]);
    if (st?.err) return { status: "failed", err: st.err, slot: st.slot };
    if (st && (st.confirmationStatus === "confirmed" || st.confirmationStatus === "finalized")) {
      return { status: "confirmed", slot: st.slot };
    }
    const height = await call("getBlockHeight", [{ commitment: "confirmed" }]);
    if (height > lastValidBlockHeight) {
      const { value: [last] } = await call("getSignatureStatuses", [[sig], { searchTransactionHistory: true }]);
      if (last?.err) return { status: "failed", err: last.err, slot: last.slot };
      if (last?.confirmationStatus) return { status: "confirmed", slot: last.slot };
      return { status: "expired" }; // never landed; safe to quote again
    }
    await sleep(pollMs);
  }
}

// quote -> swap -> sign -> send -> confirm. Quotes again (max `rounds`) on a dead quote, expiry, or slippage (6004).
export async function swap(wallet, { src, dst, amountIn, slippageBps = 50, dex, cuPrice, rounds = 3, dryRun = false }) {
  for (let round = 1; round <= rounds; round++) {
    let q;
    try {
      q = await call("quote", [{ src_mint: src, dst_mint: dst, amount_in: String(amountIn), slippage_bps: slippageBps, ...(dex ? { dex } : {}) }]);
    } catch (e) {
      if (e.code === -32053 && e.data?.max_amount_in) throw Object.assign(e, { hint: "send well under " + e.data.max_amount_in });
      throw e; // -32051 (read e.data.why) / -32054 / -32602 / 401 / 403: retrying now changes nothing
    }
    if (q.partial) console.warn(`partial: fills ${q.srcAmountIn} of ${q.requestedAmountIn}`);

    let s;
    try {
      s = await call("swap", [{ quote_id: q.quoteId, user_pubkey: wallet.publicKey.toBase58(), ...(cuPrice != null ? { compute_unit_price_micro_lamports: cuPrice } : {}) }]);
    } catch (e) {
      if (REQUOTE.has(e.code) || (e.code === -32093 && e.http === 200)) continue;
      throw e; // -32098 gate (see e.data), -32099, -32602, or 503s that outlived retries
    }

    const tx = VersionedTransaction.deserialize(Buffer.from(s.transaction, "base64"));
    tx.sign([wallet]); // wallet = Keypair for user_pubkey: fee payer and only signer
    const wire = Buffer.from(tx.serialize()).toString("base64");
    if (dryRun) return call("simulateTransaction", [wire, { encoding: "base64", sigVerify: true }]);

    const sig = await call("sendTransaction", [wire, { encoding: "base64", skipPreflight: true }]);
    const res = await confirm(sig, s.lastValidBlockHeight);
    if (res.status === "confirmed") return { sig, ...res, quote: q, build: s };
    if (res.status === "expired") continue;
    const custom = res.err?.InstructionError?.[1]?.Custom;
    if (custom === 6004) continue; // under the slippage floor: the price moved, quote again
    throw Object.assign(new Error("swap failed on chain: " + JSON.stringify(res.err)), { sig, err: res.err });
  }
  throw new Error(`no landed swap after ${rounds} rounds`);
}
```

Usage:
```js
import fs from "node:fs";
import { Keypair } from "@solana/web3.js";
import { swap } from "./carbium-swap.mjs";

const wallet = Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(process.env.WALLET_PATH, "utf8")))); // solana-keygen JSON
try {
  const r = await swap(wallet, {
    src: "So11111111111111111111111111111111111111112",   // SOL
    dst: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  // USDC
    amountIn: 10_000_000,                                  // 0.01 SOL in lamports
    slippageBps: 50,
  });
  console.log("landed", r.sig, "slot", r.slot, "got at least", r.build.minAmountOut);
} catch (e) {
  if (e.code === -32051) console.log("no route:", e.data?.why);           // see the why table
  else if (e.code === -32098) console.log("token gate:", e.data);         // hold gate_min of gate_mint
  else if (e.http === 402) console.log("credits exhausted: buy a plan or upgrade");
  else if (e.http === 401 || e.http === 403) console.log("key/scope/module:", e.message);
  else throw e;
}
```

`@solana/kit` variant of the signing step (`npm i @solana/kit`):
```js
import {
  getBase64Encoder, getTransactionDecoder, signTransaction,
  getBase64EncodedWireTransaction, getSignatureFromTransaction,
} from "@solana/kit";

// keyPair: CryptoKeyPair for user_pubkey, e.g. await createKeyPairFromBytes(secret64)
export async function signSwap(b64, keyPair) {
  const tx = getTransactionDecoder().decode(getBase64Encoder().encode(b64));
  const signed = await signTransaction([keyPair], tx);
  return { wire: getBase64EncodedWireTransaction(signed), sig: getSignatureFromTransaction(signed) };
}
// then: call("sendTransaction", [wire, { encoding: "base64", skipPreflight: true }]) and confirm(sig, s.lastValidBlockHeight)
```

### Agent checklist (quote plane)

- [ ] Use the full key in `x-api-key`. The key has the QUOTE scope and the account has the quote module.
- [ ] One quote-plane call per HTTP request; no batches.
- [ ] Amounts are decimal strings in base units, handled with BigInt.
- [ ] Call `swap` within 30 s of `quote`. On `-32095`, quote again.
- [ ] Sign only as `user_pubkey`; never modify the message.
- [ ] Send with `skipPreflight:true`, confirm with `getSignatureStatuses`, and quote again after `lastValidBlockHeight` passes.
- [ ] Treat `platformFee` as already netted in `destAmountOut` / `minAmountOut`; do not subtract it again.
- [ ] Respect `partial`: the swap spends `srcAmountIn`, not what you asked for.
- [ ] Read the HTTP status and `error.code` together; HTTP 200 can carry an `error`. Retry only 429, 503 and getTransactionsForAddress's `-32602` `the walk read no history`, with jittered backoff that honours `retry-after-ms`.
- [ ] Do not poll `prices` per swap (30 s cache); do not gate swaps on `health.canBuild`.
- [ ] At most 8 quote-plane calls in flight per key.

## Account, keys and billing

You manage accounts, keys and payments on the dashboard at `https://carbium.sh`, whose keys work on `services.carbium.sh`. A person signs in there and uses KEYS, MODULES and ACCOUNT. Every call below is that dashboard's own API on `https://carbium.sh`, and an agent can make them all with only a Solana keypair (Agents, below). They take the dashboard session (`Authorization: Bearer <session token>`) or, for the calls listed under Account API keys, an account API key (`Authorization: Bearer c_acct_...`). A service key (`c_serv_...`) is refused. Send each JSON body with `Content-Type: application/json`: without it the call answers 415 with the plain-text body `` Expected request with `Content-Type: application/json` ``, not the error JSON below. A call with no body, such as `POST /v1/keys/{id}/secret`, needs no header. Errors come back as `{"error": "<code>", "message": "<text>"}`:

- 400 `bad_request`: fix the body as the message says. A body that is not valid JSON answers 400, and one with a missing or wrong-typed field 422, each as plain text naming the problem.
- 401 `unauthorized`: sign in again. With an account API key: the key is unknown, revoked or expired, was made on the other dashboard name, or the call is closed to keys.
- 403 `forbidden`: the message names the cause, for example `this key is read only`.
- 404 `not_found`: also returned for a key that is not on your account.
- 409 `conflict`: the message names the reason.
- 429 `rate_limited`: back off, then retry. A 429 to an account API key carries `Retry-After` in seconds; the others carry no retry hint.
- 503 `upstream`: a service behind the dashboard did not answer. Make the same call again.

### Agents: onboard yourself with only a Solana keypair

An agent signs up, gets a free key and buys a plan over HTTPS with only a Solana keypair: no browser, no inbox. Make every call on one dashboard name: a challenge, `nonce_token` or session from one dashboard is refused on another.

A free key, on `https://carbium.sh`:

1. `GET /v1/signup/challenge` needs no session and answers `{"challenge": "<string>", "difficulty": 18}`. Use the `difficulty` it gives; do not hard-code it. A challenge is good for 300 seconds and opens one account at most: fetch a new one for each try.
2. Find a whole number `nonce` (0 to 2^64-1) for which BLAKE3 over the challenge's UTF-8 bytes followed by `nonce` as 8 little-endian bytes starts with at least `difficulty` zero bits, counted from the highest bit of the first byte. At 18 bits that takes about 262,000 hashes on average.
3. `POST /v1/auth/wallet` with `{"step": "challenge", "wallet": "<your base58 public key>"}` answers `{"nonce_token": "…", "message": "…"}`. The message is `carbium.sh wants you to sign in with your Solana account:`, your public key on the next line, a blank line, `I accept the Carbium Terms, version <version>: <terms URL>`, a blank line, then `Nonce: <32 hex characters>`, joined by `\n`. Sign it exactly as returned. Signing it accepts that Terms version, and the account records it; a wallet sign-in sends no `terms_version`. The `nonce_token` is good for 600 seconds and signs in once.
4. Sign the message's UTF-8 bytes with the wallet's ed25519 key, and send the 64-byte signature in base58, or in standard base64 with its padding: `POST /v1/auth/wallet` with `{"step": "verify", "wallet": "<the same key>", "nonce_token": "…", "signature": "…", "pow": {"challenge": "<the challenge string>", "nonce": <number>}}`, with `nonce` a JSON number, not a string. It answers `{"session_token": "…", "account": {"account_id": <n>, "email": null, "wallet": "<key>", "status": "active", "created_at": "YYYY-MM-DD", "tier": "free"}}`. The session lasts 30 days.
   - A first sign-in without `pow` answers 400 `proof of work required`: send the same `nonce_token` and `signature` again with a `pow`. A wallet that already has an account is never asked for one.
   - 401: a wrong, expired or used `nonce_token`, or a bad signature. 400 `invalid proof of work`. 400 `terms acceptance required`: the Terms changed after your challenge, so start again.
5. Your first sign-in makes one starter key (FREE, with `rpc` and `ws`; FREE has no carbon stream) and gives the account the free grant of credits, once: a wallet whose earlier account was deleted gets none, so its calls that cost credits answer 402 `credits exhausted` until it buys an RPC tier (a Quote plan adds no credits; a call that costs 0 credits is still answered). `GET /v1/keys` with `Authorization: Bearer <session_token>` lists the key. A wallet account has no email address, so nothing is mailed: read the key with `POST /v1/keys/{key_id}/secret`, no body, which answers `{"available": true, "raw_key": "c_serv_…"}`. That `raw_key` is your API key.
6. Call `https://services.carbium.sh` with the header `x-api-key: <raw_key>` and a JSON-RPC body. A new account's first call can arrive before its credits reach that node: it answers 429, `-32005`, reason `CREDITS_PENDING`, with `Retry-After`; wait that long and send it again.
7. For quotes, add the free Quote plan: `POST /v1/modules/quote` with `Authorization: Bearer <session_token>`, `content-type: application/json` and the body `{"plan": "free"}`. It answers the module with `enabled: true`, and every active key gains `quote` in its `scope`; `quote`, `swap`, `prices` and `health` then answer on `https://services.carbium.sh` and cost no credits. Without the module they answer 403 `-32050` `module not enabled for this account`.

A plan, paid in USDC or USDT on Solana, on `https://carbium.sh` only: a dashboard that does not sell answers 403 `purchases are not offered here`. A session works only on the dashboard that issued it, so to buy, sign in on carbium.sh with the same wallet (steps 1 to 4); it opens the same account, with no second sign-up challenge.

1. `GET /v1/plans` (public) lists each plan's `tier` (or, under `quote[]`, `plan`), `amount_minor` (US cents a month), `sellable` and `credit_grant`. Buy only an entry with `sellable: true`.
2. `POST /v1/billing/crypto-intent` with `{"tier": "dev"}` (or `buss`, `pro`), or `{"plan": "starter"}` (or `pro`, `elite`) for a Quote plan, plus `months` (1 to 12, default 1), `mint` and `payer` (your base58 wallet). The mints are USDC `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` and USDT `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`, both 6 decimals (USDC when `mint` is absent); SOL itself is not taken as payment. The answer carries `intent_id`, `status` `open`, `amount_minor` (US cents for all the `months`: the monthly price × `months`), `amount` in base units (`amount_minor` × 10,000), `expiry` (30 minutes after the intent opened; a transfer that lands after it is refused), `reference` and `tx`.
3. `tx` is an unsigned v0 transaction in base64: your `payer` wallet is its fee payer and only signer. Sign it at once (its blockhash is fresh) and send it with preflight on, through any Solana RPC: an account with no credits yet cannot send it through `services.carbium.sh`. Keep at least 0.003 SOL in the wallet for the fee, its rent-exempt minimum and, if missing, the recipient's token account. Your token account for `mint` must already hold the amount: `payer_balance`, and `sim_error` when the transaction would fail, say so before you sign.
4. Poll `GET /v1/billing/crypto-intent/{intent_id}` every few seconds. `status` is `open` (waiting), `paid` (applied), `held` (received but not applied, for example on a suspended account) or `expired` (nothing paid by `expiry`). `refused` lists any other transfer found under the reference, with its reason.
5. Once `paid`, the plan is applied: `GET /v1/account` shows the `tier` and `term`, `GET /v1/balance` the added credits, and `GET /v1/keys` every live key on the new tier. A Quote plan leaves the tier, the credits and the keys' tier as they were: `GET /v1/modules` shows the `quote` entry `enabled: true` with the `plan` you bought and its `period_end`. If the account did not hold the module before, every active key also gains `quote` in its `scope`; an upgrade or a renewal adds it to no key (add it with `PATCH /v1/keys/{id}/scope`).
   - Once you have sent the payment, never POST again for that plan: poll. A POST that answers 409 `a payment for this intent is on its way; it is applied once it lands` means the same.
   - 409 `account suspended: contact support`: a suspended account opens no intent.
   - A payment with status `held`, or a transfer in `refused` that reached Carbium's wallet without being applied, was received but not applied and buys no plan: contact support with the `intent_id` and the transaction signature and, where the law allows, Carbium returns it by hand.

Limits an agent must know:

- One IPv4 address, or one IPv6 /56, opens at most 3 accounts in 24 hours. The next sign-up answers 429 `registration cap (ip)` with no retry hint: do not retry it sooner.
- Sign up from the address you will call from. A sign-up from a Tor exit, a network on Spamhaus ASN-DROP or a subnet Carbium denied answers 403 `signup refused (tor_exit)`, `signup refused (asn_drop)` or `signup refused (subnet_denied)`.
- Every 429 on RPC and the quote plane carries `retry-after-ms`, the exact wait: never retry before it. A free account whose calls are refused with `rate limit exceeded` in most hours of a day (at least 60 refusals an hour, in 20 of the last 24 hours) is suspended; its keys then answer 401 `api key suspended; contact support`.
- A free account holds one key: another `POST /v1/keys` answers 409 `key limit reached: the free tier allows 1 key; revoke one or upgrade`.

The whole sequence in one file, in TypeScript on `@solana/kit`. Node 22.18 or later runs it as is, with two packages: `npm i @solana/kit @noble/hashes` (it was run with 8.6.0 and 2.4.0). `KEYPAIR` names your keypair, a solana-keygen JSON file (without it the run makes a new one). Add `PLAN=starter` (a Quote plan) or `TIER=dev` (an RPC tier) to buy that plan too, on carbium.sh only: it pays before the first call and sends the payment through `SOLANA_RPC` (any Solana RPC; `https://api.mainnet-beta.solana.com` when unset).

```ts
// Onboard to Carbium with only a Solana keypair, no browser and no inbox: a free account, its key, the free Quote plan, a first call
// and a first quote; then, if you ask for one, a paid plan paid in USDC or USDT from the same wallet (carbium.sh only).
//   npm i @solana/kit @noble/hashes
//   KEYPAIR=~/agent.json node onboard.ts            free account, key and Quote plan (Node 22.18+ runs TypeScript as is)
//   KEYPAIR=~/agent.json PLAN=starter node onboard.ts    and the Quote API Starter plan (or TIER=dev for an RPC tier)
//   KEYPAIR=~/agent.json ACCOUNT_KEY=read node onboard.ts  and an account API key for your automation (read or full), saved to ./carbium-account-key
import {
  createKeyPairSignerFromBytes, generateKeyPairSigner, getBase58Decoder, getBase64EncodedWireTransaction, getBase64Encoder,
  getTransactionDecoder, signBytes, signTransaction,
} from "@solana/kit";
import { blake3 } from "@noble/hashes/blake3.js";
import { readFileSync, writeFileSync } from "node:fs";

const DASH = process.env.CARBIUM_DASH ?? "https://carbium.sh";           // the account API
const DOOR = process.env.CARBIUM_DOOR ?? "https://services.carbium.sh";  // the RPC door
// Any Solana RPC sends the plan payment: an account with no credits (a wallet whose earlier account was deleted starts at 0) cannot use the door.
const SOLANA_RPC = process.env.SOLANA_RPC ?? "https://api.mainnet-beta.solana.com";

async function call(path: string, init: { body?: unknown; session?: string; post?: boolean } = {}) {
  const res = await fetch(DASH + path, {
    method: init.post || init.body !== undefined ? "POST" : "GET",
    headers: {
      ...(init.body !== undefined ? { "content-type": "application/json" } : {}),
      ...(init.session ? { authorization: `Bearer ${init.session}` } : {}),
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status} ${text}`);
  return JSON.parse(text);
}

async function rpc(key: string, method: string, params: unknown[]) {
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(DOOR, {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": key },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    });
    const r = await res.json();
    // A new key's first call can reach a node before its credits do: 429 CREDITS_PENDING (-32005, retryable). Wait and retry.
    if (r.error?.data?.reason === "CREDITS_PENDING" && attempt < 4) {
      await new Promise((ok) => setTimeout(ok, Number(res.headers.get("retry-after-ms") ?? 1000)));
      continue;
    }
    if (r.error) throw new Error(`${method}: ${JSON.stringify(r.error)}`);
    return r.result;
  }
}

// The sign-up challenge (an anti-abuse puzzle): the first u64 nonce whose blake3(challenge's UTF-8 bytes, then the nonce as 8 little-endian bytes)
// starts with at least `difficulty` zero bits.
function solve(challenge: string, difficulty: number): number {
  const c = new TextEncoder().encode(challenge);
  const buf = new Uint8Array(c.length + 8);
  buf.set(c);
  const view = new DataView(buf.buffer);
  for (let nonce = 0; ; nonce++) {
    view.setBigUint64(c.length, BigInt(nonce), true);
    let bits = 0;
    for (const b of blake3(buf)) {
      if (b === 0) { bits += 8; continue; }
      bits += Math.clz32(b) - 24;
      break;
    }
    if (bits >= difficulty) return nonce;
  }
}

// The agent's keypair: a solana-keygen JSON file (64 bytes), or a new one for a trial.
const signer = process.env.KEYPAIR
  ? await createKeyPairSignerFromBytes(new Uint8Array(JSON.parse(readFileSync(process.env.KEYPAIR, "utf8"))))
  : await generateKeyPairSigner();
const wallet = signer.address;

// 1. A one-use sign-up challenge (it lasts 300 s), solved locally.
const { challenge, difficulty } = await call("/v1/signup/challenge");
const nonce = solve(challenge, difficulty);

// 2. The sign-in message. It names the Carbium Terms and their version: signing it is your acceptance of them.
const { nonce_token, message } = await call("/v1/auth/wallet", { body: { step: "challenge", wallet } });
const signature = getBase58Decoder().decode(await signBytes(signer.keyPair.privateKey, new TextEncoder().encode(message)));

// 3. Verify. A new wallet opens a free account (500,000 credits) with one starter key; a known wallet signs in.
const { session_token } = await call("/v1/auth/wallet", {
  body: { step: "verify", wallet, nonce_token, signature, pow: { challenge, nonce } },
});

// 4. A paid plan, if you want one (carbium.sh only), before the first call: a wallet whose earlier account was deleted starts with
// no credits; an RPC tier (TIER) adds credits and a Quote plan (PLAN) adds none. The wallet pays the plan's price in USDC (or USDT with "mint") and a little SOL for the fee.
if (process.env.PLAN || process.env.TIER) {
  const want = process.env.PLAN ? { plan: process.env.PLAN } : { tier: process.env.TIER };
  const intent = await call("/v1/billing/crypto-intent", { session: session_token, body: { ...want, payer: wallet } });
  if (intent.sim_error) throw new Error(`the payment would fail: ${intent.sim_error}`);
  // `tx` is an unsigned v0 transaction on a fresh blockhash that pays this intent from your wallet: sign it and send it at once.
  const signed = await signTransaction([signer.keyPair], getTransactionDecoder().decode(getBase64Encoder().encode(intent.tx)));
  const sent = await fetch(SOLANA_RPC, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "sendTransaction", params: [getBase64EncodedWireTransaction(signed), { encoding: "base64" }] }),
  }).then((res) => res.json());
  if (sent.error) throw new Error(`sendTransaction: ${JSON.stringify(sent.error)}`);
  for (;;) {
    const s = await call(`/v1/billing/crypto-intent/${intent.intent_id}`, { session: session_token });
    if (s.status === "paid") break;
    if (s.status !== "open") throw new Error(`intent ${intent.intent_id} is ${s.status}`); // held: received, not applied, no plan bought: contact support; expired: start again
    await new Promise((r) => setTimeout(r, 2000));
  }
  console.log(JSON.stringify({ paid: intent.intent_id, account: await call("/v1/account", { session: session_token }) }));
}

// 5. The key's secret. A wallet account has no email, so read it here: list the keys, then reveal one.
const [key] = await call("/v1/keys", { session: session_token });
const { raw_key } = await call(`/v1/keys/${key.key_id}/secret`, { session: session_token, post: true });

// 6. The free Quote plan, unless you bought a paid one above: every live key gains `quote`, and the quote plane costs no credits.
if (!process.env.PLAN) await call("/v1/modules/quote", { session: session_token, body: { plan: "free" } });

// 7. A first call on the door. getSlot costs 1 credit: an account with none (a wallet whose earlier account was deleted, which
// bought nothing or only a Quote plan) is answered 402 -32002 `credits exhausted` until it buys an RPC tier (TIER=dev).
const slot = await rpc(raw_key, "getSlot", []).catch((e) => {
  if (String(e).includes('"code":-32002')) return "no credits: buy an RPC tier (TIER=dev) to call RPC";
  throw e;
});

// 8. A first quote: 0.001 SOL to USDC, amounts in base units as strings. `swap` with its `quoteId` builds the transaction to sign.
const quote = await rpc(raw_key, "quote", [{
  src_mint: "So11111111111111111111111111111111111111112", dst_mint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  amount_in: "1000000", slippage_bps: 50,
}]);
const now = await call("/v1/account", { session: session_token }); // the tier after any purchase above
console.log(JSON.stringify({ wallet, account_id: now.account_id, tier: now.tier, key_id: key.key_id, slot, usdc_out: quote.destAmountOut }));

// 9. An account API key for your automation, if you ask for one (ACCOUNT_KEY=read or full). It runs the account by API without
// this wallet, and it cannot pay or cancel. Its value is shown once: it goes to a file only you can read, never to the console.
if (process.env.ACCOUNT_KEY) {
  const made = await call("/v1/account/api-keys", { session: session_token, body: { name: "automation", access: process.env.ACCOUNT_KEY, expires_in_days: 90 } });
  writeFileSync("carbium-account-key", made.raw_key + "\n", { mode: 0o600 });
  const self = await call("/v1/api-key", { session: made.raw_key }); // the key as the bearer: its own record
  console.log(JSON.stringify({ account_api_key: self.prefix, access: self.access, expires_at: self.expires_at, saved: "carbium-account-key" }));
}
```

Never open more accounts for more free capacity (see Acceptable use).

### Sign in

- There are four ways to sign in: an emailed 6-digit code, Google, X, or a Solana wallet. You can connect your own wallet, or have the dashboard create a sign-in key in the browser. It shows the key's secret once and never sends it, so save it.
- Asking for a code for a new address creates the account. A code expires in 10 minutes. A wrong or expired code answers 401. Too many tries answer 429 `too many PIN attempts`: ask for a new code later.
- Every sign-up and sign-in needs the current Carbium Terms ticked. `GET /v1/terms` gives the version and the link. Without the tick the answer is 400 `terms acceptance required`. A wallet sign-in accepts them by signing the message that names them (Agents, above).
- To get a session token by email: `POST /v1/login/pin` with `{"email": "<address>", "terms_version": "<version from GET /v1/terms>"}` answers `{"pin_token": "…"}` and mails the code. Then `POST /v1/login/pin/verify` with `{"pin_token": "…", "code": "<6 digits>", "terms_version": "<same version>"}` answers `{"session_token": "…", "account": {…}}`. Send the token as `Authorization: Bearer <session token>`; it works only on the dashboard that issued it. An address with no account also sends `"pow": {"challenge": "<the challenge string>", "nonce": <number>}`, solved as in Agents, steps 1 and 2 (above): that opens the account and mails the code. Without a `pow`, with a wrong, used or expired one, or over the registration cap, it still answers 200 with a `pin_token` but opens nothing and mails no code, so the verify answers 401. An address that already has an account is never asked for a `pow`. Google and X sign-in run on the dashboard; wallet sign-in is also an API (Agents, above).
- A code or link asked for before the account was deleted answers 403 `this account was deleted`. Signing in later with the same email, wallet, Google or X opens a new account.

### Starter key and free credits

- When you sign in with no live key, you get one starter key. On FREE it carries `rpc` and `ws`; FREE has no carbon stream.
- A new account gets one free grant of credits, once. Nothing tops it up later; paid plans add credits. `GET /v1/balance` answers `granted`, `used` and `remaining`.
- An identity (email, wallet, Google or X account) whose earlier account was deleted gets no free grant on its new account. It can still buy a plan.

### Keys

Live keys per account: FREE 1, DEV 5, BUSINESS 10, PRO 50. Revoked keys do not count. A create over the limit answers 409 `key limit reached: the <plan> tier allows <n> keys; revoke one or upgrade`.

| Action | Call | What comes back and what happens |
|---|---|---|
| List | `GET /v1/keys` | Every key with its prefix, name, scopes, allowlist, caps, status and `revoked_at`. |
| Create | `POST /v1/keys` `{"name": "server-1", "scope": ["rpc", "ws", "grpc", "quote"]}` | `key_id`, `prefix`, `name` and the full `raw_key`. Without `scope` the key gets `rpc`, `ws`, `grpc` and `das`. `quote` needs the Quote module: 409 `quote module required`. Names are at most 48 characters. |
| Show the secret again | `POST /v1/keys/{id}/secret` | `{"available": true, "raw_key": "c_serv_…"}`. An old key whose secret was never stored answers `available: false`: rotate it. Too many reveals answer 429 `too many key reveals`. |
| Rotate | `POST /v1/keys/{id}/rotate` | A new `raw_key` and `prefix` on the same key, which keeps its scopes, allowlist and caps. The old secret is refused at once on every new call, handshake and subscribe (`unknown api key`), so update every client right away; a WebSocket or stream already open with it ends within about 2 s (WebSocket close `1008 key_revoked`; a Carbon stream ends UNAUTHENTICATED `api key revoked`). |
| Revoke | `POST /v1/keys/{id}/revoke` | Every plane refuses the key on new calls, handshakes and subscribes (`api key revoked`), and its stored secret is wiped; a WebSocket or stream already open with it ends within about 2 s (`1008 key_revoked`, or UNAUTHENTICATED `api key revoked`). It stays listed with `revoked_at` set; its `status` does not change, so check `revoked_at`. |
| Delete | `DELETE /v1/keys/{id}` | `{"deleted": true}`. The key leaves the list. A live key is refused on every plane at once. The dashboard has no delete: a revoked key leaves its list, and this call removes it from the API's list too. |
| Scopes | `PATCH /v1/keys/{id}/scope` `{"scope": ["rpc", "ws", "das"]}` | The stored scopes. The list (`rpc`, `ws`, `grpc`, `quote`, `das`) replaces the whole set, so a plane left out is removed. Name at least one plane. A revoked key answers 409 `key is revoked`. |
| Rename | `POST /v1/keys/{id}/name` `{"name": "…"}` | The stored name. |

Each key you create, and the starter key your first sign-in makes, sends one email to the account's address. It holds the full key, the planes the key serves and each plane's endpoint on `services.carbium.sh`, with the carbon stream on `https://services.carbium.sh:9443` and the header `x-token`. A rotation sends one email the same way with the new secret, and says the old one is refused with 401. A revoke and a delete each send one email naming the key, without the secret. An account with no email address (signed in by wallet) gets none: it reads the key with `POST /v1/keys/{id}/secret`. If you did not create or delete a key, sign in and check KEYS.

### IP allowlist

`PATCH /v1/keys/{id}/allowlist` with `{"ip_allow": ["203.0.113.7", "203.0.113.0/24", "2001:db8::/32"]}`:

- Send the whole list every time. `[]` admits any address, and that is the default.
- The list holds up to 16 IPv4 or IPv6 addresses or CIDRs. A bare address means its /32 or /128.
- The answer is the stored list.
- Errors (400): `too many allowlist entries: at most 16`; `'<entry>' is not an IPv4 or IPv6 address or CIDR …`; `'<entry>' has bits set past its /<n>: use <network>/<n> …`.

Every plane (RPC, WebSocket, stream) refuses a call from an address off the list. On RPC that is HTTP 403, `-32001`, reason `IP_NOT_ALLOWED`. Do not retry: add the address. The dashboard itself does not check the list, so you can always fix it there.

### Per-method caps

`PATCH /v1/keys/{id}/caps` with `{"per_method_caps": [{"method_class": "write_send", "rps_ceiling": 2}]}` sets one key's own requests-per-second ceiling on one group of methods. The ceiling sits below the account's plan rate.

- The list replaces the key's caps; `[]` clears them.
- `method_class` names the group:
  - `o1_cached`: `getSlot`, `getBlockHeight`, `getEpochInfo`, `getLatestBlockhash`, `isBlockhashValid`, `getHealth`, `getVersion` and the other cached reads
  - `bounded_read`: `getSignatureStatuses`, `getRecentPrioritizationFees`, `getBlockTime`, `getLeaderSchedule`, `getVoteAccounts`, `getClusterNodes` and similar
  - `bounded_slot`: `getAccountInfo`, `getMultipleAccounts`, `getTokenAccountBalance`, `getTokenSupply`
  - `write_send`: `sendTransaction`
  - `compute`: `simulateTransaction`
  - `bounded_disk`: `getTransaction`, `getSignaturesForAddress`, `getTransactionsForAddress`, `getBlock`
  - `range`: `getBlocks`, `getBlocksWithLimit`
  - `scan`: `getLargestAccounts`, `getSupply`
  - `gpa`: `getProgramAccounts`
  - `das`: the 10 DAS methods together
- `getBalance`, `getMinimumBalanceForRentExemption`, `getFeeForMessage`, `getBlockCommitment`, `getTokenAccountsByOwner` and `getTokenAccountsByDelegate` cannot be capped. Any other `method_class` answers 400 `unknown method_class '<name>'`.
- Past its ceiling, a call in that group gets the ordinary 429 (`-32005`; wait `retry-after-ms`). Other groups and other keys are not affected.

### Plans and prices

The plans are FREE, DEV, BUSINESS (`buss` on the wire) and PRO, each by the month. Live prices and the credits each plan adds come from the dashboard's `GET /v1/plans` (public, no session):

- `plans[]`, one entry per paid plan: `tier`, `amount_minor` (US cents), `currency`, `period` (`month`), `sellable`, `recurring` (also sold as auto-renew), `card` (sold by card here) and `credit_grant` (the credits each paid month adds; `null` means unmetered).
- `quote[]`: the Quote module's plans, with their `rps`.

Never hard-code a price. Read this endpoint. Per-plan rates and connection limits are in the RPC, WebSocket and stream sections. The quote ladder is under Quote plans and what counts.

- **Moving up:** you can move up at any time, except by card for one month while another plan renews on the card (see Paying by card or in USDC or USDT). The unused part of the current term carries over by value.
- **Same plan again:** buying it extends its term. While it renews by card, buy it for one month or in USDC or USDT.
- **Moving down:** a lower plan is refused while a higher one runs (400 `'<plan>' is below the current tier '<plan>'`). Buy it once the term ends.
- **Credits:** each paid month adds its plan's credits, and unspent credits stay on the account. The 402 `credits exhausted` is answered by renewing or buying a plan.
- **Term end:** when a term ends without a renewal, the account drops to FREE and its keys keep working at FREE limits. A card renewal gets one extra day for its charge to land first.
- **Quote module:** add it on MODULES. Its free plan is `POST /v1/modules/quote` `{"plan": "free"}`; paid quote plans are bought like a plan, below. Adding the module turns `quote` on for every live key.
- **No sales:** a dashboard that does not sell answers 403 `purchases are not offered here`.

### Paying by card or in USDC or USDT

Card through Stripe is the main way to pay. You can also pay in USDC or USDT from your own wallet.

- **Card:** `POST /v1/billing/checkout` with `{"tier": "dev", "recurring": true}`, or `{"module": "quote", "plan": "starter"}` for a quote plan. It answers a Stripe Checkout `url`, plus `amount_minor` and the `term` it would buy.
  - `recurring: true` renews every month on the card. False or absent buys one month.
  - The plan and the Quote plan can each have one renewal. Buying the one that renews again with `recurring: true` answers 400 `'<plan>' already renews automatically; manage it from Billing` (`quote '<plan>' …` for the Quote plan). A higher plan bought with `recurring: true` replaces the renewal. A one-month card buy of another plan while one renews answers 400 `this account renews '<plan>' automatically: buy '<plan>' with auto-renew on, or turn auto-renew off from Billing first`. Paying in USDC or USDT is allowed and moves the plan off the card.
- **USDC or USDT on Solana:** `POST /v1/billing/crypto-intent` with `{"tier": "dev", "months": 3, "mint": "<USDC or USDT mint>", "payer": "<your wallet>"}`. For a quote plan send `"plan"` in place of `"tier"`. Without `mint` you pay in USDC.
  - The answer is a Solana Pay request: `recipient`, `mint`, `amount` in base units (`amount_ui` as text), `reference`, `expiry`, `solana_pay_url`. With `payer` it also carries the unsigned transaction `tx` to sign.
  - 1 USDC or USDT pays 100 US cents.
  - Pay before `expiry`, 30 minutes after the intent opened. The plan starts once the payment is finalized. Poll `GET /v1/billing/crypto-intent/{intent_id}` for its `status`. The whole sequence for an agent, with the mints, the SOL it needs and every status, is under Agents, above.
  - You can buy 1 to 12 months (400 `months must be 1 to 12`). A prepaid term never renews.
  - Paying in USDC or USDT for a plan the card renews moves it off the card, and the card is not charged again.

### Renewals, low balance and invoices

- **Manage billing** (`POST /v1/billing/portal` answers a `url`; add `?module=quote` for the Quote plan) opens Stripe's portal for a plan bought by card with auto-renew on, where you change the card, cancel and get invoices. A one-month card plan has no portal (400 `no auto-renewing subscription on this account`); its invoice is `GET /v1/payments/{id}/document`.
- `GET /v1/payments` lists every payment, card, USDC and USDT, newest first.
- `GET /v1/payments/{id}/document` answers a card payment's Stripe `pdf` and `page`. A USDC or USDT payment answers 404; its row is the receipt.
- `GET /v1/invoices` gives monthly credit statements (`period_start`, `period_end`, `granted`, `used`), with the current month first and `current: true`.
- The Billing card on ACCOUNT lists payments with their invoices and exports them as CSV.
- The account's email gets:
  - a receipt for each payment
  - a monthly usage statement
  - one low-balance notice a month while the balance is under 50,000 credits
  - a reminder 3 days before a term that does not renew ends
  - a notice when a card renewal fails. Stripe retries the card; update it in Manage billing.

### Cancel a renewal

On the dashboard, the Billing card on ACCOUNT shows the plan and the Quote plan with the date each renews or ends, and **Cancel renewal** while it renews by card (**Resume renewal** after a cancel, while the term runs). The call is `POST /v1/billing/renewal`; add `?module=quote` for the Quote plan.

- **200:** `{"module": null, "renews": false, "ends_at": "YYYY-MM-DD"}`. The plan keeps every feature to `ends_at`, the card is not charged again, and there is no refund.
- **409:** `this plan does not renew; it ends on <date>` for a prepaid or one-month term (there is nothing to cancel), or `this plan has no renewal to cancel`.
- **503:** `the renewal was not stopped; try again`.

To undo the cancel while the term still runs, call `DELETE /v1/billing/renewal` (same `?module=`). It answers `{"renews": true, "ends_at": …}`, or 409 `no cancelled renewal to resume while its term runs`.

### Delete the account

On the dashboard, **Delete account** on the Billing card warns twice: first that every key stops, then with what the delete ends (step 1 below) or the reason it is refused. Then it asks you to type `DELETE`.

1. `GET /v1/account/deletion` shows what a delete ends: `terms` (each paid plan or module with its `ends_at` and whether it `renews`), `keys` (live keys it revokes) and `credits_remaining`. If a delete would be refused now, `blocked` gives the reason:
   - `this account is already deleted`
   - `account suspended: contact support`
   - `a payment on this account is held for a refund: contact support`
   - `a crypto payment is in flight; try again once it settles or expires`
2. `DELETE /v1/account` with `{"confirm": "DELETE"}`. It is the same word for every account.
   - **200:** `{"deleted": true, "keys_revoked": <n>, "renewals_stopped": <n>}`. Renewals stop, any paid time left is lost with no refund, every service key and every account API key is revoked, and the session ends (the next call is 401).
   - **400:** `type DELETE to confirm`.
   - **409:** one of the `blocked` reasons above.
   - **503:** `the account was not deleted: …`. What already stopped stays stopped; the same call finishes the delete.

Payment and invoice records are kept. A code or link asked for before the delete answers 403 `this account was deleted`. Signing in later with the same email, wallet, Google or X opens a new account, with no free credits.

## Account API keys (run the account by API)

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

## Common mistakes

- The short dashboard prefix (`c_serv_` plus four characters) instead of the whole key.
- `x-api-key` on the gRPC stream: it reads metadata `x-token` (or `authorization: Bearer`).
- A FREE key on the gRPC stream: not a wrong key, FREE has no stream (`PERMISSION_DENIED` `streaming is not included in this tier; upgrade the plan`).
- `"params"` before `"method"`, or a third permit method in one batch.
- `maxSupportedTransactionVersion` absent or 0 on `getTransaction`, `getBlock` or `blockSubscribe`.
- Retrying a 4xx unchanged, or re-signing a swap that may still land.
- Calling RPC methods over the WebSocket: they answer `-32601`.
- Expecting `accountSubscribe`, or a gRPC `accounts` list, to stream a plain SOL wallet.
- Other providers' quote params (`inputMint`, `outputMint`, `amount`, `onlyDirectRoutes`): this quote takes `src_mint`, `dst_mint`, `amount_in`, `slippage_bps`, an optional `dex`, an optional `txVersion` and an optional `swapTag`, and refuses any other name.

