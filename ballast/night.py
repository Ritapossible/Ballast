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
from .costs import HEDGE_COST_BP
from .market import MarketDataUnavailable
from .llm import available as llm_available
from .book import Book
from .earnings import symbols_on
from .enforcer import Enforcer, OrderIntent
from .ledger import Ledger
from .mandate import NightMandate, SignedMandate
from .market import bars as market_bars
from .overnight import overnight_returns
from .news import fetch, in_window
from .policy import Action, EventType, Impact, NightRisk, decide
from .reader import read
from .sessions import (UTC, close_utc, current_session, next_session, open_utc,
                       window_hours)

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
    flag = symbols_on(session).get(ticker) or symbols_on(next_session(session)).get(ticker)
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

    headlines = fetch(ticker)                       # one request, not two
    start, end = close_utc(session), open_utc(next_session(session))
    windowed = in_window(headlines, start, end)
    items = windowed or headlines[:8]
    provenance = {
        "headlines_fetched": len(headlines),
        "in_window": len(windowed),
        "source": "window" if windowed else "recent_fallback",
        "shown": len(items),
    }
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
        except Exception as exc:                       # noqa: BLE001 - isolate, then record
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

    from .executor import PaperExecutor
    executor = PaperExecutor()
    hedged = declined = 0

    errors = 0
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
        except Exception as exc:                       # noqa: BLE001 - isolate, then record
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
            fill = executor.execute(intent.perp_symbol, intent.side, intent.notional_usdt,
                                    perp_marks[pos.perp_symbol], now)
            record["fill"] = fill.to_record()
        hedged += 1
        ledger.append("decision", record, now)

    summary = {
        "session": session.isoformat(), "positions": len(book),
        "hedged": hedged, "declined": declined, "errors": errors,
        "window_hours": round(total_hours, 1),
        # How late the decision was taken, so the record says for itself whether it
        # was made before the outcome was known rather than asking to be trusted.
        "decided_after_close_hours": round(lag_hours, 2),
        "window_elapsed_at_decision": round(elapsed, 3),
        "forced": bool(force),
        "usage": enforcer.usage, "dry_run": dry_run,
        "reader": "on" if use_reader and llm_available() else "off (no QWEN_API_KEY)",
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
