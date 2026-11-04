"""LLM layer: one `generate(messages, schema=None, tools=None)` interface,
Gemini -> Groq -> None (rules-based) fallback."""
from fed_decoder.llm.base import LLMResponse, ToolSpec  # noqa: F401
from fed_decoder.llm.router import GuardrailError, generate  # noqa: F401
