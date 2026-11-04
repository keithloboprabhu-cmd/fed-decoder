"""Provider-neutral LLM interface.

Messages use one internal shape so a conversation can move between providers
mid-stream when one hits its quota:
  {"role": "system" | "user" | "assistant" | "tool",
   "content": str,
   "tool_calls": [{"id", "name", "args"}],   # assistant only
   "tool_call_id": str, "name": str}          # tool only
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class RateLimited(Exception):
    """429 / quota exhausted. `retry_after` in seconds if the provider said."""

    def __init__(self, msg: str = "", retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class ProviderUnavailable(Exception):
    """Missing key, network error, or any non-retryable failure."""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema (object)


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_s: float
    parsed: BaseModel | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None

    @property
    def label(self) -> str:
        return {"gemini": "Gemini Flash", "groq": "Groq (open-weight)"}.get(self.provider, self.provider)


class RateLimiter:
    """Sliding-window requests-per-minute limiter shared by all callers."""

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self, block: bool = True) -> bool:
        while True:
            with self.lock:
                now = time.time()
                while self.calls and now - self.calls[0] > 60:
                    self.calls.popleft()
                if len(self.calls) < self.rpm:
                    self.calls.append(now)
                    return True
                sleep_for = 60 - (now - self.calls[0]) + 0.05
            if not block:
                return False
            time.sleep(sleep_for)


class Provider:
    name = "base"
    model = ""

    def available(self) -> bool:
        raise NotImplementedError

    def generate(
        self,
        messages: list[dict],
        schema: type[BaseModel] | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        raise NotImplementedError


def parse_json_into(schema: type[BaseModel], text: str) -> BaseModel:
    """Tolerant JSON extraction for providers without strict schema support."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{") :]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return schema.model_validate(json.loads(t[start : end + 1]))
