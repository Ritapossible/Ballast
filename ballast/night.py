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
from .earnings import symbols_on
from .enforcer import Enforcer, OrderIntent
from .ledger import Ledger
from .mandate import NightMandate, SignedMandate
from .market import closes
from .overnight import overnight_returns
from .policy import Action, EventType, Impact, NightRisk, PolicyConfig, decide
from .sessions import UTC, close_utc, next_session, open_utc, window_hours

MAX_HEDGE_RATIO = 1.0
MAX_NOTIONAL_USDT = 100_000.0
MAX_ORDERS = 50


def current_session(now: dt.datetime) -> dt.date:
    """The most recent weekday session whose close has already passed."""
    day = now.date()
    while day.weekday() > 4 or now < close_utc(day):
        day -= dt.timedelta(days=1)
        while day.weekday() > 4:
            day -= dt.timedelta(days=1)
    return day


def read_night_risk(ticker: str, session: dt.date) -> NightRisk:
    """v0 reader: the earnings calendar only.

    From day 6 an LLM populates the same record from unstructured news. Its output
    contract does not change — it gains sources, never authority.
    """
    reporting = symbols_on(next_session(session))
    reporting_tonight = symbols_on(session)
    flag = reporting_tonight.get(ticker) or reporting.get(ticker)
    if flag is None:
        return NightRisk(ticker=ticker, unknowns=("no news source beyond the calendar in v0",))
    return NightRisk(
        ticker=ticker,
        event_type=EventType.EARNINGS,
        expected_impact=Impact.HIGH,
        confidence=1.0,
        source_url=f"https://api.nasdaq.com/api/calendar/earnings?date={session.isoformat()}",
        verbatim_quote=f"{ticker} scheduled to report ({flag})",
        unknowns=("exact release time not supplied for historical dates",),
    )


def run(dry_run: bool = False) -> dict:
    now = dt.datetime.now(UTC)
    session = current_session(now)
    expires = open_utc(next_session(session))

    book = Book.load(config.BOOK_PATH)
    ledger = Ledger(config.LEDGER_PATH, config.secret())

    spot_marks, histories, perp_marks = {}, {}, {}
    for pos in book:
        bars = closes(pos.spot_symbol, "spot")
        spot_marks[pos.spot_symbol] = bars[max(bars)]
        perp_bars = closes(pos.perp_symbol, "mix")
        perp_marks[pos.perp_symbol] = perp_bars[max(perp_bars)]
        prior = overnight_returns(bars)
        histories[pos.ticker] = [v for d, v in sorted(prior.items()) if d < session]

    mandate = NightMandate(
        issued_at=now, expires_at=expires, universe=book.symbols(),
        max_hedge_ratio=MAX_HEDGE_RATIO, max_notional_usdt=MAX_NOTIONAL_USDT,
        max_orders=MAX_ORDERS, account="paper",
    )
    signed = SignedMandate.issue(mandate, config.secret())
    enforcer = Enforcer(signed, config.secret())
    notionals = book.notionals(spot_marks)

    ledger.append("mandate", {
        "session": session.isoformat(), "expires_at": expires.isoformat(),
        "universe": list(mandate.universe), "max_hedge_ratio": mandate.max_hedge_ratio,
        "max_notional_usdt": mandate.max_notional_usdt, "max_orders": mandate.max_orders,
        "signature": signed.signature, "dev_secret": config.using_dev_secret(),
    }, now)

    from .executor import PaperExecutor
    executor = PaperExecutor()
    hedged = declined = 0

    for pos in book:
        risk = read_night_risk(pos.ticker, session)
        decision = decide(pos.ticker, pos.spot_symbol, histories[pos.ticker], risk,
                          window_hours(session))
        record = decision.to_record()
        record["session"] = session.isoformat()
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

        if not dry_run:
            fill = executor.execute(intent.perp_symbol, intent.side, intent.notional_usdt,
                                    perp_marks[pos.perp_symbol], now)
            enforcer.commit(intent)
            record["fill"] = fill.to_record()
        hedged += 1
        ledger.append("decision", record, now)

    summary = {
        "session": session.isoformat(), "positions": len(book),
        "hedged": hedged, "declined": declined,
        "window_hours": round(window_hours(session), 1),
        "usage": enforcer.usage, "dry_run": dry_run,
    }
    ledger.append("night_summary", summary, now)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="decide and record, place no fills")
    s = run(**vars(ap.parse_args()))
    print(f"session {s['session']} · window {s['window_hours']}h · "
          f"{s['positions']} positions · {s['hedged']} hedged · {s['declined']} declined")
    if config.using_dev_secret():
        print("note: BALLAST_SECRET unset — signing with the development key")
