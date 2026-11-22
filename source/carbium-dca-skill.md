---
name: carbium-dca
description: "Run Carbium DCAs from your own app or agent: open, read, pause and close orders that buy a token on a schedule on Solana. Use it for scheduled buys or the Carbium DCA API."
---

# Carbium DCA API

## Overview

A DCA buys one token with another in equal parts on a schedule. The API builds each transaction, you check and sign it with the owner's wallet, and Carbium's keeper sends each buy inside the limits the owner signed. The funds wait in an on-chain escrow, and only the owner can take them back.

| What | Value |
|---|---|
| Access | No sign-up and no key |
| Network | Solana mainnet, real funds |
| Tokens | Classic SPL tokens, Token-2022 tokens, and SOL at either end |
| Fees | 5 bps of the whole schedule at opening, 5 bps of each buy |

#### Who can do what

- The opening moves the whole schedule into the DCA's escrow and names Carbium's keeper as the key that sends its buys.
- The escrow is a token account whose only authority is an address of the DCA program, one per DCA. No Carbium key can take the funds out, and Carbium never holds the owner's key.
- The keeper can do one thing: send a due buy, a swap of that buy's part through Carbium's router. The program takes the amount from the schedule, not from the keeper, and allows one buy per interval.
- The program refuses a buy outside the slippage limit, measured from the quote the keeper sends with it, or over the max price, the owner's own limit held on chain.
- What is bought goes to the owner's own token account in the same transaction, or to the wallet as plain SOL.
- Only the owner can pause, resume, change the limits, withdraw and close.
- With the keeper down, no buys run and the funds stay in the escrow. With the API down, the owner can still close or withdraw with a transaction built from the program's public interface.
- The program can be upgraded by a key held by Carbium. Its interface is published on chain ([Addresses](#addresses)).

## For agents

This API is made to be driven by a coding agent: the agent builds and checks each transaction, and the owner still signs. Paste this prompt into any agent:

```text
Fetch https://carbium.io/docs/dca/skill.md and follow it to set up a Carbium DCA for me on Solana, then ask me what to buy, what to pay with, how much per buy, how many buys and how often.
Before anything is signed, run the check that file describes (refusals in check.mjs) on the built transaction and show me the schedule, the fee rate, the total with the fee and the result of the check; amounts are integers in the token's base units.
I sign with my own wallet: never ask for, print or store a seed phrase or a private key, and send nothing until I say yes.
```

For Claude Code, this line installs the page as a skill:

```bash
mkdir -p ~/.claude/skills/carbium-dca && curl -fsSL https://carbium.io/docs/dca/skill.md -o ~/.claude/skills/carbium-dca/SKILL.md
```

Codex, Cursor and other agents read the same file from their own skills folder, or from a pointer line in `AGENTS.md`.

#### Rules for an agent

- Use this file when a task opens, reads, changes or closes a Carbium DCA, or builds on its API.
- The owner signs. Never ask for, print or store a seed phrase or a private key. A script that signs reads a key file whose path the owner gives (`KEYPAIR` in the example).
- Before any signature, run `refusals` from `check.mjs` on the built transaction. After signing, run `walletChanges` on the signed one. If either returns a reason, stop: do not sign, do not send.
- Amounts are integers in the token's base units, as decimal strings. Take decimals and the token program from the mint account.
- This is Solana mainnet and the funds are real. Show the owner the schedule, the fee rate and the total with the fee, and send only on the owner's yes.
- An opening is not safe to repeat. Pass your own `index` and keep it, so a retry answers `position_exists`.
- Check your work: read `ok` on every answer, then read `GET /position/{address}` and report `status`, `cyclesDone` of `cyclesTotal`, `escrow` and `nextTs`.

## Endpoints

The read requests on this page can be run in place; the builds and the send are shown to copy, because they need the owner's wallet.

```bash
export DCA_API=https://dex.carbium.io/api/dca
export OWNER=YourWalletAddress
export IN_MINT=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v OUT_MINT=AT79ReYU9XtHUTF5vM6Q4oa9K8w7918Fp5SU7G1MDMQY
```

| Call | What it does |
|---|---|
| `GET /health` | `ok` is true whenever the API answers. The keeper's state is in `heartbeat.at`, `stream.connected` and `streamSlotLag` |
| [`GET /quote`](#quote) | Price for one buy, the opening fee rate and the limits |
| [`GET /positions?owner=`](#get-positions) | The owner's open DCAs, in the order they were opened |
| [`GET /position/{address}`](#get-position-address) | One DCA with its buys |
| [`GET /history?owner=`](#get-history) | The owner's past DCAs, newest close first |
| [`POST /open`](#open-a-dca) | Builds the transaction that opens a DCA |
| [`POST /update`](#post-update) | Builds a pause, a resume, or a max price set, changed or removed |
| [`POST /withdraw`](#post-withdraw) | Builds a withdrawal from the escrow |
| [`POST /close`](#post-close) | Builds the close |
| [`POST /send`](#check-sign-and-send) | Sends a transaction this API built, once the owner signed it |

```bash run
curl -s "$DCA_API/health"
```

#### Requests and answers

- `$DCA` is a DCA's address, `position` in the opening's answer. `$BUILT` is a build's `txn_base64` and `$SIGNED` that transaction signed by the owner, both base64.
- JSON in and out. Call from a server or a script: a browser page on another site is refused, and so is a call that carries another site's `Origin` or `Referer`. The read requests this page runs are the one exception.
- With no key, a refusal the DCA service explains arrives with HTTP 200, except its rate refusals, which stay 429. With a key it carries the HTTP status listed under [Errors](#errors).
- A refusal from in front of the service keeps its HTTP status for every caller: 401, 403, 404, 429 and 502 to 504.
- Amounts are integers in the token's base units, sent and returned as decimal strings. USDC has 6 decimals: 10 USDC is `"10000000"`.
- So are `minOutE6`, `last_valid_block_height` and the times `nextTs`, `openedTs`, `closedTs` and a buy's `ts`, in unix seconds.
- Counts, rates in bps, `intervalSecs`, slots, `index` and `lastTry.at` are JSON numbers.
- A request takes a whole number up to 9007199254740991 or a decimal string. Send larger amounts, and any `maxPrice`, as a decimal string.
- `/positions` answers `positions` and `/history` answers `orders`, at most 100 a call, with `next`. When `next` is not null, the same call with `&after={next}` answers the rest.

#### Addresses

| What | Address |
|---|---|
| The DCA program | `dca1HQzdAnibwxoE7vMYdEmYhqggVUjADsB9YAXdDoi` |
| Its interface on chain (Program Metadata account) | `Gh6d4Tr9TgKbnQdhJmvrhdmnWQd7NpitL9jHLhdqV9dG` |
| Carbium's keeper | `dcaqWvrzmkUbHSdAmATQU3m8GKJAyhapUzfvibM4DJf` |
| Carbium's fee wallet | `cqvz12kjCQe6ck4PayVNBe3wsnbh8AXUDsUpB4RPTVV` |
| Its fee account for USDC | `2sAZArTKkqhBKM3XboQYNbRwgGe8MC3X8RZBVpfW7z6H` |
| Wrapped SOL mint | `So11111111111111111111111111111111111111112` |
| Classic token program | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` |
| The DCA with a form | https://dex.carbium.io/dca |

## Authentication

The API needs no sign-up and no key. A free key is made at once, with no approval, and counts calls by account.

1. Sign in on https://dex.carbium.io. The account needs Google or X as a sign-in method.
2. Open the account menu and choose DCA API access.
3. Press Add key and copy it.
4. Send it as the `x-api-key` header.

#### Copy, replace or revoke a key

Copy a key again or revoke it there at any time. A new key starts working within a minute and answers 401 `key_unknown` until then. A revoked key answers the same within a minute.

To change a PLUS or PRO key, press Replace there: the new key keeps the rate and the schedule limits, and revoking your only one gives both up. This key is separate from the Swap API keys of carbium.sh.

## Rate limits

| Access | Requests a second | Counted by | How to get it |
|---|---|---|---|
| No key | 50 | IP address | Nothing needed |
| Free key | 50 | Account, all its free keys together | [Get a key](#authentication) |
| Higher rate | 100 (PLUS) or 400 (PRO) | That key | [Get a higher rate](#get-a-higher-rate) |

Calls with no key or a free key also share 500 a second on `GET /quote` and `POST /open`. Past a rate the answer is HTTP 429: wait the seconds in its `Retry-After` header, then retry.

#### Get a higher rate

1. In DCA API access, press Higher rate on a key. It shows once the account also has a signed wallet.
2. Pick PLUS (100 requests a second) or PRO (400), say what the key runs and press Send.
3. The key works at 50 a second until Carbium approves, then gets the new rate within a minute.

A higher rate counts that key on its own, outside the shared 500, lifts `GET /history` and widens the [schedule limits](#schedule-limits). Quotes, new openings, sends and the reads of open DCAs also run inside a budget that all callers share, which no key lifts: see [Shared budget](#shared-budget).

#### Shared budget

- All callers share a budget for each second's chain reads, quotes and sends: about 50 quotes and 2 sends a second for everyone together, and for one caller about 12 quotes, 6 reads of one open DCA, one list of 25 open DCAs or one new opening a second.
- Each owner gets one send a second. Past the budget the answer is `door_busy`, which a higher rate does not lift.

#### Schedule limits

| Limit | Any wallet | PLUS | PRO |
|---|---|---|---|
| Smallest buy | Worth 0.01 USDC | The same | The same |
| Shortest interval | 60 seconds | 30 seconds | 10 seconds |
| Buys in one DCA | 1,000 | 5,000 | 65,535 |
| Running DCAs | 10 for one wallet | 30 | 100 |

`limits` in the quote answers these for a wallet, with the smallest buy in the token you pay with as `limits.minAmountPerCycle`. PLUS and PRO hold for the wallets that signed for an account with an approved key, whatever key the call carries, and for no other wallet. Their cap on running DCAs counts all those wallets together. Carbium can set other values for an account.

## Quote

The price of one buy now, the opening fee rate and your wallet's schedule limits.

```bash run
curl -s "$DCA_API/quote?inputMint=$IN_MINT&outputMint=$OUT_MINT&amount=10000000&owner=$OWNER"
```

Check: `ok` is true and your `amount` is at or over `limits.minAmountPerCycle`. Keep `feeBps`: the check holds the opening to it.

#### Quote: fields

| Param | Required | Description |
|---|---|---|
| `inputMint`, `outputMint` | yes | Mints of the token you spend and the token you buy |
| `amount` | yes | One buy, in input base units, above 0 |
| `slippageBps` | no | Default 50, at most 300 |
| `owner` | no | The wallet that will own the DCA: the limits answered are that wallet's |

| Answer | Meaning |
|---|---|
| `amount`, `out`, `minOut` | The buy asked about, its output now and the least inside the slippage, in base units |
| `rateE6` | `out` x 1,000,000 / `amount` |
| `feeBps` | The opening fee rate |
| `inDecimals`, `outDecimals` | Read from the two mint accounts |
| `valueUsdc` | What `amount` is worth, in USDC base units |
| `limits` | `minAmountPerCycle` (the smallest buy in input base units at this amount's price, null when the amount is worth 0 USDC), `minValueUsdc`, `minIntervalSecs`, `maxCycles` and `maxActive` ([Schedule limits](#schedule-limits)) |

## Open a DCA

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

## Check, sign and send

The owner's signed transaction on its way to the chain, sent only after the check passed on the built bytes and on the signed ones.

```js
import { WSOL, ataOf, fromB64, mintOf, refusals, walletChanges } from './check.mjs'
const feeOwner = 'cqvz12kjCQe6ck4PayVNBe3wsnbh8AXUDsUpB4RPTVV'   // Carbium's fee wallet
const tin = mintOf(inputMintAccount), tout = mintOf(outputMintAccount)   // each mint account {owner, data}, read through your own RPC
if (!tin || !tout || tin.refuse || tout.refuse) throw new Error('a DCA cannot use this token')
const ctx = { wallet, keeper: 'dcaqWvrzmkUbHSdAmATQU3m8GKJAyhapUzfvibM4DJf', feeOwner, feeAccount: await ataOf(feeOwner, inputMint, tin.program),
  wsolAccount: await ataOf(wallet, WSOL), inMint: inputMint, outMint: outputMint, inProgram: tin.program, outProgram: tout.program, maxSlippageBps: 300, maxPriorityLamports: 100_000 }
const want = { amountPerCycle: 10_000_000n, cycles: 2, intervalSecs: 86_400, firstTs: 0n, minOutE6: 0n, maxSlippageBps: 50, feeBps: quote.feeBps }
const why = refusals('open', fromB64(built.txn_base64), want, ctx)
if (why.length) throw new Error(why.join('; '))   // do not sign
// the owner signs; signed is the result in base64
const changed = walletChanges(fromB64(built.txn_base64), fromB64(signed), ctx)
if (changed.length) throw new Error(changed.join('; '))   // do not send
```

```bash
curl -s -X POST "$DCA_API/send" -H 'content-type: application/json' \
  -d '{"txn_base64":"'$SIGNED'","built_txn_base64":"'$BUILT'"}'
```

Check: `refusals` returns no reason before the owner signs, and `walletChanges` none after ([What the check enforces](#what-the-check-enforces)). Send within about a minute of the build, then read the DCA until it shows the change.

#### What the check enforces

You should not have to trust the transaction the API builds. `check.mjs`, the check the DCA page at https://dex.carbium.io/dca runs, gives `refusals(kind, bytes, want, ctx)`: the reasons not to sign, for kind `open`, `update`, `withdraw` or `close`. It refuses any other kind. `check.mjs` is one file, with no dependency.

Read each token's decimals and token program from its mint account through your own RPC, never from the API or a token list. `mintOf({ owner, data })` gives `program`, `decimals` and `refuse`, the reason a DCA cannot use a Token-2022 token. The fee account is derived with the input token's own program, classic or Token-2022.

The rules for each kind are with its call: [an opening](#open-the-check), [an update](#update-the-check), [a withdrawal](#withdraw-the-check) and [a close](#close-the-check).

The example's `signAndSend` is this step as one function.

#### After the wallet signed

- `walletChanges(built, signed, ctx)` takes both transactions as bytes (`fromB64` of each, as in [Check, sign and send](#check-sign-and-send)) and gives the reasons not to send. There are none when the signed transaction is the built one with nothing added but compute budget instructions under your cap (`ctx.maxPriorityLamports`) and Lighthouse assertions.
- A key file changes nothing. A browser wallet may compile the message again and add its own fee and guard instructions, so the bytes can differ even when nothing harmful was added.

#### Send fields

- Body: `{"txn_base64": "<the signed transaction>", "built_txn_base64": "<the build's own txn_base64>"}`. The answer has `signature`.
- `/send` takes only a transaction this API built, signed by its owner alone, while its blockhash is valid ([Timing](#timing)).
- A browser wallet may add its own instructions before it signs: a priority fee (compute budget instructions, at most 100,000 lamports) and Lighthouse guard assertions.
- Such a transaction is taken when `built_txn_base64` names the build it came from and every built instruction is still in it, unchanged and in order, with the same blockhash and fee payer.
- The answer comes back as soon as the transaction is sent, before it lands. The service keeps re-sending until it lands or expires; confirm with `GET /position/{address}`.

## Read DCAs

A wallet's open DCAs, up to 100 a call, and one DCA with its buys. There is no push notice. Read a wallet's DCAs once, about a minute after the next `nextTs`: one read per due buy is far under the rate.

### GET /positions

```bash run
curl -s "$DCA_API/positions?owner=$OWNER"
```

### GET /position/{address}

```bash run
curl -s "$DCA_API/position/$DCA"
```

Check: when a buy does not run, `cyclesDone` and `nextTs` stay, `status` is `waiting`, and `statusCode` and `lastTry` say why ([Status](#status)).

#### A DCA's fields

| Field | Type | Meaning |
|---|---|---|
| `address`, `owner` | string | The DCA's address and the wallet that owns it |
| `index` | number | 0 to 255 |
| `inMint`, `outMint` | string | The token paid with and the token bought |
| `inProgram`, `outProgram` | string | Each token's token program |
| `amountPerCycle` | string | One buy, in input base units |
| `cyclesTotal`, `cyclesDone` | number | Buys scheduled and buys done |
| `intervalSecs` | number | Seconds between buys |
| `nextTs` | string | Unix seconds: when the next buy is due |
| `minOutE6`, `maxSlippageBps` | string, number | The max price as the program stores it (`"0"`: no max price), and the slippage limit |
| `cumIn`, `cumOut` | string | Spent so far in input base units, bought so far in output base units |
| `escrow` | string or null | What is left in the escrow, in input base units |
| `crank` | string | The key that sends the buys besides the owner: Carbium's keeper while it runs, the owner alone while it is paused |
| `active` | boolean | False once the last buy ran or a full withdrawal emptied it |
| `status`, `statusCode` | string | The DCA's state and why ([Status](#status)) |
| `statusDetail` | string or null | The reason in words; the wording can change |
| `lastTry` | object or null | The last try at a buy: `at` (unix seconds), `cycle`, `result` (`filled`, `missed`, `refused`, `deferred` or `skipped`), `code`, `detail`, `signature` |
| `openedSlot` | number or null | The slot at which the service first saw this opening: the opening's own slot when it saw it live |
| `openedSignature` | string or null | The transaction that opened this DCA (`https://solscan.io/tx/<it>` shows it). Null until the service has found it on the chain |
| `middleDebt` | object or null | `{payer, owed}`: lamports the close pays Carbium back for route accounts |
| `fills` | list | One DCA only: this opening's newest 100 buys, oldest first |
| `ownerIn`, `ownerOut`, `tracked` | string or null, boolean | One DCA only: the owner's balances of the two tokens in base units, and whether the service's index has seen this DCA |

- `openedSignature` is found seconds after the service first sees the opening, as a rule, and up to about two minutes later when the chain's index trails. It stays null when three lookups a minute apart find none.
- `served` and `notServed` are answered too. Read `status` and `statusCode` in their place: their meaning can change.
- Each of `fills` has `signature`, `cycle` (from 1), `inAmount` and `outAmount` (strings, base units), `ts` (string, unix seconds), `slot` (number or null), `openedSlot`, `verdict` and `detail`.
- `verdict` is `filled`, or `missed` when the buy landed but the check after it did not see one clean buy. `detail` is what that check saw, else null.
- When a buy runs, `cyclesDone` goes up by one, `nextTs` moves on, `cumIn` and `cumOut` grow and `fills` gains the buy.

#### Status

| `status` | `statusCode` | Meaning | What the owner can do |
|---|---|---|---|
| `active` | `scheduled` | The next buy is ahead, at `nextTs` | Nothing |
| `waiting` | `due`, or the last try's code, such as `below_price_floor` | A buy is due and has not run. `below_price_floor`: the price is over the max price | Wait, or raise the max price with `/update` |
| `paused` | `paused` | The owner paused it | `/update` with `paused: false` |
| `not_served` | `amount_below_min`, `interval_below_min`, `cycles_over_max`, `owner_cap_reached`, `amount_not_valued`, `not_our_keeper` or another code | Carbium does not send its buys: it is outside the limits, or another key runs it | Close it and open one inside the limits, or close another DCA |
| `empty` | `empty_escrow`, `inactive` | Nothing is left to buy with, or it stopped before its last buy | Close it |
| `finished` | `schedule_complete` | Every buy has run | Close it to get the deposits back |
| `closed` | `closed` | Closed | Nothing |

A closed DCA answers `{address, closed: true, closedSlot, openedSlot, openedSignature, status: "closed", statusCode: "closed", statusDetail: null, lastTry, fills}` with its last opening's newest 100 buys and no other field. An address that never was a DCA here answers `position_not_found`.

#### Timing

| Event | When |
|---|---|
| The first buy | With `startAt` 0 it is due at once and is usually sent within a minute of the opening. Later buys follow one interval apart |
| A due buy | First tried 0 to 30 seconds after `nextTs` (at most a tenth of the interval), then up to 5 times in all, each with a fresh price |
| A buy that cannot run | If the price is over your max price, or the buy cannot be routed inside your slippage limit, it waits and is tried again one interval later |
| Missed buys | Never made up in a burst, and never after a pause, so a DCA can end later than planned |
| The bought token's account | A buy needs the owner's token account for the bought token. Opening creates it; if the owner closes it, buys stop until it exists again. SOL bought needs none |
| A built transaction | Valid for about a minute (`last_valid_block_height`). After that `/send` answers `message_expired`, and a few minutes after the build `unknown_message`: build it again |

#### Read a DCA from the chain

A DCA's own account through your RPC: where `want` for an update comes from, and the read that still works when the API is down.

```js
import { DCA_PROGRAM, positionOf } from './check.mjs'
// account: getAccountInfo for the DCA's address through your own RPC, with its data as bytes
if (account.owner !== DCA_PROGRAM) throw new Error('not a DCA')
const p = positionOf(account.data)   // null when the data is not shaped like a DCA's
```

The answer: `owner`, `inMint`, `outMint`, `crank`, `minOutE6`, `maxSlippageBps` and `owed`, the lamports a close pays the keeper back. The DCA is paused when `crank` equals `owner`.

Check: a DCA is an account of 228 bytes owned by the program, at the address derived from the seeds `"dca-pos"`, owner, output mint and one index byte. Its escrow is the input token account of the address derived from `"dca-auth"` and the DCA's address. The published interface gives every field; `crank` is its `crank_authority`.

### GET /history

The wallet's DCAs that ended, newest close first, with how each one ended.

```bash run
curl -s "$DCA_API/history?owner=$OWNER"
```

#### History fields

- Each of `orders` holds `address`, `inMint`, `outMint`, `cyclesDone`, `cyclesTotal`, `amountPerCycle`, `intervalSecs`, `cumIn` (spent), `cumOut` (bought), `minOutE6`, `openedSlot`, `openedSignature`, `openedTs`, `closedSlot`, `closedSignature`, `closedTs`, `lastTry` and `ended`.
- `ended` is `finished` (every buy ran), `emptied` (stopped before its last buy, as a withdraw of the whole escrow does) or `closed_early` (closed with buys left).
- `openedSignature`, `openedTs`, `closedSignature` and `closedTs` (unix seconds, block times) are null until the service has found the transaction.
- For the DCA still open at an address, `GET /position/{address}?openedSlot=` answers as without it.
- For DCAs closed before 2026-11-18, History holds the last DCA of each address only. One opened before then has no `openedTs`.
- An address opened again keeps each earlier DCA as its own row, and `GET /position/{address}?openedSlot=` answers that one's buys.

## Change or close a DCA

A `POST` other than `/send` answers an unsigned transaction and puts nothing on chain: [Check, sign and send](#check-sign-and-send) lands it.

### POST /update

An unsigned update. A pause, a resume and a new max price or slippage are one write that sets all three values together.

```bash
curl -s -X POST "$DCA_API/update" -H 'content-type: application/json' \
  -d '{"owner":"'$OWNER'","position":"'$DCA'","paused":true}'
```

#### Update: fields

A running DCA keeps its amount per buy, interval, number of buys and start. To change one, close the DCA and open a new one: the new one pays the opening fee again, and the close returns the old one's deposits.

Other bodies: `"paused":false` resumes, `"maxPrice":"0.0014"` sets or changes the max price, `"maxPrice":null` removes it, `"maxSlippageBps":100` changes the slippage.

Fields: `owner`, `position`, and `paused` (true or false) or a new `minOutE6` or `maxPrice` or `maxSlippageBps`. With `maxPrice` left out, the DCA keeps the max price it has.

The answer: `txn_base64`, with `summary.paused` and `summary.maxPriceHeld` as they will be.

#### Update: the check

`want` names all three values as they must be after the update, read from the DCA's own account:

```js
import { fromB64, positionOf, refusals } from './check.mjs'
const p = positionOf(positionAccount.data)   // the DCA's own account, read through your own RPC
const keep = { position, minOutE6: p.minOutE6, maxSlippageBps: p.maxSlippageBps }
const why = refusals('update', fromB64(built.txn_base64), { ...keep, paused: true }, ctx)   // paused: false for a resume
```

- A pause, a resume and new limits are all kind `update`: one keeper setting on the position you named. The check also passes the creation of the owner's own token accounts for the two tokens, which the service does not add, and a compute budget under your cap (`ctx.maxPriorityLamports`).
- `want` is `{ position, paused, minOutE6, maxSlippageBps }`, the values as they must be after the write, `minOutE6` as a BigInt and `maxSlippageBps` as a number. `paused: true` names the owner's wallet as the only key that may run the DCA, `false` names Carbium's keeper.
- For a pause or a resume the two limits are the ones the DCA has. Read them with `positionOf` ([Read a DCA from the chain](#read-a-dca-from-the-chain)), or keep the ones you set last, at opening or at your last update.
- The API's read shows the same two values, but taken from the API a wrong answer there would pass the check.

### POST /withdraw

Input tokens back in the wallet, with the DCA still open.

```bash
curl -s -X POST "$DCA_API/withdraw" -H 'content-type: application/json' \
  -d '{"owner":"'$OWNER'","position":"'$DCA'","amount":"5000000"}'
```

The answer: `txn_base64`. An `amount` of 0, or none, withdraws all of it.

A finished or emptied DCA cannot run again, and there is no top-up.

#### Withdraw: the check

- `refusals('withdraw', fromB64(built.txn_base64), { position, amount: 5_000_000n }, ctx)` returns no reason.
- It is one withdraw on the position you named, for the amount you asked: `want.amount`, a BigInt in input base units.
- It may create the owner's own token accounts for the two tokens (the service creates the one for the token you pay with) and set a compute budget under your cap (`ctx.maxPriorityLamports`).
- For a DCA paid with SOL it also closes the wallet's wrapped SOL account back to the wallet, so the SOL returns as plain SOL. A close does the same.

#### Partial withdrawal

A partial withdrawal keeps the amount per buy and the number of buys. Buys stay whole until the escrow holds less than one, then one smaller buy takes the rest, and the DCA ends `empty`, or `finished` when that buy was its last.

### POST /close

The end of a DCA, in any state: what is left in the escrow and the deposits return to the wallet.

```bash
curl -s -X POST "$DCA_API/close" -H 'content-type: application/json' \
  -d '{"owner":"'$OWNER'","position":"'$DCA'"}'
```

#### Close: the check

Keep the mints and amounts of a DCA you follow: once closed, it answers its buys and little else ([Status](#status)).

The answer: `txn_base64` and `cost.middleShortfall`, lamports the close takes from the wallet for route accounts ([Fees and deposits](#fees-and-deposits)).

`refusals('close', fromB64(built.txn_base64), { position }, ctx)` returns no reason.

- It is one close on the position you named. It may create the owner's own token accounts for both tokens, except that SOL bought needs none, and set a compute budget under your cap (`ctx.maxPriorityLamports`).
- With a Token-2022 token it may first move that token's withheld fees from the DCA's own two accounts to the mint, and it may name route accounts of the DCA to close with it.
- With `want` as `{ position, owed, middles, agreed }` it is also held to what the DCA owes the keeper. With `position` alone that part is not checked.
- `owed` is `positionOf(data).owed`, and `agreed` the lamports the owner accepted to pay from the wallet, 0 if you did not ask.
- `middles` is the lamports, as a BigInt, of the accounts `closeMiddles(bytes)` names that are empty classic token accounts (165 bytes, amount 0, owned by the classic token program), each read through your RPC. Count no other account: the program skips any other.
- A close that would take more than `agreed` from the wallet is refused. The check counts `owed` less `middles` against `agreed` and leaves the DCA's own lamports out, so ask the owner for that difference, never for `cost.middleShortfall`.

## Full example

The example opens a DCA of 2 buys of 10 USDC, one a day, reads it back and closes it, printing `open sent`, `buys done` and `close sent`.

1. Get the check, the example and their one package, on Node 20.18 or newer.

   ```bash
   curl -fsSLO https://carbium.io/docs/dca/check.mjs
   curl -fsSLO https://carbium.io/docs/dca/example.mjs
   npm i @solana/kit
   ```

2. Fund a wallet with 20.01 USDC and about 0.02 SOL. The example spends real funds on Solana mainnet.

3. Run it with the wallet's key file. With `DCA_API_KEY` set, it sends your key as `x-api-key`.

   ```bash
   DCA_API=https://dex.carbium.io/api/dca DCA_KEEPER=dcaqWvrzmkUbHSdAmATQU3m8GKJAyhapUzfvibM4DJf KEYPAIR=~/.config/solana/id.json node example.mjs
   ```

#### example.mjs

The first buy is due at once and can run before the close.

The example's four numbered comments are the blocks [Quote](#quote), [Open a DCA](#open-a-dca) with [Check, sign and send](#check-sign-and-send), [Read DCAs](#read-dcas) and [Change or close a DCA](#change-or-close-a-dca).

```js
// npm i @solana/kit, save check.mjs beside this file (both are on the DCA API page of the Carbium docs), then:
//   DCA_API=<the API base that page names> KEYPAIR=~/.config/solana/id.json node example.mjs
// On a host other than production, also DCA_KEEPER=<the keeper that host's page names>.
// Opens a DCA of 2 buys of 10 USDC, one a day, reads it back and closes it. The wallet needs 20.01 USDC and about 0.02 SOL.
// It spends real funds on Solana mainnet. Optional: DCA_API_KEY (sent as x-api-key), PER_BUY (base units), BUYS, START_AT.
import { readFileSync } from 'node:fs'
import { createKeyPairSignerFromBytes, getBase64EncodedWireTransaction, getBase64Encoder, getTransactionDecoder, signTransaction } from '@solana/kit'
import { TOKEN_PROGRAM, ataOf, fromB64, refusals, walletChanges } from './check.mjs'

const API = (process.env.DCA_API ?? '').replace(/\/$/, ''), KEY = process.env.DCA_API_KEY
if (!API || !process.env.KEYPAIR) { console.error('Set DCA_API (the API base the docs page names) and KEYPAIR (the path of your Solana key file).'); process.exit(2) }
const USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v', OUT = 'AT79ReYU9XtHUTF5vM6Q4oa9K8w7918Fp5SU7G1MDMQY'
const PER_BUY = BigInt(process.env.PER_BUY ?? 10_000_000), BUYS = Number(process.env.BUYS ?? 2), EVERY = 86_400
const START_AT = Number(process.env.START_AT ?? 0) // 0: the first buy runs now

const owner = await createKeyPairSignerFromBytes(Uint8Array.from(JSON.parse(readFileSync(process.env.KEYPAIR, 'utf8'))))
// What the check holds every transaction to. The keeper and the fee wallet are Carbium's, named here and never taken from the API; the fee
// account is that wallet's own account for the token paid with, derived here and not taken from the API. Both tokens of
// this example are classic SPL tokens: for another pair, read each mint account for its token program (mintOf in check.mjs),
// and paying with SOL add wsolAccount: await ataOf(owner.address, WSOL).
const FEE_OWNER = 'cqvz12kjCQe6ck4PayVNBe3wsnbh8AXUDsUpB4RPTVV'
const KEEPER = process.env.DCA_KEEPER ?? 'dcaqWvrzmkUbHSdAmATQU3m8GKJAyhapUzfvibM4DJf' // production's keeper, unless you name another host's
const ctx = { wallet: owner.address, keeper: KEEPER, feeOwner: FEE_OWNER, feeAccount: await ataOf(FEE_OWNER, USDC, TOKEN_PROGRAM),
  inMint: USDC, outMint: OUT, inProgram: TOKEN_PROGRAM, outProgram: TOKEN_PROGRAM, maxSlippageBps: 300, maxPriorityLamports: 100_000 }

async function call(method, path, body) {
  for (let tries = 1; ; tries++) {
    const r = await fetch(API + path, { method, headers: { ...(body && { 'content-type': 'application/json' }), ...(KEY && { 'x-api-key': KEY }) }, body: body && JSON.stringify(body) })
    if (r.status === 429 && tries < 5) { await new Promise((ok) => setTimeout(ok, 1000 * (Number(r.headers.get('retry-after')) || 1))); continue } // too many calls: wait as asked, then ask again
    const j = await r.json().catch(() => ({ err: `http_${r.status}`, detail: 'the answer is not JSON' })) // a door in front of the API can answer with a page
    if (!j.ok) throw new Error(`${path}: ${j.err}: ${j.detail}`) // a refusal can arrive with HTTP 200
    return j
  }
}

/** Check the built transaction, sign it as the owner, check what was signed, send it with the built bytes beside it. */
async function signAndSend(kind, built, want) {
  const bytes = fromB64(built.txn_base64)
  const why = refusals(kind, bytes, want, ctx)
  if (why.length) throw new Error(`not signing the ${kind}: ${why.join('; ')}`)
  const tx = await signTransaction([owner.keyPair], getTransactionDecoder().decode(getBase64Encoder().encode(built.txn_base64)))
  const signed = getBase64EncodedWireTransaction(tx)
  const changed = walletChanges(bytes, fromB64(signed), ctx) // a key file changes nothing; a browser wallet may add its own fee and guard instructions
  if (changed.length) throw new Error(`not sending the ${kind}: ${changed.join('; ')}`)
  return call('POST', '/send', { txn_base64: signed, built_txn_base64: built.txn_base64 })
}
const until = async (what, read) => {
  for (let i = 0; i < 30; i++) { const v = await read().catch(() => null); if (v) return v; await new Promise((r) => setTimeout(r, 2000)) }
  throw new Error(`${what}: not seen after a minute`)
}

// 1. The price now and the opening fee rate. The max price here is about 11% over the price now (a buy must get at least 90% of
//    the tokens it would get now): no buy fills above it.
const quote = await call('GET', `/quote?inputMint=${USDC}&outputMint=${OUT}&amount=${PER_BUY}`)
const want = { amountPerCycle: PER_BUY, cycles: BUYS, intervalSecs: EVERY, firstTs: BigInt(START_AT), minOutE6: BigInt(quote.rateE6) * 9n / 10n, maxSlippageBps: 50, feeBps: quote.feeBps }

// 2. Build the opening, check it, sign it, send it.
const built = await call('POST', '/open', { owner: owner.address, inputMint: USDC, outputMint: OUT, cycles: BUYS, amountPerCycle: String(PER_BUY),
  intervalSecs: EVERY, minOutE6: String(want.minOutE6), maxSlippageBps: 50, startAt: START_AT })
const opened = await signAndSend('open', built, want)
console.log('open sent', opened.signature, 'DCA', built.position)

// 3. Read it back once the opening has landed, with its buys so far. (An address used before answers its old closed record until then.)
const dca = await until('the DCA', () => call('GET', `/position/${built.position}`).then((p) => (p.closed ? null : p)))
console.log('buys done', dca.cyclesDone, 'of', dca.cyclesTotal, '| in escrow', dca.escrow, '| bought', dca.cumOut)

// 4. Close it: what is left in the escrow and the deposits return to the wallet.
const closing = await call('POST', '/close', { owner: owner.address, position: built.position })
const closed = await signAndSend('close', closing, { position: built.position })
await until('the close', () => call('GET', `/position/${built.position}`).then((p) => p.closed, (e) => /position_not_found/.test(e.message)))
console.log('close sent', closed.signature)
```

## Errors

A refusal is `{"ok": false, "err": "<code>", "detail": "<text>"}`: treat an answer without `"ok": true` as a refusal.

| `err` | HTTP with a key | Meaning | What to do |
|---|---|---|---|
| `rate_limited`, `rate_limited_open` | 429 | Over your rate, or callers with no key or a free key are together over the 500 a second they share | Wait for `Retry-After`, or [get a higher rate](#get-a-higher-rate) |
| `key_unknown` | 401 | The key is not valid, or was revoked | Copy the key again, or add one, in your account at https://dex.carbium.io |
| `not_found`, `forbidden_origin` | 404, 403 | No such path for this method, a `/position/` address that is not base58 included, or a page on another site calling it | Fix the path or the method; call from your own server |
| `bad_request` | 400 | A field is missing or malformed | Fix the request |
| `same_mint`, `not_a_mint` | 400 | The two mints are the same, or one is not a token mint (classic SPL or Token-2022) | Fix the mints |
| `sol_end` | 400 | Token-2022's own wrapped SOL mint | Use `So11111111111111111111111111111111111111112` for SOL |
| `token_transfer_fee`, `token_transfer_hook`, `token_non_transferable`, `token_frozen_default`, `token_paused`, `token_unknown_extension` | 400 | A Token-2022 token a DCA cannot use; the code says why | Use another token |
| `owner_cpi_guard`, `owner_memo_required`, `owner_confidential_only` | 422 | The owner's own Token-2022 account has a setting a DCA cannot work with | Change the setting, or use another wallet |
| `middle_token_2022` | 422 | The route for this pair at this amount passes through a Token-2022 token, and none goes straight from one token to the other | Try another amount or another pair |
| `no_route`, `amount_not_valued` | 422 | The router has no route for this pair at this amount, or cannot value the input in USDC | Try another amount or another pair |
| `amount_below_min`, `interval_below_min`, `cycles_over_max` | 400 | Outside the [schedule limits](#schedule-limits) | Change the schedule |
| `cycles_out_of_range`, `interval_out_of_range`, `first_ts_out_of_range` | 400 | A number of buys, an interval or a start outside what the field takes | Fix the field |
| `min_out_zero` | 400 | A `minOutE6` of 0, or a `maxPrice` so high that it is held as 0 | For no max price leave both out at `/open`, or send `maxPrice: null` to `/update`; else send a lower `maxPrice` |
| `slippage_over_cap` | 400 | Slippage over 300 bps | Lower the slippage |
| `owner_cap_reached` | 409 | The wallet runs its most DCAs | Close one first |
| `position_exists` | 409 | A DCA is open at that index now or, with no `index`, at every one of 0 to 15 | Pass a free `index` |
| `no_input_ata`, `insufficient_balance`, `insufficient_sol` | 422 | The wallet lacks the token, the total plus fee, or the SOL | Fund the wallet |
| `position_not_found`, `not_owner` | 404, 403 | No such DCA, or another owner's | Check the address and owner |
| `no_change`, `withdraw_over_escrow` | 409, 422 | Nothing to update, or more than the escrow holds | Fix the request |
| `unknown_message`, `message_expired` | 403, 410 | Not built here, too old, or changed by the wallet and sent with no `built_txn_base64` beside it | Build it again, sign, send it with `built_txn_base64` |
| `message_changed` | 403 | The wallet changed the built transaction beyond what `/send` takes ([Send fields](#send-fields)); `detail` names what | Build again and sign with a lower priority fee, or with a wallet that adds nothing else |
| `already_sent` | 409 | Another signed version of this build already went out; `signature` names it | Confirm that signature or read the position; build again only if it did not land before its blockhash expired |
| `bad_transaction`, `bad_signature` | 400 | Not a transaction, or not signed by the owner alone | Send the built transaction, signed with the owner's key |
| `send_refused`, `program_error` | 422 | The chain refused it; `detail` says why | Read `detail`, rebuild |
| `door_busy` | 503 | The service is at its share of chain reads, quotes or sends this second | Retry in a second; it carries no `Retry-After` |
| `rpc_unavailable` | 502 | The network did not answer right now | Ask again; send the same signed transaction again |
| `quote_unavailable` | 502 | No price right now | Retry shortly |
| `swap_tag_not_applied` | 502 | Buys cannot run right now, so nothing is built | Retry later |
| `internal` | 500 | The service failed on its side | Retry; read the position before sending again |
| `dca_unavailable` | 502, 503, 504 | The service did not answer | Retry; a sent transaction may still land, so read the position before sending again |
