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

## Reference files

Every other section of the guide is its own file under `references/`. Open the one for the task; each starts with its contents and the line each part starts on.

| Section | File | Parts |
|---|---|---|
| Quote | [references/quote.md](references/quote.md) | Quote: fields |
| Open a DCA | [references/open-a-dca.md](references/open-a-dca.md) | Open: fields; What a build answers; Open: the check; Run many DCAs; Max price steps; Tokens; Fees and deposits |
| Check, sign and send | [references/check-sign-and-send.md](references/check-sign-and-send.md) | What the check enforces; After the wallet signed; Send fields |
| Read DCAs | [references/read-dcas.md](references/read-dcas.md) | GET /positions; GET /position/{address}; A DCA's fields; Status; Timing; Read a DCA from the chain; GET /history; History fields |
| Change or close a DCA | [references/change-or-close-a-dca.md](references/change-or-close-a-dca.md) | POST /update; Update: fields; Update: the check; POST /withdraw; Withdraw: the check; Partial withdrawal; POST /close; Close: the check |
| Full example | [references/full-example.md](references/full-example.md) | example.mjs |

Links from this file to other files: #quote is in references/quote.md; #open-a-dca is in references/open-a-dca.md; #check-sign-and-send and #send-fields are in references/check-sign-and-send.md; #get-positions, #get-position-address and #get-history are in references/read-dcas.md; #post-update, #post-withdraw and #post-close are in references/change-or-close-a-dca.md.

Files the guide's code fetches: `check.mjs` and `example.mjs`, in references/full-example.md under "Full example".

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
