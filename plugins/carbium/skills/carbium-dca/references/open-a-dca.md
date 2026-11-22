## Open a DCA

Contents, with the line each part starts on in this file:

  - Open: fields: line 26
  - What a build answers: line 42
  - Open: the check: line 55
  - Run many DCAs: line 66
  - Max price steps: line 82
  - Tokens: line 92
  - Fees and deposits: line 100

Links from this file to other files: #schedule-limits and #addresses are in SKILL.md; #check-sign-and-send is in references/check-sign-and-send.md.

An unsigned transaction that opens a schedule, here 2 buys of 10 USDC, one a day.

```bash
curl -s -X POST "$DCA_API/open" -H 'content-type: application/json' \
  -d '{"owner":"'$OWNER'","inputMint":"'$IN_MINT'","outputMint":"'$OUT_MINT'","cycles":2,"amountPerCycle":"10000000","intervalSecs":86400}'
```

An opening is not safe to repeat: a build after the first one landed opens a second DCA and pays a second opening fee. With your own `index` that build answers `position_exists`.

Check: the wallet holds `cost.requiredLamports`, and the amounts in `summary` are the ones you sent.

#### Open: fields

Other bodies: `"totalAmount":"20000000","frequency":"daily"` in place of `amountPerCycle` and `intervalSecs`, `"maxPrice":"0.0014"` for a max price, the wrapped SOL mint for SOL.

| Field | Required | Description |
|---|---|---|
| `owner` | yes | The wallet that owns and signs |
| `inputMint`, `outputMint` | yes | The token you spend and the token you buy ([Tokens](#tokens)) |
| `cycles` | yes | Number of buys, 1 to 65,535 |
| `amountPerCycle` | yes, or `totalAmount` | One buy in input base units. `totalAmount` is split evenly in its place, rounded down: the remainder is not scheduled |
| `intervalSecs` | yes, or `frequency` | Seconds between buys, up to one year. `frequency` is one of `hourly`, `daily`, `weekly`, `biweekly`, `monthly` |
| `maxPrice` | no, or `minOutE6` | Your max price, in input tokens per whole output token: no buy runs above it ([Max price steps](#max-price-steps)) |
| `maxSlippageBps` | no | Default 50, at most 300 |
| `startAt` | no | Unix seconds of the first buy, up to 30 days ahead. 0 or absent: now |
| `index` | no | Which of the owner's DCAs for this output token, 0 to 255. Absent: the first of 0 to 15 that is free when the build runs |

#### What a build answers

| Field | Meaning |
|---|---|
| `txn_base64` | The unsigned transaction, to check, sign and send |
| `blockhash`, `last_valid_block_height` | Its blockhash and the last block height at which it can land |
| `position` | The DCA's address |
| `index`, `escrowAccount`, `authority` | `/open`: the index used, the escrow's address and the DCA's own authority |
| `cost` | Lamports. `feeLamports` on every build. `/open` adds `lamportsLocked`, `feeAccountRent`, `middleAccountsRent`, `wrapLamports` and `requiredLamports`, the least SOL the wallet must hold for this opening. `/close` adds `middleShortfall` ([Fees and deposits](#fees-and-deposits)) |
| `cost.wrapLamports` | Paying with SOL: the schedule plus the fee, plus the rent of a wrapped SOL account when the wallet has none. Else `"0"` |
| `summary` | Its addresses, mints, token programs and amounts are facts to compare with your request. `instructions` is a list of labels whose wording can change. A close adds `middleDebt` |
| `plan` | `/open`: what the transaction does, in fields |

#### Open: the check

- `refusals('open', fromB64(built.txn_base64), want, ctx)` returns no reason, with `want` and `ctx` as in [Check, sign and send](#check-sign-and-send).
- It is a v0 transaction with no lookup table, so every account is visible. The owner is the only signer and pays the network fee.
- It calls only the DCA program, the creation of the owner's own token accounts for the two tokens and of at most two for classic tokens the route passes through, each owned by the DCA's own authority, and an optional compute budget under a cap.
- Paid with SOL, it also wraps it: one transfer of exactly the schedule plus the fee from the wallet into its own wrapped SOL account, placed before the open, and a sync of that account.
- It may close that account back to the wallet after the DCA's instructions. The service leaves it open when the wallet already had one.
- It has exactly one `open` and one keeper setting, for your owner, tokens, amount, number of buys, interval, start and max price. With `want.minOutE6` at `0n`, only an open with no max price passes.
- The keeper it names is Carbium's keeper and no other key.
- The fee rate it names is the `feeBps` you were quoted, inside 5 to 50 bps as the program also requires. The fee account is the one `ataOf` derives for Carbium's fee wallet and the input mint, and no token transfer rides beside the open.

#### Run many DCAs

Many schedules from one wallet, each opening safe to retry because you choose its `index`.

```bash
curl -s -X POST "$DCA_API/open" -H 'content-type: application/json' \
  -d '{"owner":"'$OWNER'","inputMint":"'$IN_MINT'","outputMint":"'$OUT_MINT'","cycles":2,"amountPerCycle":"10000000","intervalSecs":86400,"index":7}'
```

The answer: the `index` you passed and `position`, the address that comes from the owner, the token bought and `index`. The token paid with is not part of it.

- Sending the same signed transaction again is safe: it cannot land twice.
- One wallet can hold up to 256 DCAs for one token bought, and Carbium runs at most the wallet's cap of them ([Schedule limits](#schedule-limits)).
- Closing frees the index. A new DCA at that index has the same address, a new `openedSlot`, and buys that start again at cycle 1. Keep `openedSlot` with each DCA you follow.
- `GET /positions?owner=` answers up to 100 open DCAs in one call. Read `GET /position/{address}` for a DCA whose `cyclesDone` moved.

#### Max price steps

- `maxPrice` and `minOutE6` are one limit. `minOutE6` is the way the program stores it: the least output base units per 1,000,000 input base units.
- For no max price leave both out at `/open`, or send `maxPrice: null`. Each buy then runs at the price of its moment, inside your slippage limit.
- A `minOutE6` of 0, or a `maxPrice` so high that it is held as 0, is refused `min_out_zero`. `maxPrice: null` beside a `minOutE6` is `bad_request`.
- Where `rateE6` in the quote is small, the max price moves in steps of 1/`rateE6` (at `rateE6` 100 a step is 1%), and a `maxPrice` you send is held at the next step above it.
- `/open` and `/update` answer the price held as `summary.maxPriceHeld` (null for no max price), beside `summary.minOutE6`.
- A cheap token with many decimals paid into USDC or SOL is such a pair. Send `minOutE6` yourself to choose the step.
- Where `rateE6` is under 1 no max price sits over the price now: open such a pair with no max price.

#### Tokens

- A DCA takes any two different tokens that Carbium's router can route at your amount: classic SPL tokens, Token-2022 tokens, and SOL at either end. A pair it cannot route answers `no_route`.
- For SOL at either end pass the wrapped SOL mint ([Addresses](#addresses)): the wallet pays plain SOL and receives plain SOL.
- When the route at your amount passes through a Token-2022 token, the DCA asks again for a route straight from one token to the other and uses that. With none, the quote and the opening answer `middle_token_2022`.
- A Token-2022 token is refused, by name, when it charges a transfer fee, runs a transfer hook, cannot be transferred, starts its accounts frozen, is paused, or carries an extension the DCA does not know (the `token_*` codes).
- So is the owner's own Token-2022 account when it requires a memo or takes only confidential transfers, and the account the owner pays from when its CPI guard blocks program transfers (the `owner_*` codes).

#### Fees and deposits

The owner pays each of these except the router fee, which comes out of the buy.

| What | How much | Comes back |
|---|---|---|
| Opening fee | 5 bps (0.05%) of the whole schedule, in the input token, on top of the schedule | No, even when you close early |
| Router fee | 5 bps of each buy | No |
| Network fee | 5,000 lamports for each transaction the owner signs. Carbium pays it for every buy | No |
| Deposits | About 0.01 SOL of rent for the DCA's accounts, a little more for a Token-2022 token's. `cost.lamportsLocked` is the exact amount | At close, except the rent of your own account for the bought token if the opening created it: that account stays yours |
| Carbium's fee account | `cost.feeAccountRent`: about 0.0015 SOL for a classic token, more for a Token-2022 token with extensions, 0 when the account exists | No |
| Route accounts | `cost.middleAccountsRent`: about 0.0015 SOL each for up to two at opening, 0 for a direct route | At close, for the empty ones |
| Wrapped SOL account | About 0.0015 SOL, when you pay with SOL and the wallet has none | In the same transaction |

- `feeBps` in the quote is the opening fee rate. The program takes the fee itself, inside the open: `amountPerCycle` x `cycles` x `feeBps` / 10,000, rounded down, from the owner's input account to Carbium's fee account for the input token.
- Paying with SOL, the wallet needs the schedule plus the fee in SOL on top of the deposits. The opening wraps exactly the schedule plus the fee and nothing else.
- A route that passes through tokens other than SOL needs a token account for each of them, owned by the DCA's authority. If a later buy's route needs another one, Carbium's keeper pays for it and the DCA records that amount.
- Closing pays the keeper back exactly that: first from the DCA's authority account and the route accounts the close closes, then from the owner's wallet for the rest.
- That rest is `cost.middleShortfall`: `"0"` unless the DCA owes more than its authority account holds (about 0.003 SOL, part of the opening's deposits) plus the rent of the route accounts closed with it.

