## Change or close a DCA

Contents, with the line each part starts on in this file:

- POST /update: line 18
  - Update: fields: line 27
  - Update: the check: line 37
- POST /withdraw: line 53
  - Withdraw: the check: line 66
  - Partial withdrawal: line 73
- POST /close: line 77
  - Close: the check: line 86

Links from this file to other files: #fees-and-deposits is in references/open-a-dca.md; #check-sign-and-send is in references/check-sign-and-send.md; #read-a-dca-from-the-chain and #status are in references/read-dcas.md.

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

