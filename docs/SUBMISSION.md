# Submission - Bitget AI Base Camp Hackathon S2

Paste each part into the matching form field. Judges weight **parts 1–3 most heavily**.
Every figure is labelled `observed` / `estimated` / `targeted` as the form requires, and
each is reproducible from `research/` with no API key.

| Field | Value |
|---|---|
| **Track** | Agentic Trading |
| **Sub-theme** | Event-Driven Agent |
| **Project** | Ballast |
| **Demo** | https://ballast-v1.vercel.app · docs at `/docs` |
| **Code** | https://github.com/Ritapossible/Ballast |
| **X post** | ⚠️ *fill in - must include `#BitgetHackathon` and `@Bitget_AI`* |

---

## 1 · Thesis

**Tokenized US stocks trade around the clock. The market that prices them is open 32.5 of
every 168 hours, so for ~81% of the week a holder carries exposure to an asset whose
reference market is shut** - through earnings, through the Fed, through weekends. Their
only options today are to sell before the close and give up the position, or hold and
absorb whatever arrives. Measured overnight moves in this sample reach **1,262 bp in a
single night** (`observed`).

Ballast adds a third option: **keep the position, and switch the night's risk off for a
stated price.**

**The mechanism.** Of 1,173 live rTokens, **241 have a matched stock perpetual** trading the
same 24/7 clock (`observed`). Shorting that perp against the token removes a **median 98.2%
of overnight variance at β within 4% of 1.00** across 12 names and 100–264 nights each
(`observed`). It costs **11.3 bp** taker round trip net of funding received - against
**20 bp** to exit the position and lose it (`estimated` from observed fee schedules).

Critically, **the hedge strengthens under stress**: R² is 0.978–0.999 on top-decile move
nights and 0.77–0.96 on calm ones (`observed`). On a big-news night the common factor
dominates and both instruments track it almost exactly; on a quiet night the residual is
venue microstructure noise. It is imprecise only when little is at stake.

**Signal sources and decision logic.** A delta hedge is symmetric - it removes upside with
downside - so value exists only on nights carrying variance *without* compensation. Two
selectors were tested against that bar:

| Selector | Separation | Compensated? | Verdict |
|---|---|---|---|
| Trailing realised volatility | 1.41× | **yes** - +19.3 bp, t=3.08 | rejected |
| **Earnings calendar** | **3.2×** | **no** - −61 bp, t=−1.59, 0/15 names significant | **adopted** |

Volatility barely distinguishes a risky night and the nights it picks carry positive
expected return, so hedging them *pays to remove return*. **The volatility gate therefore
ships disabled**, with that measurement written into the code comment. Earnings nights
separate three times better and carry no reliable compensation: 1σ of **392 bp against an
11.3 bp cost, roughly 35:1** (`observed`).

The calendar alone is insufficient - in replay it covered only 2 of the 6 worst
position-nights. Macro shocks, guidance, legal rulings and product events drive the rest and
appear on no calendar. **That gap is what the LLM is for**, and it is a measured requirement
rather than an assumption.

**Risk controls.** The central claim is a negative capability, enforced structurally:

> Ballast cannot place a bet. Every order it is capable of emitting is opposite in sign to,
> and bounded in size by, a spot position already held. There is no code path to a
> directional trade.

An enforcer runs as a separate process holding the only write-scoped credential. It never
sees the model's reasoning; it checks arithmetic against a signed, expiring mandate - a
position exists, the order opposes it, size within ratio, symbol in universe, night caps
intact. **18 red-team tests** drive hostile intents at it, each asserting the specific rule
that refused it.

## 2 · Target user and product value

**Conviction holders of tokenized US equities.**

| | |
|---|---|
| Segment | Retail to pro; **not** institutions, **not** intraday traders |
| Holding | 1–10 rToken positions, held **weeks to months** |
| Size | **500–50,000 USDT** per position |
| Risk appetite | Directionally bullish, **drawdown-averse** |
| Frequency | Acts 1–2 times a month, not daily |
| Exposure | **10–20 high-impact overnight events per year, per name** |

The defining trait: **they will not exit before a catalyst, because exiting defeats a
multi-month thesis.** Someone holding rPLTR on a twelve-month view does not want to be flat
into earnings - they want the position and not the gap.

**Why every existing option fails them, specifically:**

- **Exiting** costs 20 bp round trip *and* surrenders the position.
- **Options** do not exist on rTokens.
- **Hedging in the underlying** is impossible - that market is closed, which is the whole
  problem.
- **Reducing size** is unexecutable at weekends, when rToken spot books are thin and the
  exposure window is longest.

**The value, stated plainly:** for ~11 bp they keep the position and remove ~98% of a
specific night's variance - median **88% off the p95 tail**, MSFT's worst night **1,128 bp →
233 bp**, AMD's **1,262 bp → 90 bp** (`observed`). Ballast also states which of their
positions it *cannot* protect: **932 of 1,173 rTokens have no perp leg.**

## 3 · Validation data and key metrics

**Test period.** Hedge measurements: 2024-05 → 2026-09, 12 names, 100–264 overnight windows
each. Selector tests: 2025-10 → 2026-09, 15 names. Policy replay: 55 sessions × 12
equal-weighted positions. Forward paper log: from 2026-09-08, running to submission.

**Costs modelled, never assumed away.** Perp taker 0.06% each way, funding accrued on 8h
boundaries, 2 bp modelled slippage. **All costs default to taker** - maker fills would be
~3.3 bp but a 4am perp book may not fill a resting order, so maker pricing is treated as
upside and never assumed.

### Mechanism (`observed`)

| Metric | Value |
|---|---|
| Median overnight variance removed | **98.2%** |
| Hedge ratio β | 0.985–1.040 (12 names) |
| R² on top-decile move nights | **0.978–0.999** |
| R² on calm nights | 0.77–0.96 |
| Median p95 tail reduction | **88%** |
| Weekend (Fri→Mon) R² | 0.941–0.992 |
| Median R² against BTC | 0.114 - crypto is **not** a hedge |

### Policy replay, calendar-led (`observed`)

| Metric | Unhedged | Ballast |
|---|---|---|
| Volatility (annualised) | 20.65% | **18.35%** |
| Max drawdown | 10.15% | **9.24%** |
| Total return | 1.11% | −0.75% |
| Turnover | - | **2.4%** of position-nights |
| Cost drag | - | **0.3 bp** per position-night |
| Hedges that reduced the move | - | **15 of 16 (94%)** |

**Metric definitions, stated so they cannot be misread.** Every call is scored against the
**signed P&L of the choice refused**: hedging wins on a night that fell, declining wins on a
night that rose or stayed flat. Scoring on the size of the move alone would say "always
hedge", which is the policy the research rejected. *Tail coverage* is the share of the worst
1%/5%/10% of position-nights that were hedged.

### The open question

**Tail coverage is the open problem**: 2 of the worst 6 position-nights, 6 of the worst 33.
The mechanism fires accurately and costs almost nothing; its *reach* is incomplete because
v0's selector reads a calendar. Extending it to unscheduled events is the reader's job.

**No return claim is made.** 16 hedges over 55 sessions cannot support one, and Gate 1b says
direction is not predictable. **Ballast is priced protection, not alpha, and makes no Sharpe
claim.** Insurance carrying negative expected value is not a defect - that is what insurance
is.

### Live forward record (`observed`)

The scheduled job runs unattended. Session **2026-09-09**: 12 positions, **ORCL and ADBE
hedged** on scheduled earnings (1,978 USDT notional), 10 declined - including **COIN at a
423 bp 1σ, refused because volatility alone is not a reason to spend 11 bp.** That is the
Gate 1 result behaving as measured, on live data, decided by a job nobody was watching.

## 4 · Progress

**Built and working:** the full nightly loop (calendar → reader → engine → enforcer →
executor → ledger), morning settlement against the exact counterfactual, the signed
tamper-evident ledger, the enforcer and its red-team suite, the Qwen event reader with three
verification gates, the research suite behind every number, a scheduled workflow that runs
and commits unattended, and a public site with full documentation. **79 tests, network-free
and key-free.**

**Not built:** live execution (paper only, by choice); Bitget Agentic Account OAuth wiring -
fills are simulated against observed prices with the real fee schedule, then exported in UTA
order field names; US exchange holidays in the session calendar.

**Problems found and fixed - published rather than quietly corrected:**

1. **DST** - the US close was hardcoded at 20:00 UTC while four months of sample were EST.
   Fixed; both transitions pinned by test.
2. **Look-ahead** - the first neutrality test selected nights by *realised* move. Fixed; the
   invalid version survives behind a flag to document it.
3. **Hour-snapping** - the 09:30 ET open does not fall on an hourly bar boundary, so price
   lookups silently missed every time. Fixed.
3b. **A holiday counted as a trading day** - the function picking the session to trade tested
   only for a weekday while the rest of the calendar excludes holidays, so Thanksgiving came
   back as a tradeable session. Fixed.
3f. **The calendar selector hedged a night early** - it matched the session date or the next
   session's without checking the release time, so an after-hours report on the next session
   hedged both nights. The 2026-09-09 ORCL and ADBE hedges were such cases; they cut the move
   but for a reason that was not true of that window. Fixed, disclosed on the settled page,
   and the replay now shares the selector instead of copying the rule.
3e. **The night could be decided twice** - settlement was made idempotent in the audit, the
   decide half was not. A repeat run doubled the decisions, the notional against one book,
   and the settlement grades. Now a no-op.
3d. **A session decided after its own window** - a run taken while testing re-decided the
   2026-09-09 session 16.8 hours after its close, 45 minutes before the reopen, while
   settlement still graded it close-to-open. The entry stays in the chain and now discloses
   its own lag; the night run refuses a window more than half elapsed, and records the lag
   on every run.
3c. **Settlement never ran unattended** - the gitignored cache directory has no parent on a
   fresh runner, so every scheduled settlement failed from the day the loop was automated.
   Invisible locally, and invisible to tests that mock the market client. Fixed; the pages
   now state how many sessions behind they are, so the next silent stoppage shows up.
4. **A broken metric, twice** - an early "decision accuracy" compared move against cost on
   every night, scoring nearly every unhedged night as an error. Its replacement, signed
   value added, is the right number, but was still shown as a per-night correct/wrong on
   refusals - positive exactly when the position rose, which is a directional verdict this
   system does not make. Refusals now carry their arithmetic and no verdict; hedges are
   graded on whether they cut the move. Both fixed.
5. **A policy that lost money** - the first replay hedged 45% of nights and cost ~13% a year.
   Diagnosed to the selector, not the mechanism, and published as a negative result. **No
   parameters were tuned to make that table look better.**

**Held out:** the hedge ratio is fitted on the first 70% of each name's nights and applied
unchanged to the last 30%. Median variance removed 0.980 to 0.996, median p95 tail cut 86% to
94%, median absolute beta drift 0.009, twelve of twelve names holding. A hedge is a mechanism
rather than an edge, so the test it must pass is that nothing decays on unseen data. The
out-of-sample figures being *higher* is a property of that period, not an improvement.

**Measured on the instrument.** A tokenized US stock trades continuously, so its overnight
move is a path through the closed window rather than a gap at the bell - a close-to-open gap
measured on the listed share describes a different instrument from the one being held. Every
price here comes from the rToken's own candles and the matched perpetual's, one endpoint, no
equity feed and nothing synthetic. Nasdaq supplies event dates only, never a price.

**Verify it:** `git clone` then `python3 verify.py` - one command, no key, no network. It runs
the suite, requires the enforcer to refuse a naked directional order, re-derives the hash chain,
mutates a ledger copy and requires verification to fail, checks every published figure comes
from `docs/facts.json` rather than a literal, and builds all five pages. What needs the
exchange, it names rather than pretends to check.

**Next:** measure whether the reader closes the tail-coverage gap; wire the Agentic Account;
model exchange holidays.

**Stack:** Python 3.11, standard library only - no third-party dependencies. Bitget public
market API (spot + USDT-futures), Nasdaq earnings calendar, Google News RSS, Qwen
`qwen3.8-max` via `hackathon.bitgetops.com/v1`.

## 5 · Deliverables

| | |
|---|---|
| **Live demo** | https://ballast-v1.vercel.app |
| **Documentation** | https://ballast-v1.vercel.app/docs - 17 sections incl. the defects found and the roadmap |
| **Source** | https://github.com/Ritapossible/Ballast |
| **Paper trading log** | `state/ledger.jsonl` - hash-chained, signed, committed by the scheduled job |
| **Bitget-schema log** | `state/bitget_orders.json` - the same fills in UTA order field names |
| **Research suite** | `research/` - reproduces every figure, no API key needed |
| **Tests** | `python3 -m unittest discover -s tests` - 103, network-free, incl. 17 end-to-end |
| **Workflows** | `.github/workflows/` - nightly loop and CI |

**Why the log is evidence rather than assertion:** each decision is written before its
outcome is known, the chain breaks if any entry is edited, and GitHub timestamps each commit
independently. The chain proves nothing was altered; the commit history proves nothing was
backfilled.

## 6 · Take on AI trading

The useful question is not how much autonomy to give a model, but **which part of the job it
is actually better at.**

We measured that directly. A statistical selector - trailing volatility - separates risky
nights at 1.41×, and the nights it picks carry compensated return, so acting on it destroys
value. A calendar does three times better. Neither reaches most of the tail, because
overnight equity risk arrives as *events*, and events arrive as *text*. That is a real gap
that arithmetic cannot close and a language model can.

So Ballast gives the model exactly that: it reads the night and owns the hedge judgment. It
does not size, price or direct anything, because those are arithmetic and arithmetic should
be deterministic, auditable and testable.

**The corollary is that autonomy and safety are not a trade-off if the boundary is drawn in
the right place.** Ballast's model has genuine authority - it can overrule the calendar in
both directions - and simultaneously cannot place a directional trade, because the enforcer
that permits orders has never seen the model's output and only does arithmetic against a
signed mandate. Give a model judgment; never give it the keys.

---

## Role of the LLM (separate form field)

**Qwen `qwen3.8-max`**, via `https://hackathon.bitgetops.com/v1`, at **temperature 0** so
judgments are reproducible.

**What it does:** reads the night's headlines plus the exchange calendar flag for one ticker
and returns the **HEDGE / NO_HEDGE / ABSTAIN judgment**, with an event classification,
expected impact, confidence, a verbatim supporting quote, and what it could not determine.
**That judgment leads** - it can overrule the deterministic calendar rule in either
direction.

**What it cannot do:** there is no size, side, price or quantity field anywhere in its output
contract, and a test asserts their absence. Three gates stand between it and an order:

1. **Schema** - the answer parses into the contracted shape, or it is refused.
2. **Identity** - a judgment about a different ticker is never accepted.
3. **Grounding** - the quoted headline must appear in the supplied sources. **A fabricated
   source cannot reach the book.**

Anything failing a gate is discarded and the calendar rule decides instead. Degradation is
transparent: with no key the reader abstains, the rule decides, and both the abstention and
its reason are written to the ledger - so a night decided without the model is visibly a
night decided without the model.

**Qwen was also used as a development tool** for parts of the build, alongside the analysis
in `research/`.
