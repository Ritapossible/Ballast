"""The documentation site - docs/docs.html.

Written for someone who has to decide whether to believe the numbers: what the
product does, how each mechanism was measured, where the model's authority starts
and stops, and what is deliberately not claimed.
"""
from __future__ import annotations

from pathlib import Path

from . import config
from .facts import load as load_facts
from .theme import REPO, page

OUT = config.ROOT / "docs" / "docs.html"

SECTIONS = [
    ("Start", [("what", "What Ballast is"), ("problem", "The problem"),
               ("who", "Who it is for")]),
    ("Mechanism", [("hedge", "The hedge"), ("selector", "Choosing the night"),
                   ("policy", "The decision policy")]),
    ("System", [("architecture", "Architecture"), ("authority", "Bounded authority"),
                ("ledger", "The ledger"), ("settlement", "Settlement")]),
    ("Evidence", [("research", "Research findings"), ("defects", "Defects found"),
                  ("roadmap", "Roadmap"), ("verify", "Reproduce it")]),
    ("Reference", [("cli", "CLI"), ("env", "Environment"), ("glossary", "Glossary")]),
]

F = load_facts()

BODY = f"""
<h2 id="what">What Ballast is</h2>
<p>Ballast is an autonomous overnight risk desk for <strong>tokenized US
equities</strong>. Every evening it looks at each position you hold, judges whether
tonight can move it, and - when it can - buys protection that removes almost all of
the night's price risk. Every call it makes is graded against reality the next
morning.</p>
<div class="callout"><p><strong>It is priced protection, not alpha.</strong> Ballast
makes no claim to improve returns and no Sharpe claim. It removes variance for a
stated price, on nights where that trade is worth making.</p></div>

<h2 id="problem">The problem</h2>
<p>The US primary market is open 6.5 hours a day, five days a week - <strong>32.5 of
every 168 hours</strong>. For the other ~81% of the week a tokenized stock keeps
trading while the market that prices its underlying is closed.</p>
<p>Companies report earnings after the close by design. The Fed moves mid-afternoon
and the consequences play out overnight. Geopolitics arrives at weekends. All of it
lands while a holder is exposed and cannot act in the underlying.</p>
<p>Today that holder has two options: sell before the close and give up the position
they actually want, or hold and absorb whatever arrives. Measured overnight moves in
this sample reach <strong>1,262 bp</strong> in a single night.</p>

<h2 id="who">Who it is for</h2>
<p>Conviction holders of tokenized US equities - someone holding one to ten positions
for weeks or months, 500–50,000 USDT apiece, directionally bullish and
drawdown-averse, who will not exit before a catalyst because exiting defeats a
multi-month thesis.</p>
<p>Their alternatives fail specifically: exiting a position costs <strong>{F['exit_cost_bp']:.0f} bp</strong>
round trip and surrenders it; there are no options on rTokens; and the underlying
market is shut, so it cannot be hedged there.</p>

<h2 id="hedge">The hedge</h2>
<p>Every rToken with a perp leg has a matched stock perpetual trading on the same
24/7 clock. Shorting that perp against the token cancels almost all of the overnight
move.</p>
<ul>
<li><strong>Median R² 0.980</strong> across 12 names, 100–260 nights each, with β
within 4% of 1.00 - close to a one-for-one hedge.</li>
<li><strong>It strengthens under stress.</strong> R² is 0.978–0.999 on top-decile
move nights and 0.77–0.96 on calm ones. On a big-news night the common factor
dominates and both instruments track it almost exactly; on a quiet night the residual
is venue microstructure noise. The hedge is loosest only when little is at stake.</li>
<li><strong>Median {F['median_tail_cut_pct']}% reduction in the p95 tail.</strong> MSFT's worst night falls
from 1,128 bp to 233 bp; AMD's from 1,262 bp to 90 bp.</li>
<li><strong>Cost {F['hedge_cost_bp']} bp</strong> taker round trip, net of funding received on the
short. Cheaper than the {F['exit_cost_bp']:.0f} bp it costs to exit - and you keep the position.</li>
<li><strong>Crypto is not a hedge.</strong> Median R² against BTC is 0.114. Crypto
legs are excluded by measurement, not preference.</li>
</ul>
<p>Of {F['rtokens_total']} live rTokens, <strong>{F['rtokens_hedgeable']} have a perp leg</strong> (measured {F['measured_on']}). Ballast states plainly
which positions it cannot protect rather than pretending otherwise.</p>

<h2 id="selector">Choosing the night</h2>
<p>Because a delta hedge is symmetric - it removes upside with downside - value exists
only on nights carrying variance <em>without</em> compensation. Two selectors were
tested against that bar.</p>
<div class="scroll"><table><thead><tr><th>Selector</th><th class="num">Separation</th>
<th>Compensated?</th><th>Verdict</th></tr></thead><tbody>
<tr><td>Trailing realised volatility</td><td class="num">1.41×</td>
<td>yes - +19.3 bp, t=3.08</td><td class="dim">unusable</td></tr>
<tr><td><strong>Earnings calendar</strong></td><td class="num">3.2×</td>
<td>no - −61 bp, t=−1.59</td><td class="hl">the selector</td></tr>
</tbody></table></div>
<p>Volatility barely distinguishes a risky night from an ordinary one, and the nights
it picks carry positive expected return - so hedging them pays to remove return.
Earnings nights separate three times better and carry no reliable compensation.
Earnings-night 1σ is <strong>392 bp against a {F['hedge_cost_bp']} bp cost</strong>, roughly 35:1.</p>
<div class="callout"><p><strong>This is why the model is necessary.</strong> The
statistical selector demonstrably fails, and the calendar reaches only part of the
tail - in replay it covered 2 of the 6 worst position-nights. Macro shocks, guidance,
legal rulings and product events drive the rest and appear on no calendar. Reading
them requires reading text.</p></div>

<h2 id="policy">The decision policy</h2>
<p>Each evening, per position:</p>
<ul>
<li>The <strong>calendar</strong> is checked for a scheduled report inside the window.</li>
<li>The <strong>event reader</strong> is given the night's headlines and the calendar
flag, and returns <code>HEDGE</code>, <code>NO_HEDGE</code> or <code>ABSTAIN</code>.</li>
<li>Its judgment <strong>leads</strong>. On abstention or a failed gate, the
deterministic calendar rule decides instead.</li>
<li>The <strong>volatility gate ships off.</strong> Re-enabling it requires new
evidence, not a hunch - the measurement above is encoded in the code comment.</li>
</ul>

<h2 id="architecture">Architecture</h2>
<pre>CALENDAR   scheduled events - Nasdaq, serves historical dates
READER     Qwen qwen3.8-max, temperature 0 · headlines + calendar flag
           -> HEDGE | NO_HEDGE | ABSTAIN, with sources
ENGINE     deterministic: risk vs cost, under the signed mandate
ENFORCER   separate process, only write-scoped key, sees no reasoning
EXECUTOR   Bitget SDK, paper mode
LEDGER     append-only, hash-chained, signed
SETTLEMENT graded at the primary open against the exact counterfactual</pre>
<p>Sources are deliberately keyless where possible: Nasdaq for scheduled events,
Google News RSS per ticker for unscheduled ones, filtered to the window being decided
so a headline published after the open cannot inform a decision taken before it.</p>

<h2 id="authority">Bounded authority</h2>
<div class="callout"><p><strong>Ballast cannot place a bet.</strong> Every order it is
structurally capable of emitting is opposite in sign to, and bounded in size by, a
spot position already held. There is no code path to a directional trade.</p></div>
<p>The model owns the judgment and nothing else - there is no size, side, price or
quantity field anywhere in its output contract, and a test asserts their absence.
Three gates stand between it and an order:</p>
<ul>
<li><strong>Schema</strong> - the answer parses into the contracted shape, or it is refused.</li>
<li><strong>Identity</strong> - a judgment about a different ticker is never accepted.</li>
<li><strong>Grounding</strong> - the quoted headline must actually appear in the
supplied sources. This is what stops a fabricated source reaching the book.</li>
</ul>
<p>The enforcer runs as a separate process holding the only write-scoped credential.
It never sees the model's reasoning; it checks arithmetic against a signed mandate -
a position exists, the order opposes it, the size is within the ratio, the symbol is
in the universe, the mandate has not expired, the night's caps are intact.
<strong>18 red-team tests</strong> drive hostile intents at it, each asserting the
specific rule that refused it.</p>

<h2 id="ledger">The ledger</h2>
<p>Every decision, including every refusal, is appended to a hash-chained, signed
ledger. Mutating, deleting, reordering or forging an entry breaks verification, and
tests cover each of those attacks.</p>
<p>A scheduled job writes it and commits it, so each decision is recorded
<strong>before its outcome is known</strong> and timestamped independently. The chain
proves nothing was edited; the commit history proves nothing was backfilled.</p>

<h2 id="settlement">Settlement</h2>
<p>At the next primary open every decision is graded against the
<strong>exact counterfactual</strong> - what the position would have done unhedged is
not modelled, it is observed on the same window.</p>
<ul>
<li><strong>Win rate</strong> is the share of hedges that reduced the move. A hedge is
symmetric, so a P&amp;L-direction win rate would be meaningless.</li>
<li><strong>Tail coverage</strong> is the share of the worst 1% / 5% / 10% of
position-nights that were hedged - the metric the product should be judged on.</li>
<li>A session is <strong>never settled partially</strong>. Marking it done while a
row is still ungradeable would strand that row permanently, so settlement waits for
the whole session.</li>
</ul>

<h2 id="research">Research findings</h2>
<p>All figures are produced by code in <code>research/</code> from public endpoints,
labelled <em>observed</em>, <em>estimated</em> or <em>targeted</em>.</p>
<div class="scroll"><table><thead><tr><th>Finding</th><th>Value</th></tr></thead><tbody>
<tr><td>rTokens live on spot / with a perp leg</td><td class="num">{F['rtokens_total']} / {F['rtokens_hedgeable']}</td></tr>
<tr><td>Median overnight variance removed</td><td class="num">{F['median_r2'] * 100:.1f}%</td></tr>
<tr><td>R² on top-decile move nights</td><td class="num">0.978–0.999</td></tr>
<tr><td>Median p95 tail reduction</td><td class="num">{F['median_tail_cut_pct']}%</td></tr>
<tr><td>Earnings-night variance ratio</td><td class="num">3.2×</td></tr>
<tr><td>Volatility-selector separation</td><td class="num">1.41×</td></tr>
<tr><td>Hedge cost / exit cost</td><td class="num">{F['hedge_cost_bp']} bp / {F['exit_cost_bp']:.0f} bp</td></tr>
<tr><td>Hourly history reachable per rToken</td><td class="num">2+ years</td></tr>
</tbody></table></div>
<p>The first policy replay is published as a <strong>negative result</strong>:
a volatility-led policy hedged 45% of nights, cost roughly 13% a year and turned a
1.11% return into −6.96%. Switching to calendar-led selection cut the hedge rate to
2.4% and the drag to 0.3 bp per position-night, with 15 of 16 hedges reducing the
move - but coverage of the worst nights remains the open problem.</p>

<h2 id="defects">Defects found</h2>
<p>Published rather than quietly corrected, because a project that reports only its
successes has told you nothing about its error rate.</p>
<ul>
<li><strong>DST</strong> - the US close was hardcoded at 20:00 UTC while four months
of sample were EST. Fixed; both transitions are pinned by test.</li>
<li><strong>Look-ahead</strong> - the first neutrality test selected nights by
<em>realised</em> move. Fixed; the invalid version survives behind a flag to document it.</li>
<li><strong>Hour-snapping</strong> - the 09:30 ET open does not fall on an hourly bar
boundary, so price lookups silently missed. Fixed.</li>
<li><strong>Broken metrics</strong> - an early "decision accuracy" compared move
against cost on every night, scoring nearly every unhedged night as an error. Replaced.</li>
</ul>

<h2 id="roadmap">Roadmap</h2>
<p>What is still open, why, and what it would take. Ordered by how much it would
change the product rather than by effort. What is <em>not</em> planned is listed too,
so an absence reads as a decision rather than an oversight.</p>

<div class="callout"><p>The <a href="#defects">defects</a> above are a different list
and not a backlog - every item on it is already fixed. It stays published because a
project that reports only its successes has told you nothing about its error rate.</p></div>

<h4>1 &middot; Does the reader close the tail-coverage gap?</h4>
<p><strong>The open question the whole thesis rests on.</strong> The calendar selector
covered 2 of the 6 worst position-nights in replay. Macro shocks, guidance, legal
rulings and product events drive the rest, and the reader exists to reach them - but
that has not been measured.</p>
<p>It cannot be measured retrospectively without look-ahead: judging a past night needs
the headlines as they stood <em>before</em> the open, and no free source serves a
point-in-time archive. So it accumulates forward.</p>
<ul>
<li><strong>Needs</strong> roughly 30 sessions of live reader decisions, then the
tail-coverage cohorts re-run split by who decided.</li>
<li><strong>Blocked by</strong> wall-clock time. A handful of sessions exist.</li>
<li><strong>Until then</strong> the site says coverage is incomplete rather than
implying otherwise.</li>
</ul>

<h4>2 &middot; Live execution through the Agentic Account</h4>
<p>Fills are simulated against observed prices with the real fee schedule, and the
ledger is exported in Bitget UTA order field names so it reads alongside a real log -
but <strong>no order reaches an exchange</strong>. The executor interface is already the
seam: a live implementation replaces one class and nothing upstream changes.</p>
<ul>
<li><strong>Needs</strong> OAuth credentials for a Bitget Agentic sub-account.</li>
<li><strong>Blocked by</strong> credentials, which are the operator's to issue.</li>
<li><strong>Risk if rushed</strong> - an untested live-order path is worse than an
honest simulated one.</li>
</ul>

<h4>3 &middot; Position-level reporting</h4>
<p>The replay measures a twelve-name equal-weight book, which is already diversified, so
its worst night is a market-wide move that hedging some names barely dents. The target
user holds one to ten positions. Position-level tail cohorts are computed but not yet
surfaced. <strong>Nothing blocks this</strong>; it is the next substantive feature.</p>

<h4>4 &middot; The rTokens with no perp leg</h4>
<p>Two thirds of the listed universe cannot be hedged at all. Ballast reports which, and
stops there. A correlated proxy with a tradeable leg could cover some of them, with the
residual basis risk reported honestly - but a proxy hedge is a different product with a
different error profile, and claiming one without measuring it is exactly what the
defects list exists to prevent.</p>

<h4>5 &middot; Maker execution</h4>
<p>Every cost assumes taker on both legs. Maker pricing would be roughly a third of that,
which materially widens the set of nights worth hedging. It is
<strong>deliberately not assumed</strong> until the fill rate in a 4am perp book has been
measured: an unfilled hedge is worse than an expensive one.</p>

<h4>6 &middot; Richer sources for the reader</h4>
<p>The reader sees news headlines. Earnings calls, filings and the macro calendar are
richer signals it does not read. The grounding gate already accepts any source, since it
only checks that a quote appears in what was supplied.</p>

<h4>Not planned</h4>
<ul>
<li><strong>Predicting direction.</strong> Earnings nights measured as not reliably
compensated; the product removes variance and makes no directional claim.</li>
<li><strong>A volatility-based selector.</strong> Measured at 1.41&times; separation on
compensated nights. The gate exists in the code and ships disabled; re-enabling it needs
new evidence, not a hunch.</li>
<li><strong>Real capital.</strong> Out of scope for this build.</li>
</ul>

<h2 id="verify">Reproduce it</h2>
<pre><b>git clone {REPO} &amp;&amp; cd ballast</b>
python3 -m unittest discover -s tests   <span class="dim"># full suite, no network, no key</span>
python3 research/hedge_study.py         <span class="dim"># the hedge measurements</span>
python3 research/gate1_selection.py     <span class="dim"># why volatility fails</span>
python3 research/gate1_calendar.py      <span class="dim"># why the calendar works</span>
python3 research/replay.py              <span class="dim"># the policy over history</span>
python3 research/costs_study.py         <span class="dim"># every fee and funding figure</span>
python3 research/facts_study.py         <span class="dim"># re-measure the universe counts</span></pre>

<h2 id="cli">CLI</h2>
<pre><b>python3 -m ballast.bootstrap</b>   build the paper position book
<b>python3 -m ballast.night</b>       decide, enforce, execute, record
<b>python3 -m ballast.morning</b>     settle against the counterfactual
<b>python3 -m ballast.report</b>      rebuild this site
<b>python3 -m ballast.export</b>      export the log in Bitget order schema
<b>python3 -m ballast.preflight</b>   check credentials without writing
<b>python3 -m ballast.universe</b>    list the hedgeable universe</pre>
<p><code>--dry-run</code> records decisions without fills. <code>--no-reader</code>
runs the deterministic calendar rule alone.</p>

<h2 id="env">Environment</h2>
<div class="scroll"><table><thead><tr><th>Variable</th><th>Effect if unset</th>
</tr></thead><tbody>
<tr><td><code>QWEN_API_KEY</code></td><td>the reader abstains, the calendar rule
decides, and the abstention is logged with its reason</td></tr>
<tr><td><code>BALLAST_SECRET</code></td><td>writing is <strong>refused</strong>;
set <code>BALLAST_DEV_SECRET=1</code> to accept an unverifiable key. Reading still
works and the page says "signatures NOT verified".</td></tr>
<tr><td><code>QWEN_BASE_URL</code></td><td>defaults to the hackathon endpoint</td></tr>
<tr><td><code>QWEN_MODEL</code></td><td>defaults to <code>qwen3.8-max</code></td></tr>
</tbody></table></div>
<p>Degradation is transparent by design: a night decided without the model is visibly
a night decided without the model.</p>

<h2 id="glossary">Glossary</h2>
<div class="scroll"><table><thead><tr><th>Term</th><th>Meaning</th></tr></thead><tbody>
<tr><td><strong>rToken</strong></td><td>A tokenized US equity trading 24/7 against
USDT - <code>RTSLAUSDT</code> tracks Tesla.</td></tr>
<tr><td><strong>Perp leg</strong></td><td>The matched stock perpetual, using the bare
ticker - <code>TSLAUSDT</code>. The hedge instrument.</td></tr>
<tr><td><strong>Overnight window</strong></td><td>A session's 16:00 ET close to the
next 09:30 ET open. Friday spans the weekend.</td></tr>
<tr><td><strong>Basis point (bp)</strong></td><td>One hundredth of a percent. The
hedge costs {F['hedge_cost_bp']} bp; a bad night can cost 1,000.</td></tr>
<tr><td><strong>Counterfactual</strong></td><td>What the position would have done
unhedged - observed, not estimated.</td></tr>
<tr><td><strong>Night Mandate</strong></td><td>The signed document bounding what may
be traded tonight. Expires at the open.</td></tr>
<tr><td><strong>Uncompensated variance</strong></td><td>Risk carrying no expected
return. The only kind worth paying to remove.</td></tr>
</tbody></table></div>
"""


def build() -> Path:
    toc = "".join(
        f'<div class="h">{group}</div>' +
        "".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in items)
        for group, items in SECTIONS)

    body = f"""<section class="bd bd-deep" style="border-bottom:1px solid var(--line)">
<div class="wrap center" style="padding:26px 0 6px">
<p class="eyebrow">Documentation</p>
<h1>How Ballast works,<br>and how to check it.</h1>
<p class="lede">The mechanism, the measurements behind it, where the model's
authority starts and stops - and what is deliberately not claimed.</p>
</div></section>
<div class="wrap"><div class="docs">
<aside class="toc">{toc}</aside>
<article class="prose">{BODY}</article>
</div></div>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page(
        "Ballast - documentation",
        "How Ballast hedges overnight risk in tokenized US stocks, and how to verify it.",
        "Docs", body))
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size:,} bytes)")
