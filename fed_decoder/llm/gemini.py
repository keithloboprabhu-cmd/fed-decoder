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

# The free tier caps requests per day *per model* (20/day each, Nov 2026).
# When a model's daily quota is spent we skip it until the date changes.
_EXHAUSTED: dict[str, str] = {}


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 3600))  # quota resets at midnight Pacific


def _is_daily_quota(err: Exception) -> bool:
    return "PerDay" in str(err)


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
            from google.genai import types

            # Bounded timeout and no hidden SDK retries: an overloaded model
            # should fail fast so the router can fall back to Groq.
            self._client = genai.Client(
                api_key=self._key,
                http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_S * 1000, retry_options=types.HttpRetryOptions(attempts=1)),
            )
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
            elif role == "assistant" and m.get("gemini_content") is not None:
                # Replay Gemini's own content so thought signatures survive (required
                # by Gemini 3 for multi-turn function calling).
                contents.append(m["gemini_content"])
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
        # A conversation that already holds Gemini tool-call content must stay on
        # the model that produced it (thought signatures are model-specific).
        pinned = next((m.get("gemini_model") for m in messages if m.get("gemini_model")), None)
        models = [pinned] if pinned else [self.model] + [m for m in config.GEMINI_FALLBACK_MODELS if m != self.model]
        models = [m for m in models if _EXHAUSTED.get(m) != _today()]
        if not models:
            raise RateLimited("every Gemini model's free daily quota is used up", None)
        resp, used, last_err = None, None, None
        for model in models:
            _LIMITER.wait()
            t0 = time.time()
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(**cfg))
                used = model
                break
            except errors.ClientError as e:
                if e.code == 429 or "RESOURCE_EXHAUSTED" in str(e):
                    if _is_daily_quota(e) and not pinned:
                        _EXHAUSTED[model] = _today()  # this model is done for today: try the next
                        last_err = e
                        continue
                    raise RateLimited(str(e), _retry_after(e)) from e
                if e.code == 404:  # model retired for this account: try the next one
                    last_err = e
                    continue
                raise ProviderUnavailable(str(e)) from e
            except errors.ServerError as e:  # 503 overload: try the next model
                last_err = e
                continue
            except Exception as e:  # network, timeout
                last_err = e
                continue
        if resp is None:
            if last_err is not None and _is_daily_quota(last_err):
                raise RateLimited(f"all Gemini models out of daily quota: {last_err}", None)
            raise ProviderUnavailable(f"all Gemini models failed: {last_err}")
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
        out = LLMResponse(text=text, provider=self.name, model=used, latency_s=latency, parsed=parsed, tool_calls=calls, raw=resp)
        try:
            out.provider_content = resp.candidates[0].content  # type: ignore[attr-defined]
        except Exception:
            out.provider_content = None  # type: ignore[attr-defined]
        return out
