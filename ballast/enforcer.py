"""The enforcer — the component that makes Ballast's central claim structural.

    Ballast cannot place a bet. Every order it is capable of emitting is opposite
    in sign to, and bounded in size by, a spot position already held.

The enforcer holds the only write-scoped credential and admits an order only if
every rule below passes. It never sees the model's reasoning or the engine's
rationale: it does arithmetic against a signed mandate and an observed position
book. If the reasoning layer were fully compromised, the worst reachable state is
an unwanted hedge, bounded by a position that already exists.

Deployment note: in production this runs as a separate process. The class boundary
here is the seam that split follows; the rules are identical either way.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .mandate import SignedMandate

# Rule identifiers are stable strings: they appear in the ledger and in the
# red-team suite, so renaming one is a breaking change.
RULE_SIGNATURE = "mandate_signature"
RULE_EXPIRED = "mandate_expired"
RULE_UNIVERSE = "symbol_outside_universe"
RULE_NO_POSITION = "no_spot_position"
RULE_NOT_OPPOSITE = "not_opposite_to_position"
RULE_RATIO = "exceeds_max_hedge_ratio"
RULE_NOTIONAL = "exceeds_night_notional"
RULE_ORDER_COUNT = "exceeds_order_count"
RULE_NONPOSITIVE = "non_positive_size"


@dataclass(frozen=True)
class OrderIntent:
    spot_symbol: str        # the position being protected, e.g. RTSLAUSDT
    perp_symbol: str        # the hedge leg, e.g. TSLAUSDT
    side: str               # "sell" (short the perp) or "buy" (unwind)
    notional_usdt: float
    reason: str = ""


# Only this module can mint an admission. The executor demands one, so an order
# that never passed the enforcer cannot be constructed to hand it - the rule stops
# being a convention the caller has to remember and becomes a type error.
_ADMISSION = object()


class Admitted:
    """Proof that an intent passed every rule. Issued by Enforcer.evaluate only.

    The claim this project is built on is that Ballast cannot place a bet. That was
    previously true only because night.py happened to check the verdict before
    calling the executor: the executor itself took a symbol, a side and a size, so
    any new code path that forgot the check was a naked directional order, and the
    red-team suite would not have caught it - those tests drive the enforcer, not
    the executor.
    """

    __slots__ = ("intent", "rule")

    def __init__(self, intent: OrderIntent, token: object = None):
        if token is not _ADMISSION:
            raise TypeError(
                "Admitted cannot be constructed directly - it is issued by "
                "Enforcer.evaluate() and only to an intent that passed every rule")
        self.intent = intent
        self.rule = None

    def __repr__(self) -> str:
        return f"Admitted({self.intent.perp_symbol} {self.intent.side} " \
               f"{self.intent.notional_usdt:.2f})"


@dataclass(frozen=True)
class Verdict:
    admitted: bool
    rule: str | None = None
    detail: str = ""
    capped_notional: float | None = None
    # Present only when admitted. The executor will not act without it.
    admission: Admitted | None = None

    @property
    def rejected(self) -> bool:
        return not self.admitted


class Enforcer:
    """Stateful across one overnight window: counts orders and notional used."""

    def __init__(self, signed: SignedMandate, secret: bytes):
        signed.mandate.verify(secret, signed.signature)   # raises if tampered
        self._mandate = signed.mandate
        self._orders_used = 0
        self._notional_used = 0.0

    @property
    def mandate(self):
        return self._mandate

    def evaluate(self, intent: OrderIntent, positions: dict[str, float],
                 now: dt.datetime) -> Verdict:
        """positions: {spot_symbol: signed notional USDT}. Long is positive."""
        m = self._mandate

        if intent.notional_usdt <= 0:
            return Verdict(False, RULE_NONPOSITIVE, "order size must be positive")

        if m.is_expired(now):
            return Verdict(False, RULE_EXPIRED, f"mandate expired at {m.expires_at.isoformat()}")

        if intent.spot_symbol not in m.universe:
            return Verdict(False, RULE_UNIVERSE, f"{intent.spot_symbol} not in mandate universe")

        held = positions.get(intent.spot_symbol, 0.0)
        if held == 0:
            return Verdict(False, RULE_NO_POSITION,
                           f"no spot position in {intent.spot_symbol} to hedge")

        # A hedge opposes the position. Long spot -> sell perp; short spot -> buy perp.
        required_side = "sell" if held > 0 else "buy"
        if intent.side != required_side:
            return Verdict(False, RULE_NOT_OPPOSITE,
                           f"holding {held:+.2f} requires side={required_side}, got {intent.side}")

        ceiling = abs(held) * m.max_hedge_ratio
        if intent.notional_usdt > ceiling + 1e-9:
            return Verdict(False, RULE_RATIO,
                           f"{intent.notional_usdt:.2f} exceeds {ceiling:.2f}",
                           capped_notional=ceiling)

        if self._notional_used + intent.notional_usdt > m.max_notional_usdt + 1e-9:
            remaining = max(0.0, m.max_notional_usdt - self._notional_used)
            return Verdict(False, RULE_NOTIONAL,
                           f"night notional budget exhausted ({remaining:.2f} left)",
                           capped_notional=remaining or None)

        if self._orders_used >= m.max_orders:
            return Verdict(False, RULE_ORDER_COUNT, f"order cap {m.max_orders} reached")

        return Verdict(True, admission=Admitted(intent, _ADMISSION))

    def commit(self, intent: OrderIntent) -> None:
        """Record an admitted order against the night's budget."""
        self._orders_used += 1
        self._notional_used += intent.notional_usdt

    @property
    def usage(self) -> dict:
        return {"orders": self._orders_used, "notional_usdt": round(self._notional_used, 2)}
