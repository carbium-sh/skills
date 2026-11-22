## Check, sign and send

Contents, with the line each part starts on in this file:

  - What the check enforces: line 35
  - After the wallet signed: line 45
  - Send fields: line 50

Links from this file to other files: #open-the-check is in references/open-a-dca.md; #timing is in references/read-dcas.md; #update-the-check, #withdraw-the-check and #close-the-check are in references/change-or-close-a-dca.md.

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

