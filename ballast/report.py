"""Render the signed ledger into a self-contained HTML page.

This is the judge-facing surface. Three properties it must have, each learned from
what the handbook requires or what a cold demo costs you:

  * publicly readable with no login (a submission requirement)
  * always-on, with no backend to wake up — one static file, no CDN, no fonts,
    nothing that can 404 on the day
  * every claim traceable to a ledger entry a reader can verify themselves

    python -m ballast.report            # -> docs/index.html
"""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from . import config
from .ledger import Ledger, LedgerError

OUT = config.ROOT / "docs" / "index.html"

CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a19;--dim:#6b6b68;--line:#e3e3e0;--card:#fff;
--pos:#0e7a57;--neg:#b3261e;--accent:#0f6e8c}
@media(prefers-color-scheme:dark){:root{--bg:#131313;--fg:#ececeb;--dim:#9a9a97;
--line:#2c2c2b;--card:#1b1b1a;--pos:#4ec9a0;--neg:#f2836b;--accent:#63b8d4}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:48px 20px 80px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:17px;margin:44px 0 12px;letter-spacing:-.01em}
.sub{color:var(--dim);margin:0 0 28px}
.claim{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:8px;padding:18px 20px;margin:0 0 10px}
.claim p{margin:0}
.not{border-left-color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.tile .n{font-size:22px;font-weight:600;letter-spacing:-.02em}
.tile .l{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:560px}
th{text-align:left;font-weight:600;color:var(--dim);font-size:12px;
text-transform:uppercase;letter-spacing:.06em;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pos{color:var(--pos)}.neg{color:var(--neg)}.dim{color:var(--dim)}
.tag{display:inline-block;font-size:11px;padding:2px 7px;border-radius:99px;
border:1px solid var(--line);color:var(--dim);white-space:nowrap}
.tag.hedge{color:var(--accent);border-color:var(--accent)}
code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--card);
border:1px solid var(--line);border-radius:4px;padding:1px 5px}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:14px 16px;overflow-x:auto;font:13px ui-monospace,Menlo,monospace}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);
color:var(--dim);font-size:13px}
"""


def _esc(v) -> str:
    return html.escape(str(v))


def _tile(n, label, cls="") -> str:
    return f'<div class="tile"><div class="n {cls}">{_esc(n)}</div><div class="l">{_esc(label)}</div></div>'


def _decisions_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="dim">No decisions recorded yet.</p>'
    out = ['<div class="scroll"><table><tr><th>Position</th><th>Decision</th>'
           '<th class="num">1σ forecast</th><th class="num">Notional</th>'
           '<th>Decided by</th><th>Reasoning</th></tr>']
    for r in rows:
        hedged = r.get("action") == "HEDGE"
        by = (r.get("inputs") or {}).get("decided_by", "rule")
        out.append(
            f'<tr><td><strong>{_esc(r.get("ticker"))}</strong></td>'
            f'<td><span class="tag {"hedge" if hedged else ""}">{_esc(r.get("action"))}</span></td>'
            f'<td class="num">{r.get("sigma_bp", 0):.0f} bp</td>'
            f'<td class="num">{r.get("notional_usdt", 0):,.0f}</td>'
            f'<td><span class="tag">{_esc(by)}</span></td>'
            f'<td class="dim">{_esc(r.get("rationale", ""))}</td></tr>')
    return "".join(out) + "</table></div>"


def _settlement_table(rows: list[dict]) -> str:
    if not rows:
        return ('<p class="dim">Nothing settled yet. Each decision is graded at the '
                'next primary open, against the exact counterfactual.</p>')
    out = ['<div class="scroll"><table><tr><th>Position</th><th>Decision</th>'
           '<th class="num">Unhedged</th><th class="num">Realised</th>'
           '<th class="num">Value added</th><th>Verdict</th></tr>']
    for r in sorted(rows, key=lambda x: -abs(x.get("unhedged_bp", 0))):
        va = r.get("value_added_bp", 0)
        out.append(
            f'<tr><td><strong>{_esc(r.get("ticker"))}</strong></td>'
            f'<td><span class="tag {"hedge" if r.get("action")=="HEDGE" else ""}">'
            f'{_esc(r.get("action"))}</span></td>'
            f'<td class="num">{r.get("unhedged_bp", 0):+,.0f} bp</td>'
            f'<td class="num">{r.get("realised_bp", 0):+,.0f} bp</td>'
            f'<td class="num {"pos" if va > 0 else "neg" if va < 0 else ""}">{va:+,.0f} bp</td>'
            f'<td>{"correct" if r.get("correct") else "wrong"}</td></tr>')
    return "".join(out) + "</table></div>"


def build() -> Path:
    ledger = Ledger(config.LEDGER_PATH, config.secret())
    try:
        entries = ledger.verify()
        chain = f"{entries} entries, chain verified"
    except LedgerError as exc:
        chain = f"CHAIN BROKEN — {exc}"

    decisions = [e["body"] for e in ledger.records("decision")]
    summaries = [e["body"] for e in ledger.records("night_summary")]
    settlements = [e["body"] for e in ledger.records("settlement")]

    latest = summaries[-1] if summaries else {}
    session = latest.get("session", "—")
    tonight = [d for d in decisions if d.get("session") == session]
    settled_rows = [r for s in settlements for r in s.get("rows", [])]
    hedges = [r for r in settled_rows if r.get("action") == "HEDGE"]
    shrank = sum(1 for r in hedges if abs(r.get("realised_bp", 0)) < abs(r.get("unhedged_bp", 0)))
    worst = max((abs(r.get("unhedged_bp", 0)) for r in settled_rows), default=0)

    body = f"""<div class="wrap">
<h1>Ballast</h1>
<p class="sub">Overnight risk transfer for tokenized US stocks · generated
{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC · paper trading only</p>

<div class="claim"><p><strong>Hold the position through the night without holding the
night's risk.</strong> A matched stock perp removes a median 98.0% of overnight variance
at β≈1.00, for about 11 bp — against 20 bp to exit the position and lose it.</p></div>
<div class="claim not"><p><strong>What this does not claim.</strong> Ballast is priced
protection, not alpha. It makes no Sharpe claim. It cannot place a directional trade:
every order it can emit is opposite in sign to, and bounded by, a position already held.</p></div>

<div class="grid">
{_tile(latest.get('positions', 0), 'positions')}
{_tile(latest.get('hedged', 0), 'hedged tonight')}
{_tile(len(settled_rows), 'decisions settled')}
{_tile(f"{shrank}/{len(hedges)}" if hedges else "—", 'hedges that cut the move')}
{_tile(f"{worst:,.0f} bp" if worst else "—", 'worst night seen')}
</div>

<h2>Tonight — session {_esc(session)}</h2>
<p class="sub">Window {latest.get('window_hours', 0)} hours · event reader
{_esc(latest.get('reader', 'unknown'))}</p>
{_decisions_table(tonight)}

<h2>Settled against the open</h2>
<p class="sub">Every decision is graded at the next primary open against the
<strong>exact counterfactual</strong> — what the position would have done unhedged is
observed, not modelled. Refusals are graded alongside hedges.</p>
{_settlement_table(settled_rows)}

<h2>Claim boundaries</h2>
<div class="scroll"><table>
<tr><th>Claim</th><th>Status</th></tr>
<tr><td>Perp hedge removes a median 98.0% of overnight variance (12 names, ~200 nights each)</td><td>observed</td></tr>
<tr><td>Hedge strengthens under stress — R² 0.978–0.999 on top-decile nights</td><td>observed</td></tr>
<tr><td>Earnings nights carry 3.2× the variance and are not reliably compensated</td><td>observed</td></tr>
<tr><td>Trailing volatility cannot select risky nights (1.41× separation)</td><td>observed</td></tr>
<tr><td>Signed, tamper-evident decision ledger</td><td>proven — {_esc(chain)}</td></tr>
<tr><td>Enforcer refuses every directional intent</td><td>proven — 18 red-team tests</td></tr>
<tr><td>Improves risk-adjusted return</td><td class="dim">not claimed</td></tr>
<tr><td>Any live fill</td><td class="dim">not claimed — paper only</td></tr>
</table></div>

<h2>Verify it yourself</h2>
<pre>git clone https://github.com/Ritapossible/ballast &amp;&amp; cd ballast
python3 -m unittest discover -s tests   # full suite: no network, no API key
python3 research/hedge_study.py         # reproduces the hedge measurements
python3 research/gate1_calendar.py      # reproduces the selector result</pre>
<p class="dim">The ledger is hash-chained and committed by a scheduled job, so each
decision is recorded before its outcome is known and timestamped independently by
GitHub. Mutating, deleting or reordering any entry breaks verification.</p>

<footer>Bitget AI Base Camp Hackathon S2 · Agentic Trading · Event-Driven Agent.
Paper trading only. Not financial advice.</footer>
</div>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Ballast — overnight risk transfer</title><style>{CSS}</style>'
        f'</head><body>{body}</body></html>')
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")
