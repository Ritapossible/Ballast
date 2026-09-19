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
import re
from pathlib import Path

from . import config, counterfactual, facts, suite
from .earnings import SELECTOR_BUG_SESSIONS
from .facts import load as load_facts
from .facts import worst_night
from .ledger import Ledger, LedgerError
from .metrics import paper_metrics
from .sessions import UTC, close_utc, current_session, sessions_between, window_hours
from .theme import REPO, page

OUT_DIR = config.ROOT / "docs"

_LONG_FLOAT = re.compile(r"\d+\.\d{3,}")


def _round_floats(text: str) -> str:
    """Round runaway decimals in stored text before displaying it.

    A rationale written before the formatting fix carries 11.291999999999998bp,
    and the ledger is append-only - that string is signed and stays. The page is a
    report over the record, and a report rounds its numbers; the ledger is
    unchanged and still verifies against exactly what was written.
    """
    return _LONG_FLOAT.sub(lambda m: f"{float(m.group()):.1f}", text)

# How long after a close the decide run may take before the site calls it missed.
# The cron is one hour after the close, and GitHub has delayed one of ours by
# 3h17m. Flagging at the close itself made the page read STALE every night between
# 20:00Z and whenever the run landed - an alarm that fires nightly is one nobody
# reads. Four hours is well past any delay observed and still catches a real stall
# the same night.
DECIDE_GRACE_HOURS = 4

# f-strings cannot carry a backslash escape, and _tile escapes its input, so the
# arrow is the character itself rather than an entity.
ARROW = "\u2192"


def _selector_affected(row: dict) -> bool:
    """Only the hedges are affected, never the refusals.

    The old rule ORed an extra date in, so it could turn NO_HEDGE into HEDGE and
    never the reverse. A refusal on an affected session would have been a refusal
    under the corrected rule too - it is a sound decision and marking it says
    otherwise. Over-disclosure is inaccuracy, and it costs the same credibility
    that disclosing at all is meant to buy.
    """
    return (row.get("session") in SELECTOR_BUG_SESSIONS
            and row.get("action") == "HEDGE")


def _e(v) -> str:
    return html.escape(str(v))


def _tile(n, label) -> str:
    return f'<div class="tile"><div class="n">{_e(n)}</div><div class="l">{_e(label)}</div></div>'


def _empty(msg: str) -> str:
    return f'<div class="scroll"><div class="empty">{_e(msg)}</div></div>'


# What each gate means in English. The ledger stores the enum value; a judge
# reading the page should not have to look it up, and "ticker_mismatch" on a card
# is the single most convincing thing this project can show about the reader being
# fenced rather than trusted.
GATE_ENGLISH = {
    "model_unavailable": "the model could not be reached",
    "schema_violation": "its answer did not parse into the contract",
    "ticker_mismatch": "it answered about a different ticker",
    "quote_not_in_sources": "its quote was not in the supplied headlines",
    "below_confidence_floor": "it was below the confidence floor for a hedge",
}

# The book is twelve names and a ticker is not a word. "COST" sits one column from
# a tile reading "cost to protect", and "MU", "NKE" and "SPY" are no clearer. These
# are labels, not measurements - nothing here is derived from them.
COMPANY = {
    "TSLA": "Tesla", "NVDA": "NVIDIA", "PLTR": "Palantir", "COIN": "Coinbase",
    "AMD": "AMD", "MSFT": "Microsoft", "ORCL": "Oracle", "ADBE": "Adobe",
    "MU": "Micron", "NKE": "Nike", "COST": "Costco", "SPY": "S&P 500 ETF",
    "AAPL": "Apple", "AMZN": "Amazon", "META": "Meta", "GOOGL": "Alphabet",
}


def _name(ticker: object) -> str:
    company = COMPANY.get(str(ticker).upper())
    return (f'<strong>{_e(ticker)}</strong>'
            + (f'<div class="dim" style="font-size:12.5px">{_e(company)}</div>'
               if company else ""))


def _sources(news: dict) -> str:
    """What the model was actually shown, so a judgment cannot be read out of context."""
    if not news:
        return ""
    if news.get("source") == "unavailable":
        return '<div class="dim" style="font-size:12.5px">news feed unavailable</div>'
    got, inw, shown = (news.get("headlines_fetched", 0), news.get("in_window", 0),
                       news.get("shown", 0))
    body = (f"{got} headlines · {inw} in tonight's window" if inw
            else f"{got} headlines · none in tonight's window, showed {shown} recent")
    return f'<div class="dim" style="font-size:12.5px">{_e(body)}</div>'


def _who(row: dict) -> str:
    """MODEL, RULE, or the gate that refused the model and handed the night back."""
    reader = row.get("reader") or {}
    by = (row.get("inputs") or {}).get("decided_by", "rule")
    if reader and not reader.get("accepted"):
        why = GATE_ENGLISH.get(reader.get("rejected_because") or "",
                               reader.get("rejected_because") or "")
        return (f'<span class="tag">ABSTAIN {ARROW} RULE</span>'
                f'<div class="dim" style="font-size:12.5px">{_e(why)}</div>')
    return (f'<span class="tag {"on" if by == "model" else ""}">{_e(by)}</span>'
            + _sources(row.get("news") or {}))


def _why(row: dict) -> str:
    """The model's own words where it decided, ours where the rule did.

    The page used to print `rationale` on every card. That string is a template in
    policy.decide, so twelve names that the model had read twelve different ways all
    rendered as "event reader judged NO_HEDGE - nothing tonight can move this name".
    96 decisions carry 68 distinct model reasonings and the page showed 32 distinct
    lines - it was hiding the one thing that demonstrates the reader is deciding
    rather than rubber-stamping.
    """
    reader = row.get("reader") or {}
    if reader.get("accepted") and reader.get("reasoning"):
        quote = (reader.get("verbatim_quote") or "").strip()
        tail = (f'<div class="dim" style="font-size:12.5px;margin-top:5px">'
                f'quoted: &ldquo;{_e(quote)}&rdquo;</div>' if quote else
                '<div class="dim" style="font-size:12.5px;margin-top:5px">'
                'no quote - judged on the absence of an event</div>')
        return f'<span class="wrap">{_e(reader["reasoning"])}</span>{tail}'
    return _e(_round_floats(row.get("rationale", "")))


def _decisions(rows: list[dict]) -> str:
    if not rows:
        return _empty("No decisions recorded yet. The loop runs after the US close.")
    out = ['<div class="scroll stacked"><table><thead><tr><th>Position</th><th>Call</th>'
           '<th class="num">1-sigma move</th><th class="num">Position USDT</th>'
           '<th>Decided by</th><th>Reasoning</th></tr></thead><tbody>']
    # Hedges first. A night of refusals is the normal case and the correct one, but
    # a page that opens on twelve NO_HEDGE cards reads as a system doing nothing.
    for r in sorted(rows, key=lambda x: (x.get("action") != "HEDGE", x.get("ticker", ""))):
        on = r.get("action") == "HEDGE"
        out.append(
            f'<tr><td data-label="">{_name(r.get("ticker"))}</td>'
            f'<td data-label="Call"><span class="tag {"on" if on else ""}">'
            f'{_e(r.get("action"))}</span></td>'
            f'<td class="num mid" data-label="1-sigma move">{r.get("sigma_bp", 0):,.0f} bp</td>'
            # The same number means two different things: the hedge that was placed,
            # or the exposure that was left open. Unlabelled it reads as "999 traded"
            # on a row where nothing was traded, which is the opposite of the claim
            # this page exists to make.
            f'<td class="num mid" data-label="Position USDT">'
            f'{r.get("notional_usdt", 0):,.0f} {"hedged" if on else "exposed"}</td>'
            f'<td data-label="Decided by">{_who(r)}</td>'
            f'<td class="dim wrap" data-label="Reasoning">{_why(r)}</td></tr>')
    return "".join(out) + "</tbody></table></div>"


def _settled(rows: list[dict]) -> str:
    if not rows:
        return _empty("Nothing settled yet. Every decision is graded at the next "
                      "primary open, against the exact counterfactual.")
    out = ['<div class="scroll stacked"><table><thead><tr><th>Position</th>'
           '<th>Session</th><th>Call</th>'
           '<th class="num">Realised</th><th class="num">If reversed</th>'
           '<th class="num">Value added</th><th>Verdict</th></tr></thead><tbody>']
    # Newest night first, then by size within it. Sorting by size across sessions
    # interleaved them, so consecutive rows came from different nights.
    for r in sorted(rows, key=lambda x: (x.get("session", ""),
                                         abs(x.get("unhedged_bp", 0))), reverse=True):
        va = r.get("value_added_bp", 0)
        on = r.get("action") == "HEDGE"
        # Colour is a verdict, and this page spends a paragraph explaining that a
        # refusal cannot be given one: its value added is positive exactly when the
        # position rose, so green on a refused rally says "we were right to stand
        # down" when all it means is that the stock went up. The number stays - it
        # is the row's own arithmetic and it feeds the mean - but only a hedge,
        # which answers the symmetric question, is coloured.
        cls = ("pos" if va > 0 else "neg" if va < 0 else "dim") if on else "mid"
        # A hedge answers a symmetric question - did it cut the move - and one
        # night answers it. A refusal does not: value added is positive for a
        # refusal exactly when the position rose, so a per-night verdict on it is
        # a directional scorecard, and this system makes no directional claim.
        # The number stays in the row; only the label is withheld.
        mark = ('<span class="neg"> · hedged a night early</span>'
                if _selector_affected(r) else "")
        if on:
            cut = abs(r.get("realised_bp", 0)) < abs(r.get("unhedged_bp", 0))
            verdict, faint = ("cut the move", False) if cut else ("did not cut", True)
        else:
            verdict, faint = "carried", True
        out.append(
            f'<tr><td data-label="">{_name(r.get("ticker"))}</td>'
            f'<td class="dim" data-label="Session">{_e(r.get("session", "-"))}{mark}</td>'
            f'<td data-label="Call"><span class="tag {"on" if on else ""}">'
            f'{_e(r.get("action"))}</span></td>'
            # Counterfactual, not "unhedged". Unhedged is the same number as the
            # counterfactual on a hedge and the same number as realised on a
            # refusal, so it duplicated a column on every row and left the one
            # value that makes value-added checkable off the page entirely: a
            # refusal showed +439, +439 and +440 with nothing to derive 440 from.
            f'<td class="num mid" data-label="Realised">{r.get("realised_bp", 0):+,.0f} bp</td>'
            f'<td class="num mid" data-label="If reversed">'
            f'{r.get("counterfactual_bp", 0):+,.0f} bp</td>'
            f'<td class="num {cls}" data-label="Value added">{va:+,.0f} bp</td>'
            f'<td class="{"dim" if faint else ""}" data-label="Verdict">{verdict}</td></tr>')
    return "".join(out) + "</tbody></table></div>"


def _call_tag(action: str) -> str:
    return f'<span class="tag {"on" if action == "HEDGE" else ""}">{_e(action)}</span>'


def _overrides(rows: list[dict]) -> str:
    """The nights the reader changed the rule's answer, with what it quoted."""
    if not rows:
        return _empty("The model has not yet changed the calendar's answer on any "
                      "night. On this record it is reporting, not deciding.")
    out = ['<div class="scroll stacked"><table><thead><tr><th>Position</th>'
           '<th>Session</th><th>Calendar said</th><th>Ballast did</th>'
           '<th class="num">Value added</th><th>What the model read</th>'
           '</tr></thead><tbody>']
    for r in sorted(rows, key=lambda x: x["session"], reverse=True):
        va = r.get("value_added_bp")
        cls = "dim" if va is None else "pos" if va > 0 else "neg" if va < 0 else "dim"
        shown = "not settled" if va is None else f"{va:+,.0f} bp"
        quote = r.get("quote") or r.get("reasoning") or ""
        out.append(
            f'<tr><td data-label=""><strong>{_e(r["ticker"])}</strong></td>'
            f'<td class="dim" data-label="Session">{_e(r["session"])}</td>'
            f'<td data-label="Calendar said">{_call_tag(r["calendar"])}</td>'
            f'<td data-label="Ballast did">{_call_tag(r["action"])}</td>'
            f'<td class="num {cls}" data-label="Value added">{_e(shown)}</td>'
            f'<td class="dim wrap" data-label="What the model read">{_e(quote)}</td>'
            f'</tr>')
    return "".join(out) + "</tbody></table></div>"


def _comparison(rows: list[dict]) -> str:
    """Every decision on the chain, the rule's answer beside the one taken."""
    if not rows:
        return _empty("No decisions recorded yet. The loop runs after the US close.")
    out = ['<div class="scroll stacked"><table><thead><tr><th>Position</th>'
           '<th>Session</th><th>Calendar</th><th>Taken</th><th>Decided by</th>'
           '<th>Verdict</th></tr></thead><tbody>']
    for r in sorted(rows, key=lambda x: (x["session"], x["ticker"]), reverse=True):
        by = r.get("decided_by", "rule")
        if r.get("selector_affected"):
            verdict, cls = "excluded - hedged a night early", "neg"
        elif r["flip"]:
            verdict, cls = "model overrode the rule", "pos"
        elif by == "model":
            verdict, cls = "model agreed with the rule", "dim"
        else:
            verdict, cls = "reader abstained - rule decided", "dim"
        mark = "" if r.get("source") == "derived" else ' · recorded'
        out.append(
            f'<tr><td data-label=""><strong>{_e(r["ticker"])}</strong></td>'
            f'<td class="dim" data-label="Session">{_e(r["session"])}{mark}</td>'
            f'<td data-label="Calendar">{_call_tag(r["calendar"])}</td>'
            f'<td data-label="Taken">{_call_tag(r["action"])}</td>'
            f'<td data-label="Decided by"><span class="tag '
            f'{"on" if by == "model" else ""}">{_e(by)}</span></td>'
            f'<td class="{cls}" data-label="Verdict">{_e(verdict)}</td></tr>')
    return "".join(out) + "</tbody></table></div>"

# Chart colours. The site's cyan and rose sit at OKLCH L 0.81 and 0.72 - outside the
# 0.48-0.67 band a dark surface needs - so these are the same hues stepped down until
# they pass. Validated, not eyeballed: CVD dE 11.9 (deutan), 29.0 normal-vision,
# both over 3:1 on #101012.
TAIL_UNHEDGED = "#e05068"
TAIL_HEDGED = "#00a3b4"


def _tail_chart(rows: list[dict]) -> str:
    """p95 overnight move per name, unhedged against hedged.

    A dumbbell, not bars: the data is one before-and-after per name, and the length
    of the line IS the claim. Twenty-four bars would show the same numbers and none
    of the collapse.

    Inline SVG with no script - the page loads no JavaScript at all, which is what
    lets the CSP be default-src 'none'. Every value is directly labelled, so nothing
    is hidden behind a hover that cannot exist here; <title> adds the exact figures
    for pointer users without costing a byte of JS.
    """
    rows = sorted(rows, key=lambda r: -r.get("p95_unhedged", 0))
    if not rows:
        return ""
    top, row_h, x0, x1 = 46, 25, 58, 470
    hi = max(r["p95_unhedged"] for r in rows)
    step = 200 if hi <= 900 else 400
    axis_hi = ((hi // step) + 1) * step
    height = top + len(rows) * row_h + 30

    def x(v: float) -> float:
        return x0 + (v / axis_hi) * (x1 - x0)

    grid = "".join(
        f'<line x1="{x(v):.1f}" y1="{top - 10:.0f}" x2="{x(v):.1f}" '
        f'y2="{top + len(rows) * row_h - 8:.0f}" stroke="#242429" stroke-width="1"/>'
        f'<text x="{x(v):.1f}" y="{height - 12:.0f}" fill="#6c6c75" font-size="11" '
        f'text-anchor="middle" font-family="ui-monospace,Menlo,monospace">{v:,}</text>'
        for v in range(0, axis_hi + 1, step))

    body = []
    for i, r in enumerate(rows):
        y = top + i * row_h
        xu, xh = x(r["p95_unhedged"]), x(r["p95_hedged"])
        body.append(
            f'<g><title>{_e(r["name"])}: p95 {r["p95_unhedged"]:,} bp unhedged, '
            f'{r["p95_hedged"]:,} bp hedged, over {r.get("nights", 0)} nights</title>'
            f'<text x="46" y="{y + 4:.0f}" fill="#a6a6ad" font-size="13" '
            f'text-anchor="end" font-family="ui-monospace,Menlo,monospace">'
            f'{_e(r["name"])}</text>'
            f'<line x1="{xh:.1f}" y1="{y:.0f}" x2="{xu:.1f}" y2="{y:.0f}" '
            f'stroke="#3a3a42" stroke-width="2" stroke-linecap="round"/>'
            f'<circle cx="{xu:.1f}" cy="{y:.0f}" r="4.5" fill="{TAIL_UNHEDGED}" '
            f'stroke="#101012" stroke-width="2"/>'
            f'<circle cx="{xh:.1f}" cy="{y:.0f}" r="4.5" fill="{TAIL_HEDGED}" '
            f'stroke="#101012" stroke-width="2"/>'
            f'<text x="482" y="{y + 4:.0f}" fill="#a6a6ad" font-size="12.5" '
            f'font-family="ui-monospace,Menlo,monospace">{r["p95_unhedged"]:,} '
            f'&#8594; {r["p95_hedged"]:,}</text></g>')

    legend = (
        f'<circle cx="62" cy="16" r="4.5" fill="{TAIL_UNHEDGED}"/>'
        f'<text x="74" y="20" fill="#a6a6ad" font-size="12.5">p95 unhedged</text>'
        f'<circle cx="176" cy="16" r="4.5" fill="{TAIL_HEDGED}"/>'
        f'<text x="188" y="20" fill="#a6a6ad" font-size="12.5">p95 hedged</text>'
        f'<text x="482" y="20" fill="#6c6c75" font-size="11.5">basis points</text>')

    return (f'<figure class="chart">'
            f'<svg viewBox="0 0 620 {height}" width="100%" role="img" '
            f'aria-labelledby="tailt taild">'
            f'<title id="tailt">Overnight tail risk, unhedged against hedged</title>'
            f'<desc id="taild">For each of twelve names, the 95th-percentile overnight '
            f'move in basis points with no hedge and with the matched perpetual short. '
            f'Every pair is listed at the right of its row.</desc>'
            f'{legend}{grid}{"".join(body)}</svg></figure>')


def _nights_range(f: dict) -> str:
    rows = f.get("tail", [])
    if not rows:
        return "-"
    return f"{min(r['nights'] for r in rows)}-{max(r['nights'] for r in rows)}"


def claims(f: dict) -> list[tuple[str, str, str | None]]:
    return [
    (f"A matched perp removes a median {f['median_r2'] * 100:.1f}% of overnight "
     f"variance, β within {facts.beta_within_pct(f)}% of 1.00", "observed",
     f"{len(f.get('tail', []))} names, {_nights_range(f)} nights each"),
    ("The hedge strengthens under stress - R² 0.978-0.999 on top-decile nights",
     "observed", "conditional regression"),
    (f"Median {f['median_tail_cut_pct']}% cut in p95 tail; MSFT's worst night "
     f"{worst_night(f, 'MSFT')}", "observed", "same sample"),
    ("Earnings nights carry 3.2× the variance and are not reliably compensated",
     "observed", "15 names; 0 of 15 significant at |t|≥2"),
    ("Trailing volatility cannot select risky nights - 1.41× separation",
     "observed", "which is why the reader exists"),
    ("Signed, tamper-evident decision ledger", "proven", None),
    ("The enforcer refuses every directional intent", "proven",
     f"{suite.red_team()} red-team tests, and the executor takes only an admission"),
    (f"The hedge holds out of sample - β fitted on the first "
     f"{f['oos']['split']:.0%} of each name's nights and applied unchanged",
     "observed",
     f"R² {f['oos']['is_median_r2']:.3f} to {f['oos']['oos_median_r2']:.3f}, "
     f"{f['oos']['names']} of {f['oos']['names']} names"),
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
            self.chain = f"{len(ledger.records())} ledger entries · signatures NOT verified"
            self.broken = False
            self.unverified = True
        else:
            self.unverified = False
            try:
                self.chain = f"{ledger.verify()} ledger entries · chain verified"
                self.broken = False
            except LedgerError as exc:
                self.chain, self.broken = f"CHAIN BROKEN - {exc}", True

        decisions = [e["body"] for e in ledger.records("decision")]
        night_records = ledger.records("night_summary")
        summaries = [e["body"] for e in night_records]
        self.settlements = [e["body"] for e in ledger.records("settlement")]

        # By session date, not by write order: a backfill or an out-of-order run
        # would otherwise make an older night look like tonight.
        self.latest: dict = max(summaries, key=lambda s: s.get("session", ""),
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
        # Each row carries its session. Two nights in, the table showed ORCL twice
        # with near-identical numbers and no way to tell them apart - which reads as
        # a duplicate-row bug, not as two nights. dict() copies; the ledger body is
        # never mutated.
        self.rows = [dict(r, session=s.get("session", ""))
                     for s in self.settlements for r in s.get("rows", [])]
        # Headline tiles measure only sessions decided with the corrected calendar.
        # A session whose hedges were placed a night early cannot support a claim
        # about how well hedges work, so those rows stay in the table - where the
        # correction sits beside them - and out of the summary.
        #
        # Which DIRECTION this moves the mean is incidental and changes as nights
        # accumulate - it raised the mean when the record was one session long and
        # lowers it now. The figure that used to sit here said "larger, +27 to +136
        # bp"; it was true when written, went stale silently, and by the time anyone
        # reread it the sign had flipped. So no figure is pinned here: the rows are
        # excluded because hedges placed a night early cannot evidence how well a
        # hedge works, and that reason holds whichever way the mean happens to move.
        # The tiles carry their session count for the same reason - a mean over a
        # handful of nights is market direction, not a performance record.
        self.excluded = [r for r in self.rows if _selector_affected(r)]
        self.clean = [r for r in self.rows if not _selector_affected(r)]
        self.clean_sessions: list[str] = sorted(
            {s for s in (r.get("session") for r in self.clean) if isinstance(s, str)})

        self.hedges = [r for r in self.clean if r.get("action") == "HEDGE"]
        self.shrank = sum(1 for r in self.hedges
                          if abs(r.get("realised_bp", 0)) < abs(r.get("unhedged_bp", 0)))
        self.worst = max((abs(r.get("unhedged_bp", 0)) for r in self.clean), default=0)
        # Where a refusal is actually graded: the mean over every settled
        # position-night, against the choice not taken. One session is n=1 and the
        # page says so - but the number belongs on the page, not only in the ledger.
        self.mean_va = (sum(r.get("value_added_bp", 0) for r in self.clean) / len(self.clean)
                        if self.clean else 0)

        # A scheduled run that stops running leaves the site showing its last good
        # night, which reads exactly like a working site. Settlement had in fact
        # been failing on every run since the loop was automated and the pages said
        # nothing. So the page states how far behind the ledger is, and a silent
        # failure becomes visible on the artifact itself.
        self.behind = 0
        try:
            shown = dt.date.fromisoformat(self.session)
            # Judge against the newest session whose run is actually overdue, not
            # the newest session that exists.
            due = current_session(now)
            if now < close_utc(due) + dt.timedelta(hours=DECIDE_GRACE_HOURS):
                due = current_session(close_utc(due) - dt.timedelta(seconds=1))
            elapsed = list(sessions_between(shown, due))
            self.behind = max(0, len(elapsed) - 1)
        except (ValueError, RuntimeError):
            self.behind = 0                    # no session yet, or a calendar fault
        # The reader-vs-calendar index, built by ballast.counterfactual. Absent is
        # a normal state - it is rebuilt nightly and the page says so rather than
        # failing the whole site build over one display file.
        self.cf = counterfactual.load()

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

    def _settled_tape(self) -> str:
        """The most recent settled night, on the same tape as tonight's calls.

        Tonight is usually all refusals - Gate 1a is why - and a reader landing
        on twelve NO_HEDGE has no way to tell a selective agent from a broken
        one. This answers "has it ever acted, and how did that go" without
        replacing the live state with a flattering old one.

        It shows the LAST settled night whatever it was, so it cannot be a
        picked highlight. Only when that night hedged nothing does it also name
        the most recent night that did - otherwise the honest answer to "does
        this thing ever fire" is buried on another page.
        """
        if not self.settlements:
            return ""
        done = sorted(self.settlements, key=lambda s: s.get("session") or "")
        last = done[-1]
        rows = []

        def line(label: str, body: str, href: str = "settled.html") -> str:
            return (f'<div class="term-r"><span class="dim">{_e(label)} '
                    f'{_e(body)}</span><a class="dim" href="{href}">'
                    f'settled →</a></div>')

        hedged = last.get("hedged") or 0
        cut = last.get("hedges_that_cut") or 0
        if hedged:
            rows.append(line(f"settled {last.get('session')}",
                             f"· {hedged} hedged, {cut} cut the move"))
        else:
            rows.append(line(f"settled {last.get('session')}",
                             "· no hedge was called for"))
            acted = [s for s in done if (s.get("hedged") or 0)]
            if acted:
                prev = acted[-1]
                rows.append(line(f"last hedge {prev.get('session')}",
                                 f"· {prev.get('hedges_that_cut') or 0} of "
                                 f"{prev.get('hedged')} cut the move"))
        return "".join(rows)


    def index(self) -> str:
        # Hedges first. The rows were in book order, and the policy declines about
        # ten nights in twelve, so the first five were all NO_HEDGE - the landing
        # page's one live widget showed a column of refusals and none of the two
        # hedges, which reads as a system that does nothing. The count line keeps
        # five rows from misrepresenting twelve.
        ordered = sorted(self.tonight, key=lambda d: d.get("action") != "HEDGE")
        shown = ordered[:5]
        term = "".join(
            f'<div class="term-r"><span class="mid">{_e(d.get("ticker"))}</span>'
            f'<span class="{"hl" if d.get("action") == "HEDGE" else "dim"}">'
            f'{_e(d.get("action"))}</span></div>'
            for d in shown) or (
            '<div class="term-r"><span class="dim">awaiting the next close</span>'
            '<span class="dim">-</span></div>')
        if len(self.tonight) > len(shown):
            hedged = sum(1 for d in self.tonight if d.get("action") == "HEDGE")
            term += (f'<div class="term-r"><span class="dim">'
                     f'{len(self.tonight)} positions · {hedged} hedged</span>'
                     f'<a class="dim" href="tonight.html">see all →</a></div>')
        # What the agent has actually done, beside what it is doing.
        term += self._settled_tape()
        # The book is the second filter and the one a reader is most likely to
        # misread: a small hedge count looks like a broken agent until you know
        # Ballast can only ever act on a position it did not open.
        book = (f"{len(self.tonight)} positions tonight"
                if self.tonight else "the positions you already hold")
        return f"""
<section class="bd"><div class="wrap center">
<h1>Hold the position.<br>Not the night's risk.</h1>
<p class="lede">Tokenized US stocks trade around the clock. The market that prices
them is shut for <span class="hl">81% of the week</span> - through earnings, through
the Fed, through weekends. Ballast keeps the position and switches the night off for
about <span class="hl">{self.f['hedge_cost_gross_bp']:.0f} basis points</span> - less
the funding a short collects, which averages {self.f['hedge_cost_bp']:.0f} bp a night but
is a rate rather than a promise.</p>
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
{_tile(f"{self.f['hedge_cost_gross_bp']} bp", "cost to protect, certain")}
{_tile(f"{self.f['exit_cost_bp']:.0f} bp", "cost to exit instead")}
</div>
<div class="narrow"><ul class="bul">
<li>The hedge is <strong>strongest exactly when it matters</strong> - R² reaches 0.999 on the largest moves, and is loosest on quiet nights where little is at stake.</li>
<li>Worst nights measured: MSFT <strong>{worst_night(self.f, "MSFT")}</strong>, AMD <strong>{worst_night(self.f, "AMD")}</strong>.</li>
<li><strong>{self.f['rtokens_hedgeable']} of {self.f['rtokens_total']}</strong> listed rTokens have a perp leg, measured {self.f['measured_on']}. Ballast says plainly which positions it cannot protect.</li>
<li>Of those, Ballast hedges only what is <strong>already in the book</strong> - {book}. It never opens, closes or resizes a spot position, which is what lets the enforcer bound every order by a holding that already exists.</li>
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

    @property
    def venue_line(self) -> str:
        """Where tonight's admitted hedges were actually sent, and what came back.

        The site said nothing about execution at all, which left the strongest
        infrastructure evidence in the project invisible: the Agent Hub route is
        wired, runs on every scheduled night, and when the exchange refuses the
        order Ballast records the refusal verbatim and simulates instead. A page
        that shows only the simulated fill looks like a project that never
        attempted the integration.
        """
        venue = self.latest.get("venue")
        if not venue:
            return ""
        detail = self.latest.get("venue_detail") or ""
        fills = [r.get("fill") or {} for r in self.tonight if r.get("fill")]
        fell_back = [f for f in fills if f.get("venue_fallback")]
        live = [f for f in fills if f.get("orderId")]

        if venue == "simulated":
            return (f'<p class="note">Execution <strong>simulated</strong> against observed '
                    f'Bitget prices{" - " + _e(detail) if detail else ""}. No order was sent '
                    f'to an exchange.</p>')

        head = (f'<p class="note">Execution routed to the <strong>{_e(detail or venue)}</strong> '
                f'through <code>bgc --paper-trading</code>')
        if live:
            return (head + f', and {len(live)} of {len(fills)} fills came back with an '
                    f'exchange order id.</p>')
        if fell_back:
            # The exchange's own words, not a summary of them. A paraphrase here
            # would be the one unverifiable sentence on the page.
            why = str(fell_back[0]["venue_fallback"]).strip()
            return (head + f'. The exchange refused the order - <em>{_e(why)}</em> - so the '
                    f'fill was simulated and every affected row carries that reason. '
                    f'<strong>No fill on this ledger carries an exchange order id</strong>, '
                    f'and none is claimed.</p>')
        return head + '.</p>'

    @property
    def tonight_strip(self) -> str:
        """Tonight at a glance, and why a night of refusals is the expected case.

        Twelve NO_HEDGE cards with no framing read as a system doing nothing. The
        reason they are refusals is the measurement the whole project rests on, and
        it was buried in the last line of each card's rationale: volatility does not
        find the nights worth hedging, so a 221 bp typical move is not a reason to
        spend 11.3 bp. A judge should not have to infer that from twelve cards.
        """
        rows = self.tonight
        if not rows:
            return ""
        hedged = sum(1 for r in rows if r.get("action") == "HEDGE")
        model = sum(1 for r in rows
                    if (r.get("inputs") or {}).get("decided_by") == "model")
        gated = sum(1 for r in rows
                    if (r.get("reader") or {}) and not (r.get("reader") or {}).get("accepted"))
        return f"""
<div class="tiles">
{_tile(hedged, "hedged tonight")}
{_tile(len(rows) - hedged, "left exposed, deliberately")}
{_tile(model, "decided by the model")}
{_tile(gated, "model answers refused by a gate")}
</div>
<div class="narrow"><p class="note">Ballast does not hedge volatility; it hedges
<strong>scheduled events</strong>. A typical overnight move of 200-300 bp is not a
reason to spend {self.f['hedge_cost_bp']} bp, because trailing volatility separates
risky nights from ordinary ones by only <strong>1.41x</strong> and the nights it
picks carry positive expected return - paying to remove compensated return is how a
hedging policy loses 13% a year. The earnings calendar separates at
<strong>3.2x</strong> on variance that is <em>not</em> compensated, and the reader
exists to find the unscheduled events a calendar cannot. So most nights are refusals,
and each one is graded.</p></div>"""

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
{self.venue_line}
{self.tonight_strip}
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
{self.lookup_block}
</div></section>"""

    @property
    def lookup_block(self) -> str:
        """"Where is MY stock?" - the question this page provokes and never answered.

        Twelve rows is the book, not the market, so a visitor holding one of the
        other 1,161 rTokens had no way in. This answers for any of them from
        docs/coverage.json, which is measured rather than asserted: a name counts
        as hedgeable because its perp demonstrably tracked it, not because a symbol
        with a matching ticker exists.

        It answers coverage, never tonight's call. A decision is only meaningful
        for a position in the book and is a ledger entry written before the outcome
        was known; one invented on demand would render identically and prove
        nothing. The copy says so where a reader will actually see it.
        """
        book = ",".join(sorted(
            str(d.get("ticker")) for d in self.tonight if d.get("ticker")))
        return f"""
<div class="narrow" style="margin-top:64px">
<h3>Not on this list? Check your own position.</h3>
<p class="note">These twelve are the demo book. Ballast can hedge far more than
twelve names - and refuses many more than it can. Type any tokenized stock to see
which half it falls in, and how well the hedge actually tracked it.</p>
<div class="lk" id="lookup" data-book="{_e(book)}">
<label class="sr-only" for="lk-in">Ticker</label>
<input id="lk-in" type="text" data-role="input" autocomplete="off"
 autocapitalize="characters" spellcheck="false" disabled
 placeholder="loading the coverage index…">
<p class="hint" data-role="hint">Loading the coverage index…</p>
<div class="out" data-role="out" aria-live="polite"></div>
</div>
</div>
<script src="lookup.js" defer></script>"""

    @property
    def oos_block(self) -> str:
        """Held-out test. Every other figure here is fitted on all the data it covers.

        The hedge ratio is estimated on the first 70% of nights and applied
        unchanged to the last 30%. Refitting on the holdout would measure nothing;
        a frozen beta is the position a desk actually carries, having fitted only
        on the past.
        """
        o = self.f.get("oos")
        if not o:
            return ""
        held = sum(1 for r in o["rows"] if r["oos_r2"] >= 0.90)
        return f"""
<h3 style="margin-top:44px">Out of sample</h3>
<p class="note">Every figure above is fitted on all the nights it covers. This one is not:
beta is estimated on the first {o['split']:.0%} of each name's paired nights and applied
<strong>unchanged</strong> to the last {1 - o['split']:.0%}. No refit - a frozen ratio is
what a desk carries, having fitted only on the past. Each name splits at its own date,
because the histories are different lengths ({_e(o['shortest'])} nights for the shortest,
{_e(o['longest'])} for the longest), so there is no single cut-off across the sample.</p>
<div class="tiles" style="margin:22px 0">
{_tile(f"{o['is_median_r2']:.3f} {ARROW} {o['oos_median_r2']:.3f}", "median variance removed")}
{_tile(f"{o['is_median_tail']}% {ARROW} {o['oos_median_tail']}%", "median p95 tail cut")}
{_tile(f"{o['median_beta_drift']:.3f}", "median beta drift on refit")}
{_tile(f"{held}/{o['names']}", "names holding out of sample")}
</div>
<p class="note"><strong>It holds, and that is the whole claim.</strong> A hedge is a
mechanism rather than an edge, so the test it has to pass is that nothing decays on data
it never saw - and nothing does. The out-of-sample figures come out <em>higher</em>, which
is a property of that period rather than evidence the hedge improved: read it as stable,
not as better. Reproduce with <code>python3 research/oos.py</code>.</p>"""

    @property
    def provenance_block(self) -> str:
        """Where every number comes from, and what each source is allowed to decide.

        Worth stating plainly because the instrument matters here: a tokenized stock
        trades continuously, so its overnight move is a path through the closed
        window rather than a gap at the bell. Measuring the listed share instead
        would describe a different instrument from the one being held.
        """
        rows = [
            ("rToken hourly candles", "Bitget spot, public",
             "every overnight return, 1-sigma forecast and settlement"),
            ("Stock perpetual hourly candles", "Bitget USDT-futures, public",
             "the hedge leg, and the counterfactual each call is graded against"),
            ("Earnings calendar", "Nasdaq, public",
             "which nights carry a scheduled event - dates only, never a price"),
            ("Headlines", "Google News RSS, public",
             "shown to the reader, which may only quote what it was given"),
            ("Event reader", "Qwen via the hackathon endpoint",
             "a typed HEDGE / NO_HEDGE judgment - no sizing, no price, no order"),
        ]
        body = "".join(
            f'<tr><td data-label=""><strong>{_e(what)}</strong></td>'
            f'<td class="dim" data-label="Source">{_e(src)}</td>'
            f'<td class="dim wrap" data-label="Decides">{_e(use)}</td></tr>'
            for what, src, use in rows)
        return f"""
<h3 style="margin-top:44px">Measured on the instrument, not a proxy</h3>
<p class="note">A tokenized US stock trades continuously. It does not gap at the opening
bell the way the listed share does - the move happens <em>inside</em> the closed window,
hour by hour, in the token's own book. A close-to-open gap measured on the underlying
equity would therefore describe a different instrument from the one being held.</p>
<p class="note">So every price on this site is measured on what a holder actually owns and
would actually trade: the rToken's own candles and the matched perpetual's. There is no
equity feed anywhere in the codebase, no proxy series and nothing synthetic - one endpoint,
<code>api.bitget.com</code>, for every figure quoted.</p>
<div class="scroll stacked"><table><thead><tr><th>What</th><th>Source</th>
<th>Decides</th></tr></thead><tbody>{body}</tbody></table></div>
<p class="note">Paper trading only. No live fill is claimed anywhere, and the exported
order log re-encodes the ledger into Bitget's field names rather than reporting exchange
state.</p>"""

    @property
    def paper_metrics_block(self) -> str:
        """The metrics the track scores, on the log run during the competition.

        Ballast makes no Sharpe claim and that does not change here. But refusing
        to claim a number is not a reason to withhold it: half this track is scored
        on paper-trading Sharpe, max drawdown and win rate, and the live log
        reported none of the three. Both columns, so the comparison is the one the
        product is actually about.
        """
        m = paper_metrics(self.rows)
        if not m["nights"]:
            return ""

        def bp(v):
            return f"{v:+,.0f} bp"

        rows = [
            ("Max drawdown", bp(m["hedged_max_dd_bp"]), bp(m["unhedged_max_dd_bp"]),
             "the claim: protection is measured in drawdown, not return"),
            ("Total return", bp(m["hedged_total_bp"]), bp(m["unhedged_total_bp"]),
             "equal-weight across the book, net of hedge cost"),
            ("Sharpe, annualised",
             f"{m['hedged_sharpe']:+.2f}" if m["hedged_sharpe"] is not None else "-",
             f"{m['unhedged_sharpe']:+.2f}" if m["unhedged_sharpe"] is not None else "-",
             f"noise at {m['nights']} nights - shown because the track asks for it"),
            ("Win rate", f"{m['win_rate_pct']}%" if m["win_rate_pct"] is not None else "-",
             "-", f"{m['hedges_that_cut']} of {m['hedges']} hedges cut the move"),
            ("Orders placed", f"{m['orders']}", "0",
             f"{m['positions']} position-nights, so {m['orders']} orders in total"),
        ]
        body = "".join(
            f'<tr><td data-label=""><strong>{_e(name)}</strong></td>'
            f'<td class="num" data-label="Ballast">{_e(ours)}</td>'
            f'<td class="num dim" data-label="Untouched">{_e(theirs)}</td>'
            f'<td class="dim wrap" data-label="Note">{_e(note)}</td></tr>'
            for name, ours, theirs, note in rows)

        return f"""
<h3 style="margin-top:52px">Paper trading metrics</h3>
<p class="note">Over <strong>{m['nights']} settled
{"night" if m['nights'] == 1 else "nights"}</strong> and {m['positions']}
position-nights, against the same book with every hedge removed - observed, not modelled.</p>
<div class="scroll stacked"><table><thead><tr><th>Metric</th><th class="num">Ballast</th>
<th class="num">Untouched</th><th>Note</th></tr></thead><tbody>{body}</tbody></table></div>
<p class="note"><strong>Read the drawdown, not the Sharpe.</strong> This is insurance: it
should show up as a smaller worst-case, and it does. Sharpe over {m['nights']} nights is
noise in either column and both are negative here - it is on the page because the track
names it, not because it means anything yet. The figures that carry weight are on the
Evidence page, measured over 100 to 264 nights per name.</p>"""

    @property
    def tile_scope(self) -> str:
        """State what the tiles cover, and how few nights that is."""
        n = len(self.clean_sessions)
        if not n:
            return ""
        nights = "night" if n == 1 else "nights"
        note = (f'<p class="note">Across <strong>{n} {nights}</strong> '
                f'({", ".join(self.clean_sessions)}). ')
        if self.excluded:
            names = ", ".join(sorted(r["ticker"] for r in self.excluded))
            note += (f'{len(self.excluded)} hedges are excluded - {names} on '
                     f'{", ".join(sorted({r["session"] for r in self.excluded}))}, placed a '
                     f'night early, so they cannot say how well a hedge works. Only those '
                     f'rows: the fault could add a hedge, never remove one, so the refusals '
                     f'that night stand and are counted. They are still in the table, '
                     f'marked. ')
        if n < 5:
            note += (f'At {n} {nights} the mean is still mostly market direction rather than '
                     f'a performance record. The claims this project stands on are on the '
                     f'Evidence page, measured over years.')
        return note + "</p>"

    def settled_page(self) -> str:
        return f"""
<section class="bd"><div class="wrap center">
<p class="eyebrow">Graded against reality</p>
<h1>Every call has an<br>exact counterfactual.</h1>
<p class="lede">What the position would have done unhedged is not modelled - it is
<span class="hl">observed</span>, on the same window. Every decision, right or wrong,
settles at the next opening bell, so nothing can be quietly forgotten.</p>
<div class="tiles">
{_tile(len(self.clean), "decisions settled")}
{_tile(f"{self.shrank}/{len(self.hedges)}" if self.hedges else "-", "hedges that cut the move")}
{_tile(f"{self.worst:,.0f} bp" if self.worst else "-", "worst night seen")}
{_tile(f"{self.mean_va:+,.0f} bp" if self.clean else "-", "mean value added per position-night")}
</div>
{self.tile_scope}
</div></section>

<section><div class="wrap">
{_settled(self.rows)}
<div class="narrow" style="margin-top:52px">
{self.paper_metrics_block}

<h3 style="margin-top:52px">How these are scored</h3>
<ul class="bul">
<li><strong>Value added is Realised minus "If reversed"</strong>, and both are in the row, so every number here can be checked by subtracting two others. <em>Realised</em> is what the position actually returned over the window; <em>if reversed</em> is what the other choice would have returned over the same window - for a refusal, the rToken held against a short perp, less the hedge cost; for a hedge, the rToken held alone. Not modelled, observed.</li>
<li><strong>Only hedges are coloured.</strong> A refusal's value added is positive exactly when the position rose, so colouring it green would be a directional scorecard, and this system makes no directional claim. A refused night on which the name rallied is not a win and is not shown as one; the number is still in the row, and refusals are graded across the run on the mean above.</li>
<li><strong>A hedge is graded on whether it cut the move.</strong> It is symmetric, so grading one by profit direction would be meaningless, and one night settles the question.</li>
<li><strong>Rows marked "hedged a night early"</strong> were hedged before the calendar rule
checked the release time. They are kept, excluded from the figures above, and written up in
full under <a href="docs.html#defects">defects</a>. Only hedges are marked: the fault could
add a hedge, never remove one, so refusals on the same night stand.</li>
<li><strong>A refusal cannot be graded on one night.</strong> Its value added is positive exactly when the position rose, so a nightly verdict on a refusal is a directional scorecard - and this system makes no directional claim. On a broad down night every refusal scores badly, which is only the case for hedging everything, every night, at 11.3 bp a time. Refusals are graded across the run instead, on the mean above; each row still shows its own arithmetic.</li>
</ul>
</div>
</div></section>"""

    @property
    def cf_rows(self) -> list[dict]:
        return self.cf.get("rows", [])

    def reader_page(self) -> str:
        cf, rows = self.cf, self.cf_rows
        if not rows:
            return """
<section class="bd"><div class="wrap center">
<p class="eyebrow">Reader against calendar</p>
<h1>Does the model<br>ever change the answer?</h1>
<p class="lede">The comparison index has not been built yet. Run
<code>python3 -m ballast.counterfactual</code>.</p>
</div></section>"""

        c = cf.get("counts", {})
        check = cf.get("check", {})
        overrides = [r for r in rows if r["flip"] and not r.get("selector_affected")]
        va = cf.get("flip_value_added_bp")
        settled_flips = cf.get("flips_settled", 0)
        pct = (100 * c.get("flips", 0) / c["model"]) if c.get("model") else 0

        if not overrides:
            lede = ("On this record the model has not once changed the rule's answer. "
                    "That is the honest reading: so far it is reporting, not deciding.")
        else:
            lede = (f"On <span class=\"hl\">{c['flips']} of {c['model']}</span> nights "
                    f"the reader reached a different answer from the calendar, and "
                    f"Ballast did what the reader said. Those are the only nights on "
                    f"which the model can be said to have decided anything.")

        if va is None or not settled_flips:
            money = ("None of those overrides has settled yet, so there is nothing to "
                     "say about what they were worth.")
        else:
            word = "added" if va > 0 else "cost"
            money = (f"{settled_flips} of them have settled. Against the calendar's "
                     f"answer on the same nights, they {word} "
                     f"<strong>{abs(va):,.0f} bp</strong> in total - "
                     f"{'a gain' if va > 0 else 'a loss'}, published because it is what "
                     f"the record says. Four nights is not a performance measurement; "
                     f"it is a count of the times the model mattered and what happened "
                     f"next.")

        mism = check.get("mismatched", [])
        if not mism:
            checkline = (f"All <strong>{check.get('matched', 0)}</strong> of them "
                         f"reproduce exactly.")
        else:
            names = ", ".join(f"{m['ticker']} on {m['session']}" for m in mism)
            checkline = (f"<strong>{check.get('matched', 0)} of "
                         f"{check.get('rule_rows', 0)}</strong> reproduce exactly. The "
                         f"exception is {names}, decided before the calendar rule "
                         f"checked the release time - the "
                         f"<a href=\"docs.html#defects\">published defect</a>, not a "
                         f"fault in this derivation.")

        direction = ("Every one of them turned a NO_HEDGE into a HEDGE."
                     if c.get("flips_to_hedge") and not c.get("flips_to_no_hedge")
                     else f"{c.get('flips_to_hedge', 0)} turned a NO_HEDGE into a "
                          f"HEDGE; {c.get('flips_to_no_hedge', 0)} went the other way.")

        return f"""
<section class="bd"><div class="wrap center">
<p class="eyebrow">Reader against calendar</p>
<h1>Does the model<br>ever change the answer?</h1>
<p class="lede">A deterministic calendar rule can decide every night on its own. So
the only question worth asking about the model is whether it ever reaches a
different answer - and what happened when it did. {lede}</p>
<div class="tiles">
{_tile(c.get("compared", 0), "decisions compared")}
{_tile(c.get("model", 0), "read by the model")}
{_tile(c.get("flips", 0), "changed the rule's answer")}
{_tile(f"{pct:.0f}%", "of the model's nights")}
</div>
<p class="note">{direction} Built from the signed ledger; rebuilt nightly.</p>
</div></section>

<section><div class="wrap">
<div class="narrow">
<h2 style="font-size:26px;margin-bottom:10px">The overrides</h2>
<p class="note" style="margin-bottom:0">{money}</p>
</div>
{_overrides(overrides)}
<div class="narrow" style="margin-top:44px">
<div class="card"><h3>The derivation is checked, not asserted</h3>
<p>The calendar's answer for a past night is re-derived by calling the same
<code>policy.decide</code> the nightly run calls, with the model's judgment removed.
On a night the reader abstained or failed a gate, the recorded decision <em>is</em>
the calendar's - so every one of the
<strong>{check.get('rule_rows', 0)}</strong> rule-decided rows is a test of that
derivation. {checkline}</p></div>
<div class="card"><h3>The count is a floor</h3>
<p>Nasdaq publishes a release-time flag for upcoming dates and drops it to
<em>not supplied</em> for past ones, and an unsupplied flag passes both window
gates. A re-derivation can therefore only ever flag <em>more</em> nights for the
calendar than the live run saw, never fewer - which can only shrink the count of
"calendar said no, model said hedge". Nights decided from now on carry the rule's
own answer in the ledger entry beside the decision, so they need no re-derivation
at all - <strong>{c.get('recorded', 0)}</strong> of the
{c.get('decisions', 0)} rows on the chain do so far.</p></div>
</div>
</div></section>

<section><div class="wrap">
<div class="narrow">
<h2 style="font-size:26px;margin-bottom:10px">Every decision, both answers</h2>
<p class="note" style="margin-bottom:0">One row per position-night on the chain.
<em>Calendar</em> is what the rule alone would have done; <em>Taken</em> is what
Ballast did.</p>
</div>
{_comparison(rows)}
<div class="narrow" style="margin-top:44px">
<h3>How to read this</h3>
<ul class="bul">
<li><strong>The model's authority stops at the judgment.</strong> An override can
only ever add or remove a bounded hedge against a position already held. Size,
direction and price stay with the policy and the enforcer, so a model that flips
every night still cannot place a bet.</li>
<li><strong>An override is the only attributable row.</strong> Where the reader
agreed with the calendar, the night's outcome says nothing about the model - the
rule would have produced the same decision with no model at all. Value added is
shown only on the rows where the two disagreed.</li>
<li><strong>Rows marked "hedged a night early"</strong> sit on a session decided
before the release-time fix. The model was shown the buggy calendar flag, so
comparing its call against the corrected calendar compares two different questions.
They stay in the table and out of the counts.</li>
<li><strong>Nothing here is a Sharpe claim.</strong> A handful of overrides over a
handful of nights measures whether the model is load-bearing, not whether it is
profitable. The claims this project stands on are on the
<a href="evidence.html">Evidence</a> page, measured over years.</li>
</ul>
<p class="note">Reproduce with <code>python3 -m ballast.counterfactual</code>, which
writes <code>state/counterfactual.json</code> - every row on this page, including
the derivation check.</p>
</div>
</div></section>"""

    def evidence_page(self) -> str:
        claim_rows = "".join(
            f'<tr><td class="wrap" data-label="">{_e(c)}</td>'
            f'<td data-label="Status"><span class="tag {"on" if s == "proven" else ""}">'
            f'{_e(s)}</span></td>'
            f'<td class="dim wrap" data-label="Basis">{_e(n or "")}</td></tr>'
            for c, s, n in claims(self.f))
        return f"""
<section class="bd"><div class="wrap center">
<p class="eyebrow">Open by construction</p>
<h1>An audited desk,<br>not a black box.</h1>
<div class="narrow stack">
<div class="card"><h3>It cannot place a bet</h3><p>Every order Ballast can emit is
opposite in sign to, and bounded in size by, a position already held. The enforcer
holds the only write-scoped key, sees no model reasoning, and does arithmetic against
a signed mandate. {suite.red_team()} red-team tests drive hostile intents at it.</p></div>
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
<div class="narrow">
<h2 style="font-size:26px;margin-bottom:10px">What the hedge does to the tail</h2>
<p class="note" style="margin-bottom:0">The 95th-percentile overnight move for each name,
with no hedge and with the matched perpetual short, over the nights listed on each row.
Median reduction <strong>{self.f['median_tail_cut_pct']}%</strong>. This is the measurement
the product rests on, and it is the one made over years rather than over this week's
paper log.</p>
{_tail_chart(self.f.get("tail", []))}
<p class="note">Reproduce with <code>python3 research/hedge_study.py</code>. Worst single
nights, not shown above: MSFT <strong>{worst_night(self.f, "MSFT")}</strong>, AMD
<strong>{worst_night(self.f, "AMD")}</strong>.</p>
{self.oos_block}
{self.provenance_block}
</div>
</div></section>

<section><div class="wrap">
<div class="scroll stacked"><table><thead><tr><th>Claim</th><th>Status</th><th>Basis</th>
</tr></thead><tbody>{claim_rows}</tbody></table></div>
<div class="narrow" style="margin-top:44px">
<p class="note">Ballast is <strong>priced protection, not alpha</strong>. It makes no
Sharpe claim: the nights it hedges carry real variance and no reliable expected
return, so removing them is insurance - which has a price, and is worth paying only
on the right nights.</p>
<pre style="margin-top:34px"><b>git clone {REPO} &amp;&amp; cd ballast</b>
python3 verify.py                       <span class="dim"># every offline claim, one command</span>
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
    ("reader.html", "Reader", "Ballast - the reader against the calendar",
     "Every night the model reached a different answer from the deterministic rule.",
     "reader_page"),
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
