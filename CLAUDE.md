# Ballast — working memory

Read this before touching anything. It exists so facts are looked up, not recalled.
**Every number here was measured from a live endpoint on the date shown. Nothing is from memory.**

---

## 1. What we are building

**Ballast lets you hold tokenized US stocks through the night without holding the night's
risk — one decision per position, priced before you sleep, settled at the opening bell.**

Entry: **Bitget AI Base Camp Hackathon S2 · Agentic Trading track · Event-Driven Agent sub-theme.**
Deadline **2026-09-21 (UTC+8)**. Single entry unless the Day-9 checkpoint clears a second.

### The negative capability — enforce it, never merely claim it
> Ballast cannot place a bet. Every order it is structurally capable of emitting is opposite in
> sign to, and bounded in size by, a spot position already held. There is no code path to a
> directional trade.

---

## 2. Hackathon links

| What | URL |
|---|---|
| **S2 handbook (authoritative)** | https://bitget-ai.gitbook.io/bitgetai_hackathons2 |
| S1 handbook (rules baseline) | https://bitget-ai.gitbook.io/hackathon/base-camp-hackathon-s1-en |
| Announcement post | https://x.com/Bitget_AI/status/2097230641452785752 |
| Activity hub | https://www.bitget.com/activity-hub/hackathon |
| **Submission form** | https://forms.gle/GyWZCMCPocgJdJon6 |
| Qwen credits form | `https://forms.gle/2QeJpvGB5Vpipq…` ⚠️ **truncated — get the full URL** |
| Telegram | https://t.me/+o1tYqQ_lXxllYjgy |

## 3. Sponsor technology

| What | URL / value |
|---|---|
| Agent Hub | https://github.com/Bitget-AI/agent_hub *(handbook also cites `BitgetLimited/agent_hub`)* |
| agent-sdk (TS, 89 UTA v3 ops, 14 intent verbs) | https://github.com/Bitget-AI/agent-sdk |
| agent-cli (`bgc`) | https://github.com/Bitget-AI/agent-cli |
| agent-mcp | https://github.com/Bitget-AI/agent-mcp |
| agent-skill | https://github.com/Bitget-AI/agent-skill |
| bitget-signal (5 skills, no key) | https://github.com/Bitget-AI/bitget-signal |
| Playbook | https://www.bitget.com/zh-CN/activity/ai-get-agent/playbook?tab=explore |
| **Qwen base URL** | `https://hackathon.bitgetops.com/v1` |
| **Qwen model** | `qwen3.8-max` |

SDK safety features to use, not reinvent: `--read-only`, `--paper-trading` (Demo), `riskLevel`
gating (`read` < `write` < `high`), high-risk self-gate via `{confirmationRequired:true}`, and an
in-memory `MockServer` under `@bitget-ai/bitget-agent-sdk/testing` for network-free tests.

**Agentic Account** — OAuth sub-account with fund isolation, quota control, **no withdrawals**.
This is our capital ceiling, enforced by the exchange rather than by our code. Use it.

## 4. Prior art — read before designing anything

Both are **S1 winners in this exact problem space**. The handbook forbids porting S1 work and
requires "substantive new additions". Know these cold so we never re-tread them.

| Project | Links |
|---|---|
| **NightDesk** (S1 1st overall, 6,600 USDT) | https://github.com/Pratiikpy/NightDesk · https://night-desk-nine.vercel.app/ |
| **Nocturne** (S1 winner, Track 3) | https://github.com/theeagle2407/Nocturne · https://nocturne-suz6.onrender.com/ |

Their published findings we treat as settled and do **not** re-litigate:
- Nocturne: overnight-gap directional strategy loses money in *and* out of sample after 0.10%/night costs.
- NightDesk: token↔real-stock convergence is **49.6% corrective — a coin flip**; champion Sharpe
  not significant after deflating across 9,720 candidates.

**Ballast is not a directional strategy.** That is the whole point of the design.

Idea vault (patterns P1–P19, 28 captured winners): https://github.com/Ritapossible/Wining-hackathon-skills

## 5. Verified API facts — measured 2026-09-08

Base: `https://api.bitget.com`. All of the below need **no API key**.

| Fact | Value |
|---|---|
| Spot symbols | `GET /api/v2/spot/public/symbols` |
| Spot tickers | `GET /api/v2/spot/market/tickers` |
| **Recent candles (max 1000 bars ≈ 43d)** | `GET /api/v2/spot/market/candles?symbol=&granularity=1h&limit=1000` |
| **Historical candles — pages backwards** | `GET /api/v2/spot/market/history-candles?symbol=&granularity=1h&endTime=<ms>&limit=200` |
| Futures tickers | `GET /api/v2/mix/market/tickers?productType=usdt-futures` |
| Futures history candles | `GET /api/v2/mix/market/history-candles?symbol=&granularity=1H&productType=usdt-futures&endTime=&limit=` |
| Funding history | `GET /api/v2/mix/market/history-fund-rate?symbol=&productType=usdt-futures&pageSize=100` |
| Contract spec | `GET /api/v2/mix/market/contracts?productType=usdt-futures&symbol=` |

### Traps that will cost you a day if forgotten
- **Granularity casing differs**: spot wants `1h`, futures wants `1H`. Wrong case returns an
  empty `data` array with `code: 00000` — a silent failure, not an error.
- **`candles` vs `history-candles`**: the former caps at 1000 bars (~43 days) and *looks* like a
  hard history limit. It is not. `history-candles` + `endTime` reaches **over two years** of hourly
  rToken data (RTSLA reaches 2024-05-28). A prior S1 project published the 41-day figure as a hard cap; it is wrong.
- rToken identification: `baseCoin` matches `^r[A-Z]` (e.g. `rPBR`). Do **not** regex the
  `symbol` field — `RUNEUSDT`, `ROSEUSDT`, `RAYUSDT`, `REDUSDT` are crypto, not stocks.
- Stock **perps use the bare ticker**: `TSLAUSDT`, `NVDAUSDT` — no `R` prefix. `RTXSTOCKUSDT`
  is the disambiguated form for RTX the defense company.

### Measured market facts

| Fact | Value | Date |
|---|---|---|
| rTokens live on spot | **699**, all `status: online` | 2026-09-08 |
| **rTokens with a matched perp leg** | **219** — this is our tradeable universe | 2026-09-08 |
| rToken spot fees | taker **0.10%** / maker **0.10%** — *no maker discount* | 2026-09-08 |
| rToken spot round-trip exit cost | **20 bp** | derived |
| Perp fees | taker 0.06% / maker 0.02%, `fundInterval` 8h, min 5 USDT | 2026-09-08 |
| **Hedge round trip (taker), net of funding** | **11.3 bp** — use this as the default | derived |
| Hedge round trip (maker) | ~3.3 bp — **upside only, never assume it fills** | derived |
| Funding | positive; a short perp **receives** ~3.9% annualised | 2026-09-08 |
| rToken spot limit band | ±10% (`buyLimitPriceRatio` 0.1) | 2026-09-08 |
| Min trade | rToken spot 20 USDT · perp 5 USDT | 2026-09-08 |

## 6. Research findings (see `docs/RESEARCH.md`; reproduce with `research/`)

- Overnight perp hedge, 12 names, ~200 nights each: **median R² 0.980**, β within 4% of 1.00,
  split-half stable.
- **The hedge strengthens under stress** — top-decile move nights R² 0.978–1.000; quiet nights
  0.77–0.96. Imprecision is confined to nights where little is at stake.
- Tail: **median 88% cut in p95 |move|**. MSFT 1,128bp → 233bp. AMD 1,262bp → 90bp.
- Weekends (Fri→Mon) hold: R² 0.941–0.992.
- **Crypto is not a hedge** — median BTC R² 0.114. Do not add crypto legs.
- **Gate 1b (PASSES): the earnings calendar separates at 3.2x and those nights are
  UNCOMPENSATED** (pooled -61bp, t=-1.59, 0/15 names significant). Earnings-night 1-sigma is
  392bp against an 11.3bp cost -- 35:1. **The calendar is the selector.** The volatility gate
  ships OFF in `policy.py`; re-enabling needs new evidence.
- **Replay, calendar-only: 15/16 hedges reduced the move (94%) at 0.3bp average drag.
  But only 2 of the 6 worst nights were covered** -- scheduled earnings are a minority of
  the tail. Extending the selector to unscheduled events is the LLM reader's job.
- **Gate 1a: trailing realised vol does NOT select risky nights.** Variance ratio of ex-ante
  selected vs rest = **1.41×** (versus 13.2× when selected ex-post). Statistical vol selection
  is useless here. **The selector must be the event calendar.** This is why the LLM is load-bearing
  rather than decorative.

## 6b. Environment

| Variable | Purpose | Without it |
|---|---|---|
| `QWEN_API_KEY` (or `BITGET_QWEN_KEY`) | the event reader | reader abstains, calendar rule decides, reason logged |
| `BALLAST_SECRET` | mandate + ledger signing | a development key is used and every run says so |
| `QWEN_BASE_URL` | default `https://hackathon.bitgetops.com/v1` | — |
| `QWEN_MODEL` | default `qwen3.8-max` | — |

The endpoint is live and OpenAI-compatible: a dummy key returns HTTP 401, not a connection
error. News comes from Google News RSS (free, keyless); **Yahoo's feeds return 429 from
datacenter IPs** and are not usable here.

## 7. Hard rules for this codebase

0. **Costs come from `ballast/costs.py`; published figures come from `docs/facts.json`.**
   Never write a fee, a cost or a universe count as a literal. Three different numbers
   for the hedge cost were once in use and the site advertised a price it did not
   settle at; the universe count drifted from 219/699 to 224/704 unnoticed.
   `research/costs_study.py` and `research/facts_study.py` regenerate both.

1. **Never state a number that was not produced by code in `research/` or a live endpoint.**
   Every figure carries a label: `observed` / `estimated` / `targeted`. The submission form
   requires this and the whole strategy rests on it.
1b. **Overnight returns require `market.bars()`, never `market.closes()`.**
   Close-only input now raises. It used to degrade silently to the previous hour's
   close, which shifted returns by a mean of 71-99bp and inflated sigma ~15% - so
   production disagreed with the research that justifies it.
2. **No look-ahead, ever.** Any selection rule sees only strictly prior data. The ex-post
   selection bug is already documented in `docs/RESEARCH.md`; do not reintroduce it. Ship a
   sentinel test that fails if future data changes a past signal.
3. **DST is a correctness issue, not a detail.** US close is 20:00 UTC under EDT and 21:00 UTC
   under EST. Transitions inside our sample: **2025-11-02** and **2026-03-08**. All session logic
   goes through `research/sessions.py`; nothing hardcodes an hour.
4. **Cost model defaults to taker.** Maker fills are upside, never an assumption.
5. **The LLM translates; it never decides.** It returns a typed `NightRisk` record. All sizing,
   pricing, gating and grading is deterministic typed code.
6. **The enforcer is a separate process** and holds the only write-scoped key.
7. **Paper only.** No real fill is claimed anywhere. `ballast/export.py` re-encodes
   the ledger in Bitget UTA order field names for comparison; it invents nothing.
8. **Writing requires `BALLAST_SECRET`.** `DEV_SECRET` is public in this repo, so a
   silent fallback would make "signed and tamper-evident" untrue. Set
   `BALLAST_DEV_SECRET=1` to opt in deliberately. Reading degrades to
   "signatures NOT verified" rather than crashing.
9. **A session is never settled partially**, and settlement is idempotent. Both would
   otherwise corrupt the evidence: stranded rows, or double-counted tiles.
10. **Never present the hedge leg standalone** - always the paired hedged-vs-unhedged portfolio
   on the same positions and the same nights.

11. **A refusal gets no nightly verdict.** Its value added is positive exactly when the
    position rose, so correct/wrong on a refusal is a directional scorecard - the one claim
    two S1 winners already showed cannot be made. Hedges are graded on whether they cut the
    move (symmetric, settled by one night); refusals are graded across the run, on the mean.
    Every row still shows its own signed arithmetic.

## 7b. Operations

- `.github/workflows/nightly.yml` — decides at 21:00 UTC, settles at 14:30 UTC, Mon–Fri.
  Verifies the ledger chain, rebuilds `docs/index.html`, commits `state/`. Crons are set
  for **EDT**; US clocks fall back 2026-11-01, after the competition ends.
- `.github/workflows/ci.yml` — tests on every push. The suite is network-free and key-free,
  so CI cannot go red because a third party rate-limited us.
- **Repo secrets to set:** `QWEN_API_KEY`, `BALLAST_SECRET`. Without them the run still
  succeeds — the reader abstains and a dev signing key is used — and says so in the output.
- **Enable GitHub Pages on `/docs`** to give the demo a public URL.
- **A scheduled run is a fresh checkout.** `.cache/` is gitignored and absent there, and
  GitHub can delay a cron by hours. Anything the loop touches must work cold, on the
  first try, with no local state. Mocking a dependency in tests is right, but it means
  the dependency itself needs its own test.
- **Never rebuild `docs/` locally.** The site is static: the chain is verified when the
  pages are built and the verdict is a fixed string in the HTML. Only the workflow holds
  `BALLAST_SECRET`, so a local rebuild over a scheduled run's ledger publishes
  "CHAIN BROKEN" about a ledger that is intact - which is what broke the live site on
  2026-09-10. The builders' `__main__` now refuses a keyless build, CI rejects a page that
  misreports the chain, and `workflow_dispatch` with `task: publish` regenerates the site
  without appending anything to the ledger. Content changes to a page: edit the builder,
  push, then run `publish`.

## 8. Submission requirements — non-negotiable

Missing any one of these **invalidates the entry regardless of quality**:
- Compliant **X post** including `#BitgetHackathon` and `@Bitget_AI`
- Project description (the six-part answer — cannot be replaced by links)
- Publicly accessible submission materials (no login)

Six-part description; **judges weight parts 1–3 most heavily**:
1. Thesis · 2. **Target user & value — "all traders" is explicitly rejected** · 3. Validation data
& metrics · 4. Progress · 5. Deliverables · 6. Take on AI trading (optional)

Agentic Trading also requires: runnable demo · event→decision→execution flow · **paper trading log
run during the competition** (2+ weeks recommended; only 13 days exist — the log is the critical path).

Judged: 50% quantitative (paper Sharpe, max drawdown, win rate) + 50% judge
(decision explainability, agent architecture, **risk-control layer effectiveness**).
Note **novelty is not a listed criterion** in S2 — architecture and risk control are.

Max **2 themes** per team, separate submissions, judged independently.
