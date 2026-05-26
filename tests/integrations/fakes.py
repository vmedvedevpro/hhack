"""Test doubles for external integrations (Anthropic, Playwright, ...)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hhack.integrations.anthropic_client import AnthropicResult, ToolCallResult


class FakeAnthropicClient:
    """Canned-response ``AnthropicClientProtocol`` for tests.

    Construct with either a list of canned results (popped FIFO) or a
    callable that receives the same kwargs the protocol method does. The
    list/callable is shared across ``create_message`` and
    ``create_tool_call`` — the matching tests only exercise one path at
    a time so we don't bother splitting them.
    """

    def __init__(
        self,
        responses: list[AnthropicResult | ToolCallResult] | Callable[..., AnthropicResult | ToolCallResult],
    ) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    async def create_message(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AnthropicResult:
        result = self._next(
            mode="message",
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        assert isinstance(result, AnthropicResult), "expected AnthropicResult from canned response"
        return result

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
        result = self._next(
            mode="tool_call",
            model=model,
            system=system,
            user=user,
            tool=tool,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        assert isinstance(result, ToolCallResult), "expected ToolCallResult from canned response"
        return result

    def _next(self, **call: Any) -> AnthropicResult | ToolCallResult:
        self.calls.append(call)
        if callable(self._responses):
            return self._responses(**call)
        if not self._responses:
            raise AssertionError("FakeAnthropicClient ran out of canned responses")
        return self._responses.pop(0)


def fake_result(text: str, *, model: str = "claude-sonnet-4-6") -> AnthropicResult:
    """Build an ``AnthropicResult`` with realistic zero-usage defaults."""
    return AnthropicResult(
        text=text,
        model=model,
        input_tokens=10,
        output_tokens=20,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


def fake_tool_call(
    input_dict: dict[str, Any],
    *,
    model: str = "claude-sonnet-4-6",
) -> ToolCallResult:
    """Build a ``ToolCallResult`` with realistic zero-usage defaults."""
    return ToolCallResult(
        input=input_dict,
        model=model,
        input_tokens=10,
        output_tokens=20,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
