"""The protection leg: short the matched perpetual across a protected night.

Idle by construction. The strategy holds nothing until the US cash session
closes on a night carrying a scheduled event, and covers at the next opening
bell. Every other bar it does nothing, which is the point - the research behind
Ballast measured that trailing volatility separates a risky night from an
ordinary one far too weakly to pay a premium on, while the event calendar
separates them well and selects nights whose variance is not compensated.

The window is derived from the bar's own timestamp rather than from a lookahead
table, so a replay cannot see a night before it arrives.
"""
import datetime as dt
from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy
from window import should_protect


class OvernightProtectionConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId | None = None
    bar_type: BarType | None = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    trade_size: str = "1"
    # symbol -> ISO date whose close-to-open window is worth protecting.
    # Empty means protect every night: the indiscriminate baseline.
    event_dates: dict | None = None


class OvernightProtectionStrategy(Strategy):
    def __init__(self, config: OvernightProtectionConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._short = {}

    def on_start(self) -> None:
        bar_types = list(self.cfg.bar_types) or (
            [self.cfg.bar_type] if self.cfg.bar_type else [])
        if not bar_types:
            raise RuntimeError("no bar_type configured")
        for bar_type in bar_types:
            self.subscribe_bars(bar_type)

    # ---- decision ----------------------------------------------------------

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        symbol = instrument_id.symbol.value
        when = dt.datetime.fromtimestamp(bar.ts_event / 1e9, tz=dt.timezone.utc)
        want_short = should_protect(symbol, when, self.cfg.event_dates)
        holding = self._short.get(symbol, False)

        if want_short and not holding:
            self._enter_short(instrument_id)
            self._short[symbol] = True
        elif holding and not want_short:
            self._cover(instrument_id)
            self._short[symbol] = False

    def _size(self, instrument_id: InstrumentId) -> Quantity | None:
        instrument = self.cache.instrument(instrument_id)
        if instrument is None:
            return None
        return Quantity(Decimal(self.cfg.trade_size), instrument.size_precision)

    def _enter_short(self, instrument_id: InstrumentId) -> None:
        qty = self._size(instrument_id)
        if qty is not None:
            self._submit(instrument_id, OrderSide.SELL, qty)

    def _cover(self, instrument_id: InstrumentId) -> None:
        for position in self.cache.positions_open(instrument_id=instrument_id):
            self._submit(instrument_id, OrderSide.BUY, position.quantity)

    def _submit(self, instrument_id: InstrumentId, side: OrderSide,
                quantity: Quantity) -> None:
        self.submit_order(self.order_factory.market(
            instrument_id=instrument_id, order_side=side,
            quantity=quantity, time_in_force=TimeInForce.GTC))

    def on_stop(self) -> None:
        for instrument_id in (self.cfg.instrument_ids or
                              ([self.cfg.instrument_id] if self.cfg.instrument_id
                               else [])):
            if instrument_id is not None:
                self.cancel_all_orders(instrument_id)
                self.close_all_positions(instrument_id)
