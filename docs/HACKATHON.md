# Bitget AI Base Camp Hackathon S2 — rules reference

Authoritative source: **https://bitget-ai.gitbook.io/bitgetai_hackathons2**
Captured 2026-09-08. Where this file and the handbook disagree, the handbook wins.

## Timeline (UTC+8)

| Date | Milestone |
|---|---|
| Sep 3 | Opens; submissions and Qwen credit applications open |
| Sep 3–21 | Competition period |
| **Sep 27** | **Submission deadline — hard stop** (moved from Sep 21 by the organisers) |
| Sep 28+ | Public voting (comment project ID on the official X post) |
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
| Paper trading log, run during the competition | ✅ **automated**, ⚠️ **short** — the handbook recommends 2+ weeks; the loop went live 2026-09-09 and the deadline moved to Sep 27, so the record lands at roughly a dozen decided sessions. Nothing can be backfilled; the only lever left is that every remaining session lands. — scheduled workflow runs after the close and after the open, verifies the chain, and commits the ledger. GitHub timestamps each commit independently, so the record is provably not backfilled. |
| X post with `#BitgetHackathon` + `@Bitget_AI` | ❌ **not posted** — an entry without this is invalid regardless of quality |
| Six-part description | ✅ written — [`docs/SUBMISSION.md`](SUBMISSION.md); only the X post link is a placeholder |
| Role of the LLM | ✅ event reader implemented — Qwen owns the hedge judgment behind schema, identity and grounding gates |
| Agent Hub CLI + `--paper-trading` | ⚠️ **live and exercised nightly; the exchange refuses the order** — credentials are configured, `bgc` installs and answers, and each of the five hedges since 2026-09-14 was routed to the Agent Hub and came back `HTTP 400: exchange environment is incorrect`. **The night summary used to label those sessions `venue: bgc-paper · Bitget Agent Hub, paper-trading` regardless of what the orders did** — including on nights that sent no order at all. The per-fill rows were always honest (`venue: simulated`, with the exchange's error verbatim); the summary above them was not. The label is now written from the outcome: `none` when nothing was sent, `simulated` when every order fell back, `bgc-paper` only when an order actually routed. The seven committed rows carrying the old label stay as written — the ledger is append-only and hash-chained, so a signed record is corrected beside it, never edited. Ballast then simulated the fill and wrote the exchange's own error onto the row as `venue_fallback`, which is the designed behaviour and is now proven in production rather than only in tests. **No fill on the ledger carries an exchange `orderId`.** **The cause is measured, not guessed: Bitget's demo environment does not list a single tokenized stock perpetual.** Across all three demo product types it carries nine contracts — `SBTCSUSDT`, `SETHSUSDT`, `SXRPSUSDT`, `SBTCSUSD`, `SETHSUSD`, `SBTCSUSDU26`, `SETHSUSDU26`, `SBTCSPERP`, `SETHSPERP` — every one of them BTC, ETH or XRP. The live `USDT-FUTURES` list carries 797 including all twelve names in this book. So no position Ballast holds can be filled on demo under any credentials, which is what the exchange means by *environment is incorrect*. Checked 2026-09-19, in one command: `curl -s "https://api.bitget.com/api/v2/mix/market/contracts?productType=SUSDT-FUTURES"`. |
| Agentic Account (OAuth sub-account) | ❌ **not used** — the handbook's Agentic account is a *live* sub-account authorised by OAuth with no manual key. `ballast/bgc.py` appends `--paper-trading` unconditionally and has no parameter to turn it off, so every order routes to the Demo environment and can never reach an Agentic account. That is deliberate: the alternative is a real order with real money, which this track does not ask for. Credentials here are manual API keys, not OAuth. |
| `bitget-signal` research Skills | ⚠️ **integrated; answering in halves** — `mcp.signal()` reaches all 19 tools at `datahub.noxiaohao.com/mcp` over the same transport, no account or API key. **This row previously said every one of them returned an empty envelope, and that this had been confirmed to be the service rather than this client. That was wrong.** Every tool requires an `action`, and a call without one is *answered* rather than rejected — `technical_analysis` replies `{"error": "Unknown action: "}`, indistinguishable at a glance from the `{"error": ""}` a dead upstream returns — so a sweep that called each tool bare read a client error back from all nineteen and published it as a measurement of the service. Asked properly (`python3 -m ballast.signal_probe` → `state/signal_probe.json`): **5 of 5 catalogue actions** answer from real tables, **1 of 9 fetch-backed actions** carries anything, the news is still **0 articles across 44 feeds**, and the one that answers is `technical_analysis`, which holds its own bars — **9 of the 12 names in the book** price, ADBE/COST/NKE do not, and the invented ticker `ZZZZQQ` is refused rather than answered. `signal_headlines()` flattens the per-feed envelopes so a dead upstream reads as **no articles** rather than 44 headlines that are really source names. Re-measured by the nightly. Checked 2026-09-23. |
| `bitget-mcp-server` (US stock data) | ✅ **integrated as a second opinion on the calendar** — `ballast/mcp.py` speaks MCP 2024-11-05 over HTTP to `agent.bitget.com/mcp` with no dependencies, and `ballast/crosscheck.py` asks its `equity_calendar_earnings` entry the same question Nasdaq was asked for every decision on the chain, publishing where the two agree. **The upstream recovered**: after days of 503 it now answers, so all **120 decisions are checked with 0 recorded `unknown`** — **116 agree, 4 disagree**. The four are ADBE and ORCL on 2026-09-09 and 09-10, *the same two hedges this project already discloses as defect 3f* (the selector matched a session without checking the release time and covered a night early). A second source, asked independently, landed on exactly the rows already marked wrong. Re-verified live 2026-09-23: `equity_price_quote` and `equity_calendar_earnings` both return 200. It deliberately does **not** decide: re-pointing the selector days before a submission would invalidate the record the change is meant to support. An unreachable service is still recorded as `unknown` with the upstream's own status code, never as agreement — a second source that fails open is worse than none. |
| Playbook / GetAgent Studio | ✅ **published v0.0.2 as `Ballast Overnight Protection`** — confirmed present in the platform's published listing, not merely accepted by `/publish`. ✅ **Paper Trading running on 0.0.2** (switched in Studio 2026-09-20 16:39 UTC, positions and cumulative returns preserved; first evaluation 17:00). **`/my-playbooks` does not see it and returned 0 entries throughout** — that endpoint lists enabled *deployments* (subscription / follow-trade instances, carrying `channel` and `chat_id`), which is a different mechanism from Studio Paper Trading. An earlier revision of this line claimed the endpoint was the check for Paper Trading; it is not, and the correction is recorded rather than quietly edited. Enabling or switching an instance stays the account owner's action in GetAgent Studio and no API call here may do it (2026-09-20 14:55 UTC, strategy `b18f70be-4e9e-4402-827a-2a02ad044f2f`, version `28914b3c-3b75-403a-91a9-1910f70639bc`) — `playbook/ballast-overnight-protection/` over 10 Bitget RWA stock perpetuals. Sandbox run `pbrun-60a1da0970b5`: **−1.48% return, 3.76% max drawdown, 0.40 win rate, 20 trades, −0.76 Sharpe** over 2026-06-21 → 2026-09-18, on a real 2,121-point equity curve the platform hashed (`096c4d1e…f433f`) — the anti-fabrication check publish enforces. **Run twice, two days apart (`pbrun-e920a23cc1c7` on 09-20 00:33Z and `pbrun-60a1da0970b5` on 09-20 14:53Z), the platform returned the same curve hash and the same five figures to four significant digits** — the replay is reproducible rather than a snapshot of whatever the feed held that afternoon. Those percentages are on the **strategy basis** the run record uses, `net_pnl / margin_budget`: −29.62 USDT against a 2,000 USDT budget. **The public GetAgent card quotes the same run on the account basis** — −0.03% return, 0.08% max drawdown, against the 100,000 USDT the sandbox opened with — so the card and this checklist differ by construction, not by error. One run, one −29.62 USDT, two denominators; win rate, trade count and Sharpe are identical on both because ratios do not depend on the denominator. Verified against the platform's own published listing (`task: mine`), which also shows `official_evidence_kind: backtest` and all ten symbols. The negative return is the product: it protects 10 scheduled-event nights and holds nothing on the other ~55, so over a rising window the premium is a pure cost. It is published as the protection leg and says so — not an alpha strategy, no directional claim. `.github/workflows/playbook.yml` validates, uploads, dispatches and polls to a terminal status with `ACCESS-KEY` from the `PLAYBOOK_API_KEY` secret, so the key reaches no transcript and no process table. |
| Qwen `qwen3.8-max` via `hackathon.bitgetops.com/v1` | ✅ wired (`ballast/llm.py`) — **needs `QWEN_API_KEY`**; endpoint verified live (401 on a dummy key) |
| Scored metrics on the competition log (Sharpe, max drawdown, win rate) | ✅ `ballast/metrics.py`, rendered on the Settled page — computed on the live ledger for the book and for the same book with every hedge removed |
| Agent Hub (`bgc`) | ⚠️ **installed, reachable, routing — rejected at the exchange** — the workflow sets `BALLAST_VENUE=bgc` automatically because `BITGET_API_KEY` is configured, installs `@bitget-ai/bitget-agent-cli` globally, and fails the job outright if `bgc` is not on PATH, so a silent fallback to simulation is not possible. The route runs; the order is refused. Until one comes back with an exchange `orderId`, this stays a warning: claiming it as done would be the one unverifiable claim in a project whose whole argument is that its claims are checkable. The failure is on the ledger, per row, in the exchange's words, and the reason it cannot be fixed from this side is on the Tonight page with the command that checks it. The only venue listing these symbols is the live one, and `bgc.py` appends `--paper-trading` with no parameter to turn it off — so the honest options were a simulated fill labelled as one, or a real order with real money. It simulates. |

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

**Verified 2026-09-14.** The first cut of this module guessed the argv from the docs
and was wrong in four places: the verb is `order --action place`, not
`trade place-order`; the flag is `--orderType`, not `--order-type`; `--category` is
required; and size is `--qty` in the **base coin**, not `--notional` in USDT, so the
notional is divided by the mark. There is no `--json` flag and payloads nest under
`data`. All of it now comes from `bgc discover --tool order --action place`, and
`preflight` proves it by sending a `--dry-run` placement and checking what the CLI
says it *would* send.

`placeOrder` acknowledges an order; it does not report a fill. So past the point where
the command returns, nothing may raise: a fallback there would simulate a fill for an
order the venue already holds and the ledger would show one hedge where two were
placed. A missing fill price is recorded as `price_source: observed mark`, with the
venue order id beside it, rather than invented or retried.

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
