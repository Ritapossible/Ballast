"""The nightly run: decide, enforce, execute, record.

Runs after the US close. For every position in the book it produces exactly one
decision, and every decision -- including every refusal -- is written to the
signed ledger. Refusals are evidence too: a night Ballast declined to hedge is
graded in the morning alongside the nights it did.

    python -m ballast.night [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt

from . import config
from .book import Book
from .costs import HEDGE_COST_BP
from .earnings import scheduled_in_window
from .enforcer import Enforcer, OrderIntent
from .ledger import Ledger
from .llm import available as llm_available
from .mandate import NightMandate, SignedMandate
from .market import MarketDataUnavailable
from .market import bars as market_bars
from .news import NewsUnavailable, fetch, in_window
from .overnight import overnight_returns
from .policy import Action, EventType, Impact, NightRisk, decide
from .reader import read
from .sessions import UTC, close_utc, current_session, next_session, open_utc, window_hours

# The nightly run needs recent history for the sigma it reports, not the full
# two-year series the research scripts page down. 100 sessions is ample and keeps
# a scheduled run to seconds rather than minutes.
HISTORY_BARS = 2_400

MAX_HEDGE_RATIO = 1.0

# A fixed 100,000 USDT cap against a 12,000 USDT book never bound - it was
# decorative. The night's budget is now the book itself plus a small tolerance for
# marks moving between valuation and execution, so the cap is a real constraint.
NOTIONAL_HEADROOM = 1.05


def calendar_risk(ticker: str, session: dt.date) -> tuple[NightRisk, bool]:
    """The deterministic half: is a report scheduled inside this window?"""
    flag = scheduled_in_window(ticker, session)
    if flag is None:
        return NightRisk(ticker=ticker), False
    return NightRisk(
        ticker=ticker, event_type=EventType.EARNINGS, expected_impact=Impact.HIGH,
        confidence=1.0,
        source_url=f"https://api.nasdaq.com/api/calendar/earnings?date={session.isoformat()}",
        verbatim_quote=f"{ticker} scheduled to report ({flag})",
        unknowns=("exact release time not supplied for historical dates",),
    ), True


def assess(ticker: str, session: dt.date, use_reader: bool):
    """Calendar first, then the event reader.

    Returns (risk, judgment, verdict, provenance). `provenance` records what the
    model was actually shown: whether the headlines fell inside tonight's window or
    were the recent fallback. Without it you cannot tell afterwards whether a
    judgment rested on tonight's news or last week's - a silent degradation rather
    than a visible failure.
    """
    risk, flagged = calendar_risk(ticker, session)
    if not use_reader:
        return risk, None, None, None

    start, end = close_utc(session), open_utc(next_session(session))
    try:
        headlines = fetch(ticker)                   # one request, not two
    except NewsUnavailable as exc:
        # Not fatal: the calendar rule still decides, and the reader will abstain
        # on an empty brief. But it must not look like a quiet night - the ledger
        # records that the feed failed and why, so a systemic outage is visible
        # instead of arriving as a week of confident-looking refusals.
        headlines, windowed = [], []
        provenance = {"headlines_fetched": 0, "in_window": 0, "shown": 0,
                      "source": "unavailable", "error": exc.reason}
    else:
        windowed = in_window(headlines, start, end)
        provenance = {
            "headlines_fetched": len(headlines),
            "in_window": len(windowed),
            "source": "window" if windowed else "recent_fallback",
            "shown": len(windowed or headlines[:8]),
        }
    items = windowed or headlines[:8]
    verdict = read(ticker, session, window_hours(session), items, flagged)
    if not verdict.usable:
        return risk, None, verdict, provenance      # abstained or gated -> rule decides
    return verdict.risk, verdict.judgment.value, verdict, provenance


class WindowElapsed(RuntimeError):
    """The overnight window is too far gone for a decision to mean anything."""


# A decision recorded after most of the window has passed is not a decision: the
# move it claims to have judged has already happened, and settlement grades it
# close-to-open as though the hedge had been on the whole time. Scheduled runs are
# routinely hours late - GitHub delayed one of ours by 3h17m - so the bound has to
# be generous. Half the window still leaves eight hours of slack on a normal night
# while refusing the case that actually occurred: a session re-decided 16.8 hours
# after its close, 45 minutes before the market reopened.
MAX_WINDOW_ELAPSED = 0.5


def run(dry_run: bool = False, no_reader: bool = False, force: bool = False) -> dict:
    use_reader = not no_reader
    now = dt.datetime.now(UTC)
    session = current_session(now)
    expires = open_utc(next_session(session))

    close = close_utc(session)
    lag_hours = (now - close).total_seconds() / 3600
    total_hours = window_hours(session)
    elapsed = lag_hours / total_hours if total_hours else 1.0
    if elapsed > MAX_WINDOW_ELAPSED and not force:
        raise WindowElapsed(
            f"{lag_hours:.1f}h of the {total_hours:.1f}h window for {session} has already "
            f"passed ({elapsed:.0%}). A hedge placed now could not have covered the move "
            f"settlement would credit it with. Pass --force only to reconstruct a session "
            f"deliberately, knowing the entry is not an ex-ante decision.")

    book = Book.load(config.BOOK_PATH)
    ledger = Ledger(config.LEDGER_PATH, config.secret())

    # Appending under a new key to a chain signed with an old one produces a
    # ledger that can never verify again. Rotate first, keeping the old file.
    if ledger.signed_by_other_key():
        ledger.rotate(config.STATE / "ledger.superseded.jsonl",
                      "signing key rotated; the previous chain used the public "
                      "development key and was therefore never verifiable")

    # Deciding a session twice appends a second full set of decisions, a second
    # mandate's worth of notional against the same book, and makes settlement grade
    # every position twice. The workflow's concurrency group stops two runs at once
    # but not one after another - and a manual run followed by a cron GitHub delayed
    # by hours is exactly that. A no-op rather than an error, so the late run is not
    # reported as a failure for correctly declining to duplicate work.
    decided = {e["body"].get("session") for e in ledger.records("night_summary")}
    if session.isoformat() in decided and not force:
        return {"session": session.isoformat(), "positions": 0, "hedged": 0,
                "declined": 0, "errors": 0, "news_unavailable": 0,
                "window_hours": round(total_hours, 1),
                "decided_after_close_hours": round(lag_hours, 2),
                "window_elapsed_at_decision": round(elapsed, 3), "forced": False,
                "usage": {}, "dry_run": dry_run, "reader": "not run",
                "note": "already decided; nothing appended"}

    spot_marks, histories, perp_marks, unreachable = {}, {}, {}, {}
    for pos in book:
        # One flaky symbol used to abort the whole run, leaving decisions in the
        # ledger with no summary. Each position now fails on its own.
        try:
            series = market_bars(pos.spot_symbol, "spot",
                                 max_bars=HISTORY_BARS, use_cache=False)
            perp_series = market_bars(pos.perp_symbol, "mix",
                                      max_bars=HISTORY_BARS, use_cache=False)
            if not series or not perp_series:
                raise MarketDataUnavailable(f"empty candle series for {pos.ticker}")
            spot_marks[pos.spot_symbol] = series[max(series)][1]
            perp_marks[pos.perp_symbol] = perp_series[max(perp_series)][1]
            prior = overnight_returns(series)
            histories[pos.ticker] = [v for d, v in sorted(prior.items()) if d < session]
        except Exception as exc:
            unreachable[pos.ticker] = f"{type(exc).__name__}: {exc}"

    notionals = book.notionals(spot_marks)
    gross = sum(abs(v) for v in notionals.values())
    mandate = NightMandate(
        issued_at=now, expires_at=expires, universe=book.symbols(),
        max_hedge_ratio=MAX_HEDGE_RATIO,
        max_notional_usdt=round(gross * MAX_HEDGE_RATIO * NOTIONAL_HEADROOM, 2),
        max_orders=len(book), account="paper",
    )
    signed = SignedMandate.issue(mandate, config.secret())
    enforcer = Enforcer(signed, config.secret())

    ledger.append("mandate", {
        "session": session.isoformat(), "expires_at": expires.isoformat(),
        "universe": list(mandate.universe), "max_hedge_ratio": mandate.max_hedge_ratio,
        "max_notional_usdt": mandate.max_notional_usdt, "max_orders": mandate.max_orders,
        "signature": signed.signature, "dev_secret": config.using_dev_secret(),
    }, now)

    # Execution venue. BALLAST_VENUE=bgc routes the admitted hedge through the
    # Bitget Agent Hub CLI in paper-trading mode, so the fill price comes from the
    # exchange's Demo environment rather than from our own simulation. Unset, or
    # unavailable for any reason, Ballast simulates as before - and the ledger says
    # which of the two actually happened, per order. It is never inferred.
    from .bgc import BgcExecutor, BgcUnavailable
    from .bgc import available as bgc_available
    from .executor import PaperExecutor
    paper = PaperExecutor()
    bgc_ok, bgc_why = bgc_available()
    executor = BgcExecutor() if bgc_ok else paper
    venue = "bgc-paper" if bgc_ok else "simulated"
    hedged = declined = 0

    errors = news_down = 0
    for pos in book:
        if pos.ticker in unreachable:
            # Recorded as a decision, not dropped: a position Ballast could not
            # assess is a fact the morning needs to know about.
            errors += 1
            ledger.append("decision", {
                "ticker": pos.ticker, "spot_symbol": pos.spot_symbol,
                "perp_symbol": pos.perp_symbol, "session": session.isoformat(),
                "action": Action.NO_HEDGE.value, "sigma_bp": 0.0,
                "cost_bp": HEDGE_COST_BP, "notional_usdt": 0.0,
                "rationale": f"no decision taken - market data unavailable "
                             f"({unreachable[pos.ticker]})",
                "error": unreachable[pos.ticker],
                "inputs": {"decided_by": "none"},
            }, now)
            continue

        try:
            risk, judgment, verdict, provenance = assess(pos.ticker, session, use_reader)
            decision = decide(pos.ticker, pos.spot_symbol, histories[pos.ticker], risk,
                              window_hours(session), model_judgment=judgment)
        except Exception as exc:
            errors += 1
            ledger.append("decision", {
                "ticker": pos.ticker, "spot_symbol": pos.spot_symbol,
                "perp_symbol": pos.perp_symbol, "session": session.isoformat(),
                "action": Action.NO_HEDGE.value, "sigma_bp": 0.0,
                "cost_bp": HEDGE_COST_BP, "notional_usdt": 0.0,
                "rationale": f"no decision taken - {type(exc).__name__}: {exc}",
                "error": f"{type(exc).__name__}: {exc}",
                "inputs": {"decided_by": "none"},
            }, now)
            continue

        record = decision.to_record()
        if verdict is not None:
            record["reader"] = verdict.to_record()
        if provenance is not None:
            record["news"] = provenance
            if provenance.get("source") == "unavailable":
                news_down += 1
        record["session"] = session.isoformat()
        record["perp_symbol"] = pos.perp_symbol        # settlement must not guess it
        record["spot_mark"] = spot_marks[pos.spot_symbol]
        record["notional_usdt"] = round(notionals.get(pos.spot_symbol, 0.0), 2)

        if decision.action is not Action.HEDGE:
            declined += 1
            ledger.append("decision", record, now)
            continue

        held = notionals.get(pos.spot_symbol, 0.0)
        intent = OrderIntent(
            spot_symbol=pos.spot_symbol, perp_symbol=pos.perp_symbol,
            side="sell" if held > 0 else "buy",
            notional_usdt=abs(held) * MAX_HEDGE_RATIO,
            reason=decision.rationale,
        )
        verdict = enforcer.evaluate(intent, notionals, now)
        record["enforcer"] = {"admitted": verdict.admitted, "rule": verdict.rule,
                              "detail": verdict.detail}

        if verdict.rejected:
            declined += 1
            ledger.append("decision", record, now)
            continue

        enforcer.commit(intent)          # budget is consumed in rehearsal too
        if not dry_run:
            if verdict.admission is None:                # unreachable: rejected above
                raise RuntimeError(f"admitted verdict carried no admission for {pos.ticker}")
            mark = perp_marks[pos.perp_symbol]
            fill_venue, fallback = venue, None
            try:
                fill = executor.execute(verdict.admission, mark, now)
            except BgcUnavailable as exc:
                # Route failed mid-session. Simulate, and say so on this row rather
                # than letting a simulated fill inherit the Agent Hub's label.
                fill = paper.execute(verdict.admission, mark, now)
                fill_venue, fallback = "simulated", exc.reason
            record["fill"] = fill.to_record() | {"venue": fill_venue}
            if fallback:
                record["fill"]["venue_fallback"] = fallback
        hedged += 1
        ledger.append("decision", record, now)

    summary = {
        "session": session.isoformat(), "positions": len(book),
        "hedged": hedged, "declined": declined, "errors": errors,
        "window_hours": round(total_hours, 1),
        # How late the decision was taken, so the record says for itself whether it
        # was made before the outcome was known rather than asking to be trusted.
        "news_unavailable": news_down,
        "decided_after_close_hours": round(lag_hours, 2),
        "window_elapsed_at_decision": round(elapsed, 3),
        "forced": bool(force),
        "usage": enforcer.usage, "dry_run": dry_run,
        "reader": "on" if use_reader and llm_available() else "off (no QWEN_API_KEY)",
        "venue": venue,
        "venue_detail": "Bitget Agent Hub, paper-trading" if bgc_ok else bgc_why,
    }
    ledger.append("night_summary", summary, now)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="decide and record, place no fills")
    ap.add_argument("--no-reader", action="store_true", help="calendar rule only, skip the LLM")
    ap.add_argument("--force", action="store_true",
                    help="decide even though most of the window has already passed; "
                         "the entry is marked as not an ex-ante decision")
    s = run(**vars(ap.parse_args()))
    print(f"session {s['session']} · window {s['window_hours']}h · "
          f"decided {s['decided_after_close_hours']}h after the close · reader {s['reader']}\n"
          f"{s['positions']} positions · {s['hedged']} hedged · {s['declined']} declined")
    if config.using_dev_secret():
        print("note: BALLAST_SECRET unset - signing with the development key")
