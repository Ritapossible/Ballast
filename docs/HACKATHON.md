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

**Agentic Trading:** Event-Driven Agent ← *ours* · Market Sentiment Agent ·
Earnings-Driven Trading Agent · Cross-Asset Execution Agent · Factor Discovery Agent · Open

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
