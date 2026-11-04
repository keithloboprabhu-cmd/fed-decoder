"""Groq free tier, open-weight model (default openai/gpt-oss-120b).

Groq is OpenAI-compatible. We ask for strict `json_schema` output; if the
model rejects it we fall back to `json_object` mode plus pydantic validation.
"""
from __future__ import annotations

import json
import time

from pydantic import BaseModel

from fed_decoder import config
from fed_decoder.llm.base import (
    LLMResponse,
    Provider,
    ProviderUnavailable,
    RateLimited,
    RateLimiter,
    ToolCall,
    ToolSpec,
    parse_json_into,
)

_LIMITER = RateLimiter(config.GROQ_RPM)


def _strictify(schema: dict) -> dict:
    """OpenAI-style strict mode wants additionalProperties=false and every
    property required. Applied recursively, including $defs."""
    s = json.loads(json.dumps(schema))

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for k in ("default", "title"):
                node.pop(k, None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(s)
    return s


class GroqProvider(Provider):
    name = "groq"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or config.GROQ_MODEL
        self._key = api_key or config.groq_key()
        self._client = None
        self._strict_ok = True

    def available(self) -> bool:
        return bool(self._key)

    def _get_client(self):
        if self._client is None:
            if not self._key:
                raise ProviderUnavailable("GROQ_API_KEY not set")
            from groq import Groq

            self._client = Groq(api_key=self._key, max_retries=0)
        return self._client

    @staticmethod
    def _to_messages(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                out.append(
                    {
                        "role": "assistant",
                        "content": m.get("content") or "",
                        "tool_calls": [
                            {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}}
                            for tc in m["tool_calls"]
                        ],
                    }
                )
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            else:
                out.append({"role": m["role"], "content": m["content"]})
        return out

    def _call(self, **kw):
        import groq

        _LIMITER.wait()
        try:
            return self._get_client().chat.completions.create(**kw)
        except groq.RateLimitError as e:
            ra = None
            try:
                ra = float(e.response.headers.get("retry-after"))
            except Exception:
                pass
            raise RateLimited(str(e), ra) from e
        except groq.BadRequestError:
            raise
        except Exception as e:
            raise ProviderUnavailable(str(e)) from e

    def generate(self, messages, schema: type[BaseModel] | None = None, tools: list[ToolSpec] | None = None, temperature: float = 0.2) -> LLMResponse:
        import groq

        kw = dict(model=self.model, messages=self._to_messages(messages), temperature=temperature)
        if tools:
            kw["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}} for t in tools]
            kw["tool_choice"] = "auto"
        elif schema is not None:
            if self._strict_ok:
                kw["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__, "schema": _strictify(schema.model_json_schema()), "strict": True},
                }
            else:
                kw["response_format"] = {"type": "json_object"}
                kw["messages"] = kw["messages"] + [
                    {"role": "user", "content": "Reply with one JSON object matching this schema:\n" + json.dumps(schema.model_json_schema())}
                ]
        t0 = time.time()
        try:
            resp = self._call(**kw)
        except groq.BadRequestError as e:
            if schema is not None and self._strict_ok and not tools:
                msg = str(e).lower()
                if "json_validate_failed" in msg or "failed to generate" in msg:
                    # One output broke the schema: retry this call in JSON mode + pydantic validation.
                    self._strict_ok = False
                    try:
                        return self.generate(messages, schema=schema, tools=tools, temperature=temperature)
                    finally:
                        self._strict_ok = True
                self._strict_ok = False  # strict json_schema unsupported for this model: JSON mode from now on
                return self.generate(messages, schema=schema, tools=tools, temperature=temperature)
            raise ProviderUnavailable(str(e)) from e
        latency = time.time() - t0
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
        text = msg.content or ""
        parsed = parse_json_into(schema, text) if (schema is not None and not calls) else None
        return LLMResponse(text=text, provider=self.name, model=self.model, latency_s=latency, parsed=parsed, tool_calls=calls, raw=resp)
