import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from openai import APITimeoutError, OpenAIError

from app.bedrock_client import DEFAULT_TIMEOUT_SECONDS, BedrockClient, BedrockClientError


def _response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@patch("app.bedrock_client.AsyncOpenAI")
def test_chat_returns_text(mock_openai_cls):
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create = AsyncMock(return_value=_response("Hello there"))

    client = BedrockClient()
    result = asyncio.run(client.chat([{"role": "user", "content": "hi"}]))

    assert result == "Hello there"


@patch("app.bedrock_client.AsyncOpenAI")
def test_chat_empty_response_raises(mock_openai_cls):
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create = AsyncMock(return_value=_response(None))

    client = BedrockClient()

    with pytest.raises(BedrockClientError):
        asyncio.run(client.chat([{"role": "user", "content": "hi"}]))


@patch("app.bedrock_client.AsyncOpenAI")
def test_chat_api_error_raises(mock_openai_cls):
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create = AsyncMock(side_effect=OpenAIError("boom"))

    client = BedrockClient()

    with pytest.raises(BedrockClientError):
        asyncio.run(client.chat([{"role": "user", "content": "hi"}]))


@patch("app.bedrock_client.AsyncOpenAI")
def test_chat_timeout_raises_bedrock_client_error(mock_openai_cls):
    mock_client = mock_openai_cls.return_value
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    mock_client.chat.completions.create = AsyncMock(side_effect=APITimeoutError(request=request))

    client = BedrockClient()

    with pytest.raises(BedrockClientError):
        asyncio.run(client.chat([{"role": "user", "content": "hi"}]))


@patch("app.bedrock_client.AsyncOpenAI")
def test_client_is_constructed_with_a_default_timeout(mock_openai_cls):
    BedrockClient()

    _, kwargs = mock_openai_cls.call_args
    assert kwargs["timeout"] == DEFAULT_TIMEOUT_SECONDS


@patch("app.bedrock_client.AsyncOpenAI")
def test_client_accepts_a_custom_timeout(mock_openai_cls):
    BedrockClient(timeout=5)

    _, kwargs = mock_openai_cls.call_args
    assert kwargs["timeout"] == 5
