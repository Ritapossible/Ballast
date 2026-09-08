# Ballast

**Hold tokenized US stocks through the night without holding the night's risk.**

The US primary market is open 32.5 of every 168 hours. For the other ~81% of the week an
rToken keeps trading while the market that prices its underlying is shut — through
earnings, through Fed decisions, through weekends. A holder's only options today are to
exit before the close, surrendering the position, or to absorb whatever arrives.

Ballast is a third option: **keep the position, and switch off the night's risk for a
stated price.**

---

## What is measured

All figures **observed** on 2026-09-08 from public Bitget endpoints, reproducible via
`research/`. Full detail and disclosed defects in [`docs/RESEARCH.md`](docs/RESEARCH.md).

| | |
|---|---|
| Overnight variance removed by a matched perp hedge | **median R² 0.980**, β within 4% of 1.00 |
| R² on the largest-move nights | **0.978 – 0.999** — the hedge strengthens under stress |
| p95 tail reduction | **median 88%** |
| Worst nights | MSFT 1,128 bp → 233 bp · AMD 1,262 bp → 90 bp |
| Cost of protection | **11.3 bp** taker, net of funding received |
| Cost of exiting instead | **20 bp**, and you lose the position |
| Hedgeable universe | **219** of 699 live rTokens |

## What it does not claim

Ballast is **priced protection, not alpha.** It does not claim a Sharpe improvement.
[Gate 1](docs/RESEARCH.md#5-gate-1--can-risky-nights-be-selected-in-advance) measured that
the nights worth hedging carry compensated return, so hedging them forgoes it — as
insurance always does. The claim is tail and drawdown reduction per basis point spent, and
it is graded against reality every morning.

It also does not trade direction. It structurally **cannot**:

> Every order Ballast is capable of emitting is opposite in sign to, and bounded in size
> by, a spot position already held. There is no code path to a directional trade.

Enforced by a separate process holding the only write-scoped credential — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository

| Path | Contents |
|---|---|
| [`PLAN.md`](PLAN.md) | Build plan, schedule, risk register |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design and trust boundaries |
| [`docs/RESEARCH.md`](docs/RESEARCH.md) | Measured findings, with defects disclosed |
| [`docs/HACKATHON.md`](docs/HACKATHON.md) | Rules, deadlines, submission requirements |
| [`research/`](research/) | The code behind every number quoted anywhere |
| [`CLAUDE.md`](CLAUDE.md) | Working memory — links, verified facts, hard rules |

```bash
python3 research/universe.py        # 219 hedgeable pairs of 699 rTokens
python3 research/hedge_study.py     # hedge quality, stress conditioning, tail
python3 research/gate1_selection.py # can risky nights be chosen in advance
```

No API key needed. No dependencies beyond the Python standard library.

---

Built for the **Bitget AI Base Camp Hackathon S2** — Agentic Trading, Event-Driven Agent.
Paper trading only; no live fill is claimed.
