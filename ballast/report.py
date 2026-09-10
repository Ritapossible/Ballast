"""Build the public site from the signed ledger.

Four pages rather than one long scroll: the landing page makes the case, and each
working surface - tonight's calls, what settled, the evidence - gets its own URL so
it can be linked to, deep-linked from a submission, and read on a phone without
scrolling past everything else.

Every page is self-contained: no CDN, no web fonts, no scripts, nothing that can
404 or hang when a judge opens it.

    python -m ballast.report            # -> docs/*.html
"""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from . import config
from .facts import load as load_facts
from .ledger import Ledger, LedgerError
from .sessions import UTC, close_utc, current_session, sessions_between, window_hours
from .theme import REPO, page

OUT_DIR = config.ROOT / "docs"


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
        # A hedge answers a symmetric question - did it cut the move - and one
        # night answers it. A refusal does not: value added is positive for a
        # refusal exactly when the position rose, so a per-night verdict on it is
        # a directional scorecard, and this system makes no directional claim.
        # The number stays in the row; only the label is withheld.
        if on:
            cut = abs(r.get("realised_bp", 0)) < abs(r.get("unhedged_bp", 0))
            verdict, faint = ("cut the move", False) if cut else ("did not cut", True)
        else:
            verdict, faint = "carried", True
        out.append(
            f'<tr><td><strong>{_e(r.get("ticker"))}</strong></td>'
            f'<td><span class="tag {"on" if on else ""}">{_e(r.get("action"))}</span></td>'
            f'<td class="num mid">{r.get("unhedged_bp", 0):+,.0f} bp</td>'
            f'<td class="num mid">{r.get("realised_bp", 0):+,.0f} bp</td>'
            f'<td class="num {cls}">{va:+,.0f} bp</td>'
            f'<td class="{"dim" if faint else ""}">{verdict}</td></tr>')
    return "".join(out) + "</tbody></table></div>"


def claims(f: dict) -> list[tuple[str, str, str | None]]:
    return [
    (f"A matched perp removes a median {f['median_r2'] * 100:.1f}% of overnight "
     f"variance, β within 4% of 1.00", "observed", "12 names, 100-260 nights each"),
    ("The hedge strengthens under stress - R² 0.978-0.999 on top-decile nights",
     "observed", "conditional regression"),
    (f"Median {f['median_tail_cut_pct']}% cut in p95 tail; MSFT's worst night "
     f"1,128 bp to 233 bp", "observed", "same sample"),
    ("Earnings nights carry 3.2× the variance and are not reliably compensated",
     "observed", "15 names; 0 of 15 significant at |t|≥2"),
    ("Trailing volatility cannot select risky nights - 1.41× separation",
     "observed", "which is why the reader exists"),
    ("Signed, tamper-evident decision ledger", "proven", None),
    ("The enforcer refuses every directional intent", "proven", "18 red-team tests"),
    ("Improves risk-adjusted return", "not claimed", "priced protection, not alpha"),
    ("Any live fill", "not claimed", "paper only"),
    ]


class Site:
    """Everything the pages need, read from the ledger once."""

    def __init__(self, now: dt.datetime | None = None):
        now = now or dt.datetime.now(UTC)      # injectable, so staleness is testable
        self.f = load_facts()
        # Rendering is a read. It must not require the signing key - anyone should
        # be able to clone and rebuild the site - but it must never imply the
        # signatures were checked when they were not.
        try:
            ledger = Ledger(config.LEDGER_PATH, config.secret())
        except config.UnsignedError:
            ledger = Ledger(config.LEDGER_PATH, config.DEV_SECRET)
            self.chain = f"{len(ledger.records())} entries · signatures NOT verified"
            self.broken = False
            self.unverified = True
        else:
            self.unverified = False
            try:
                self.chain = f"{ledger.verify()} entries · chain verified"
                self.broken = False
            except LedgerError as exc:
                self.chain, self.broken = f"CHAIN BROKEN - {exc}", True

        decisions = [e["body"] for e in ledger.records("decision")]
        night_records = ledger.records("night_summary")
        summaries = [e["body"] for e in night_records]
        self.settlements = [e["body"] for e in ledger.records("settlement")]

        # By session date, not by write order: a backfill or an out-of-order run
        # would otherwise make an older night look like tonight.
        self.latest = max(summaries, key=lambda s: s.get("session", ""),
                          default={}) if summaries else {}
        self.session = self.latest.get("session", "-")

        # How late the night was decided. Newer runs record it; for entries written
        # before that field existed it is derived from the ledger's own timestamp,
        # so the published record reports its own provenance either way. One session
        # was re-decided 16.8 hours after its close - 45 minutes before the market
        # reopened - while settlement still graded it close-to-open, as though the
        # hedge had been on for the whole move. That entry now says so itself.
        self.decided_after = self.latest.get("decided_after_close_hours")
        if self.decided_after is None and self.session != "-":
            record = max((e for e in night_records
                          if e["body"].get("session") == self.session),
                         key=lambda e: e["at"], default=None)
            if record:
                written = dt.datetime.fromisoformat(record["at"])
                closed = close_utc(dt.date.fromisoformat(self.session))
                self.decided_after = round((written - closed).total_seconds() / 3600, 2)
        total = self.latest.get("window_hours") or (
            window_hours(dt.date.fromisoformat(self.session)) if self.session != "-" else 0)
        self.decided_late = bool(self.decided_after and total
                                 and self.decided_after > 0.5 * total)
        self.tonight = [d for d in decisions if d.get("session") == self.session]
        self.rows = [r for s in self.settlements for r in s.get("rows", [])]
        self.hedges = [r for r in self.rows if r.get("action") == "HEDGE"]
        self.shrank = sum(1 for r in self.hedges
                          if abs(r.get("realised_bp", 0)) < abs(r.get("unhedged_bp", 0)))
        self.worst = max((abs(r.get("unhedged_bp", 0)) for r in self.rows), default=0)
        # Where a refusal is actually graded: the mean over every settled
        # position-night, against the choice not taken. One session is n=1 and the
        # page says so - but the number belongs on the page, not only in the ledger.
        self.mean_va = (sum(r.get("value_added_bp", 0) for r in self.rows) / len(self.rows)
                        if self.rows else 0)

        # A scheduled run that stops running leaves the site showing its last good
        # night, which reads exactly like a working site. Settlement had in fact
        # been failing on every run since the loop was automated and the pages said
        # nothing. So the page states how far behind the ledger is, and a silent
        # failure becomes visible on the artifact itself.
        self.behind = 0
        try:
            shown = dt.date.fromisoformat(self.session)
            elapsed = list(sessions_between(shown, current_session(now)))
            self.behind = max(0, len(elapsed) - 1)
        except (ValueError, RuntimeError):
            self.behind = 0                    # no session yet, or a calendar fault
        self.freshness = ("" if not self.behind else
                          f" · <strong>{self.behind} session{'s' if self.behind > 1 else ''} "
                          f"behind</strong> - the scheduled run has not reported")

    @property
    def provenance(self) -> str:
        """One line on when this night was decided, and a plain warning if too late."""
        if self.decided_after is None:
            return ""
        when = (f'<p class="note">Decided <strong>{self.decided_after:.1f} hours</strong> '
                f'after the close.</p>')
        if not self.decided_late:
            return when
        return (f'<p class="note">Decided <strong>{self.decided_after:.1f} hours</strong> '
                f'after the close, with most of the overnight window already gone. '
                f'<span class="neg">This entry is not an ex-ante decision</span> and should '
                f'not be read as one: settlement grades it close-to-open, crediting a hedge '
                f'that could not have been on for the move. It is left in the chain rather '
                f'than removed, and later runs refuse a window this far elapsed.</p>')

    # -- pages ---------------------------------------------------------------

    def index(self) -> str:
        term = "".join(
            f'<div class="term-r"><span class="mid">{_e(d.get("ticker"))}</span>'
            f'<span class="{"hl" if d.get("action") == "HEDGE" else "dim"}">'
            f'{_e(d.get("action"))}</span></div>'
            for d in self.tonight[:5]) or (
            '<div class="term-r"><span class="dim">awaiting the next close</span>'
            '<span class="dim">-</span></div>')
        return f"""
<section class="bd"><div class="wrap center">
<h1>Hold the position.<br>Not the night's risk.</h1>
<p class="lede">Tokenized US stocks trade around the clock. The market that prices
them is shut for <span class="hl">81% of the week</span> - through earnings, through
the Fed, through weekends. Ballast keeps the position and switches the night off for
about <span class="hl">{self.f['hedge_cost_bp']:.0f} basis points</span>.</p>
<div class="row">
<a class="btn btn-p" href="tonight.html">Tonight's decisions</a>
<a class="btn btn-s" href="docs.html">Read the docs</a>
</div>
<div class="term">
<div class="term-bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
<span>ballast / session {_e(self.session)}{" / STALE" if self.behind else ""}</span>
<span class="live"><span class="pulse"></span>{"BROKEN" if self.broken else "LEDGER OK"}</span></div>
<div class="term-b">{term}</div>
</div>
</div></section>

<section class="bd bd-deep"><div class="wrap center">
<p class="eyebrow">The exposure</p>
<h2>Every night, unhedged,<br>by default.</h2>
<p class="lede">A matched stock perp trades the same clock as the token and moves with
it almost exactly. Shorting it overnight removes nearly all of the move - and costs
less than selling the position and buying it back.</p>
<div class="tiles">
{_tile(f"{self.f['median_r2'] * 100:.1f}%", "median variance removed")}
{_tile("β 1.00", "hedge ratio, ±4%")}
{_tile(f"{self.f['median_tail_cut_pct']}%", "median p95 tail cut")}
{_tile(f"{self.f['hedge_cost_bp']} bp", "cost to protect")}
{_tile(f"{self.f['exit_cost_bp']:.0f} bp", "cost to exit instead")}
</div>
<div class="narrow"><ul class="bul">
<li>The hedge is <strong>strongest exactly when it matters</strong> - R² reaches 0.999 on the largest moves, and is loosest on quiet nights where little is at stake.</li>
<li>Worst nights measured: MSFT <strong>1,128 bp to 233 bp</strong>, AMD <strong>1,262 bp to 90 bp</strong>.</li>
<li><strong>{self.f['rtokens_hedgeable']} of {self.f['rtokens_total']}</strong> listed rTokens have a perp leg, measured {self.f['measured_on']}. Ballast says plainly which positions it cannot protect.</li>
</ul></div>
</div></section>

<section><div class="wrap center">
<p class="eyebrow">The desk</p>
<h2>Three surfaces,<br>one record.</h2>
<div class="narrow stack">
<div class="card"><h3><a href="tonight.html" class="hl">Tonight →</a></h3>
<p>One call per position, taken before the window opens. Refusals are recorded as
carefully as hedges, because a night Ballast declined is a decision it will be
graded on.</p></div>
<div class="card"><h3><a href="settled.html" class="hl">Settled →</a></h3>
<p>Every call graded at the next opening bell against the exact counterfactual -
what the position would have done unhedged is observed, not modelled.</p></div>
<div class="card"><h3><a href="evidence.html" class="hl">Evidence →</a></h3>
<p>What is proven, what is merely observed, and what is deliberately not claimed -
plus the commands to reproduce every figure yourself.</p></div>
</div>
</div></section>"""

    def tonight_page(self) -> str:
        return f"""
<section class="bd"><div class="wrap center">
<p class="eyebrow">Live from the desk</p>
<h1>Tonight's decisions.</h1>
<p class="lede">One call per position, taken before the window opens and written to a
signed ledger. Refusals are recorded as carefully as hedges - a night Ballast
declined is a decision it will be graded on.</p>
<p class="note">Session <strong>{_e(self.session)}</strong> · window
{self.latest.get('window_hours', 0)} hours · event reader
<strong>{_e(self.latest.get('reader', 'unknown'))}</strong> · {_e(self.chain)}{self.freshness}</p>
{self.provenance}
</div></section>

<section><div class="wrap">
{_decisions(self.tonight)}
<div class="narrow" style="margin-top:52px">
<h3>How a call is made</h3>
<ul class="bul">
<li>The <strong>exchange calendar</strong> is checked for a report scheduled inside this window.</li>
<li>The <strong>event reader</strong> gets the night's headlines and that flag, and returns HEDGE, NO_HEDGE or ABSTAIN. Its judgment leads.</li>
<li>On abstention or a failed gate the <strong>deterministic rule</strong> decides instead, and the ledger records which.</li>
<li>Every intended order passes the <strong>enforcer</strong>, which can only permit a hedge against a position already held.</li>
</ul>
<div class="row" style="justify-content:center;margin-top:34px">
<a class="btn btn-s" href="settled.html">See what settled →</a></div>
</div>
</div></section>"""

    def settled_page(self) -> str:
        return f"""
<section class="bd"><div class="wrap center">
<p class="eyebrow">Graded against reality</p>
<h1>Every call has an<br>exact counterfactual.</h1>
<p class="lede">What the position would have done unhedged is not modelled - it is
<span class="hl">observed</span>, on the same window. Every decision, right or wrong,
settles at the next opening bell, so nothing can be quietly forgotten.</p>
<div class="tiles">
{_tile(len(self.rows), "decisions settled")}
{_tile(f"{self.shrank}/{len(self.hedges)}" if self.hedges else "-", "hedges that cut the move")}
{_tile(f"{self.worst:,.0f} bp" if self.worst else "-", "worst night seen")}
{_tile(f"{self.mean_va:+,.0f} bp" if self.rows else "-", "mean value added per position-night")}
</div>
</div></section>

<section><div class="wrap">
{_settled(self.rows)}
<div class="narrow" style="margin-top:52px">
<h3>How these are scored</h3>
<ul class="bul">
<li><strong>Value added</strong> is what the call returned minus what the other choice would have returned, over the same window, with the hedge cost charged to whichever side pays it. The counterfactual leg is not modelled - it is observed.</li>
<li><strong>A hedge is graded on whether it cut the move.</strong> It is symmetric, so grading one by profit direction would be meaningless, and one night settles the question.</li>
<li><strong>A refusal cannot be graded on one night.</strong> Its value added is positive exactly when the position rose, so a nightly verdict on a refusal is a directional scorecard - and this system makes no directional claim. On a broad down night every refusal scores badly, which is only the case for hedging everything, every night, at 11.3 bp a time. Refusals are graded across the run instead, on the mean above; each row still shows its own arithmetic.</li>
</ul>
</div>
</div></section>"""

    def evidence_page(self) -> str:
        claim_rows = "".join(
            f'<tr><td>{_e(c)}</td>'
            f'<td><span class="tag {"on" if s == "proven" else ""}">{_e(s)}</span></td>'
            f'<td class="dim">{_e(n or "")}</td></tr>'
            for c, s, n in claims(self.f))
        return f"""
<section class="bd"><div class="wrap center">
<p class="eyebrow">Open by construction</p>
<h1>An audited desk,<br>not a black box.</h1>
<div class="narrow stack">
<div class="card"><h3>It cannot place a bet</h3><p>Every order Ballast can emit is
opposite in sign to, and bounded in size by, a position already held. The enforcer
holds the only write-scoped key, sees no model reasoning, and does arithmetic against
a signed mandate. Eighteen red-team tests drive hostile intents at it.</p></div>
<div class="card"><h3>The model is fenced, not trusted</h3><p>Qwen owns the hedge
judgment. Three gates stand between it and an order - schema, ticker identity, and a
grounding check that the quoted headline actually appears in the supplied sources. A
fabricated source cannot reach the book.</p></div>
<div class="card"><h3>The record cannot be edited</h3><p>The ledger is hash-chained
and signed; mutation, deletion or reordering breaks verification. A scheduled job
commits it, so each decision is timestamped before its outcome is known.</p></div>
</div>
</div></section>

<section><div class="wrap">
<div class="scroll"><table><thead><tr><th>Claim</th><th>Status</th><th>Basis</th>
</tr></thead><tbody>{claim_rows}</tbody></table></div>
<div class="narrow" style="margin-top:44px">
<p class="note">Ballast is <strong>priced protection, not alpha</strong>. It makes no
Sharpe claim: the nights it hedges carry real variance and no reliable expected
return, so removing them is insurance - which has a price, and is worth paying only
on the right nights.</p>
<pre style="margin-top:34px"><b>git clone {REPO} &amp;&amp; cd ballast</b>
python3 -m unittest discover -s tests   <span class="dim"># full suite, no network, no key</span>
python3 research/hedge_study.py         <span class="dim"># the hedge measurements</span>
python3 research/gate1_calendar.py      <span class="dim"># why the calendar is the selector</span>
python3 research/replay.py              <span class="dim"># the policy, replayed over history</span></pre>
<ul class="bul">
<li><strong>No look-ahead is possible</strong> - every selector sees strictly prior data, and a sentinel test fails if a future night ever moves a past decision.</li>
<li><strong>Defects are published, not patched over</strong> - a DST bug, a look-ahead contamination and an hour-snapping bug are all written up.</li>
<li><strong>Paper trading only.</strong> No live fill is claimed anywhere.</li>
</ul>
<div class="row" style="justify-content:center;margin-top:34px">
<a class="btn btn-s" href="docs.html">Full documentation →</a></div>
</div>
</div></section>"""


PAGES = [
    ("index.html", "Overview", "Ballast - overnight risk transfer for tokenized US stocks",
     "Hold tokenized US stocks through the night without holding the night's risk.", "index"),
    ("tonight.html", "Tonight", "Ballast - tonight's decisions",
     "One call per position, taken before the overnight window opens.", "tonight_page"),
    ("settled.html", "Settled", "Ballast - settled against the open",
     "Every decision graded against the exact counterfactual.", "settled_page"),
    ("evidence.html", "Evidence", "Ballast - evidence and claim boundaries",
     "What is proven, what is observed, and what is deliberately not claimed.", "evidence_page"),
]


def build() -> list[Path]:
    site = Site()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, active, title, description, method in PAGES:
        path = OUT_DIR / filename
        path.write_text(page(title, description, active, getattr(site, method)()))
        written.append(path)
    return written


if __name__ == "__main__":
    config.refuse_dev_build()
    for p in build():
        print(f"wrote {p.name} ({p.stat().st_size:,} bytes)")
