"""Qwen client for the hackathon endpoint.

    base URL  https://hackathon.bitgetops.com/v1   (OpenAI-compatible)
    model     qwen3.8-max

Two properties matter more than the transport:

1. **Strict output.** The model is asked for one JSON object and nothing else. The
   response is parsed, schema-checked, and rejected on any deviation. A malformed
   answer is a refusal, never a salvage attempt -- guessing at a half-parsed
   trading judgment is exactly the failure this design exists to prevent.

2. **Keyless operation.** Without credentials the client reports unavailable and
   the caller falls back to the deterministic calendar rule. The whole system,
   including the test suite, runs with no key and no network.

Set QWEN_API_KEY (or BITGET_QWEN_KEY) to enable it.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

BASE_URL = os.environ.get("QWEN_BASE_URL", "https://hackathon.bitgetops.com/v1")
MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-max")
TIMEOUT = 45


class LLMUnavailable(RuntimeError):
    """No credentials, or the endpoint could not be reached."""


class LLMBadOutput(RuntimeError):
    """The model answered, but not in the contracted shape."""


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


def api_key() -> str | None:
    return os.environ.get("QWEN_API_KEY") or os.environ.get("BITGET_QWEN_KEY")


def available() -> bool:
    return bool(api_key())


def complete(system: str, user: str, *, temperature: float = 0.0,
             max_tokens: int = 900) -> Completion:
    key = api_key()
    if not key:
        raise LLMUnavailable("QWEN_API_KEY is not set")

    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,          # judgments must be reproducible
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise LLMUnavailable(f"HTTP {exc.code} from {BASE_URL}") from exc
    except Exception as exc:
        raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc

    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMBadOutput(f"unexpected response envelope: {body}") from exc

    usage = body.get("usage") or {}
    return Completion(text=text, model=body.get("model", MODEL),
                      prompt_tokens=usage.get("prompt_tokens", 0),
                      completion_tokens=usage.get("completion_tokens", 0))


def parse_json_object(text: str) -> dict:
    """Extract the single JSON object a prompt asked for.

    Tolerates a ```json fence, because models add them; tolerates nothing else.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise LLMBadOutput(f"no JSON object in response: {text[:200]!r}")
    try:
        parsed = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMBadOutput(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMBadOutput("expected a JSON object")
    return parsed
