## DAS: getAsset, getAssets, getAssetBatch, getAssetsByOwner, getAssetsByGroup, getAssetsByCreator, getAssetsByAuthority, searchAssets, getNftEditions, getTokenAccounts

Contents, with the line each part starts on in this file:

- Rules: line 18
- Limits: line 33
- Billing: line 48
- Coverage: line 52
- Errors: line 68
- Quick start: line 102
- A client with retries (Node 18+, global fetch): line 130
- How we test it: line 184
- Common mistakes: line 202
- Agent checklist: line 213

The ten Digital Asset Standard methods are JSON-RPC calls on the RPC endpoint, `POST https://services.carbium.sh`, with the same key. Answers come from our own index of the chain's finalized state, in the field names and answer shapes of the Helius DAS API, so a DAS client switches by its URL alone: `https://services.carbium.sh/?api-key=<KEY>`, or the key in the `x-api-key` header.

### Rules

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

### Limits

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

### Billing

Each served call costs 1 credit, and each served element of a batch costs 1, so a batch of three costs 3. These cost nothing: an error answer, a batch element that fails, times out or goes over the answer cap, a call refused before it runs (key, rate, credits, size) and the `nativeBalance` read. Every admitted call spends its rate cell, one that ends in an error included.

### Coverage

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

### Errors

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

### Quick start

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

### A client with retries (Node 18+, global fetch)

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

### How we test it

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

### Common mistakes

- Paging deep with `page`. Past 500,000 items it is refused, and past 10,000 on an unanchored searchAssets or on a mint's token accounts. Walk by `cursor`.
- Reading `total` as the full count. It counts this page only. Ask for `showGrandTotal`.
- Expecting images, attributes, `content.files` or `content.links` from the off-chain JSON. Fetch `content.json_uri` yourself.
- Sorting by `created` and expecting creation order. It returns id order.
- Mixing DAS and other RPC methods in one batch.
- Using the Umi DAS plugin without `heliusCompatibility: true`.
- Retrying a `-32602`, or looping on `-32022`.
- Sending more calls at once than the plan's in-flight cap allows. Queue them per key.

### Agent checklist

- Call `https://services.carbium.sh` with the full key in `x-api-key` or `?api-key=`.
- Send the Helius field names, and put `"method"` before `"params"`.
- Walk lists by `cursor` with `limit` 1000 until a page comes back short.
- Keep calls in flight per key within your plan; a batch counts as one. Batch DAS calls only with each other, up to 100 a batch.
- Retry `-32005`, `-32011`, `-32021`, `-32024`, `-32026` and `-32603` with jittered backoff, and honour `retry-after-ms`; narrow the request instead on `response too large` and `could not finish this read in time`. Retry `-32022` and `-32023` later. Stop on every other code.
- Apply unserved `searchAssets` filters on your side. Name an owner, creator, authority or grouping before you use `showGrandTotal`, `burnt: true`, `interface` `MplCoreGroup` or the `updated` and `recent_action` sorts.
- Fetch off-chain JSON yourself, and expect no prices and no compressed NFTs.
- Budget 1 credit per served call.

