"""Scriptable fake providers for exercising the LLM paths without API keys."""
from __future__ import annotations

from fed_decoder.llm import router
from fed_decoder.llm.base import LLMResponse, Provider, RateLimited, ToolCall, parse_json_into


class FakeProvider(Provider):
    """`script` is a list of items consumed one per call: an Exception to
    raise, a str to return as text (parsed into the schema if one is given),
    or a list of (name, args) tool calls."""

    def __init__(self, name: str, script: list):
        self.name = name
        self.model = f"fake-{name}"
        self.script = list(script)
        self.calls: list[dict] = []

    def available(self) -> bool:
        return True

    def generate(self, messages, schema=None, tools=None, temperature=0.2):
        self.calls.append({"messages": messages, "schema": schema, "tools": tools})
        item = self.script.pop(0) if self.script else "no more script"
        if isinstance(item, Exception):
            raise item
        if isinstance(item, list):
            return LLMResponse("", self.name, self.model, 0.01, tool_calls=[ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(item)])
        parsed = parse_json_into(schema, item) if schema is not None else None
        return LLMResponse(item, self.name, self.model, 0.01, parsed=parsed)


def install(**providers: FakeProvider) -> None:
    router._PROVIDERS.clear()
    router._PROVIDERS.update(providers)
    router.MAX_BACKOFF_S = 0.0


def rate_limited() -> RateLimited:
    return RateLimited("429 quota", retry_after=0.0)
