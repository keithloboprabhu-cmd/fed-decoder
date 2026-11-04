"""Fallback router: Gemini -> Groq -> None (caller uses rules-based text).

On a 429/quota error we back off once, then fall back to the next provider.
Every attempt is logged to .cache/llm_log.jsonl (used by the evals and the
global daily counter).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel

from fed_decoder import config
from fed_decoder.llm.base import LLMResponse, Provider, ProviderUnavailable, RateLimited, ToolSpec
from fed_decoder.llm.gemini import GeminiProvider
from fed_decoder.llm.groq_provider import GroqProvider

LOG_PATH = config.CACHE_DIR / "llm_log.jsonl"
MAX_BACKOFF_S = 12.0

_PROVIDERS: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    if name not in _PROVIDERS:
        _PROVIDERS[name] = GeminiProvider() if name == "gemini" else GroqProvider()
    return _PROVIDERS[name]


def default_order() -> list[str]:
    return ["gemini", "groq"]


def log_event(**kw) -> None:
    try:
        config.CACHE_DIR.mkdir(exist_ok=True)
        kw["ts"] = datetime.now(timezone.utc).isoformat()
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(kw) + "\n")
    except Exception:
        pass


class GuardrailError(Exception):
    pass


def _call_with_backoff(p: Provider, messages, schema, tools, temperature) -> LLMResponse:
    try:
        return p.generate(messages, schema=schema, tools=tools, temperature=temperature)
    except RateLimited as e:
        wait = min(e.retry_after or 4.0, MAX_BACKOFF_S)
        log_event(provider=p.name, event="rate_limited", backoff_s=wait)
        time.sleep(wait)
        return p.generate(messages, schema=schema, tools=tools, temperature=temperature)


def generate(
    messages: list[dict],
    schema: type[BaseModel] | None = None,
    tools: list[ToolSpec] | None = None,
    validate: Callable[[LLMResponse], None] | None = None,
    temperature: float = 0.2,
    providers: list[str] | None = None,
    purpose: str = "",
) -> LLMResponse | None:
    """Return the first valid response, or None if every provider failed.

    `validate` raises GuardrailError (with a message) on ungrounded output.
    A guardrail failure gets exactly one retry with the error fed back; if the
    retry also fails we return None and the caller shows rules-based text.
    """
    order = providers or default_order()
    retried_guardrail = False
    for i, name in enumerate(order):
        p = get_provider(name)
        if not p.available():
            log_event(provider=name, event="skipped_no_key", purpose=purpose)
            continue
        msgs = list(messages)
        for attempt in range(2):
            try:
                resp = _call_with_backoff(p, msgs, schema, tools, temperature)
            except (RateLimited, ProviderUnavailable, ValueError) as e:
                log_event(provider=name, event="failed", error=type(e).__name__, detail=str(e)[:300], purpose=purpose)
                break  # next provider
            except Exception as e:  # pydantic ValidationError, etc.
                log_event(provider=name, event="failed", error=type(e).__name__, detail=str(e)[:300], purpose=purpose)
                break
            if validate is None:
                log_event(provider=name, event="ok", latency_s=round(resp.latency_s, 2), fallback=i > 0, purpose=purpose)
                return resp
            try:
                validate(resp)
                log_event(provider=name, event="ok", latency_s=round(resp.latency_s, 2), fallback=i > 0, guardrail_retry=retried_guardrail, purpose=purpose)
                return resp
            except GuardrailError as g:
                log_event(provider=name, event="guardrail_fail", detail=str(g)[:300], purpose=purpose)
                if retried_guardrail:
                    return None
                retried_guardrail = True
                msgs = msgs + [
                    {"role": "assistant", "content": resp.text},
                    {
                        "role": "user",
                        "content": f"Your answer failed a grounding check: {g}. Rewrite it using only numbers and quotes "
                        "that appear verbatim in the provided context. Do not introduce any other numbers.",
                    },
                ]
    return None
