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

**Median R² = 0.982. Every β within 4% of 1.00.**

*(0.980 before exchange holidays were modelled; correcting the window labelling moved it slightly up and left every conclusion unchanged.)*

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
| US exchange holidays are not modelled | **Fixed** — `ballast/holidays.py` computes NYSE closures and early closes from rules. A Good Friday window measured 17.5 hours and is now 89.5. |
| Maker fills assumed to be available in a 4am book | **Avoided** — all costs default to taker |
| Hedgeable universe paired on the bare ticker alone, so 34 rTokens were matched to a *crypto* perp sharing their ticker (`rF`/Ford against `FUSDT`, `rSUI` against the Sui perp, and 32 more). Measured tracking on those pairs is R² ≈ 0.00 against ≈ 0.99 on a real one. | **Fixed** — the perp leg must also be `symbolType: stock`, which only the v3 instruments endpoint reports; v2 returns "perpetual" for every contract. The universe is 206 of 1,173, not 240. No position in the book was ever mispaired (all 12 legs are stock perps) but `Book.from_tickers` would have accepted one, so it is a gate, not a display filter. Pinned by `tests/test_universe.py`. Found by building the public coverage index, which measures every pair instead of assuming it. |

## 6b. Gate 1b — the event calendar as the selector ✅ PASSES BOTH CONDITIONS

Gate 1a killed the *statistical* selector. This tests the calendar, over 2025-10-01 →
2026-09-08, 15 names, earnings dates from Nasdaq's public endpoint. A release after a
session's close or before the next open both land inside that session's window.

| Name | earnings nights | mean | t | sd | other nights | sd | **variance ratio** |
|---|---|---|---|---|---|---|---|
| MSFT | 8 | +12 bp | 0.07 | 474 bp | 222 | 127 bp | **14.0×** |
| NKE | 6 | −118 bp | — | 544 bp | 218 | 146 bp | **13.8×** |
| AAPL | 8 | −81 bp | −0.69 | 312 bp | 222 | 107 bp | **8.5×** |
| COST | 6 | −89 bp | — | 203 bp | 218 | 91 bp | 4.9× |
| TSLA | 8 | −300 bp | −1.87 | 423 bp | 222 | 192 bp | 4.8× |
| AMZN | 8 | +83 bp | 0.75 | 294 bp | 221 | 138 bp | 4.6× |
| NVDA | 8 | +76 bp | 0.60 | 332 bp | 222 | 174 bp | 3.6× |

| Condition | Result | Verdict |
|---|---|---|
| **(a) Separation** | variance ratio **3.2×** pooled, **3.0×** median per name | **PASS** |
| **(b) Neutrality** | pooled mean **−61 bp**, t = **−1.59**, 95% CI **[−136, +14] bp**; **0 of 15** names significant at \|t\|≥2 | **UNCOMPENSATED** |

Earnings-night 1σ is **392 bp** against an 11.3 bp hedge cost — a **35:1** ratio. At roughly
four reports a year, hedging every earnings night costs about **45 bp per position per year**.

### Why this matters

Gate 1a and 1b together give a clean rule:

| Selector | Separation | Compensated? | Use it? |
|---|---|---|---|
| Trailing realised volatility | 1.41× | **yes** (+19.3 bp, t=3.08) | **No** — pays to remove return |
| **Earnings calendar** | **3.2×** | **no** (−61 bp, t=−1.59) | **Yes** — uncompensated variance |

**The volatility gate is therefore OFF by default in `ballast/policy.py`.** Re-enabling it
requires new evidence, not a hunch. The point estimate on earnings nights is negative, but
with 4–8 observations per name and a 392 bp standard deviation it must not be read as a
directional claim — only as "not reliably compensated".

## 7. Policy replay — calendar-only selection (2026-09-09)

`research/replay.py` runs the **live policy** over history, 55 sessions × 12 positions.

| Metric | Unhedged | Ballast | |
|---|---|---|---|
| Volatility (ann.) | 20.65% | **18.35%** | ✓ |
| Max drawdown | 10.15% | **9.24%** | ✓ |
| Total return | 1.11% | −0.75% | −1.86 |
| Sharpe | 0.24 | −0.19 | −0.43 |

**Position-level tail — the level the product actually operates at:**

| Cohort | n | hedged | mean \|move\| | mean realised |
|---|---|---|---|---|
| worst 1% | 6 | **2** | 1,237 bp | 870 bp |
| worst 5% | 33 | **6** | 827 bp | 674 bp |
| worst 10% | 66 | **8** | 660 bp | 569 bp |
| all | 660 | 16 | 186 bp | 175 bp |

- Hedge rate **2.4%** (down from 45%), total drag **0.3 bp per position-night**
- **15 of 16 hedges reduced the move (94%)**
- Worst position-night **1,536 bp — unhedged**

### The honest reading

**The mechanism fires accurately and costs almost nothing. Its coverage is the problem.**
Only 2 of the 6 worst nights and 6 of the worst 33 were hedged: scheduled earnings are a
minority of the tail. Macro shocks, guidance, legal and product events drive the rest, and
v0 cannot see them because it reads a calendar and nothing else.

**That gap is exactly what the LLM event reader is for**, and it is now measured rather than
assumed: the model's job is to extend the selector from *scheduled* events to *all* events.

On returns: 16 hedges over 55 sessions is far too small a sample to attribute the −1.86 pp.
A delta hedge is symmetric, so hedged nights that happened to rise cost the upside — which
Gate 1b says we cannot predict. **No return claim is made from this sample.**

### Metric definitions

The first replay reported a "decision accuracy" of 47%, then 10%, using
`|move| > cost` on hedged nights and `|move| <= cost` on unhedged ones. **That metric was
wrong** — typical overnight moves are 100–400 bp against a 12 bp cost, so nearly every
unhedged night scored as an error regardless of the decision's quality. It has been replaced:

- **Win rate** = share of hedges that reduced \|move\|. A hedge is symmetric, so a
  P&L-direction win rate is meaningless.
- **Tail coverage** = share of the worst 1% / 5% / 10% of position-nights that were hedged.
  This is the metric the product should be judged on, and the one v0 fails.
