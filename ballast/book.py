"""The paper position book.

Ballast protects positions it did not open. The book is therefore an INPUT to the
system, never an output of it: nothing in Ballast may add, remove or resize a spot
position. That constraint is what makes the enforcer's "opposite in sign, bounded
by a position already held" rule meaningful.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .universe import hedgeable_pairs


class BookError(RuntimeError):
    pass


@dataclass(frozen=True)
class Position:
    spot_symbol: str        # RTSLAUSDT
    perp_symbol: str        # TSLAUSDT
    ticker: str             # TSLA
    quantity: float         # units of the rToken; negative would be short
    entry_price: float

    def notional(self, mark: float) -> float:
        """Signed notional in USDT at `mark`."""
        return self.quantity * mark


class Book:
    def __init__(self, positions: list[Position]):
        self._positions = {p.spot_symbol: p for p in positions}

    def __len__(self) -> int:
        return len(self._positions)

    def __iter__(self):
        return iter(self._positions.values())

    def get(self, spot_symbol: str) -> Position | None:
        return self._positions.get(spot_symbol)

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._positions))

    def notionals(self, marks: dict[str, float]) -> dict[str, float]:
        """{spot_symbol: signed notional} — exactly what the enforcer consumes."""
        return {
            s: p.notional(marks[s])
            for s, p in self._positions.items()
            if s in marks and marks[s] > 0
        }

    @staticmethod
    def load(path: Path) -> Book:
        raw = json.loads(Path(path).read_text())
        return Book([Position(**p) for p in raw["positions"]])

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(
            {"positions": [p.__dict__ for p in self]}, indent=2))

    @staticmethod
    def from_tickers(tickers: list[str], usdt_each: float,
                     marks: dict[str, float]) -> Book:
        """Build an equal-notional paper book. Tickers must be hedgeable."""
        pairs = {p.ticker: p for p in hedgeable_pairs()}
        positions = []
        for t in tickers:
            pair = pairs.get(t)
            if pair is None:
                raise BookError(f"{t} has no perp leg — not hedgeable, refusing to add")
            mark = marks.get(pair.spot)
            if not mark or mark <= 0:
                raise BookError(f"no usable mark for {pair.spot}")
            positions.append(Position(
                spot_symbol=pair.spot, perp_symbol=pair.perp, ticker=t,
                quantity=usdt_each / mark, entry_price=mark,
            ))
        return Book(positions)
