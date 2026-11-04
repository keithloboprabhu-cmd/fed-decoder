"""Google Gemini (free tier via AI Studio key). Uses native JSON-schema output
and native function calling; automatic function calling is disabled so our
own loop executes tools and enforces guardrails."""
from __future__ import annotations

import re
import time
import uuid

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

_LIMITER = RateLimiter(config.GEMINI_RPM)


def _retry_after(err: Exception) -> float | None:
    m = re.search(r"retry in ([\d.]+)s|retryDelay['\"]?: ?['\"]?(\d+)", str(err))
    if not m:
        return None
    return float(m.group(1) or m.group(2))


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or config.GEMINI_MODEL
        self._key = api_key or config.gemini_key()
        self._client = None

    def available(self) -> bool:
        return bool(self._key)

    def _get_client(self):
        if self._client is None:
            if not self._key:
                raise ProviderUnavailable("GEMINI_API_KEY not set")
            from google import genai

            self._client = genai.Client(api_key=self._key)
        return self._client

    @staticmethod
    def _to_contents(messages: list[dict]):
        from google.genai import types

        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system") or None
        contents = []
        for m in messages:
            role = m["role"]
            if role == "system":
                continue
            if role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=m["content"])]))
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append(types.Part(text=m["content"]))
                for tc in m.get("tool_calls") or []:
                    parts.append(types.Part.from_function_call(name=tc["name"], args=tc["args"]))
                contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_function_response(name=m["name"], response={"result": m["content"]})],
                    )
                )
        return system, contents

    def generate(self, messages, schema: type[BaseModel] | None = None, tools: list[ToolSpec] | None = None, temperature: float = 0.2) -> LLMResponse:
        from google.genai import errors, types

        client = self._get_client()
        system, contents = self._to_contents(messages)
        cfg = dict(system_instruction=system, temperature=temperature)
        if tools:
            cfg["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
                        for t in tools
                    ]
                )
            ]
            cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        elif schema is not None:
            cfg["response_mime_type"] = "application/json"
            cfg["response_json_schema"] = schema.model_json_schema()
        _LIMITER.wait()
        t0 = time.time()
        try:
            resp = client.models.generate_content(model=self.model, contents=contents, config=types.GenerateContentConfig(**cfg))
        except errors.ClientError as e:
            if e.code == 429 or "RESOURCE_EXHAUSTED" in str(e):
                raise RateLimited(str(e), _retry_after(e)) from e
            raise ProviderUnavailable(str(e)) from e
        except errors.ServerError as e:
            raise ProviderUnavailable(str(e)) from e
        except Exception as e:  # network etc.
            raise ProviderUnavailable(str(e)) from e
        latency = time.time() - t0
        calls = [ToolCall(id=uuid.uuid4().hex[:8], name=fc.name, args=dict(fc.args or {})) for fc in (resp.function_calls or [])]
        text = ""
        try:
            text = resp.text or ""
        except Exception:
            text = ""
        parsed = None
        if schema is not None and not calls:
            parsed = parse_json_into(schema, text)
        return LLMResponse(text=text, provider=self.name, model=self.model, latency_s=latency, parsed=parsed, tool_calls=calls, raw=resp)
