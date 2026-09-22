# X post — required, and an entry without it is invalid

Must contain **`#BitgetHackathon`** and **`@Bitget_AI`**. Post from the account
entering the hackathon, then replace the placeholder row in `docs/SUBMISSION.md`
with the URL.

Every figure below comes from `docs/facts.json`, which the nightly regenerates —
**re-check before posting**, because a post cannot be corrected after the fact.

| Claim in the drafts | Source key |
|---|---|
| 98.2% of overnight variance removed | `median_r2` = 0.982 |
| ~11 bp hedge cost | `hedge_cost_bp` = 11.3 |
| 20 bp to exit instead | `exit_cost_bp` = 20.0 |
| 226 of 2,125 rTokens hedgeable | `rtokens_hedgeable` / `rtokens_total` |
| 1.41× volatility vs 3.2× earnings | Gate 1b, `docs/RESEARCH.md` |

---

## Option B — the negative result (288 chars) ← recommended

```
We tested two ways to pick which nights to hedge.

Volatility: separates risky nights 1.41x, and those nights pay you to hold. Hedging them destroys value. We shipped it DISABLED.

Earnings: 3.2x, no compensation. Adopted.

Publishing the one that failed too.

#BitgetHackathon @Bitget_AI
```

Why this one: everyone's post claims their thing works. A measured negative
result, shipped disabled with the measurement in the code comment, is the least
imitable thing this project has — and it is the reason to believe the positive
claims sitting next to it.

## Option C — the product, shortest (284 chars)

```
Hold a tokenized stock through earnings without being flat into it.

Short the matched perp: 98.2% of overnight variance removed, ~11 bp. 226 of 2,125 rTokens can do this - Ballast names the ones that can't.

No directional trade is reachable in the code.

#BitgetHackathon @Bitget_AI
```

## Option A — the negative capability (317 chars)

```
Tokenized stocks trade 24/7. The market that prices them is open 32.5 of every 168 hours.

Ballast hedges the night: short the matched perp, 98.2% of the overnight variance gone for ~11 bp. Exiting costs 20 and loses the position.

It cannot place a directional bet. Not "won't" - cannot.

#BitgetHackathon @Bitget_AI
```

---

## If a thread is allowed

1. Option B as the opener.
2. *"The hedge strengthens under stress: R² 0.978–0.999 on the biggest move
   nights, 0.77–0.96 on calm ones. It is imprecise only when little is at
   stake."*
3. *"The model reads the night and owns the hedge judgment. It cannot size,
   price or direct anything — a separate enforcer holds the only write
   credential, never sees the model's reasoning, and checks arithmetic against
   a signed mandate. 25 red-team tests drive hostile intents at it."*
4. *"Every decision is signed into a hash-chained ledger before the outcome is
   known. Clone it and run `python3 verify.py` — no key, no network."*

## Do not claim

- **Any Sharpe, edge or return.** Ballast is priced protection; the replay's
  total return is negative and that is what insurance costs. 16 hedges over 55
  sessions cannot support a return claim and the site says so.
- **That it trades live.** Fills are simulated and every row says so.
- **That tail coverage is solved.** The calendar reaches 2 of the worst 6
  position-nights. That gap is the published open problem.
- Do not round 98.2% up, and do not drop the "median".
