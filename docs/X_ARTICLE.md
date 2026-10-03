# X article — Ballast

Long-form post for X. Every figure is from `docs/facts.json`, the signed ledger,
or `state/calendar_crosscheck.json`, measured 2026-09-25. **Re-check before
posting** — the nightly moves the live-record numbers.

Must contain `#BitgetHackathon` and `@Bitget_AI`.

---

## Title

**I built an agent to hedge overnight risk. Its own log says it's arriving too late to work. Here's the number.**

## Body

Bitget lists 2,810 tokenized US stocks. They trade 24/7.

The market that prices the share underneath them is open 32.5 hours a week.

So for about 81% of every week you hold an asset whose reference market is shut —
through earnings, through the Fed, through the weekend. Your options today are to
sell before the close and give up a position you believe in, or hold and take
whatever arrives at 3am.

Ballast adds a third: keep the position, switch off that night's risk, pay a
stated price.

The mechanism works. The execution doesn't yet, and I only know that because the
log caught me. That's the post.

### The mechanism

Of those 2,810 rTokens, **241 have a matched stock perpetual** trading the same
24/7 clock. Short the perp against the token and you remove a **median 98.2% of
overnight variance**, with hedge ratios between **0.992 and 1.027** across 12
names and 100–264 nights each.

It costs **12.0 bp** taker round trip — the certain part. A short also collects
funding, bringing the average night to about **11.3 bp**. Exiting the position
instead costs **20 bp** and you lose the position.

The hedge gets *better* under stress: R² runs **0.978–0.999** on top-decile move
nights and 0.77–0.96 on calm ones. On a big-news night the common factor dominates
and both legs track it almost exactly. It's imprecise only when little is at stake.

Held out properly: fitted on the first 70% of each name's nights, applied
unchanged to the last 30%. Median variance removed **0.980 → 0.996**, median tail
cut **86% → 94%**, median absolute beta drift **0.009**, twelve of twelve names
holding.

None of that moved tonight. It's measured on paired candles and never involved a
decision timestamp.

### The part I didn't expect, round one

A delta hedge is symmetric. It removes upside with downside. So it only creates
value on nights that carry variance *without* compensation.

I tested two ways to pick those nights.

**Trailing volatility** separates risky nights at **1.41×** — and the nights it
picks carry positive expected return, **+19.3 bp, t=3.08**. Hedging them pays to
remove return.

**The earnings calendar** separates at **3.2×**, with no reliable compensation:
−61 bp, t=−1.59, 0 of 15 names significant. About 392 bp of overnight movement
against an 11.3 bp cost.

So the volatility gate **ships disabled**, with that measurement in the code
comment next to it. A negative result, shipped off.

### What the model actually does

Qwen `qwen3.8-max`, temperature 0, reads the night's headlines plus the calendar
flag for one ticker and returns a **HEDGE / NO_HEDGE / ABSTAIN** judgment. That
judgment leads — it can overrule the calendar in both directions.

It cannot size, price or direct anything. There is no field for quantity, side or
price anywhere in its output contract, and a test asserts their absence. Three
gates stand between it and an order: the answer must parse into the contracted
shape, it must be about the right ticker, and **the quote it cites must appear in
the headlines it was given**.

Over 216 decisions on the live chain: **143 decided by the model, 73 by the rule**.
The gates refused **30 answers for quoting a headline that wasn't in the sources**
and 3 for schema violations, and the rule took over on 26 nights where the model
was unreachable. On the remaining 14 the model answered cleanly and said it did not
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

- **10 of 11 graded hedges cut the move.** Two more were sent and are excluded —
  a defect I published: the selector matched a session without checking the
  release time and covered a night early.
- **Max drawdown −235 bp, against −227 bp untouched.** That is 8 bp worse, not
  better.
- **Total return +209 bp, against +279 bp untouched.** The book carrying Ballast
  made *less* than the book left alone.
- Sharpe is +2.00 vs +2.53.

Read the first two lines again. This is an insurance product, and insurance is
supposed to show up as a **smaller worst case**. On this record it doesn't. The
protected book is worse on drawdown, worse on return, worse on Sharpe.

Until last night the same page said −203 against −227 and called it 24 bp of
protection.

### What I had wrong

I was grading every hedge over the whole close-to-open window, as though the perp
short had been on from the closing bell. It never was.

GitHub delays the 21:00Z cron and the 00:00Z backup fires instead, so **all
thirteen hedges went on between 1.7 and 16.8 hours after the close** — a median
21% of the night already gone. On an earnings night, the move lands in the first
hour.

Grading the full window subtracts the perp leg from a fall the hedge was not there
for. **NKE on 1 October was recorded as +17 bp. It actually cost 526 bp.** The
position had already fallen 560 bp by the time the order went in; it rebounded 314
bp afterwards, and the hedge was short into the rebound. A 542 bp swing on one
row, and the verdict flipped from "cut the move" to "did not cut".

The worst part: the lag was never unmeasured. `window_elapsed_at_decision` was
written into every night summary from early on. **Nothing read it.** I had
instrumented the exact failure and then graded as if it couldn't happen.

Every hedge is now graded from its own signed fill timestamp, the night cut in two
at that moment, the hedge credited only with the part that followed. The seventeen
signed settlements are **not edited** — the chain is append-only, so each
correction sits beside the record it supersedes and the table prints both numbers.
You can see +17 and −526 on the same row.

While fixing it I found the sentence introducing that comparison read *"it should
show up as a smaller worst case, and it does"* — with "and it does" typed beside
the two numbers that decide it. It would have asserted protection while printing a
worse drawdown one clause later. Both verdicts are read off the figures now.

### And then the operations bug underneath it

Last night, 2 October, GitHub dropped the decide cron *and* its backup. The only
job that fired was a settle run arriving four hours late — and because a delayed
schedule is delivered under its original cron string, it matched the settle branch
and skipped deciding entirely. **The job went green having decided nothing.**

The Friday-to-Monday window is 65.5 hours, the longest exposure this book ever
carries, and it had no decision on the chain. I ran it by hand 4.1 hours after the
close: twelve positions, all refused.

So there's an operations bug sitting directly under the grading bug, and they're
the same bug wearing two hats: **the desk decides too late to own the night it's
grading.**

### What I'm not claiming

No return claim. No Sharpe claim. 13 hedges over 17 nights cannot support one, and
the research says direction isn't predictable anyway.

The 17-night log does **not** confirm the mechanism. It isn't allowed to any more.
The long-sample evidence — 98.2% of variance removed, the held-out test, the tail
chart across 100–264 nights per name — is the measurement with a real sample. The
live log's job is to say whether the desk can actually deliver that, and right now
the honest answer is not yet.

Tail coverage is the other open problem: the calendar reaches 2 of the worst 6
position-nights. Macro shocks, guidance and legal rulings appear on no calendar.

### Why I'm posting the version that looks worse

I could have left the old grading in. It was already published, nobody had
questioned it, and it said 11 of 11 and 24 bp of protection.

But the entire argument for this project is that its claims are checkable. A
checkable claim you quietly decline to check is just a claim. The re-grade is
reproducible from the signed decisions and the public candle endpoint — anyone
with the ledger derives the same thirteen rows.

An independent second opinion, Bitget's own MCP stock service, is asked the same
calendar question for every decision. **Across 216 decisions it agrees on
206 and disagrees on 10.** The ten are five names, each disagreeing on both nights
of its event window, every one the same way: Nasdaq carried an earnings date,
Bitget's service returned none. When that service went down and answered `503`,
every decision was recorded `unknown`, never as agreement. A second source that
fails open is worse than none.

### Verify it

`git clone`, then `python3 verify.py`. One command, no key, no network. It runs
552 tests, requires the enforcer to refuse a naked directional order, re-derives
the hash chain, mutates a copy and requires verification to fail, and checks that
every published figure comes from measurement rather than a literal.

The next thing I build is not a model change. It's a decide job that fires near
the close, so the next NKE is actually hedged for the move it was hedged against.

Give a model judgment. Never give it the keys. And let the log tell you when
you're wrong.

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
