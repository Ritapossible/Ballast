# Bitget AI Base Camp Hackathon S2 — rules reference

Authoritative source: **https://bitget-ai.gitbook.io/bitgetai_hackathons2**
Captured 2026-09-08. Where this file and the handbook disagree, the handbook wins.

## Timeline (UTC+8)

| Date | Milestone |
|---|---|
| Sep 3 | Opens; submissions and Qwen credit applications open |
| Sep 3–21 | Competition period |
| **Sep 21** | **Submission deadline — hard stop** |
| Sep 22–28 | Public voting (comment project ID on the official X post) |
| Sep 22–Oct 7 | Judge review, in parallel with voting |
| Oct 8 | Winners announced |
| Oct 9+ | Demo Day, Spotlight, payouts |

## Tracks

| Track | Scoring | Required materials |
|---|---|---|
| 🟦 Alpha Factory | **Pure quantitative** | Alpha source description · strategy code · backtest ≥60 days total, ≥30 days out-of-sample (market-making may substitute continuous high/low volatility records) |
| 🟩 **Agentic Trading** ← *ours* | **50% quantitative + 50% judge** | Runnable demo · event→decision→execution flow · **paper trading log run during the competition** (2+ weeks recommended) |
| 🟧 AI Trading Desk | Pure judge | Accessible demo · a complete research task, question → actionable insight |

### Agentic Trading judging focus (verbatim)

> "Paper trading Sharpe, max drawdown, win rate; decision explainability; Agent
> architecture quality; risk control layer effectiveness."

**Novelty is not a listed criterion in S2.** Architecture and risk control are.

### Sub-themes (5 named + open, per track)

**Agentic Trading:** **Event-Driven Agent** ← *ours* · Market Sentiment Agent ·
Earnings-Driven Trading Agent · Cross-Asset Execution Agent · Factor Discovery Agent ·
Open *(selection is optional)*

## Prizes

| Award | Slots | Each |
|---|---|---|
| Grand Prize | 1 | 3,000 USDT |
| Theme Prize (named sub-themes) | 15 | 500 USDT |
| Open Theme Prize | 6 | 500 USDT |
| University Special | 10 | 500 USDT |
| Best Spread (X reach) | 3 | 300 USDT |
| Fan Favorite (public vote) | 3 | 300 USDT |

Judge-side awards: only the **highest tier** counts. University Special is mutually
exclusive with main-track prizes. Fan Favorite **stacks with everything**.

**Realistic target: a Theme Prize.** One winner per sub-theme is a far better-odds
objective than the Grand Prize, and pursuing it costs nothing in Grand Prize contention.

## Submission

Portal: **https://forms.gle/GyWZCMCPocgJdJon6**

### Invalid — rejected regardless of quality
- Missing compliant X post link
- Missing project description
- Missing accessible submission materials

Incomplete productization or validation answers do **not** invalidate an entry but
"noticeably lower" scoring.

### Six-part project description — judges weight parts 1–3 most heavily
1. **Thesis** — hypothesis, signal sources, decision logic, risk controls
2. **Target user & product value** — segment, risk appetite, capital size, frequency,
   market, use case. **"All traders" is explicitly not accepted.**
3. **Validation data & key metrics** — test period, returns, Sharpe/Sortino, max drawdown,
   win rate, turnover, fees, slippage. **Label every figure observed / estimated / targeted.**
4. **Progress** — what is built, what is not, problems, fixes, next steps
5. **Deliverables** — contents of the materials link
6. Take on AI trading *(optional)*

### Other required fields
- **Role of the LLM** — which models, and what they actually do
- Submission materials link (one field: demo, code, video, logs)
- **X post** including `#BitgetHackathon` and `@Bitget_AI`, plus the required retweet
- Track → sub-theme
- Optional: university name · Demo Day · K3 subsidy

### Multi-entry and S1 reuse
- At most **2 themes** per team, separate submissions, judged independently
- Resubmitting S1 work with minor changes is **invalid**; substantive new additions must
  be described

## Resources

| What | Value |
|---|---|
| Qwen base URL | `https://hackathon.bitgetops.com/v1` |
| Qwen model | `qwen3.8-max` |
| Qwen credits | first 300 KYC'd teams, 30 USD equivalent |
| K3 subsidy | opt in on the form, 30 USD equivalent post-event |
| Agent Hub | https://github.com/Bitget-AI/agent_hub |
| Playbook | https://www.bitget.com/zh-CN/activity/ai-get-agent/playbook?tab=explore |
| Telegram | https://t.me/+o1tYqQ_lXxllYjgy |

## Open questions to confirm in Telegram
- Full URL for the Qwen credits form (the announcement link is truncated)
- The exact retweet target the X post requirement refers to
- Whether paper-mode perp shorting is available on the Agentic Account

## Compliance check against the build (reviewed 2026-09-13)

| Requirement | Status |
|---|---|
| Runnable demo | ✅ CLI plus a self-contained public page (`docs/index.html`, rebuilt nightly) — no login, no backend, no CDN |
| Event → decision → execution flow | ✅ `docs/ARCHITECTURE.md`; every step is in the signed ledger |
| Paper trading log, run during the competition | ✅ **automated**, ⚠️ **short** — the handbook recommends 2+ weeks; the loop went live 2026-09-09, so the deadline falls at roughly nine decided sessions. Nothing can be backfilled; the only lever left is that every remaining session lands. — scheduled workflow runs after the close and after the open, verifies the chain, and commits the ledger. GitHub timestamps each commit independently, so the record is provably not backfilled. |
| X post with `#BitgetHackathon` + `@Bitget_AI` | ❌ **not posted** — an entry without this is invalid regardless of quality |
| Six-part description | ✅ written — [`docs/SUBMISSION.md`](SUBMISSION.md); only the X post link is a placeholder |
| Role of the LLM | ✅ event reader implemented — Qwen owns the hedge judgment behind schema, identity and grounding gates |
| Agentic Account + `--paper-trading` | ✅ via the Agent Hub (`ballast/bgc.py`); `PaperExecutor` remains the default and the fallback |
| Qwen `qwen3.8-max` via `hackathon.bitgetops.com/v1` | ✅ wired (`ballast/llm.py`) — **needs `QWEN_API_KEY`**; endpoint verified live (401 on a dummy key) |
| Scored metrics on the competition log (Sharpe, max drawdown, win rate) | ✅ `ballast/metrics.py`, rendered on the Settled page — computed on the live ledger for the book and for the same book with every hedge removed |
| Agent Hub (`bgc`) | ✅ wired — `BALLAST_VENUE=bgc` routes the admitted hedge through `bgc --paper-trading`; needs a Demo API key. Off by default; every fill records which venue filled it. |

### Sub-theme: Event-Driven Agent (settled 2026-09-13)

The handbook states the question each sub-theme answers, and the two candidates differ on
what the agent *reads*:

> **Event-Driven Agent** — "How do news / announcements / macro events drive autonomous
> Agent trading?" *Policy speech → LLM interpretation → rebalance; earnings beat → add
> position; **rate decision → hedge rotation**."*
>
> **Earnings-Driven Trading Agent** — "How does the Agent autonomously **interpret
> earnings / conference calls** and execute?" *EPS beat → add; guidance cut → reduce;
> post-earnings anomaly tracking.*

**Ballast is Event-Driven.** It never reads earnings *content*. `ballast/earnings.py`
pulls the Nasdaq **calendar** — dates only, and the module says the time field is "used
when present to describe the event, never to gate it." A scheduled report means *tonight
is dangerous*, not *the print will be good*. Every Earnings-Driven example is directional
(add, reduce); Ballast is deliberately non-directional and the enforcer makes a
directional order unrepresentable. Event-Driven's own example — "rate decision → hedge
rotation" — is the mechanism.

The reader also weighs macro: the live SPY row reasons about FOMC and CPI, not earnings.

**An earlier revision of this file argued the opposite** from the abbreviated sub-theme
list, on the evidence that all four hedges to date carry `event.type == "earnings"`. That
count is real but does not support the claim: earnings is the only *calendar feed* wired,
not the only event class considered, and using a calendar as a timing signal is not
interpreting earnings. Recorded because it is the kind of mistake that gets made twice.

Sub-theme selection is **optional** per the handbook, not mandatory.

### Agent Hub

`https://github.com/Bitget-AI/agent_hub` ships an MCP server (`bitget-agent-mcp`), a CLI
(`bgc`), 89 UTA v3 trading operations behind 14 intent verbs, a `--paper-trading` mode
against Bitget's Demo environment, a `--read-only` mode, and market-analysis skills
(`bitget-signal`) that run **without credentials**. Trading operations need a Demo API key.

**Execution is now wired** (`ballast/bgc.py`). `BALLAST_VENUE=bgc` plus `BITGET_API_KEY`
routes each admitted hedge through `bgc --paper-trading`; unset, Ballast simulates as
before. `--paper-trading` is appended by the module with no parameter to disable it.

The swap cost one class because the seam was already correct: `execute()` takes an
`Admitted` and nothing else, so the venue changes *underneath* the enforcer. A model that
reaches the venue still cannot express a directional trade — it has no way to construct
the only argument the method accepts.

The failure mode that mattered was not a crash but a **silent substitution**: if `bgc` is
missing and Ballast quietly simulates while the ledger still reads `bgc-paper`, the chain
carries a false claim about the venue and nothing downstream can detect it. So every
failure is typed (`BgcUnavailable` with a reason), every fill row records `venue`, and a
mid-session fallback also records `venue_fallback` with the reason. A test perturbs the
labelling and fails.

**One honest caveat.** The order verb (`bgc.ORDER_VERB`) follows Agent Hub's documented
shape, but the published README does not spell out the argv for placing an order and no
`bgc` binary has been run against this code. If the verb is wrong the order fails, the
failure is typed, the fill is simulated and the row says so — nothing is mis-recorded, but
nothing routes either. `python -m ballast.preflight` now runs `bgc discover` and reports
whether the verb is on the CLI's actual tool surface, so that is learned from a check that
writes nothing rather than from a night that quietly fell back.

The nightly workflow installs the CLI and sets `BALLAST_VENUE=bgc` **only when a
`BITGET_API_KEY` secret exists**. Adding that secret is the entire switch; no workflow edit
is needed, and without it nothing changes.

Still unused, and a fair question a judge could ask: the **MCP server** and the keyless
`bitget-signal` research skills. Ballast reads its own news and earnings feeds.

### Prize opt-ins on the form

- **University Special** (10 × 500 USDT) — mutually exclusive with main-track prizes, so it
  is a trade, not a bonus: far better odds against a much smaller field. Only available if
  a team member is a student.
- **K3 subsidy** (30 USD, up to 60 combined) — a checkbox, post-event, costs nothing.
- **Fan Favorite** stacks with everything; it follows from the X post, not the form.

### The track definition, and how it was resolved

The handbook defines the Agentic Trading track as:

> "The LLM is the **primary trading decision-maker**, not just an assistant. The Agent must
> sense the environment, make independent judgments, and autonomously place orders with
> risk controls."

An earlier design principle here was *"the model translates; it never decides"*, chosen to
maximise the risk-control half of the score. Read literally that is the opposite of what the
track asks, and the architecture was changed rather than the wording.

**The reader now owns the hedge judgment.** `policy.decide` takes `model_judgment` and it
*leads* when present (`ballast/policy.py:172-182`): a HEDGE from the reader hedges, a
NO_HEDGE declines, and the calendar rule only decides when the reader abstained or was
gated. On the live record so far the model decided **20 of 36** calls, and each decision
names its author in the ledger and on the Tonight page.

Its authority stops at the judgment. Size, side, price and admission stay in deterministic
code, and the executor accepts only an `Admitted` the enforcer minted — so the model is the
decision-maker the track describes, and still cannot place a directional order. That is the
"with risk controls" half of the same sentence, not a contradiction of the first half.

**RESOLVED 2026-09-09.** The reader now returns the HEDGE / NO_HEDGE judgment and that call
leads in `policy.decide()`. Sizing, limits and the enforcer stay deterministic, so bounded
authority is intact.

Original resolution note:

**Give the LLM the judgment, keep the arithmetic deterministic.**
The model should return the HEDGE / NO_HEDGE judgment for a position, with its reasoning
and sources — that is a real, autonomous trading decision and satisfies the track. Sizing,
pricing, mandate limits and the enforcer stay deterministic, so bounded authority is
untouched: the model can decide *whether* to protect a position, and still has no path to a
directional trade.

This is a genuine design change driven by the handbook, not a re-labelling. Track it before
the reader is implemented.
