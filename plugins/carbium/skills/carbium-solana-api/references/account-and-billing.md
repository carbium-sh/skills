## Account, keys and billing

Contents, with the line each part starts on in this file:

- Agents: onboard yourself with only a Solana keypair: line 27
- Sign in: line 209
- Starter key and free credits: line 217
- Keys: line 223
- IP allowlist: line 240
- Per-method caps: line 251
- Plans and prices: line 270
- Paying by card or in USDC or USDT: line 287
- Renewals, low balance and invoices: line 301
- Cancel a renewal: line 315
- Delete the account: line 325

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

