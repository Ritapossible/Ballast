# X article — Ballast

Long-form post for X. Every figure is from `docs/facts.json`, the signed ledger,
or `state/calendar_crosscheck.json`, measured 2026-09-25. **Re-check before
posting** — the nightly moves the live-record numbers.

Must contain `#BitgetHackathon` and `@Bitget_AI`.

---

## Title

**I built an agent that mostly refuses to trade. Here's the measurement that made me.**

## Body

Bitget lists 2,810 tokenized US stocks. They trade 24/7.

The market that prices the share underneath them is open 32.5 hours a week.

So for about 81% of every week you're holding an asset whose reference market is
shut — through earnings, through the Fed, through the weekend. Your options today
are to sell before the close and give up a position you believe in, or hold and
take whatever arrives at 3am.

Ballast adds a third: keep the position, switch off that night's risk, pay a
stated price.

### The mechanism

Of those 2,810 rTokens, **241 have a matched stock perpetual** trading the same
24/7 clock. Short the perp against the token and you remove a **median 98.2% of
overnight variance**, with hedge ratios between **0.992 and 1.027** across 12
names and 100–264 nights each.

It costs **12.0 bp** taker round trip — the certain part. A short also collects
funding, which brings the average night to about **11.3 bp**. Exiting the
position instead costs **20 bp** and you lose the position.

The hedge gets *better* under stress: R² runs **0.978–0.999** on top-decile move
nights and 0.77–0.96 on calm ones. On a big-news night the common factor
dominates and both legs track it almost exactly. It's imprecise only when little
is at stake.

Held out properly: fitted on the first 70% of each name's nights, applied
unchanged to the last 30%. Median variance removed **0.980 → 0.996**, median tail
cut **86% → 94%**, median absolute beta drift **0.009**, twelve of twelve names
holding.

### The part I didn't expect

A delta hedge is symmetric. It removes upside with downside. So it only creates
value on nights that carry variance *without* compensation.

I tested two ways to pick those nights.

**Trailing volatility** separates risky nights at **1.41×** — and the nights it
picks carry positive expected return, **+19.3 bp, t=3.08**. Hedging them pays to
remove return.

**The earnings calendar** separates at **3.2×**, with no reliable compensation:
−61 bp, t=−1.59, 0 of 15 names significant. About 392 bp of overnight movement
against an 11.3 bp cost.

So the volatility gate **ships disabled**, with that measurement written into the
code comment next to it. It's the most useful thing I found and it's a negative
result.

### What the model actually does

Qwen `qwen3.8-max`, temperature 0, reads the night's headlines plus the calendar
flag for one ticker and returns a **HEDGE / NO_HEDGE / ABSTAIN** judgment. That
judgment leads — it can overrule the calendar in both directions.

It cannot size, price or direct anything. There is no field for quantity, side or
price anywhere in its output contract, and a test asserts their absence. Three
gates stand between it and an order: the answer must parse into the contracted
shape, it must be about the right ticker, and **the quote it cites must appear in
the headlines it was given**.

Over 204 decisions on the live chain: **134 decided by the model, 70 by the rule**.
The gates refused **30 answers for quoting a headline that wasn't in the sources**
and 3 for schema violations, and the rule took over on 24 nights where the model
was unreachable. On the remaining 13 the model answered cleanly and said it did not
know — abstention hands the night back to the rule. A fabricated source cannot
reach the book.

Separately, an enforcer holds the only write-scoped credential. It never sees the
model's reasoning — it checks arithmetic against a signed, expiring mandate: a
position exists, the order opposes it, size within ratio, symbol in universe,
night caps intact. **25 red-team tests** drive hostile intents at it.

The claim is structural: *Ballast cannot place a bet.* Every order it can emit is
opposite in sign to, and bounded in size by, spot already held. There is no code
path to a directional trade.

### The live record, including the parts that don't flatter it

17 nights, 204 position-nights, decided by a scheduled job nobody watched — and
graded from the moment each hedge actually existed, not from the closing bell.
That distinction turned out to be the whole story.

- **10 of 11 graded hedges cut the move.** Two more were sent and are excluded
  from the grade — a defect I published: the selector matched a session without
  checking the release time and covered a night early.
- **Max drawdown −235 bp, against −227 bp untouched.** That is 8 bp worse, not
  better. Read it again, because it is the opposite of the claim this whole
  project is built on, and it is the most useful number here.
- **Total return +209 bp, against +279 bp untouched.** The book carrying Ballast
  made *less* than the book left alone. That's what paying for insurance over a
  rising window looks like, and I'm not going to argue it away.
- Sharpe is +2.00 vs +2.53.

**Here is what went wrong, because it is more interesting than the number.**

I had been grading every hedge over the whole close-to-open window, as though the
perp short had been on from the closing bell. It never was. GitHub delays the
21:00Z cron and the 00:00Z backup fires instead, so **all thirteen hedges went on
between 1.7 and 16.8 hours after the close** — a median 21% of the night already
gone. On an earnings night, the move lands in the first hour.

Grading the full window subtracts the perp leg from a fall the hedge was not there
for. **NKE on 2026-10-01 was recorded as +17 bp on a night that cost 526 bp.** The
position had already fallen 560 bp by the time the order went in; it rebounded 314
bp afterwards, and the hedge was short into the rebound. MU on 2026-09-30 was
recorded at −26 bp and actually cost −91 bp: 74 of its 296 bp fall happened before
the hedge existed.

The worst part is that the lag was never unmeasured. `window_elapsed_at_decision`
was written into every single night summary from early on. **Nothing read it.** I
had instrumented the exact failure and then graded as if it could not happen.

Each hedge is now graded from its own signed fill timestamp, with the night cut in
two at that moment and the hedge credited only with the part that followed. The
seventeen signed settlements are not edited — the chain is append-only, so each
correction sits beside the record it supersedes and the table prints both figures.

**What this does and does not break.** The mechanism is untouched: variance
removed, beta, tail reduction and the held-out test are measured on paired candles
and never involved a decision timestamp. The replay is untouched too — but its
assumption is now visible. A backtest places the hedge *at the close*, because
that is when the decision is made, and grades the full window accordingly. That is
internally consistent, and it is an **upper bound**. The gap between the replay's
drawdown and the live record's is **execution latency, and it is now measured
rather than assumed.**

A mechanism that removes 98.2% of overnight variance is worth very little if the
order arrives four hours after the news. That is what this record is actually good
for, and it is not a finding a cleaner log would have produced.

**Every fill is simulated.** Orders route to the Bitget Agent Hub in
paper-trading mode and come back `HTTP 400: exchange environment is incorrect` —
because Bitget's demo venue lists nine contracts and none of them is a tokenized
stock perp. So no fill on the chain carries an exchange order id, and every row
on the settled page says so: `simulated · Hub HTTP 400 · no order id`.

Every decision is written to a **hash-chained, signed ledger before the outcome
is known**. An independent second opinion — Bitget's MCP stock service — is asked
the same calendar question for every decision. **Across 204 decisions it agrees on
194 and disagrees on 10.** The ten are five names — ADBE, ORCL, COST, MU and NKE —
each disagreeing on *both* nights of its event window, and every one points the
same way: Nasdaq's calendar carried an earnings date and Bitget's service returned
none. Two of them are the 2026-09-09 ADBE and ORCL rows I had already published as
my own defect, which is an independent source landing on rows I'd marked wrong. MU
settles another on the record — it reported, and the position moved 296 bp on the
night Bitget's calendar said nothing was scheduled.

When that service went down for a day and answered `503`, every decision was
recorded `unknown`, never as agreement. That is the half that matters more: a
second source that fails open is worse than none. The site renders this from the
file on every build, so if the page and this paragraph differ, the page is right.

### What I'm not claiming

No return claim. No Sharpe claim. 13 hedges over 17 nights cannot support one, and
the research says direction isn't predictable anyway.

Tail coverage is the open problem: the calendar reaches 2 of the worst 6
position-nights. Macro shocks, guidance and legal rulings appear on no calendar.
That gap is what the model is for, and it's a measured requirement rather than an
assumption.

### Verify it

`git clone`, then `python3 verify.py`. One command, no key, no network. It runs
529 tests, requires the enforcer to refuse a naked directional order, re-derives
the hash chain, mutates a copy and requires verification to fail, and checks that
every published figure comes from measurement rather than a literal.

Give a model judgment. Never give it the keys.

Live demo — every night, every call, every correction:
ballast-v1.vercel.app

Code, ledger and research:
github.com/Ritapossible/Ballast

#BitgetHackathon @Bitget_AI

---

## Do not add

- Any Sharpe, edge or return claim. The return is *behind* doing nothing.
- "Live trading" — fills are simulated and every row says so.
- That tail coverage is solved. It reaches 2 of the worst 6.
- Rounded-up figures. 98.2% is a median, not a floor.
