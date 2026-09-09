# Research findings

Every figure here is produced by `research/`. Reproduce with the commands in
`research/README.md` — no API key required. Labels follow the submission form's
convention: **observed** (measured), **estimated** (derived under stated assumptions),
**targeted** (a goal, not a result).

Measurement date **2026-09-08**. Data: Bitget public endpoints only.

---

## 1. The exposure

The US primary market is open 6.5 hours a day, five days a week — **32.5 of every 168
hours**. For the remaining ~81% of the week an rToken trades and the market that prices
its underlying is closed. Earnings are released after the close by design; macro lands
overnight; geopolitics lands at weekends.

A holder's only options today are to exit before the close — surrendering the position —
or to absorb whatever the night brings.

| Instrument | Overnight 1σ | Worst night observed | *observed* |
|---|---|---|---|
| AMD | — | **1,262 bp** | |
| COIN | — | 1,185 bp | |
| MSFT | — | 1,128 bp | |
| TSLA | — | 1,099 bp | |
| PLTR | — | 1,076 bp | |

## 2. The universe — *observed*

| | |
|---|---|
| rTokens live on Bitget spot | **699** (all `status: online`) |
| …with a matched stock perp leg | **219** — the hedgeable universe |
| …without | 480 — Ballast cannot protect these, and says so |

rTokens are identified by `baseCoin` matching `^r[A-Z]`. Stock perps use the **bare
ticker**: `RTSLAUSDT` (spot) pairs with `TSLAUSDT` (perp).

## 3. The hedge — *observed*

Overnight window = that session's 16:00 ET close → the next session's 09:30 ET open,
DST-correct. Friday yields the Friday→Monday window. `RxxxUSDT` regressed on `xxxUSDT`.

| Name | n | β (all) | R² (all) | β (stress) | **R² (stress)** | R² (calm) | R² (weekend) |
|---|---|---|---|---|---|---|---|
| AMD | 101 | 1.006 | 0.997 | 1.008 | **0.999** | 0.959 | — |
| PLTR | 196 | 0.999 | 0.994 | 1.000 | **0.997** | 0.944 | 0.990 |
| QQQ | 209 | 1.017 | 0.991 | 1.022 | **0.998** | 0.922 | 0.981 |
| TSLA | 259 | 0.995 | 0.990 | 0.999 | **0.999** | 0.932 | 0.992 |
| COIN | 249 | 1.000 | 0.988 | 1.013 | **0.998** | 0.889 | 0.984 |
| NVDA | 259 | 0.991 | 0.980 | 0.979 | 0.978 | 0.917 | 0.991 |
| MSFT | 237 | 1.003 | 0.979 | 1.018 | 0.984 | 0.816 | 0.982 |
| AMZN | 253 | 1.007 | 0.979 | 1.019 | 0.986 | 0.885 | 0.985 |
| SPY | 138 | 1.011 | 0.979 | 1.013 | 0.990 | 0.805 | 0.955 |
| AAPL | 254 | 1.007 | 0.978 | 1.023 | 0.996 | 0.803 | 0.941 |
| GOOGL | 253 | 1.011 | 0.972 | 1.026 | 0.984 | 0.768 | 0.987 |
| META | 253 | 1.025 | 0.969 | 1.062 | 0.983 | 0.773 | 0.985 |

**Median R² = 0.980. Every β within 4% of 1.00.**

### The hedge strengthens under stress

R² on top-decile move nights is **0.978–0.999**; on calm nights it falls to **0.768–0.959**.
On a big-news night the common factor (real information about the company) dominates and
both instruments track it almost exactly. On a quiet night the residual is venue
microstructure noise, which is a large share of a small move.

**The hedge is imprecise only when little is at stake, and near-perfect when much is.**
That is the correct shape for protection, and it was not the expected result — the
prior worry was that β would decouple under stress.

### Tail — *observed*

| Name | Worst unhedged | Worst hedged | p95 unhedged | p95 hedged |
|---|---|---|---|---|
| AMD | 1,262 bp | **90 bp** | 688 bp | 35 bp |
| COIN | 1,185 bp | 138 bp | 612 bp | 65 bp |
| MSFT | 1,128 bp | 233 bp | 263 bp | 35 bp |
| TSLA | 1,099 bp | 177 bp | 418 bp | 40 bp |
| PLTR | 1,076 bp | 132 bp | 556 bp | 44 bp |

**Median p95 tail reduction: 88%.**

### Crypto is not a hedge — *observed*

Median R² of rToken overnight returns on BTC: **0.114**. Only COIN is meaningfully
crypto-correlated (0.67). Crypto legs are excluded from the design.

## 4. Cost — *observed / estimated*

| | |
|---|---|
| rToken spot fees | taker **0.10%** / maker **0.10%** — no maker discount *(observed)* |
| rToken exit round trip | **20 bp** *(estimated from fees)* |
| Perp fees | taker 0.06% / maker 0.02%, funding every 8h *(observed)* |
| Funding | positive — a short perp **receives** ~3.9% annualised *(observed)* |
| **Hedge round trip, taker, net of funding** | **11.3 bp** *(estimated — the default)* |
| Hedge round trip, maker | ~3.3 bp *(estimated — upside only; never assumed)* |

**Hedging is cheaper than exiting** — 11.3 bp versus 20 bp — and it keeps the position.

## 5. Gate 1 — can risky nights be selected in advance?

A delta hedge is symmetric: it removes upside with downside. Value therefore requires
that the hedged nights carry variance **without** compensation. Two conditions:

- **(a) Separation** — selected nights must actually be higher variance.
- **(b) Neutrality** — their mean return must not be reliably positive.

Selector tested: trailing 20-night realised overnight volatility, strictly prior data only.

| | Result |
|---|---|
| (a) Separation | variance ratio selected/rest = **1.41×** → **FAIL** |
| (b) Neutrality | pooled mean **+19.3 bp**, t = 3.08 → reads **compensated** |

### Reading this honestly

**The separation failure is the important half.** Trailing volatility barely distinguishes
risky nights from ordinary ones (1.41×), while selecting the same nights *ex post* gives a
13.2× ratio. High-variance nights plainly exist — trailing vol simply cannot find them.
That is expected on reflection: overnight equity variance is driven by **scheduled events**,
not by volatility persistence.

> **Consequence for the architecture.** The selector must be the event calendar, not a
> statistic. Knowing "NVDA reports tonight at 16:05" is calendar and news knowledge —
> unstructured text. This is why the LLM is load-bearing in Ballast rather than decorative:
> the quantitative selector demonstrably fails, and the textual one is the only one left.

**The neutrality result is weaker than its t-stat suggests.** No individual name reaches
significance (all |t| < 1.7); the pooled t = 3.08 comes from stacking 12 names that move
together on the same nights, which inflates significance by ignoring cross-sectional
correlation. The effective sample is far smaller than n = 1,261.

**We therefore adopt the conservative reading: Positioning B.** Ballast is presented as
**priced protection**, measured in tail and drawdown reduction per basis point spent. It
does **not** claim a Sharpe improvement. Insurance having negative expected value is not a
defect — that is what insurance is.

## 6. Known defects, and how they were handled

| Defect | Status |
|---|---|
| DST: US close hardcoded at 20:00 UTC; ~4 months of sample were EST | **Fixed** — `research/sessions.py`; verified across both 2025-11-02 and 2026-03-08 transitions |
| The 09:30 ET open does not fall on an hourly bar boundary, so lookups silently missed | **Fixed** — open snapped up to the next whole hour, `research/overnight.py` |
| First Gate 1 run selected nights by *realised* move — look-ahead | **Fixed** — ex-ante selector only; the invalid version is preserved behind `--lookahead` to document the bug |
| US exchange holidays are not modelled | **Open** — affects window length, not the hedge relationship. Tracked in `sessions.py`. |
| Maker fills assumed to be available in a 4am book | **Avoided** — all costs default to taker |

## 7. First policy replay — a negative result (2026-09-09)

`research/replay.py` runs the **live policy** over history: the same `decide()` the
nightly runner calls, with the return history truncated at each session and the event
calendar read for that date. 55 sessions × 12 equally-weighted positions.

| Metric | Unhedged | Ballast v0 | Change |
|---|---|---|---|
| Total return | 1.11% | **−6.96%** | −8.07 |
| Volatility (ann.) | 20.65% | **12.68%** | **−7.97 ✓** |
| Sharpe | 0.24 | **−2.61** | −2.85 |
| Sortino | 0.40 | −3.51 | −3.91 |
| Max drawdown | 10.15% | 9.34% | −0.82 ✓ |

Hedged on **45%** of decisions. Decision accuracy **47%**. Worst single position-night:
**1,536 bp unhedged → 1,536 bp with Ballast** — the selector missed the worst night entirely.

### What this shows, plainly

**The hedge works; the selection does not.** Volatility fell by 39% (20.65% → 12.68%),
which is the mechanism behaving exactly as §3 measured. Everything else is a
selection-and-cost failure:

1. **The hedge rate is far too high.** At 12 bp a round trip, hedging 45% of nights costs
   roughly 13% a year in fees. No tail benefit can pay for that. At this cost the
   affordable hedge rate is nearer **5–10%**, not 45%.
2. **The percentile gate drifts with regime.** `sigma_percentile` ranks tonight's forecast
   against the name's whole prior history, so in a rising-volatility regime the current
   window sits in the top quintile far more than 20% of the time. It needs a rolling
   reference window, not an expanding one.
3. **Accuracy of 47% is coin-flip.** Consistent with Gate 1: volatility cannot pick the
   nights, and the calendar was only partially populated when this ran.
4. **Portfolio level is the wrong level for this product.** Twelve equally-weighted names
   are already diversified, so the portfolio's worst night is a market-wide move that
   hedging *some* names barely dents. Ballast's value is at the **position** level for a
   concentrated holder — which is precisely the target user in `PLAN.md §2`, and the
   replay should report per-position tail metrics alongside portfolio ones.

### What is not concluded

That the product does not work. The mechanism measured in §3 is unchanged and the
variance reduction reproduced here. What failed is a deliberately naive v0 selector,
on day one of the build, which is what the replay exists to catch.

**No parameters were tuned to improve this table.** Tuning a policy until its backtest
looks good, on 55 sessions, is how the overfitting that S1 winners documented gets
manufactured. The fixes above are structural (rolling reference window, position-level
reporting, calendar-led selection) and each will be re-run against a held-out period.
