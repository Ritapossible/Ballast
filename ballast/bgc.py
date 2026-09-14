"""Execution through the Bitget Agent Hub CLI (`bgc`), in paper-trading mode.

Ballast's own `PaperExecutor` simulates a fill against the observed mark. That is
honest, reproducible and needs no credentials - and it is also Ballast marking its
own homework. The Agent Hub is the organiser's execution surface: `bgc` routes an
order to Bitget's Demo environment, which prices and fills it, and hands back a
fill Ballast did not compute.

The authority boundary is unchanged and is the reason this was a small change.
`execute()` takes an `Admitted` and nothing else - no symbol, no side, no size - so
the venue swaps underneath the enforcer rather than beside it. A model that reaches
this module still cannot express a directional trade, because it has no way to build
the only argument the method accepts.

Three things this deliberately does NOT do:

- **Trade live.** `--paper-trading` is not optional here; it is appended by this
  module and there is no parameter to turn it off. `--read-only` would refuse the
  order outright, so it is not used, but nothing in Ballast can reach a live venue
  through this path.
- **Invent a fill.** If `bgc` is absent, unconfigured, times out, or answers with
  something this module cannot parse, it raises `BgcUnavailable`. The caller falls
  back to `PaperExecutor` and the ledger records which venue actually filled. A
  silent substitution would put a simulated fill on the chain wearing the Agent
  Hub's name.
- **Hold credentials.** The Demo API key is read from the environment, never
  written to the ledger, the pages, or an argv the process table can read.

Enable with BALLAST_VENUE=bgc. Unset, Ballast runs exactly as before.

UNVERIFIED, and deliberately so: the order verb below is Agent Hub's documented
shape, but the published README does not spell out the argv for placing an order,
and no `bgc` has been run against this code. `bgc discover` is the CLI's own tool
surface - run `python -m ballast.preflight` on a machine that has the CLI and it
prints what the binary actually exposes. If the verb is wrong the order fails, the
failure is typed, the fill is simulated and the ledger row says so; nothing is
silently mis-recorded. But it also would not route, so confirm before relying on it.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess

from .costs import PERP_TAKER_FEE, SLIPPAGE_BP
from .enforcer import Admitted
from .executor import Fill

# The order verb. Confirm against `bgc discover` before enabling - see the module
# docstring. Kept as a constant so correcting it is a one-line change.
ORDER_VERB = ("trade", "place-order")
BGC_BIN = "bgc"
TIMEOUT_S = 45
VENUE_ENV = "BALLAST_VENUE"
KEY_ENV = "BITGET_API_KEY"
# Bitget signs REST requests with a triplet, not a single key, and the Agent Hub
# README says credentials are "read from environment variables only" without naming
# them. So the key is required and these are reported-but-not-required: if the CLI
# spells them differently, demanding our guess would block a correct setup, and if
# it does want them, a missing one shows up in preflight instead of at 21:00.
COMPANION_ENV = ("BITGET_SECRET_KEY", "BITGET_PASSPHRASE")


class BgcUnavailable(RuntimeError):
    """`bgc` could not be used for this order. Carries why, for the ledger.

    Every failure is typed rather than swallowed. news.py taught this lesson: a
    bare `except Exception` turned a broken feed into an empty one, and the loop
    could not tell "nothing happened" from "we failed to look".
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def requested() -> bool:
    """True when the operator asked for Agent Hub execution."""
    return os.environ.get(VENUE_ENV, "").strip().lower() == "bgc"


def available() -> tuple[bool, str]:
    """Whether an order could be routed right now, and why not if it could not."""
    if not requested():
        return False, f"{VENUE_ENV} is not set to bgc"
    if shutil.which(BGC_BIN) is None:
        return False, f"{BGC_BIN} is not on PATH"
    if not os.environ.get(KEY_ENV):
        return False, f"{KEY_ENV} is not set"
    missing = missing_companions()
    if missing:
        return True, f"ready, but {', '.join(missing)} unset - signing may fail"
    return True, "ready"


def missing_companions() -> list[str]:
    """Credential vars Bitget's request signing usually needs, that are not set."""
    return [name for name in COMPANION_ENV if not os.environ.get(name)]


def _run(args: list[str]) -> dict:
    """Run bgc and return its parsed JSON. Every failure mode is named."""
    try:
        proc = subprocess.run(
            [BGC_BIN, *args, "--paper-trading", "--json"],
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
    except FileNotFoundError:
        raise BgcUnavailable(f"{BGC_BIN} is not on PATH") from None
    except subprocess.TimeoutExpired:
        raise BgcUnavailable(f"timeout after {TIMEOUT_S}s") from None
    except OSError as exc:
        raise BgcUnavailable(f"could not run {BGC_BIN}: {exc}") from None

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise BgcUnavailable(
            f"exit {proc.returncode}: {detail[-1][:160] if detail else 'no output'}")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BgcUnavailable(f"unparseable response: {exc}") from None
    if not isinstance(parsed, dict):
        raise BgcUnavailable(f"expected an object, got {type(parsed).__name__}")
    return parsed


def _number(payload: dict, *names: str) -> float | None:
    """Pull the first present numeric field. Response shapes differ by verb."""
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            raise BgcUnavailable(f"field {name!r} is not a number: {value!r}") from None
    return None


class BgcExecutor:
    """Places the admitted hedge through `bgc --paper-trading`.

    Same signature as PaperExecutor, same Fill out, and the same refusal to accept
    anything but an Admitted. The difference is who computes the fill price.
    """

    def __init__(self, fee: float = PERP_TAKER_FEE, slippage_bp: float = SLIPPAGE_BP):
        self.fee = fee
        self.slippage_bp = slippage_bp

    def execute(self, admitted: Admitted, mark: float, at: dt.datetime) -> Fill:
        if not isinstance(admitted, Admitted):
            raise TypeError(
                "BgcExecutor.execute requires an Admitted issued by the enforcer; "
                f"got {type(admitted).__name__}")
        ok, why = available()
        if not ok:
            raise BgcUnavailable(why)

        intent = admitted.intent
        if mark <= 0:
            raise ValueError(f"unusable mark for {intent.perp_symbol}: {mark}")
        if intent.notional_usdt <= 0:
            raise ValueError("notional must be positive")

        payload = _run([
            *ORDER_VERB,
            "--symbol", intent.perp_symbol,
            "--side", intent.side,
            "--order-type", "market",
            "--notional", f"{intent.notional_usdt:.2f}",
        ])

        price = _number(payload, "avgPrice", "average_price", "price", "fillPrice")
        if price is None or price <= 0:
            raise BgcUnavailable(f"no usable fill price in response: {sorted(payload)}")
        filled = _number(payload, "notional", "filledNotional", "notional_usdt")
        fee = _number(payload, "fee", "fee_usdt", "fees")

        notional = filled if filled and filled > 0 else intent.notional_usdt
        # bgc returns the venue's own fee; fall back to our schedule if it does not.
        fee_usdt = abs(fee) if fee is not None else notional * self.fee
        # Slippage is measured against the mark we decided on, not assumed.
        realised_bp = abs(price - mark) / mark * 1e4

        return Fill(
            perp_symbol=intent.perp_symbol, side=intent.side,
            notional_usdt=notional, price=price, fee_usdt=fee_usdt,
            slippage_bp=round(realised_bp, 2), at=at, paper=True,
        )


def discover() -> tuple[bool, str]:
    """Ask the CLI what it actually exposes, and whether our order verb is there.

    Read-only: `bgc discover` places nothing. This exists because the order argv
    above is inferred from documentation rather than from a binary we have run, and
    a scheduled night is a poor place to find that out.
    """
    if shutil.which(BGC_BIN) is None:
        return False, f"{BGC_BIN} is not on PATH"
    try:
        proc = subprocess.run([BGC_BIN, "discover"], capture_output=True, text=True,
                              timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"could not run {BGC_BIN} discover: {exc}"
    if proc.returncode != 0:
        return False, f"discover exited {proc.returncode}"
    surface = proc.stdout
    verb = " ".join(ORDER_VERB)
    if verb in surface or ORDER_VERB[-1] in surface:
        return True, f"{verb!r} is on the tool surface"
    return False, (f"{verb!r} NOT found on the tool surface - correct "
                   f"bgc.ORDER_VERB before enabling")
