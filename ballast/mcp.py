"""Client for `bitget-mcp-server`, the organiser's read-only US-stock data service.

    https://agent.bitget.com/mcp   (HTTP transport, MCP 2024-11-05)

Ballast's calendar selector is the one component the whole policy rests on: Gate 1b
measured that earnings nights separate risky from ordinary at 3.2x where volatility
manages 1.41x, so a wrong calendar is a wrong decision every time. Until now that
calendar had exactly one source, Nasdaq, and a single source that quietly changes
its answer is indistinguishable from one that is right.

This module is the second opinion. It is deliberately NOT wired into the decision
path - swapping the selector's source days before a submission would invalidate the
record it is meant to support. It cross-checks what was already decided, and
publishes where the two sources disagree.

Three things about the transport, all learned by probing rather than assumed:

CLOUDFLARE REJECTS A DEFAULT PYTHON USER-AGENT. urllib's own UA gets a 403 with
`browser_signature_banned` before the request reaches the server. The same
workaround `earnings.py` already needs for Nasdaq applies here.

THE HANDSHAKE IS THREE STEPS, NOT ONE. `initialize` returns a session id in the
`mcp-session-id` header; the server then requires a `notifications/initialized`
notification (it answers 202) before it will accept a `tools/call`. Skipping it
gets a 404 that looks like a missing endpoint.

SESSIONS DO NOT SURVIVE. A session that answered one call returned 404 on the next,
so this opens one per query rather than pooling. Two extra round trips is the right
price for a client that cannot silently stop working.

Responses arrive as SSE frames (`event: message` / `data: {...}`) rather than plain
JSON, whatever the Accept header asks for.

Zero dependencies, like everything else here.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

ENDPOINT = "https://agent.bitget.com/mcp"
PROTOCOL = "2024-11-05"
TIMEOUT = 30
RETRIES = 3

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class McpUnavailable(RuntimeError):
    """The service could not be reached, or answered something unusable.

    Never swallowed into an empty result: a calendar that cannot be reached is
    unknown, and unknown must not read as "no earnings tonight".
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _post(payload: dict, session: str | None = None) -> tuple[dict, str]:
    headers = {"Content-Type": "application/json", "User-Agent": _UA,
               "Accept": "application/json, text/event-stream"}
    if session:
        headers["mcp-session-id"] = session
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return dict(resp.headers), resp.read().decode()


def _unframe(text: str) -> dict:
    """SSE frames or plain JSON, whichever the server felt like sending."""
    if text.lstrip().startswith("event:"):
        text = "".join(line[6:] for line in text.splitlines()
                       if line.startswith("data: "))
    return json.loads(text) if text.strip() else {}


def call(tool: str, arguments: dict | None = None, retries: int = RETRIES) -> dict:
    """One tool call, with its own session. Raises McpUnavailable, never guesses."""
    last = "not attempted"
    for attempt in range(retries):
        try:
            return _once(tool, arguments)
        except McpUnavailable as exc:
            last = exc.reason
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise McpUnavailable(last)


def _once(tool: str, arguments: dict | None) -> dict:
    try:
        headers, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                                       "clientInfo": {"name": "ballast",
                                                      "version": "1"}}})
        session = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        if not session:
            raise McpUnavailable("initialize returned no session id")
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
        _, body = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": tool,
                                    "arguments": arguments or {}}}, session)
    except urllib.error.HTTPError as exc:
        raise McpUnavailable(f"HTTP {exc.code} from {ENDPOINT}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise McpUnavailable(f"{type(exc).__name__}: {exc}") from exc

    try:
        payload = _unframe(body)
    except json.JSONDecodeError as exc:
        raise McpUnavailable(f"unparseable response: {exc}") from exc
    if "error" in payload:
        raise McpUnavailable(str(payload["error"])[:200])
    content = (payload.get("result") or {}).get("content") or []
    if not content:
        raise McpUnavailable("response carried no content")
    text = content[0].get("text", "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}
    # The tool answers 200 and wraps the upstream's own status. A 503 body that
    # parses cleanly would otherwise be handed back as data, and an empty result
    # would read as "no earnings scheduled tonight" - absence of evidence dressed
    # as evidence of absence, on the one input the whole policy rests on.
    if isinstance(data, dict) and data.get("success") is False:
        raise McpUnavailable(
            f"upstream {data.get('status_code', '?')}: {str(data.get('error'))[:120]}")
    return data


def catalog(category: str | None = None) -> dict:
    """The data catalog: categories, or the entries inside one."""
    return call("guide", {"category": category} if category else {})


def query(entry_id: str, **params) -> dict:
    """Run one catalog entry.

    The argument is `entry_id`, not `id`, and the entry's own parameters go in a
    nested `params` object - passing them flat returns a pydantic validation error
    rather than data. Verified against the live service, not inferred from the
    catalog listing.
    """
    return call("do_query", {"entry_id": entry_id, "params": params})


def available() -> tuple[bool, str]:
    """(reachable, why) - stated on the page rather than assumed."""
    try:
        cats = catalog()
    except McpUnavailable as exc:
        return False, exc.reason
    names = [c.get("key") for c in cats.get("categories", [])]
    return bool(names), f"bitget-mcp-server · categories: {', '.join(map(str, names))}"


if __name__ == "__main__":
    ok, why = available()
    print(f"{'reachable' if ok else 'UNAVAILABLE'} - {why}")
    if ok:
        print(json.dumps(catalog("equity"), ensure_ascii=False, indent=1)[:3000])
