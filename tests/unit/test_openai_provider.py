"""Testes unitarios do OpenAIProvider (httpx.MockTransport, sem rede real)."""
from __future__ import annotations

import httpx
import pytest

from core.llm.providers.base import ChatMessage
from core.llm.providers.openai_provider import LLMProviderError, OpenAIProvider
from conftest import make_mock_provider

pytestmark = pytest.mark.unit


def _ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "gpt-4o-mini",
            "choices": [{"message": {"role": "assistant", "content": "pong"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        },
    )


def test_init_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="api_key"):
        OpenAIProvider(api_key=None)


def test_init_reads_env_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    p = OpenAIProvider()
    assert p.api_key == "env-key"


def test_base_url_strips_trailing_slash():
    p = OpenAIProvider(api_key="k", base_url="http://x/v1/")
    assert p.base_url == "http://x/v1"


async def test_chat_builds_correct_payload(mock_provider_factory):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured.update(json.loads(request.content))
        return _ok_response(request)

    p = mock_provider_factory(handler, model="gpt-4o-mini")
    msgs = [
        ChatMessage(role="system", content="be brief"),
        ChatMessage(role="user", content="ping"),
    ]
    await p.chat(msgs, temperature=0.3, max_tokens=50)

    assert captured["model"] == "gpt-4o-mini"
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 50
    assert captured["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "ping"},
    ]


async def test_chat_passes_extra_kwargs(mock_provider_factory):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured.update(json.loads(request.content))
        return _ok_response(request)

    p = mock_provider_factory(handler)
    await p.chat([ChatMessage("user", "hi")], top_p=0.9, presence_penalty=0.5)
    assert captured["top_p"] == 0.9
    assert captured["presence_penalty"] == 0.5


async def test_chat_omits_none_kwargs(mock_provider_factory):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured.update(json.loads(request.content))
        return _ok_response(request)

    p = mock_provider_factory(handler)
    await p.chat([ChatMessage("user", "hi")], max_tokens=None, top_p=None)
    assert "max_tokens" not in captured
    assert "top_p" not in captured


async def test_chat_parses_response(mock_provider_factory):
    p = mock_provider_factory(_ok_response)
    r = await p.chat([ChatMessage("user", "ping")])
    assert r.content == "pong"
    assert r.model == "gpt-4o-mini"
    assert r.provider == "openai"
    assert r.prompt_tokens == 10
    assert r.completion_tokens == 2
    assert r.total_tokens == 12
    assert r.latency_ms >= 0
    assert p.calls == 1


async def test_chat_null_content_becomes_empty(mock_provider_factory):
    def handler(request):
        return httpx.Response(200, json={
            "model": "m",
            "choices": [{"message": {"content": None}}],
            "usage": {},
        })

    p = mock_provider_factory(handler)
    r = await p.chat([ChatMessage("user", "x")])
    assert r.content == ""
    assert r.total_tokens == 0


async def test_malformed_response_raises(mock_provider_factory):
    def handler(request):
        return httpx.Response(200, json={"choices": []})

    p = mock_provider_factory(handler)
    with pytest.raises(LLMProviderError, match="inesperada"):
        await p.chat([ChatMessage("user", "x")])


async def test_retry_on_5xx_then_success(mock_provider_factory):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="overloaded")
        return _ok_response(request)

    p = mock_provider_factory(handler, max_retries=3)
    r = await p.chat([ChatMessage("user", "x")])
    assert r.content == "pong"
    assert calls["n"] == 3


async def test_retry_on_429_then_success(mock_provider_factory):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="rate limit")
        return _ok_response(request)

    p = mock_provider_factory(handler, max_retries=3)
    r = await p.chat([ChatMessage("user", "x")])
    assert r.content == "pong"
    assert calls["n"] == 2


async def test_retry_exhausted_raises(mock_provider_factory):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    p = mock_provider_factory(handler, max_retries=3)
    with pytest.raises(LLMProviderError, match="apos 3 tentativas"):
        await p.chat([ChatMessage("user", "x")])
    assert calls["n"] == 3


async def test_4xx_no_retry(mock_provider_factory):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    p = mock_provider_factory(handler, max_retries=3)
    with pytest.raises(LLMProviderError, match="HTTP 400"):
        await p.chat([ChatMessage("user", "x")])
    assert calls["n"] == 1  # nao retentou


async def test_health_check_ok(mock_provider_factory):
    def handler(request):
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json={"data": []})

    p = mock_provider_factory(handler)
    assert await p.health_check() is True


async def test_health_check_fails_on_error(mock_provider_factory):
    def handler(request):
        return httpx.Response(500)

    p = mock_provider_factory(handler)
    assert await p.health_check() is False


async def test_close_is_idempotentish():
    p = make_mock_provider(_ok_response)
    await p.close()  
