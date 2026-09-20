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
import math

from getagent import backtest, data, runtime

INTERVAL = "1h"
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


def _run_live():
    """Live path: decide, then let the managed runtime gate any follow-trade."""
    for symbol in runtime.manifest.get("trading_symbols") or []:
        runtime.emit_signal_or_follow(
            action="watch", symbol=symbol, confidence=0.0,
            metrics={}, meta={"note": "awaiting the cash close"})


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
