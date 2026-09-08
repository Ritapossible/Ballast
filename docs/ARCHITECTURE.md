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
                    │ EXECUTOR  Bitget SDK · paper mode        │
                    │ Agentic Account: fund isolation, quota,  │
                    │ no withdrawals — ceiling enforced by the │
                    │ exchange, not by us                      │
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

## Why the LLM is necessary, and where it is forbidden

Gate 1 measured that trailing realised volatility separates risky nights from ordinary ones
by only **1.41×**, while ex-post selection separates them by **13.2×**. High-variance nights
exist; statistics cannot find them, because overnight equity variance is driven by
*scheduled events*, not volatility persistence.

So the selector must read calendars and news. That is the LLM's job — **and only that job**.

**Reader output (the only thing the model may produce):**

```
NightRisk {
  ticker            str      # resolved against the live 219-pair index
  event_type        enum     # earnings | guidance | macro | legal | product | none
  scheduled_time    datetime | null
  expected_impact   enum     # low | medium | high
  confidence        float
  source_url        str
  verbatim_quote    str      # the sentence this was read from
  unknowns          [str]    # what it could not determine
}
```

The model never emits a size, a price, a direction, or a decision. Every downstream number
is deterministic typed code. A sentinel test asserts that corrupting post-decision data
changes no pre-decision signal.

## The evidence property

**Every decision has an exact counterfactual.** "What would have happened had we not hedged"
is not estimated — it is the observed rToken return over the same window. Every decision,
right or wrong, is precisely graded at the next primary open.

This is why the design is verifiable inside a 13-day competition: the alpha thesis and the
evidence mechanism are the same structural choice.

## Data layer

Public Bitget endpoints only for research; the Agentic Account for paper execution. Two
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
