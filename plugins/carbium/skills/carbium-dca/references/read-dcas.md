## Read DCAs

Contents, with the line each part starts on in this file:

- GET /positions: line 16
- GET /position/{address}: line 22
  - A DCA's fields: line 30
  - Status: line 62
  - Timing: line 76
  - Read a DCA from the chain: line 87
- GET /history: line 102
  - History fields: line 110

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

