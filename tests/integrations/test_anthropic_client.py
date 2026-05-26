from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest

from hhack.integrations.anthropic_client import AsyncAnthropicClient


class _Block:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Usage:
    def __init__(self) -> None:
        self.input_tokens = 100
        self.output_tokens = 50
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 40


class _Response:
    def __init__(self, text: str = "ok") -> None:
        self.content = [_Block(text)]
        self.model = "claude-sonnet-4-6"
        self.usage = _Usage()


def _api_status_error(status: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=status, request=request)
    return anthropic.APIStatusError(message=f"http {status}", response=response, body=None)


def _patch_client(client: AsyncAnthropicClient, mock: AsyncMock) -> AsyncMock:
    client._client.messages.create = mock  # type: ignore[method-assign]
    return mock


async def test_retries_on_529_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # Skip the real backoff sleeps so the test runs fast.
    sleep_mock = AsyncMock()
    monkeypatch.setattr("hhack.integrations.anthropic_client.asyncio.sleep", sleep_mock)

    client = AsyncAnthropicClient(api_key="test-key")
    create = _patch_client(
        client,
        AsyncMock(side_effect=[_api_status_error(529), _api_status_error(529), _Response("done")]),
    )

    result = await client.create_message(
        model="claude-sonnet-4-6",
        system=[{"type": "text", "text": "sys"}],
        user="hi",
        max_tokens=10,
    )

    assert result.text == "done"
    assert create.await_count == 3
    # Two sleeps because the first two attempts failed.
    assert sleep_mock.await_count == 2


async def test_does_not_retry_on_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hhack.integrations.anthropic_client.asyncio.sleep", AsyncMock())
    client = AsyncAnthropicClient(api_key="test-key")
    _patch_client(client, AsyncMock(side_effect=_api_status_error(400)))

    with pytest.raises(anthropic.APIStatusError):
        await client.create_message(
            model="claude-sonnet-4-6",
            system=[],
            user="hi",
            max_tokens=10,
        )


async def test_gives_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hhack.integrations.anthropic_client.asyncio.sleep", AsyncMock())
    client = AsyncAnthropicClient(api_key="test-key")
    create_mock = _patch_client(client, AsyncMock(side_effect=_api_status_error(529)))

    with pytest.raises(anthropic.APIStatusError):
        await client.create_message(
            model="claude-sonnet-4-6",
            system=[],
            user="hi",
            max_tokens=10,
        )
    # 4 attempts: the initial call plus three retries.
    assert create_mock.await_count == 4


async def test_extracts_usage_fields_from_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncAnthropicClient(api_key="test-key")
    _patch_client(client, AsyncMock(return_value=_Response("hello")))

    result = await client.create_message(
        model="claude-sonnet-4-6",
        system=[],
        user="hi",
        max_tokens=10,
    )

    assert result.text == "hello"
    assert result.input_tokens == 100
    assert result.cache_read_input_tokens == 40


async def test_handles_usage_without_cache_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncAnthropicClient(api_key="test-key")
    response = _Response("hi")
    # Older SDK responses may not carry cache_* counters at all.
    del response.usage.cache_creation_input_tokens
    del response.usage.cache_read_input_tokens
    _patch_client(client, AsyncMock(return_value=response))

    result = await client.create_message(
        model="claude-sonnet-4-6",
        system=[],
        user="hi",
        max_tokens=10,
    )
    assert result.cache_creation_input_tokens == 0
    assert result.cache_read_input_tokens == 0


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, name: str, input_dict: dict[str, Any]) -> None:
        self.name = name
        self.input = input_dict


class _ToolResponse:
    def __init__(self, name: str, input_dict: dict[str, Any]) -> None:
        self.content = [_ToolUseBlock(name, input_dict)]
        self.model = "claude-sonnet-4-6"
        self.usage = _Usage()


async def test_create_tool_call_returns_parsed_input(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncAnthropicClient(api_key="test-key")
    tool = {"name": "score_match", "input_schema": {"type": "object"}}
    _patch_client(
        client,
        AsyncMock(return_value=_ToolResponse("score_match", {"score": 0.7, "rationale": "ok"})),
    )

    result = await client.create_tool_call(
        model="claude-sonnet-4-6",
        system=[{"type": "text", "text": "sys"}],
        user="hi",
        tool=tool,
        max_tokens=100,
    )

    assert result.input == {"score": 0.7, "rationale": "ok"}
    assert result.model == "claude-sonnet-4-6"
    assert result.input_tokens == 100


async def test_create_tool_call_raises_when_no_tool_use_block(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncAnthropicClient(api_key="test-key")
    tool = {"name": "score_match", "input_schema": {"type": "object"}}
    _patch_client(client, AsyncMock(return_value=_Response("just text, no tool block")))

    with pytest.raises(RuntimeError, match="no tool_use block"):
        await client.create_tool_call(
            model="claude-sonnet-4-6",
            system=[],
            user="hi",
            tool=tool,
            max_tokens=10,
        )
