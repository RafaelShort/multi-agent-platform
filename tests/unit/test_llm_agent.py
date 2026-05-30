"""Testes unitarios do LLMAgent (FakeProvider, sem Kafka/rede)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from core.agents.llm_agent import LLMAgent
from core.llm.providers.base import ChatMessage, LLMProvider, LLMResponse
from core.messaging.message_bus import BusMessage

pytestmark = pytest.mark.unit


class FakeProvider(LLMProvider):
    """Provider controlavel: registra a ultima chamada e devolve resposta fixa."""

    name = "fake"

    def __init__(self, *, response: LLMResponse | None = None, raise_exc: Exception | None = None):
        self._response = response
        self._raise = raise_exc
        self.last_call: dict = {}
        self.closed = False

    async def chat(self, messages, *, model=None, temperature=0.7, max_tokens=None, **kwargs):
        self.last_call = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
        }
        if self._raise:
            raise self._raise
        return self._response or LLMResponse(
            content="hello", model=model or "fake-model", provider=self.name,
            prompt_tokens=5, completion_tokens=3, total_tokens=8, latency_ms=12.3,
        )

    async def close(self):
        self.closed = True


def make_agent(provider=None, **kwargs) -> LLMAgent:
    return LLMAgent(
        agent_id="llm-test",
        bus=MagicMock(),
        registry=MagicMock(),
        provider=provider or FakeProvider(),
        **kwargs,
    )


def make_msg(content: str, **meta) -> BusMessage:
    return BusMessage(
        topic="agent.llm-test", sender_id="tester",
        content=content, metadata=meta,
    )


def test_build_plain_string_prompt():
    agent = make_agent(default_system="be nice")
    msgs, opts = agent._build_messages("ola mundo")
    assert [m.role for m in msgs] == ["system", "user"]
    assert msgs[0].content == "be nice"
    assert msgs[1].content == "ola mundo"
    assert opts == {}


def test_build_plain_string_no_system():
    agent = make_agent()
    msgs, opts = agent._build_messages("oi")
    assert [m.role for m in msgs] == ["user"]
    assert msgs[0].content == "oi"


def test_build_string_that_is_json_dict():
    agent = make_agent()
    msgs, opts = agent._build_messages(json.dumps({"prompt": "via json", "temperature": 0.1}))
    assert msgs[-1].content == "via json"
    assert opts["temperature"] == 0.1


def test_build_string_invalid_json_is_prompt():
    agent = make_agent()
    msgs, _ = agent._build_messages("{nao eh json valido")
    assert msgs[-1].content == "{nao eh json valido"
    assert msgs[-1].role == "user"


def test_build_dict_prompt_with_options():
    agent = make_agent()
    msgs, opts = agent._build_messages({
        "prompt": "resuma isso", "system": "voce eh um resumidor",
        "model": "gpt-4o", "temperature": 0.2, "max_tokens": 100,
    })
    assert msgs[0].role == "system" and msgs[0].content == "voce eh um resumidor"
    assert msgs[1].content == "resuma isso"
    assert opts == {"model": "gpt-4o", "temperature": 0.2, "max_tokens": 100}


def test_build_dict_prompt_uses_default_system():
    agent = make_agent(default_system="default sys")
    msgs, _ = agent._build_messages({"prompt": "x"})
    assert msgs[0].content == "default sys"


def test_build_dict_options_skip_none():
    agent = make_agent()
    _, opts = agent._build_messages({"prompt": "x", "model": None, "max_tokens": None})
    assert opts == {}


def test_build_dict_messages_injects_system():
    agent = make_agent()
    msgs, _ = agent._build_messages({
        "system": "sys here",
        "messages": [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}],
    })
    assert [m.role for m in msgs] == ["system", "user", "assistant"]
    assert msgs[0].content == "sys here"


def test_build_dict_messages_no_double_system():
    agent = make_agent(default_system="should-not-appear")
    msgs, _ = agent._build_messages({
        "messages": [{"role": "system", "content": "explicit sys"}, {"role": "user", "content": "q"}],
    })
    roles = [m.role for m in msgs]
    assert roles.count("system") == 1
    assert msgs[0].content == "explicit sys"


def test_build_dict_messages_coerces_content_to_str():
    agent = make_agent()
    msgs, _ = agent._build_messages({"messages": [{"role": "user", "content": 123}]})
    assert msgs[-1].content == "123"


@pytest.mark.parametrize("bad", [123, 45.6, ["list"], None, {"foo": "bar"}])
def test_build_invalid_payload_raises(bad):
    agent = make_agent()
    with pytest.raises(ValueError, match="invalido|Payload"):
        agent._build_messages(bad)


async def test_handle_task_success():
    provider = FakeProvider()
    agent = make_agent(provider=provider, default_model="m-def", default_temperature=0.5)
    out, ok = await agent.handle_task(make_msg("ping"))

    assert ok is True
    data = json.loads(out)
    assert data["content"] == "hello"
    assert data["provider"] == "fake"
    assert data["tokens"] == {"prompt": 5, "completion": 3, "total": 8}
    assert data["latency_ms"] == 12.3
    # usou defaults do agente
    assert provider.last_call["model"] == "m-def"
    assert provider.last_call["temperature"] == 0.5


async def test_handle_task_payload_options_override_defaults():
    provider = FakeProvider()
    agent = make_agent(provider=provider, default_model="m-def", default_temperature=0.7)
    payload = json.dumps({"prompt": "x", "model": "override", "temperature": 0.9})
    await agent.handle_task(make_msg(payload))
    assert provider.last_call["model"] == "override"
    assert provider.last_call["temperature"] == 0.9


async def test_handle_task_updates_stats():
    provider = FakeProvider()
    agent = make_agent(provider=provider)
    await agent.handle_task(make_msg("a"))
    await agent.handle_task(make_msg("b"))
    stats = agent.get_stats()
    assert stats["llm_calls"] == 2
    assert stats["llm_errors"] == 0
    assert stats["total_tokens"] == 16  # 8 + 8
    assert stats["provider"] == "fake"


async def test_handle_task_invalid_payload():
    agent = make_agent()
    out, ok = await agent.handle_task(make_msg("123")) 
    assert ok is True


async def test_handle_task_invalid_dict_payload():
    agent = make_agent()
    msg = make_msg("placeholder")
    object.__setattr__(msg, "content", {"foo": "bar"})
    out, ok = await agent.handle_task(msg)
    assert ok is False
    assert out.startswith("InvalidPayload:")


async def test_handle_task_provider_error():
    provider = FakeProvider(raise_exc=RuntimeError("boom"))
    agent = make_agent(provider=provider)
    out, ok = await agent.handle_task(make_msg("x"))
    assert ok is False
    assert out.startswith("LLMProviderError:")
    assert "RuntimeError" in out
    assert agent.get_stats()["llm_errors"] == 1


async def test_stop_closes_provider():
    provider = FakeProvider()
    agent = make_agent(provider=provider)
    agent._running = False
    await agent.provider.close()
    assert provider.closed is True
