"""Thin async wrapper around ``anthropic.AsyncAnthropic``.

The matcher, cover-letter and chat-reply call paths all need the same
two behaviors and nothing more:

* prompt caching on a single static system block (the resume for the
  matcher, the brand voice for letters, the thread history for chat),
* linear backoff retry on HTTP 529 / 429 / transient connection
  errors. We never retry fast — HH-facing rate caps live elsewhere.

Two entry points: ``create_message`` for free-form text output, and
``create_tool_call`` for structured output via a tool schema (used by
the matcher so the model can't return malformed JSON). Both wrapped
behind a single ``Protocol`` so tests can swap in a fake.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol, cast

import anthropic
from loguru import logger

_RETRYABLE_STATUS = {429, 529}
_MAX_ATTEMPTS = 4
_BASE_DELAY_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class AnthropicResult:
    """Free-form text response + usage counters."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """Structured tool-use response. ``input`` is already parsed by the SDK."""

    input: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


class AnthropicClientProtocol(Protocol):
    async def create_message(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AnthropicResult:
        """Send one user message, return text + usage. May raise on persistent failure."""

    async def create_tool_call(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        tool: dict[str, Any],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> ToolCallResult:
        """Force the model to invoke ``tool``; return the parsed input dict + usage."""


class AsyncAnthropicClient:
    """Real-API implementation. One instance per process is enough."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def create_message(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AnthropicResult:
        response = await self._send_with_retry(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=cast(Any, system),
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            cast(str, getattr(block, "text", ""))
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return AnthropicResult(text=text, **_usage_kwargs(response))

    async def create_tool_call(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        tool: dict[str, Any],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> ToolCallResult:
        response = await self._send_with_retry(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=cast(Any, system),
            messages=[{"role": "user", "content": user}],
            tools=cast(Any, [tool]),
            tool_choice=cast(Any, {"type": "tool", "name": tool["name"]}),
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool["name"]:
                payload = getattr(block, "input", None)
                if not isinstance(payload, dict):
                    raise RuntimeError("tool_use block has no parsed input")
                return ToolCallResult(input=cast(dict[str, Any], payload), **_usage_kwargs(response))
        raise RuntimeError(f"model returned no tool_use block for tool {tool['name']!r}")

    async def _send_with_retry(self, **kwargs: Any) -> Any:
        bound = logger.bind(component="anthropic", model=kwargs.get("model"))
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await self._client.messages.create(**kwargs)
            except anthropic.APIStatusError as exc:
                if exc.status_code not in _RETRYABLE_STATUS or attempt == _MAX_ATTEMPTS:
                    raise
                last_error = exc
                delay = _BASE_DELAY_SECONDS * attempt
                bound.warning(
                    "anthropic returned {status} on attempt {n}/{max}; sleeping {d}s",
                    status=exc.status_code,
                    n=attempt,
                    max=_MAX_ATTEMPTS,
                    d=delay,
                )
                await asyncio.sleep(delay)
            except anthropic.APIConnectionError as exc:
                if attempt == _MAX_ATTEMPTS:
                    raise
                last_error = exc
                delay = _BASE_DELAY_SECONDS * attempt
                bound.warning(
                    "anthropic connection error on attempt {n}/{max}; sleeping {d}s: {e}",
                    n=attempt,
                    max=_MAX_ATTEMPTS,
                    d=delay,
                    e=str(exc),
                )
                await asyncio.sleep(delay)
        # Unreachable: every loop path either returns or raises on the last attempt.
        raise RuntimeError("anthropic retry loop exited without a result") from last_error


def _usage_kwargs(response: Any) -> dict[str, Any]:
    usage = response.usage
    return {
        "model": response.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }


__all__ = [
    "AnthropicClientProtocol",
    "AnthropicResult",
    "AsyncAnthropicClient",
    "ToolCallResult",
]
