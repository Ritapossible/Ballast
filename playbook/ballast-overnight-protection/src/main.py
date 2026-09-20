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
