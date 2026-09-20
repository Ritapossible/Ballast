"""Sandbox entry point for the Ballast Overnight Protection Playbook.

Historical runs build one replay frame per symbol from the managed kline path
and hand them to the platform's backtest engine. The strategy decides purely
from each bar's timestamp, so nothing here can leak a future night into a past
decision.

Every getagent.* call below appears in the bundled reference or the runnable
demo. An earlier revision invented two that read plausibly - runtime.is_backtest
and backtest.write_report - and each cost a sandbox run to discover, because a
name that sounds right fails only when the platform runs it.
"""
import datetime as dt
import math

import window
from getagent import backtest, data, runtime

INTERVAL = "1h"
LOOKAHEAD_DAYS = 45
EXCHANGE = "bitget"
VENUE = "BITGET"


def _finite(value):
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _repair(frame):
    """Make each bar internally consistent, and report how many needed it.

    Nautilus refuses a bar whose high is below its open (`high was < open`) and
    the whole replay dies on the first one. Thin RWA perpetuals do produce such
    bars upstream, so the choice is to drop them, repair them, or fail.

    Repairing is the least destructive: high becomes the highest of the four
    prices it should already have been the highest of, and low the lowest.
    Nothing is invented - the extremes are taken from the bar's own open and
    close - and the count is published in the metrics so a reader can see how
    much of the series needed touching rather than having to trust that it
    didn't.
    """
    ohlc = ["open", "high", "low", "close"]
    if not all(column in frame.columns for column in ohlc):
        return frame, 0
    high = frame[ohlc].max(axis=1)
    low = frame[ohlc].min(axis=1)
    broken = int(((frame["high"] < high) | (frame["low"] > low)).sum())
    if broken:
        frame = frame.copy()
        frame["high"] = high
        frame["low"] = low
    return frame, broken


def _run_historical():
    symbols = runtime.manifest.get("trading_symbols") or []
    if not symbols:
        runtime.emit_signal(action="watch", symbol="", confidence=0.0,
                            metrics={"rows": 0},
                            meta={"reason": "no trading_symbols declared"})
        return

    frames = {}
    empty = []
    rows = 0
    repaired = 0
    for symbol in symbols:
        # closed_only leaves the forming candle out, so the same replay returns
        # the same numbers twice. A half-formed bar at the open would also be
        # the one bar deciding whether a night is still covered.
        bars = data.crypto.futures.kline(symbol=symbol, interval=INTERVAL,
                                         limit=1000, exchange=EXCHANGE,
                                         closed_only=True)
        frame = backtest.prepare_frame(bars, datetime_index="date")
        if frame.empty:
            empty.append(symbol)
            continue
        frame, broken = _repair(frame)
        repaired += broken
        frames[f"{symbol}.{VENUE}"] = frame
        rows += len(frame)

    if not frames:
        runtime.emit_signal(action="watch", symbol=symbols[0], confidence=0.0,
                            metrics={"rows": 0},
                            meta={"reason": "no bars for " + ", ".join(empty)})
        return

    result = backtest.run(ohlcv_data=frames, spec=runtime.backtest_spec)
    chart_path = backtest.generate_chart(result)

    metrics = {key: _finite(value) for key, value in {
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "sharpe_ratio": result.sharpe_ratio,
        "profit_factor": result.profit_factor,
        "rows": rows,
        "symbols_replayed": len(frames),
        "symbols_without_bars": len(empty),
        "bars_repaired": repaired,
    }.items()}

    runtime.emit_signal(
        action="watch",
        symbol=symbols[0],
        confidence=0.0,
        metrics=metrics,
        meta={"chart_path": chart_path,
              "note": "protection leg in isolation; a loss on a rising tape is "
                      "the premium, not a failed signal",
              "protected_nights": len(
                  (runtime.manifest.get("strategy_config") or {})
                  .get("event_dates") or {})},
    )


def _ticker(symbol):
    """ORCLUSDT -> ORCL.

    The perp is the tradable symbol; the disclosure calendar takes the bare US
    ticker, and mixing the two namespaces returns nothing rather than failing.
    """
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def _forward_event_dates(symbols, today):
    """The next scheduled earnings date per symbol, from the platform's calendar.

    The manifest's `event_dates` are the ten nights inside the backtest window.
    Every one of them is in the past, so a live run reading only those would hold
    nothing on every night for the rest of time - which is what this path did
    before: it emitted `watch` unconditionally and could never open a position.

    The live selector therefore asks for the calendar rather than carrying one.
    Same rule the replay runs, applied to nights that have not happened yet, and
    dates only - never the content of a report. A scheduled release means tonight
    is dangerous, not that the print will be good.

    `equity.calendar.earnings` is the cross-name endpoint, so this is one call
    for every symbol rather than ten. It takes no `provider`, which the package
    validator forbids for a backtestable Playbook.
    """
    wanted = {_ticker(symbol): symbol for symbol in symbols}
    start = dt.datetime.combine(today, dt.time(), dt.timezone.utc)
    end = start + dt.timedelta(days=LOOKAHEAD_DAYS)
    try:
        rows = data.equity.calendar.earnings(
            start_time=int(start.timestamp() * 1000),
            end_time=int(end.timestamp() * 1000),
            country="us")
        records = data.to_records(rows)
    except Exception as exc:  # BLE001 is project-wide ignored: this one is reported, not swallowed
        return {}, [f"{type(exc).__name__}: {exc}"[:120]]

    dates = {}
    for row in records:
        symbol = wanted.get(str(row.get("symbol") or "").upper())
        when = str(row.get("report_date") or "")[:10]
        if not symbol or len(when) != 10 or when < today.isoformat():
            continue
        current = dates.get(symbol)
        dates[symbol] = min(current, when) if current else when
    return dates, []


def _execute_protection(symbol, protect, qty, leverage):
    """Open or cover the protection leg. Short only - never long.

    Ballast's central claim is that it cannot place a directional bet. This
    function can emit exactly one kind of opening order and it is a short; there
    is no branch that opens a long, and a test asserts the absence.
    """
    from getagent import trade

    current = trade.contract.current_position(symbol=symbol)
    position = trade.helpers.find_contract_position(current, symbol=symbol)
    if protect:
        if position is not None:
            return {"status": "already_protected", "hold_side": position.hold_side}
        result = trade.contract.open_short_market(symbol=symbol, qty=qty,
                                                  leverage=leverage)
        if not trade.is_success(result):
            raise RuntimeError(f"open short failed: {result}")
        return {"opened": str(qty), "result": result}
    if position is None:
        return {"status": "flat"}
    result = trade.contract.close_position(symbol=symbol,
                                           hold_side=position.hold_side)
    if not trade.is_success(result):
        raise RuntimeError(f"cover failed: {result}")
    return {"covered": position.hold_side, "result": result}


def _run_live():
    """Decide from the calendar, then let the managed runtime gate the trade."""
    symbols = runtime.manifest.get("trading_symbols") or []
    config = runtime.manifest.get("strategy_config") or {}
    qty = str(config.get("trade_size") or "1")
    leverage = int(config.get("leverage") or 1)
    now = dt.datetime.now(dt.timezone.utc)
    event_dates, unreachable = _forward_event_dates(symbols, now.date())

    if not event_dates:
        # should_protect treats an empty mapping as "protect every night". That
        # is the indiscriminate baseline the research measured as value
        # destroying, so reaching it because a data call failed would be failing
        # open into the one policy this package exists to reject. Hold instead,
        # and say which lookups failed rather than reporting a quiet night.
        for symbol in symbols:
            runtime.emit_signal_or_follow(
                action="hold", symbol=symbol, confidence=0.0,
                metrics={"scheduled_symbols": 0, "calendar_failures": len(unreachable)},
                meta={"reason": "no forward calendar; refusing to hedge blind",
                      "unreachable": unreachable[:10]})
        return

    for symbol in symbols:
        protect = window.should_protect(symbol, now, event_dates)
        runtime.emit_signal_or_follow(
            action="short" if protect else "hold",
            symbol=symbol,
            confidence=1.0 if protect else 0.0,
            metrics={"scheduled_symbols": len(event_dates),
                     "calendar_failures": len(unreachable),
                     "inside_window": int(window.inside_window(now))},
            meta={"next_event": event_dates.get(symbol),
                  "protected_night": window.protected_night(now).isoformat(),
                  "note": ("protecting a scheduled-event night" if protect
                           else "no scheduled event in this window")},
            execute_trade=lambda s=symbol, p=protect: _execute_protection(
                s, p, qty, leverage))


def run():
    if runtime.is_historical():
        _run_historical()
        return
    if runtime.is_live():
        _run_live()
        return
    raise ValueError(f"unsupported evaluation_mode={runtime.evaluation_mode!r}")


if __name__ == "__main__":
    run()
