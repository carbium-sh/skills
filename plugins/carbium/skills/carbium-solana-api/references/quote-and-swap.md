## Quote and swap (`quote`, `swap`, `prices`, `health`)

Contents, with the line each part starts on in this file:

- `quote`: params: line 28
- Venue families (`dex` labels): line 42
- `quote`: result: line 68
- On-chain router fee (`platformFee`): line 96
- `quote`: errors: line 111
  - `-32051` `error.data.why`: what an agent can act on: line 144
- `swap`: params: line 169
- `swap`: result: line 177
- Signing, sending and confirming: line 199
- `swap`: refusals: line 208
- `prices`: line 229
- `health`: line 240
- Quote plans and what counts: line 244

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

