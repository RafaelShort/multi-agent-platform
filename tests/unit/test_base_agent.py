"""Testes unitarios do BaseAgent (lifecycle + dispatch, tudo mockado)."""
from __future__ import annotations

import asyncio
from typing import Any, List, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agents.base_agent import BaseAgent
from core.messaging.message_bus import BusMessage
from core.orchestration.registry import AgentStatusEnum

pytestmark = pytest.mark.unit


class _ConcreteAgent(BaseAgent):
    """Agente minimo pra exercitar o BaseAgent."""

    def __init__(self, *args, task_result=("ok", True), raise_in_task=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._task_result = task_result
        self._raise_in_task = raise_in_task
        self.other_seen: List[BusMessage] = []

    @property
    def capabilities(self) -> List[str]:
        return ["test-cap"]

    async def handle_task(self, msg: BusMessage) -> Tuple[Any, bool]:
        if self._raise_in_task:
            raise self._raise_in_task
        return self._task_result

    async def on_other_message(self, msg: BusMessage) -> None:
        self.other_seen.append(msg)


def make_agent(**kwargs) -> _ConcreteAgent:
    bus = MagicMock()
    bus.subscribe = AsyncMock()
    bus.publish_to_agent = AsyncMock()
    bus.agent_topic = MagicMock(return_value="agent.test")

    registry = MagicMock()
    registry.register = AsyncMock()
    registry.update_status = AsyncMock()
    registry.heartbeat = AsyncMock()

    return _ConcreteAgent(
        agent_id="test", bus=bus, registry=registry,
        heartbeat_interval=0.05, **kwargs,
    )


def make_msg(msg_type="task", **meta) -> BusMessage:
    return BusMessage(
        topic="agent.test", sender_id="orch",
        content="payload", msg_type=msg_type, metadata=meta,
    )


async def test_dispatch_task_calls_handle():
    agent = make_agent(task_result=("done", True))
    await agent._dispatch(make_msg("task", task_id="t1"))
    agent.bus.publish_to_agent.assert_awaited_once()
    kwargs = agent.bus.publish_to_agent.await_args.kwargs
    assert kwargs["content"] == "done"
    assert kwargs["success"] is True
    assert kwargs["msg_type"] == "task_result"
    assert kwargs["task_id"] == "t1"


async def test_dispatch_other_msg_type():
    agent = make_agent()
    msg = make_msg("status_query")
    await agent._dispatch(msg)
    assert agent.other_seen == [msg]
    agent.bus.publish_to_agent.assert_not_awaited()


async def test_dispatch_swallows_exception():
    agent = make_agent()
    # on_other_message quebra
    agent.on_other_message = AsyncMock(side_effect=RuntimeError("boom"))
    await agent._dispatch(make_msg("weird"))
    assert agent._errors == 1 


async def test_handle_task_status_transitions():
    agent = make_agent()
    await agent._handle_task_msg(make_msg("task", task_id="t1"))
    # BUSY -> IDLE
    statuses = [c.args[1] for c in agent.registry.update_status.await_args_list]
    assert statuses == [AgentStatusEnum.BUSY, AgentStatusEnum.IDLE]
    assert agent._processed == 1


async def test_handle_task_default_reply_to():
    agent = make_agent()
    await agent._handle_task_msg(make_msg("task"))  # sem reply_to
    kwargs = agent.bus.publish_to_agent.await_args.kwargs
    assert kwargs["receiver_id"] == "orchestrator"


async def test_handle_task_custom_reply_to():
    agent = make_agent()
    await agent._handle_task_msg(make_msg("task", reply_to="agent-x"))
    kwargs = agent.bus.publish_to_agent.await_args.kwargs
    assert kwargs["receiver_id"] == "agent-x"


async def test_handle_task_failure_result():
    agent = make_agent(task_result=("nope", False))
    await agent._handle_task_msg(make_msg("task"))
    kwargs = agent.bus.publish_to_agent.await_args.kwargs
    assert kwargs["success"] is False
    assert kwargs["content"] == "nope"


async def test_handle_task_exception_becomes_failure():
    agent = make_agent(raise_in_task=ValueError("kaboom"))
    await agent._handle_task_msg(make_msg("task"))
    kwargs = agent.bus.publish_to_agent.await_args.kwargs
    assert kwargs["success"] is False
    assert "ValueError: kaboom" in kwargs["content"]
    assert agent._errors == 1
    # ainda assim foi pra IDLE no finally
    last_status = agent.registry.update_status.await_args_list[-1].args[1]
    assert last_status == AgentStatusEnum.IDLE


async def test_start_registers_and_subscribes():
    agent = make_agent()
    await agent.start()
    agent.bus.subscribe.assert_awaited_once()
    agent.registry.register.assert_awaited_once()
    assert agent._running is True
    assert agent._hb_task is not None
    await agent.stop()  # cleanup


async def test_start_idempotent():
    agent = make_agent()
    await agent.start()
    await agent.start() 
    agent.registry.register.assert_awaited_once()
    await agent.stop()


async def test_stop_marks_offline():
    agent = make_agent()
    await agent.start()
    await agent.stop()
    assert agent._running is False
    last = agent.registry.update_status.await_args_list[-1].args[1]
    assert last == AgentStatusEnum.OFFLINE


async def test_stop_without_start_is_noop():
    agent = make_agent()
    await agent.stop()  # nao deve lancar
    agent.registry.update_status.assert_not_awaited()


async def test_heartbeat_fires():
    agent = make_agent()
    await agent.start()
    await asyncio.sleep(0.12)  # ~2 ciclos de 0.05s
    await agent.stop()
    assert agent.registry.heartbeat.await_count >= 1


async def test_heartbeat_survives_registry_error():
    agent = make_agent()
    agent.registry.heartbeat = AsyncMock(side_effect=RuntimeError("registry down"))
    await agent.start()
    await asyncio.sleep(0.12)
    await agent.stop()  # nao deve travar nem propagar
    assert agent.registry.heartbeat.await_count >= 1


async def test_get_stats():
    agent = make_agent()
    await agent._handle_task_msg(make_msg("task"))
    stats = agent.get_stats()
    assert stats["agent_id"] == "test"
    assert stats["processed"] == 1
    assert stats["errors"] == 0
    assert stats["running"] is False
