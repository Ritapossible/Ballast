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

VERIFIED against bgc 1.x on 2026-09-14 via `bgc discover --tool order --action
place`. The first cut of this module guessed `trade place-order --notional`; every
part of that was wrong. The real call is

    bgc order --action place --category USDT-FUTURES --symbol TSLAUSDT \
        --side sell --orderType market --qty <BASE COIN> --paper-trading

Two traps worth naming. `qty` is denominated in the BASE coin for USDT futures, not
in USDT - Ballast sizes in notional, so it divides by the mark. And responses are
wrapped: the payload lives under `data`, not at the top level.

`--paper-trading` routes writes to Bitget's demo environment and the CLI's own help
says it "needs demo credentials". A live-account key is therefore expected to fail
here, loudly and typed, rather than to place a real order.
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

# Verified against `bgc discover --tool order --action place` (operationId
# placeOrder, POST /api/v3/trade/place-order).
ORDER_VERB = ("order", "--action", "place")
# Stock perps are USDT-margined futures. Required by the API, no default.
CATEGORY = "USDT-FUTURES"
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
            [BGC_BIN, *args, "--paper-trading"],
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
    except FileNotFoundError:
        raise BgcUnavailable(f"{BGC_BIN} is not on PATH") from None
    except subprocess.TimeoutExpired:
        raise BgcUnavailable(f"timeout after {TIMEOUT_S}s") from None
    except OSError as exc:
        raise BgcUnavailable(f"could not run {BGC_BIN}: {exc}") from None

    if proc.returncode != 0:
        raise BgcUnavailable(f"exit {proc.returncode}: {_explain(proc)}")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BgcUnavailable(f"unparseable response: {exc}") from None
    if not isinstance(parsed, dict):
        raise BgcUnavailable(f"expected an object, got {type(parsed).__name__}")
    # bgc can report a refusal on a zero exit, so the envelope is checked too.
    if parsed.get("ok") is False:
        raise BgcUnavailable(_error_text(parsed) or "refused without a reason")
    # Every response is {"endpoint": ..., "requestTime": ..., "data": {...}}.
    body = parsed.get("data", parsed)
    if not isinstance(body, dict):
        raise BgcUnavailable(f"data is {type(body).__name__}, not an object")
    return body


def _error_text(parsed: dict) -> str:
    """Pull the human-readable half out of bgc's error envelope."""
    err = parsed.get("error")
    if not isinstance(err, dict):
        return ""
    parts = [str(err.get("message", "")).strip(), str(err.get("suggestion", "")).strip()]
    return " ".join(p for p in parts if p)[:200]


def _explain(proc: subprocess.CompletedProcess[str]) -> str:
    """Why bgc failed, in words.

    It prints a pretty JSON error envelope, so the previous version of this - the
    last line of output - reported the string "}" and told nobody anything.
    """
    raw = (proc.stdout or "") + (proc.stderr or "")
    try:
        text = _error_text(json.loads(raw))
        if text:
            return text
    except json.JSONDecodeError:
        pass
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    return lines[-1][:160] if lines else "no output"


def _soft_number(payload: dict, *names: str) -> float | None:
    """Like _number, but never raises - for use after an order may already exist."""
    for name in names:
        try:
            value = payload.get(name)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


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
        # Provenance for the order just placed: venue order id, and whether the
        # price came from the venue or from the mark. Read by the caller and written
        # to the ledger row, so the record never implies a fill the venue did not
        # report. Kept off Fill to leave the Executor protocol unchanged.
        self.last_order: dict = {}

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

        # qty is BASE COIN for USDT futures; Ballast sizes in USDT notional.
        qty = intent.notional_usdt / mark

        payload = _run([
            *ORDER_VERB,
            "--category", CATEGORY,
            "--symbol", intent.perp_symbol,
            "--side", intent.side,
            "--orderType", "market",
            "--qty", f"{qty:.8f}".rstrip("0").rstrip("."),
        ])

        # PAST THIS LINE THE ORDER MAY EXIST. placeOrder returns an id, not a fill,
        # so nothing below may raise: a caller that fell back here would simulate a
        # fill for an order the venue is already holding, and the ledger would show
        # one hedge where two were placed. Anything missing is recorded as missing.
        order_id = payload.get("orderId") or payload.get("clientOid")

        price = _soft_number(payload, "avgPrice", "priceAvg", "fillPrice", "price")
        source = "venue"
        if price is None or price <= 0:
            # Expected: a market placement acknowledges, it does not report a fill.
            price, source = mark, "observed mark (venue returned no fill price)"

        filled = _soft_number(payload, "notional", "filledNotional")
        notional = filled if filled and filled > 0 else intent.notional_usdt
        fee = _soft_number(payload, "fee", "fees")
        fee_usdt = abs(fee) if fee is not None else notional * self.fee

        fill = Fill(
            perp_symbol=intent.perp_symbol, side=intent.side,
            notional_usdt=notional, price=price,
            fee_usdt=fee_usdt,
            slippage_bp=round(abs(price - mark) / mark * 1e4, 2),
            at=at, paper=True,
        )
        self.last_order = {"order_id": order_id, "price_source": source,
                           "qty": round(qty, 8)}
        return fill


def discover() -> tuple[bool, str]:
    """Confirm the order operation exists and that our argv is accepted.

    Two steps, both read-only. `discover` proves the verb resolves; then a
    `--dry-run` placement proves the exact flags and units are accepted and echoes
    what WOULD be sent, without sending it. The first version of this module shipped
    an argv that was wrong in four places, and only a probe like this catches that
    before a night depends on it.
    """
    if shutil.which(BGC_BIN) is None:
        return False, f"{BGC_BIN} is not on PATH"
    probe = [*ORDER_VERB, "--category", CATEGORY, "--symbol", "TSLAUSDT",
             "--side", "sell", "--orderType", "market", "--qty", "1", "--dry-run"]
    try:
        payload = _run(probe)
    except BgcUnavailable as exc:
        return False, f"dry-run rejected: {exc.reason}"
    would = payload.get("wouldSend")
    if not isinstance(would, dict):
        return False, f"dry-run returned no wouldSend: {sorted(payload)}"
    missing = [k for k in ("category", "symbol", "side", "orderType", "qty")
               if k not in would]
    if missing:
        return False, f"dry-run dropped {missing} - argv is wrong"
    return True, f"dry-run accepted: {payload.get('operationId', 'placeOrder')}"
