"""Render the signed ledger into the public report.

This is the judge-facing surface, and the handbook makes an accessible demo a
required material. Three properties it has to keep:

  * publicly readable, no login
  * always-on with nothing to cold-start — one static file, no CDN, no web fonts,
    no scripts, so nothing can 404 or hang on the day
  * every claim traceable to a ledger entry the reader can verify themselves

    python -m ballast.report            # -> docs/index.html
"""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from . import config
from .ledger import Ledger, LedgerError
from .theme import CSS, MARK

OUT = config.ROOT / "docs" / "index.html"
REPO = "https://github.com/Ritapossible/ballast"


def _e(v) -> str:
    return html.escape(str(v))


def _tile(n, label) -> str:
    return f'<div class="tile"><div class="n">{_e(n)}</div><div class="l">{_e(label)}</div></div>'


def _empty(msg: str) -> str:
    return f'<div class="scroll"><div class="empty">{_e(msg)}</div></div>'


def _decisions(rows: list[dict]) -> str:
    if not rows:
        return _empty("No decisions recorded yet. The loop runs after the US close.")
    out = ['<div class="scroll"><table><thead><tr><th>Position</th><th>Call</th>'
           '<th class="num">1σ forecast</th><th class="num">Notional</th>'
           '<th>Decided by</th><th>Reasoning</th></tr></thead><tbody>']
    for r in rows:
        on = r.get("action") == "HEDGE"
        by = (r.get("inputs") or {}).get("decided_by", "rule")
        out.append(
            f'<tr><td><strong>{_e(r.get("ticker"))}</strong></td>'
            f'<td><span class="tag {"on" if on else ""}">{_e(r.get("action"))}</span></td>'
            f'<td class="num mid">{r.get("sigma_bp", 0):,.0f} bp</td>'
            f'<td class="num mid">{r.get("notional_usdt", 0):,.0f}</td>'
            f'<td><span class="tag {"on" if by == "model" else ""}">{_e(by)}</span></td>'
            f'<td class="dim">{_e(r.get("rationale", ""))}</td></tr>')
    return "".join(out) + "</tbody></table></div>"


def _settled(rows: list[dict]) -> str:
    if not rows:
        return _empty("Nothing settled yet. Every decision is graded at the next "
                      "primary open, against the exact counterfactual.")
    out = ['<div class="scroll"><table><thead><tr><th>Position</th><th>Call</th>'
           '<th class="num">Unhedged</th><th class="num">Realised</th>'
           '<th class="num">Value added</th><th>Verdict</th></tr></thead><tbody>']
    for r in sorted(rows, key=lambda x: -abs(x.get("unhedged_bp", 0))):
        va = r.get("value_added_bp", 0)
        cls = "pos" if va > 0 else "neg" if va < 0 else "dim"
        on = r.get("action") == "HEDGE"
        out.append(
            f'<tr><td><strong>{_e(r.get("ticker"))}</strong></td>'
            f'<td><span class="tag {"on" if on else ""}">{_e(r.get("action"))}</span></td>'
            f'<td class="num mid">{r.get("unhedged_bp", 0):+,.0f} bp</td>'
            f'<td class="num mid">{r.get("realised_bp", 0):+,.0f} bp</td>'
            f'<td class="num {cls}">{va:+,.0f} bp</td>'
            f'<td class="{"" if r.get("correct") else "dim"}">'
            f'{"correct" if r.get("correct") else "wrong"}</td></tr>')
    return "".join(out) + "</tbody></table></div>"


CLAIMS = [
    ("A matched perp removes a median 98.0% of overnight variance, β within 4% of 1.00",
     "observed", "12 names, 100–260 nights each"),
    ("The hedge strengthens under stress — R² 0.978–0.999 on top-decile nights",
     "observed", "conditional regression"),
    ("Median 88% cut in p95 tail; MSFT's worst night 1,128 bp → 233 bp",
     "observed", "same sample"),
    ("Earnings nights carry 3.2× the variance and are not reliably compensated",
     "observed", "15 names; 0 of 15 significant at |t|≥2"),
    ("Trailing volatility cannot select risky nights — 1.41× separation",
     "observed", "which is why the reader exists"),
    ("Signed, tamper-evident decision ledger", "proven", None),
    ("The enforcer refuses every directional intent", "proven", "18 red-team tests"),
    ("Improves risk-adjusted return", "not claimed", "priced protection, not alpha"),
    ("Any live fill", "not claimed", "paper only"),
]


def build() -> Path:
    ledger = Ledger(config.LEDGER_PATH, config.secret())
    try:
        chain = f"{ledger.verify()} entries · chain verified"
        broken = False
    except LedgerError as exc:
        chain, broken = f"CHAIN BROKEN — {exc}", True

    decisions = [e["body"] for e in ledger.records("decision")]
    summaries = [e["body"] for e in ledger.records("night_summary")]
    settlements = [e["body"] for e in ledger.records("settlement")]

    latest = summaries[-1] if summaries else {}
    session = latest.get("session", "—")
    tonight = [d for d in decisions if d.get("session") == session]
    rows = [r for s in settlements for r in s.get("rows", [])]
    hedges = [r for r in rows if r.get("action") == "HEDGE"]
    shrank = sum(1 for r in hedges if abs(r.get("realised_bp", 0)) < abs(r.get("unhedged_bp", 0)))
    worst = max((abs(r.get("unhedged_bp", 0)) for r in rows), default=0)
    now = dt.datetime.now(dt.timezone.utc)

    claim_rows = "".join(
        f'<tr><td>{_e(c)}</td>'
        f'<td><span class="tag {"on" if s == "proven" else ""}">{_e(s)}</span></td>'
        f'<td class="dim">{_e(n or "")}</td></tr>'
        for c, s, n in CLAIMS)

    term = "".join(
        f'<div class="term-r"><span class="mid">{_e(d.get("ticker"))}</span>'
        f'<span class="{"hl" if d.get("action") == "HEDGE" else "dim"}">'
        f'{_e(d.get("action"))}</span></div>'
        for d in tonight[:6]) or (
        '<div class="term-r"><span class="dim">awaiting the next close</span>'
        '<span class="dim">—</span></div>')

    body = f"""<header class="top"><div class="top-in">
<div class="brand">{MARK}BALLAST</div>
<a class="btn btn-p" href="#tonight">See tonight</a>
</div></header>
<nav class="nav"><div class="nav-in">
<a class="on" href="#top">Overview</a><a href="#tonight">Tonight</a>
<a href="#settled">Settled</a><a href="#evidence">Evidence</a>
<a href="#method">Method</a><a href="{REPO}">Repo</a>
</div></nav>

<main id="top"><div class="wrap">

<section>
<p class="eyebrow">Bitget AI Hackathon S2 · Agentic Trading</p>
<h1>Hold the position.<br>Not the night's risk.</h1>
<p class="lede">Tokenized US stocks trade around the clock. The market that prices
them is shut for <span class="hl">81% of the week</span> — through earnings, through
the Fed, through weekends. Ballast lets you keep the position and switch the night
off for about <span class="hl">11 basis points</span>.</p>
<div class="row">
<a class="btn btn-p" href="#tonight">Tonight's decisions</a>
<a class="btn btn-s" href="#evidence">What's verified</a>
</div>

<div class="term">
<div class="term-bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
<span>ballast / session {_e(session)}</span>
<span class="live"><span class="pulse"></span>{"BROKEN" if broken else "LEDGER OK"}</span></div>
<div class="term-b">{term}</div>
</div>
</section>

<section>
<p class="eyebrow">The exposure</p>
<h2>Every night, unhedged, by default.</h2>
<p class="lede">A matched stock perp trades the same clock as the token and moves
with it almost exactly. Shorting it overnight removes nearly all of the move —
and costs less than selling the position and buying it back.</p>
<div class="tiles">
{_tile("98.0%", "median variance removed")}
{_tile("β 1.00", "hedge ratio, ±4%")}
{_tile("88%", "median p95 tail cut")}
{_tile("11.3 bp", "cost to protect")}
{_tile("20 bp", "cost to exit instead")}
</div>
<ul class="bul">
<li>The hedge is <strong>strongest exactly when it matters</strong> — R² reaches 0.999 on the largest moves, and is loosest on quiet nights where little is at stake.</li>
<li>Worst nights measured: MSFT <strong>1,128 bp → 233 bp</strong>, AMD <strong>1,262 bp → 90 bp</strong>.</li>
<li><strong>219 of 699</strong> listed rTokens have a perp leg. Ballast says plainly which positions it cannot protect.</li>
</ul>
</section>

<section id="tonight">
<p class="eyebrow">Live from the desk</p>
<h2>Tonight's decisions.</h2>
<p class="lede">One call per position, taken before the window opens and written to
a signed ledger. Refusals are recorded as carefully as hedges — a night Ballast
declined is a decision it will be graded on.</p>
<p class="note">Session <strong>{_e(session)}</strong> · window
{latest.get('window_hours', 0)} hours · event reader
<strong>{_e(latest.get('reader', 'unknown'))}</strong> · {_e(chain)}</p>
{_decisions(tonight)}
</section>

<section id="settled">
<p class="eyebrow">Graded against reality</p>
<h2>Every call has an exact counterfactual.</h2>
<p class="lede">What the position would have done unhedged is not modelled — it is
<span class="hl">observed</span>, on the same window. So every decision, right or
wrong, is settled at the next opening bell and nothing can be quietly forgotten.</p>
<div class="tiles">
{_tile(len(rows), "decisions settled")}
{_tile(f"{shrank}/{len(hedges)}" if hedges else "—", "hedges that cut the move")}
{_tile(f"{worst:,.0f} bp" if worst else "—", "worst night seen")}
{_tile(latest.get("hedged", 0), "hedged tonight")}
</div>
{_settled(rows)}
</section>

<section id="evidence">
<p class="eyebrow">Open by construction</p>
<h2>What is verified, and what is not.</h2>
<div class="cards">
<div class="card"><h3>It cannot place a bet</h3><p>Every order Ballast can emit is
opposite in sign to, and bounded in size by, a position already held. The enforcer
holds the only write-scoped key, sees no model reasoning, and does arithmetic
against a signed mandate.</p></div>
<div class="card"><h3>The model is fenced, not trusted</h3><p>Qwen owns the
hedge judgment. Three gates stand between it and an order: schema, ticker identity,
and a grounding check that a quote actually appears in the supplied headlines.
A fabricated source cannot reach the book.</p></div>
<div class="card"><h3>The record cannot be edited</h3><p>The ledger is hash-chained
and signed; mutation, deletion or reordering breaks verification. A scheduled job
commits it, so each decision is timestamped before its outcome is known.</p></div>
</div>
<div class="scroll"><table><thead><tr><th>Claim</th><th>Status</th><th>Basis</th>
</tr></thead><tbody>{claim_rows}</tbody></table></div>
<p class="note" style="margin-top:22px">Ballast is <strong>priced protection, not
alpha</strong>. It makes no Sharpe claim: the nights it hedges carry real variance
and no reliable expected return, so removing them is insurance — which has a price
and is worth paying only on the right nights.</p>
</section>

<section id="method">
<p class="eyebrow">Reproduce it</p>
<h2>Don't take the numbers on trust.</h2>
<p class="lede">Every figure on this page is produced by code in the repository,
from public endpoints, with no API key.</p>
<pre><b>git clone {REPO} &amp;&amp; cd ballast</b>
python3 -m unittest discover -s tests   <span class="dim"># full suite, no network, no key</span>
python3 research/hedge_study.py         <span class="dim"># the hedge measurements</span>
python3 research/gate1_calendar.py      <span class="dim"># why the calendar is the selector</span>
python3 research/replay.py              <span class="dim"># the policy, replayed over history</span></pre>
<ul class="bul">
<li><strong>No look-ahead is possible</strong> — every selector sees strictly prior data, and a sentinel test fails if a future night ever moves a past decision.</li>
<li><strong>Defects are published, not patched over</strong> — a DST bug, a look-ahead contamination and an hour-snapping bug are all written up in the research notes.</li>
<li><strong>Paper trading only.</strong> No live fill is claimed anywhere.</li>
</ul>
</section>

</div></main>

<footer><div class="wrap">
Ballast · Bitget AI Base Camp Hackathon S2 · Agentic Trading, Event-Driven Agent<br>
Generated {now:%Y-%m-%d %H:%M} UTC · <a href="{REPO}">source</a> ·
paper trading only, not financial advice.
</div></footer>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Ballast — overnight risk transfer for tokenized US stocks</title>'
        '<meta name="description" content="Hold tokenized US stocks through the night '
        'without holding the night\'s risk.">'
        f'<style>{CSS}</style></head><body>{body}</body></html>')
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size:,} bytes)")
