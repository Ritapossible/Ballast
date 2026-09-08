# Ballast — Build Plan
**Bitget AI Base Camp Hackathon S2 · Agentic Trading · Event-Driven Agent**
Deadline **2026-09-21 (UTC+8)** · plan written 2026-09-08 · **13 days**

---

## 0. What is measured, and what is not

Everything below marked ✅ was computed from Bitget public endpoints on 2026-09-08.
Label discipline follows the submission form's own requirement (observed / estimated / targeted).

| Finding | Status |
|---|---|
| 699 rTokens live on spot; **219 have a matched perp leg** | ✅ observed |
| rToken spot history pages back **over 2 years** (RTSLA reaches 2024-05-28) hourly via `history-candles?endTime=` | ✅ observed |
| Overnight perp hedge: median **R² 0.980**, β within 4% of 1.00, split-half stable | ✅ observed, n≈100–260 nights × 12 names |
| Hedge **improves under stress**: top-decile nights R² 0.978–1.000 | ✅ observed |
| Tail: median **88% cut in p95 |move|**; MSFT worst night 1,128bp → 233bp, AMD 1,262bp → 90bp | ✅ observed |
| Weekend (Fri→Mon) hedge holds: R² 0.941–0.992 | ✅ observed |
| Cost: perp taker round trip **11.3bp** net of funding received; ~3.3bp at maker | ✅ observed |
| rToken spot exit costs **20bp** round trip (0.1% both ways, no maker discount) | ✅ observed |
| Funding is positive → a short perp **receives** ~3.9% annualised | ✅ observed |
| Gate 1: ex-ante vol selection separates at only **1.41×** | ✅ observed — selector must be the event calendar |

### Two known defects in the current numbers

1. **DST bug** — US close hardcoded at 20:00 UTC while ~4 months of sample were EST. **Fixed** in `research/sessions.py`, verified across both transitions.
2. **Selection look-ahead** — the first zero-mean test selected nights by *realised* move. **Fixed**; the invalid version survives behind `--lookahead` to document the bug.
3. **Hour-snapping** — the 09:30 ET open does not fall on an hourly bar boundary, so price lookups silently missed. **Fixed** in `research/overnight.py`.
4. **US exchange holidays are not modelled.** *Open* — affects window length, not the hedge relationship.

---

## 1. Gate 1 — RESOLVED 2026-09-08 · **Positioning B**

**The question:** a delta hedge is symmetric, so value exists only if the nights we hedge
carry variance *without* compensation. Two conditions had to hold.

| Condition | Result | Verdict |
|---|---|---|
| **(a) Separation** — do selected nights actually carry more variance? | ex-ante variance ratio **1.41×** (ex-post: 13.2×) | **FAIL** |
| **(b) Neutrality** — is their mean return indistinguishable from zero? | pooled **+19.3 bp**, t = 3.08 | reads **compensated** |

Reproduce: `python3 research/gate1_selection.py` · full reading in `docs/RESEARCH.md §5`.

### What this changes

**1. The selector is the event calendar, not a statistic.** Trailing realised volatility
barely separates risky nights from ordinary ones (1.41×), while the same nights chosen
*ex post* separate at 13.2×. High-variance nights exist; volatility persistence cannot
find them, because overnight equity variance is driven by **scheduled events**. This is
now the strongest argument for the architecture: the quantitative selector demonstrably
fails, so the textual one is load-bearing rather than decorative.

**2. We adopt Positioning B — priced protection, not alpha.** Ballast is measured in tail
and drawdown reduction per basis point spent. **It does not claim a Sharpe improvement.**
Insurance having negative expected value is not a defect; that is what insurance is.

**3. The neutrality result is weaker than its t-stat.** No individual name reaches
significance (all |t| < 1.7); the pooled t = 3.08 stacks 12 names that move together on the
same nights, inflating significance by ignoring cross-sectional correlation. We take the
conservative reading rather than the flattering one — but this is exactly the kind of
figure that must be labelled, never leaned on.

### Still to resolve — earnings-conditional selection
Gate 1 tested a *statistical* selector and it failed. The event-calendar selector is
untested because we have no earnings-date source yet. **Day 1: wire a real earnings
calendar and re-run (b) on calendar-selected nights.** Do not fabricate dates.


---

## 2. Locked decisions

| | Decision |
|---|---|
| **Track** | Agentic Trading — **single entry** |
| **Sub-theme** | Event-Driven Agent |
| **Why not Alpha Factory** | Pure-quantitative scoring on Sharpe/Sortino of a *return stream*. Ballast is an overlay; scored standalone the hedge leg is meaningless, and asking a judge to adopt our benchmark framing is a risk in a track that says "pure quantitative." |
| **Second entry** | **Not committed.** Candidate exists (is the post-hedge basis tradeable?) but is unmeasured. Decide at Day 9 checkpoint, not before. Two thin entries lose to one complete one. |
| **Universe** | The 219 rTokens with a matched perp. Everything else is explicitly out of scope and *reported as such* — knowing which positions are unprotectable is part of the product. |
| **Paper venue** | Bitget Agentic Account (OAuth sub-account: fund isolation, quota control, no withdrawals) in `--paper-trading` mode |

### The claim (one sentence — P4)

> **Ballast lets you hold tokenized US stocks through the night without holding the night's risk — one decision per position, priced before you sleep, settled at the opening bell.**

### The negative capability (P3)

> **Ballast cannot place a bet.** Every order it is structurally capable of emitting is a hedge, opposite in sign and bounded in size by a spot position you already hold. There is no code path to a directional trade.

This is enforced, not promised — see §4, Mandate Enforcer.

### Target user (form Part 2 — "all traders" is explicitly rejected)

**Conviction holders of tokenized US equities.**
- Holds 1–10 rToken positions continuously for **weeks to months**, not intraday
- Position size **500–50,000 USDT**; retail to pro, not institutional
- Directionally bullish, **drawdown-averse**; will not exit before a catalyst because exiting defeats a multi-month thesis
- Faces **10–20 high-impact overnight events per year per name** (earnings, guidance, macro, legal)
- Acts 1–2 times a month, not daily

**Why existing options fail them:** exiting costs 20bp round trip *and* surrenders the position; there are no options on rTokens; the underlying equity market is shut so it cannot be hedged there; and weekend rToken spot books are thin, so the exit may not even be available when the exposure is longest.

---

## 3. Architecture

```
CALENDAR   ex-ante risk selection: earnings dates, macro calendar,
           trailing realised vol, closure length (weekend/holiday)
              |
READER     LLM (Qwen) reads tonight's unstructured news for the ticker
           -> NightRisk { event_type, scheduled_time, expected_impact,
                          confidence, source_url, verbatim_quote, unknowns[] }
           translation only; never a number, never a size        [P11]
              |
ENGINE     deterministic: risk_forecast(vol, event, window_hours)
           vs cost(11.3bp) under the user's mandate
           -> HEDGE | NO_HEDGE | REDUCE
              |
ENFORCER   separate process, holds the only write-scoped key.
           Rejects any order that is not (a) opposite in sign to an
           existing spot position, (b) <= spot notional x max_ratio,
           (c) in the mandated universe, (d) before mandate expiry.  [P12]
              |
EXECUTOR   Bitget SDK, paper mode, order state machine
              |
LEDGER     append-only signed record: decision + reasoning + inputs
              |
SETTLEMENT at the primary open: outcome vs EXACT counterfactual
```

### The evidence property that makes this winnable

**Every decision has an exact counterfactual.** "What would have happened if I had not hedged" is not estimated — it is the observed rToken return. Both good and bad decisions are precisely graded, every morning, without argument. Most trading agents cannot say this; it is the strongest single asset of the design and should be the centrepiece of the demo.

### Design rules carried from the vault

| Rule | Application |
|---|---|
| P11 — LLM translates, engine computes | Model returns `NightRisk`, never a size |
| P12 — bounded authority | Enforcer in a separate process; hedge-only by construction |
| P13 — selection over generation | Symbols resolved against the live 219-pair index; never a fabricated ticker |
| P16 — precision as architecture | An event needs corroboration before it can change sizing |
| P18 — traceable output | Every decision ships reasoning + verbatim source + reference + named unknowns |
| P6 — disclose weakness | Claim-boundary table, published, before a judge finds it |

---

## 4. Critical path

**The paper log is the only deliverable that cannot be compressed.** Agentic Trading requires a log run during the competition (2+ weeks recommended; 13 days is all that exists). Every day of delay is a night that can never be recovered.

> **Day 1 ships a deliberately naive but correct nightly loop into paper trading. The policy improves for twelve days around a log that is already running.**

| Day | Work | Gate |
|---|---|---|
| **0** | ✅ *done* — Gate 1, DST calendar, data layer, universe resolution, hedge study, research docs |  |
| **1** | Earnings-calendar source + re-run neutrality on calendar-selected nights. **Naive nightly loop live in paper by tonight**: fixed vol threshold, hedge/no-hedge, unwind at open, signed log. First X dev-log post. | Calendar selector beats 1.41× separation |
| 2–3 | Pair resolution (219). Cost model: fees, 8h funding accrual, slippage. Backtest harness over 200+ nights with a ≥30-day OOS holdout. | Backtest reproduces the measured R²/tail numbers |
| 4–5 | Risk-forecast model (ex-ante only). Decision engine + mandate schema. **Enforcer + red-team suite.** | Hostile intents → 0 directional orders admitted |
| 6–7 | Qwen event reader → `NightRisk`. Corroboration stage. Swap naive policy for full policy in the live loop. | Live loop runs the real policy |
| 8–9 | Settlement + counterfactual scorecard. Morning brief surface. | **Checkpoint: second entry — go or no-go** |
| 10–11 | Judge-facing reproduction pack (one command). Claim-boundary table. Demo video. | `make judge` green from a clean clone |
| 12 | Six-part description. X posts. Buffer. | |
| 13 | **Submit early.** Deadline is UTC+8 — do not discover the timezone on the day. | |

### Events available inside the window ✅

- **Hedgeable September reporters:** ORCL, ADBE, NKE, MU, COST, CCL — all six have both legs
- **FOMC** falls mid-September — a guaranteed high-impact macro night
- All 12 mega-caps (TSLA, NVDA, AAPL, MSFT, AMZN, META, GOOGL, PLTR, COIN, AMD, SPY, QQQ) hedgeable

The flagship earnings-night demo **can** be shown live. Confirm exact report dates on Day 1 and build the paper portfolio around them.

---

## 5. Metric definitions — write these before a judge invents their own

The rubric names *paper Sharpe, max drawdown, win rate*. Define each in our terms, publish the definition, and never present the hedge leg standalone.

- **Portfolio Sharpe / Sortino** — hedged vs unhedged, **same positions, same nights**. Always paired. The unhedged series is the benchmark and is always shown beside it.
- **Max drawdown** — portfolio level, hedged vs unhedged. Expected to be the strongest number.
- **Win rate** — fraction of decisions correct ex-post, defined symmetrically:
  - HEDGED and |unhedged move| × notional > hedge cost → correct
  - NOT HEDGED and |unhedged move| × notional < hedge cost → correct
- **Tail reduction** — p95 and worst-night |move|, hedged vs unhedged
- **Cost per bp of risk removed** — the honest unit price of the product
- **Turnover** — low by construction; state it

Label every figure **observed / estimated / targeted**, as the form requires.

---

## 6. Evidence pack (what a judge can verify without us)

1. **One-command reproduction** from a clean clone — deterministic, network-free tests
2. **Signed nightly ledger** with the counterfactual column
3. **Red-team suite**: N hostile intents → 0 directional orders admitted
4. **Claim-boundary table** — proven / paper evidence / not claimed
5. **Static always-on fallback** for the demo surface, so a cold host never blocks a judge
6. **Public read-only endpoint** a judge can curl

---

## 7. Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Gate 1 says risk is compensated | High | Positioning B (insurance). Engine unchanged. Decided Day 1. |
| 2 | DST / timezone errors corrupt every downstream number | High | Session-calendar module with tests, Day 1, before anything else |
| 3 | Cost model too optimistic (maker fills assumed, thin 4am book) | High | Default to **taker** costs everywhere; treat maker as upside only |
| 4 | Paper-mode perp shorting unavailable on Agentic Account | High | **Verify Day 1.** Fallback: simulate fills against observed book. |
| 5 | Paper log too short to be persuasive | Medium | Start Day 1; pair with the 200-night backtest |
| 6 | Judge scores the hedge leg standalone | Medium | Never present it standalone; always the paired portfolio |
| 7 | Holder base may not actually hold overnight in size | Medium | Ask in Telegram; if weak, lean the pitch on the concentrated-position case |
| 8 | Second entry dilutes the first | Medium | Default is one entry; Day 9 checkpoint must clear a high bar |

---

## 8. Submission mapping (judges weight parts 1–3 most heavily)

| Part | Content |
|---|---|
| 1 · Thesis | Overnight structural exposure; the hedge; the ex-ante selection rule; the enforcement layer |
| 2 · Target user & value | The conviction holder, §2 — specific segment, capital, frequency, and why exit/options/underlying all fail |
| 3 · Validation & metrics | §5 metrics, hedged vs unhedged, backtest + forward paper, every figure labelled |
| 4 · Progress | What is built, what is not, the DST bug and the look-ahead bug and how both were fixed |
| 5 · Deliverables | Repo, demo, ledger, reproduction pack, video |
| 6 · Take on AI trading | Where the LLM belongs and where it must be kept out of the decision |

**Role of LLM field:** Qwen (`qwen3.8-max` via `hackathon.bitgetops.com/v1`) for unstructured event extraction into `NightRisk` only. All sizing, pricing, gating and grading is deterministic typed code. State this plainly — it is a strength, not a limitation.

**Validity (non-negotiable):** compliant X post with `#BitgetHackathon` + `@Bitget_AI`, project description, publicly accessible materials. Any one missing = rejected regardless of quality.

---

## 9. What we will NOT build

Scope discipline is the difference between finishing and not (P4 — breadth loses to one clear claim).

- ✗ A multi-panel dashboard — one decision surface and one morning brief
- ✗ Crypto hedge legs (measured: median BTC R² 0.114 — it does not work)
- ✗ Directional alpha of any kind
- ✗ Coverage of all 699 rTokens — 219 hedgeable, stated plainly
- ✗ Live capital — paper only; no real fill is claimed
- ✗ A second track entry unless Day 9 clears it
