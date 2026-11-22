## Full example

Contents, with the line each part starts on in this file:

  - example.mjs: line 27

Links from this file to other files: #quote is in references/quote.md; #open-a-dca is in references/open-a-dca.md; #check-sign-and-send is in references/check-sign-and-send.md; #read-dcas is in references/read-dcas.md; #change-or-close-a-dca is in references/change-or-close-a-dca.md.

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

