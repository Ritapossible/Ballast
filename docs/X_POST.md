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
| 241 of 2,810 rTokens hedgeable | `rtokens_hedgeable` / `rtokens_total` |
| 1.41× volatility vs 3.2× earnings | Gate 1b, `docs/RESEARCH.md` |

---

## Option D — explains Ballast, and leads with the honest part ← post this

**1,460 characters**, so it needs a long-post account or a thread. If threaded,
the quote, both links and both tags go on the FIRST post.

**Quote the organiser's post rather than only mentioning the handle** - a bare
`@Bitget_AI` mention may not satisfy the requirement. Confirm the target post and
the rule against the handbook before sending; neither is verifiable from here.

Every figure below is checked against `docs/facts.json` and the ledger by
`tools/check_post.py`. Re-run it before posting.

```
Tokenized US stocks trade 24/7. The market that prices them is shut for 81% of the week.

Sell before the close and you lose a position you believe in. Hold, and you take whatever lands at 3am. Ballast is the third option: keep the position, short the matched perpetual for the night. About 12 bp taker round trip, 11.3 net of funding.

241 of 2,810 rTokens have a matched perp. Shorting it removes a median 98.2% of overnight variance, and R² runs 0.978–0.999 on top-decile move nights. Exiting instead costs 20 bp, and you lose the position.

An LLM reads the night's news and decides whether that night is worth hedging. It cannot size, price, or place anything. A separate enforcer holds the only write key and checks the order against a signed mandate. There is no path to a directional trade.

The part I would rather not write: 17 nights live, and the hedges arrive too late. Median 21% into the night. Re-graded from the moment each hedge actually existed, the protected book's drawdown is worse than doing nothing: 235 bp against 227 bp. NKE on 1 Oct was scored +17 bp. From the fill it is −526 bp — the move had already happened.

Yesterday the same page said 11 of 11 hedges cut the move. Its own record caught that. I published the correction beside the signed ledger instead of editing it.

Every decision is signed before the outcome is known. Clone it and check.

ballast-v1.vercel.app
github.com/Ritapossible/Ballast
#BitgetHackathon @Bitget_AI
```

Checked against the live site, because a judge will open the URL:

| In the post | What the site prints |
|---|---|
| about 12 bp taker round trip, 11.3 net of funding | `hedge_cost_gross_bp` 12.0, `hedge_cost_bp` 11.3 |
| R² 0.978–0.999 on top-decile move nights | Evidence page, verbatim: "R² 0.978-0.999 on top-decile nights" |
| median 21% into the night | the settled page's own correction note |
| NKE +17 bp scored, −526 bp from the fill | both print on the same row |
| 235 bp against 227 bp | the drawdown row of the paper-metrics table |

Why this one: it explains the product in four lines and then spends the rest on
the thing nobody else's post will have - a measured result that makes the author
look worse, with the ledger to prove it was not quietly fixed.

## Option B — the negative result (288 chars)

```
We tested two ways to pick which nights to hedge.

Volatility: separates risky nights 1.41x, and those nights pay you to hold. Hedging them destroys value. We shipped it DISABLED.

Earnings: 3.2x, no compensation. Adopted.

Publishing the one that failed too.

#BitgetHackathon @Bitget_AI
```

Why this one (as a single tweet): everyone's post claims their thing works. A measured negative
result, shipped disabled with the measurement in the code comment, is the least
imitable thing this project has — and it is the reason to believe the positive
claims sitting next to it.

## Option C — the product, shortest (284 chars)

```
Hold a tokenized stock through earnings without being flat into it.

Short the matched perp: 98.2% of overnight variance removed, ~11 bp. 241 of 2,810 rTokens can do this - Ballast names the ones that can't.

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
- **That the live record shows protection.** It does not. Graded from each hedge's
  own fill timestamp, the live book's max drawdown is *larger* than the untouched
  book's. The hedges went on 1.7 to 16.8 hours after the close because the cron is
  delayed, and on an earnings night the move is already gone by then. The earlier
  "24 bp of protection" figure came from grading the full close-to-open window as
  though the hedge had been on throughout; it is corrected on the Settled page and
  written up as defect 6. The *replay* drawdown (9.24% vs 10.15%) still holds, but
  it assumes the hedge is on at the close — say "replay" if you quote it.
- **That it trades live.** Fills are simulated and every row says so.
- **That tail coverage is solved.** The calendar reaches 2 of the worst 6
  position-nights. That gap is the published open problem.
- Do not round 98.2% up, and do not drop the "median".
