## Quote

Contents, with the line each part starts on in this file:

  - Quote: fields: line 17

Links from this file to other files: #schedule-limits is in SKILL.md.

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

