"""The Night Mandate — the signed document that bounds what Ballast may do.

A mandate is issued by the operator before the overnight window and expires at the
next primary open. It is the ONLY authority the enforcer recognises: no mandate,
no order. Its bounds are deliberately arithmetic so that checking them requires no
knowledge of why a trade was proposed.

Signing uses HMAC-SHA256 from the standard library. That is a symmetric scheme --
it proves the mandate was issued by the holder of the secret and has not been
altered, which is what the enforcer needs. It is deliberately NOT presented as a
public-key signature; see docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from dataclasses import asdict, dataclass


class MandateError(RuntimeError):
    pass


@dataclass(frozen=True)
class NightMandate:
    issued_at: dt.datetime
    expires_at: dt.datetime          # the next primary open
    universe: tuple[str, ...]        # rToken spot symbols this mandate covers
    max_hedge_ratio: float = 1.0     # |perp notional| <= spot notional * this
    max_notional_usdt: float = 0.0   # total hedge notional permitted tonight
    max_orders: int = 0              # order count cap for the window
    account: str = "paper"

    def payload(self) -> str:
        d = asdict(self)
        d["issued_at"] = self.issued_at.isoformat()
        d["expires_at"] = self.expires_at.isoformat()
        d["universe"] = list(self.universe)
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    def sign(self, secret: bytes) -> str:
        return hmac.new(secret, self.payload().encode(), hashlib.sha256).hexdigest()

    def verify(self, secret: bytes, signature: str) -> None:
        if not hmac.compare_digest(self.sign(secret), signature):
            raise MandateError("mandate signature does not verify")

    def is_expired(self, now: dt.datetime) -> bool:
        return now >= self.expires_at

    def validate(self) -> None:
        """Structural sanity — catches an operator mistake before the market does."""
        if self.expires_at <= self.issued_at:
            raise MandateError("mandate expires before it is issued")
        if not self.universe:
            raise MandateError("mandate covers no symbols")
        if not 0 < self.max_hedge_ratio <= 1.0:
            raise MandateError("max_hedge_ratio must be in (0, 1] — Ballast never over-hedges")
        if self.max_notional_usdt <= 0:
            raise MandateError("max_notional_usdt must be positive")
        if self.max_orders <= 0:
            raise MandateError("max_orders must be positive")


@dataclass(frozen=True)
class SignedMandate:
    mandate: NightMandate
    signature: str

    @staticmethod
    def issue(mandate: NightMandate, secret: bytes) -> SignedMandate:
        mandate.validate()
        return SignedMandate(mandate=mandate, signature=mandate.sign(secret))
