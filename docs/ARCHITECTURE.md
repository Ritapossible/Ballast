# Architecture

## Principle

**The model translates. The engine decides. The enforcer permits.**

Three processes, three trust levels. The boundaries are process boundaries, not
conventions, so that a compromise of the reasoning layer cannot become a trade.

```
                    ┌──────────────────────────────────────────┐
  scheduled events  │ CALENDAR                                 │
  earnings, macro,  │ ex-ante risk selection                   │
  closure length    │ (Gate 1: statistical vol selection FAILS  │
                    │  — the calendar is the only selector)    │
                    └────────────────────┬─────────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────┐
  overnight news    │ READER            [no keys, no writes]   │
  (unstructured)    │ Qwen qwen3.8-max                         │
                    │ → NightRisk{...}   translation only      │
                    └────────────────────┬─────────────────────┘
                                         │ typed record
                    ┌────────────────────▼─────────────────────┐
  realised vol,     │ ENGINE            [read-only key]        │
  position book,    │ risk_forecast vs cost, under the mandate │
  live quotes       │ → HEDGE | NO_HEDGE | REDUCE  + reasoning │
                    └────────────────────┬─────────────────────┘
                                         │ intent
                    ┌────────────────────▼─────────────────────┐
  signed mandate    │ ENFORCER          [ONLY write-scoped key]│
                    │ arithmetic against a signed document     │
                    │ never sees the model's reasoning         │
                    └────────────────────┬─────────────────────┘
                                         │ permitted order
                    ┌────────────────────▼─────────────────────┐
                    │  EXECUTOR  Bitget Agent Hub CLI (bgc)    │
                    │  --paper-trading -> Bitget Demo, which   │
                    │  prices and fills the order. No live     │
                    │  order is sent. Falls back to a          │
                    │  simulated fill; the ledger says which.  │
                    └────────────────────┬─────────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────┐
                    │ LEDGER    append-only, signed            │
                    │ decision + inputs + reasoning + sources  │
                    └────────────────────┬─────────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────┐
                    │ SETTLEMENT  at the primary open          │
                    │ outcome vs the EXACT counterfactual      │
                    └──────────────────────────────────────────┘
```

## The enforcer — the load-bearing component

Ballast's central claim is a **negative capability**, and negative capabilities have to be
structural or they are marketing:

> Ballast cannot place a bet. Every order it is structurally capable of emitting is
> opposite in sign to, and bounded in size by, a spot position already held.

The enforcer runs as a separate process holding the **only write-scoped credential**. It
receives an order intent and a signed **Night Mandate**, and admits the order only if all
of the following hold:

1. a spot position exists in this symbol
2. the order is **opposite in sign** to that position
3. `|order notional| ≤ spot notional × mandate.max_ratio`
4. the symbol is inside the mandate's universe
5. the mandate has not expired (mandates expire at the primary open)
6. per-night order count and notional caps are not breached

It never sees the model's output or the engine's reasoning — it performs arithmetic
against a signed document. **The test that matters:** if the reasoning layer were fully
compromised, the worst reachable state is a hedge you did not want, bounded by a position
you already hold. There is no reachable directional trade.

A red-team suite drives hostile intents at the enforcer and asserts zero admissions.

## Why the LLM is necessary, and what it decides

Three measurements, in order, and each narrowed the model's job until it was exact:

| Selector | Separation | Compensated? | Verdict |
|---|---|---|---|
| Trailing realised volatility (Gate 1a) | 1.41× | **yes** (+19.3 bp, t=3.08) | unusable — pays to remove return |
| Earnings calendar (Gate 1b) | **3.2×** | **no** (−61 bp, t=−1.59) | usable, but covers only 2 of the 6 worst nights |
| **Unscheduled events** | — | — | **the reader's territory** |

Scheduled earnings are a minority of the tail. Macro shocks, guidance, legal rulings and
product events drive the rest, and none of them appear on a calendar. Reaching them means
reading unstructured text, which is the one thing here a model does better than arithmetic.

**So the reader owns the judgment.** The handbook defines this track as *"the LLM is the
primary trading decision-maker, not just an assistant"*, and the measurements independently
agree: the deterministic selectors are demonstrably insufficient.

Its authority is real but bounded. It decides **whether** to protect a position. It never
decides size, price or direction, and the enforcer still makes a directional trade
unreachable — so a model saying HEDGE can only ever cause a bounded hedge against a
position that already exists.

### Three gates stand between the model and an order

| Gate | Rejects |
|---|---|
| **Schema** | anything that does not parse into the contracted shape |
| **Identity** | a judgment about a different ticker than the one asked about (P13) |
| **Grounding** | a `verbatim_quote` that does not appear in the supplied headlines |

A judgment failing any gate is discarded and the deterministic calendar rule runs instead.
**Precision is a pipeline stage, not a hope pinned to the prompt** (P16). The grounding gate
is the important one: it is what stops an invented headline from becoming a real order.

Degradation is transparent. With no API key the reader abstains, the rule decides, and the
abstention and its reason are written to the ledger — so a night decided without the model
is visibly a night decided without the model.

**Reader output (the only thing the model may produce):**

```
ReaderVerdict {
  ticker          str       # must equal the ticker asked about
  judgment        enum      # HEDGE | NO_HEDGE | ABSTAIN
  reasoning       str
  risk NightRisk {
    event_type      enum    # earnings | guidance | macro | legal | product | none
    expected_impact enum    # low | medium | high
    confidence      float
    source_url      str
    verbatim_quote  str     # must appear in the supplied headlines
    unknowns        [str]   # what it could not determine
  }
}
```

There is no size, side, price or quantity field anywhere in that record, and a test asserts
their absence. Every downstream number is deterministic typed code, and a sentinel test
proves corrupting post-decision data changes no pre-decision signal.

### Sources

| Layer | Source | Why |
|---|---|---|
| Scheduled events | Nasdaq earnings calendar | authoritative, serves historical dates |
| Unscheduled events | Google News RSS, per ticker, window-filtered | free and keyless; Yahoo returns 429 from datacenter IPs |
| Judgment | Qwen `qwen3.8-max` via `hackathon.bitgetops.com/v1` | temperature 0, so judgments are reproducible |

News items are filtered to the window being decided: a headline published after the open
cannot inform a decision taken before it.

## The evidence property

**Every decision has an exact counterfactual.** "What would have happened had we not hedged"
is not estimated — it is the observed rToken return over the same window. Every decision,
right or wrong, is precisely graded at the next primary open.

This is why the design is verifiable inside a 13-day competition: the alpha thesis and the
evidence mechanism are the same structural choice.

### What the executor is, and is not

`BgcExecutor` shells out to Bitget's Agent Hub CLI with `--paper-trading`, which routes the
order to Bitget's Demo environment; Demo prices and fills it and hands back a record. When
`bgc` is absent, unconfigured, times out or refuses, Ballast falls back to `PaperExecutor`
and the night summary records `venue: simulated` with the reason. It never invents a fill.

Two things this deliberately does NOT claim. There is no Bitget SDK in the tree - the
integration is the CLI. And the spending ceiling is **not** enforced by the exchange: it is
the signed mandate's `max_notional_usdt` and `max_orders`, checked by the enforcer, which
is the only component holding a write-scoped credential. Saying the venue enforced it would
be borrowing someone else's guarantee for a property this project actually provides itself.

## Data layer

Public Bitget endpoints only for research; the Agent Hub CLI in `--paper-trading` mode for
execution, which routes to Bitget's Demo environment. Two
traps are encoded in `research/bitget.py` rather than left to memory: granularity casing
differs between spot (`1h`) and futures (`1H`) and fails **silently**, and `/market/candles`
caps at 1000 bars while `/market/history-candles` pages back over two years.

All session arithmetic goes through `research/sessions.py`. Nothing else may define an hour.

## Repository layout

```
CLAUDE.md              working memory — links, verified facts, hard rules
PLAN.md                build plan and schedule
docs/
  ARCHITECTURE.md      this file
  RESEARCH.md          measured findings, with defects disclosed
  HACKATHON.md         rules, deadlines, submission requirements
research/              the code behind every number quoted anywhere
```
