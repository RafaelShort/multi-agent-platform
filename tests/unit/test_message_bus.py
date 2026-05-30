"""Testes unitarios do MessageBus (producer mockado, sem Kafka real)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.messaging.message_bus import BusMessage, MessageBus

pytestmark = pytest.mark.unit


def make_bus() -> MessageBus:
    """Bus 'pronto' com producer fake, sem tocar Kafka."""
    bus = MessageBus(bootstrap_servers="fake:9092")
    bus._ready = True
    bus._producer = MagicMock()
    bus._producer.produce = MagicMock()
    bus._producer.poll = MagicMock()
    return bus


def test_agent_topic_format():
    bus = make_bus()
    assert bus.agent_topic("worker-1") == "agent.worker-1"
    assert bus.agent_topic("orchestrator") == "agent.orchestrator"


async def test_publish_when_not_ready_raises():
    bus = MessageBus(bootstrap_servers="fake:9092")
    bus._ready = False
    with pytest.raises(Exception):
        await bus.publish(BusMessage(topic="t", sender_id="s", content="x"))


async def test_publish_produces_and_counts():
    bus = make_bus()
    msg = BusMessage(topic="agent.a1", sender_id="s", receiver_id="a1", content="hi")
    await bus.publish(msg)

    bus._producer.produce.assert_called_once()
    kwargs = bus._producer.produce.call_args.kwargs
    assert kwargs["topic"] == "agent.a1"
    assert kwargs["value"] == msg.to_json().encode("utf-8")
    assert kwargs["key"] == b"a1"
    assert kwargs["on_delivery"] == bus._delivery_callback
    bus._producer.poll.assert_called_once_with(0)
    assert bus._stats["published"] == 1
    assert bus._stats["errors"] == 0


async def test_publish_error_increments_and_reraises():
    bus = make_bus()
    bus._producer.produce.side_effect = RuntimeError("kafka down")
    with pytest.raises(RuntimeError, match="kafka down"):
        await bus.publish(BusMessage(topic="t", sender_id="s", content="x"))
    assert bus._stats["errors"] == 1
    assert bus._stats["published"] == 0


async def test_publish_to_agent_builds_message():
    bus = make_bus()
    bus._ensure_topics = AsyncMock()
    msg = await bus.publish_to_agent(
        sender_id="orch", receiver_id="a1", content="do it",
        msg_type="task", task_id="t1", success=True,
    )
    assert isinstance(msg, BusMessage)
    assert msg.topic == "agent.a1"
    assert msg.sender_id == "orch"
    assert msg.receiver_id == "a1"
    assert msg.content == "do it"
    assert msg.msg_type == "task"
    assert msg.metadata == {"task_id": "t1", "success": True}
    bus._ensure_topics.assert_awaited_once_with(["agent.a1"])
    bus._producer.produce.assert_called_once()


async def test_publish_to_agent_default_msg_type():
    bus = make_bus()
    bus._ensure_topics = AsyncMock()
    msg = await bus.publish_to_agent(sender_id="s", receiver_id="a1", content="x")
    assert msg.msg_type == "task"
    assert msg.metadata == {}


async def test_publish_to_agent_returns_published_message():
    bus = make_bus()
    bus._ensure_topics = AsyncMock()
    with patch.object(bus, "publish", new=AsyncMock()) as pub:
        msg = await bus.publish_to_agent(sender_id="s", receiver_id="a2", content="c")
        pub.assert_awaited_once_with(msg)


async def test_broadcast_uses_broadcast_topic():
    bus = make_bus()
    msg = await bus.broadcast(sender_id="orch", content="hello all", priority="high")
    assert msg.topic == MessageBus.TOPIC_BROADCAST
    assert msg.receiver_id == "*"
    assert msg.msg_type == "broadcast"
    assert msg.metadata == {"priority": "high"}
    bus._producer.produce.assert_called_once()


async def test_broadcast_returns_message():
    bus = make_bus()
    with patch.object(bus, "publish", new=AsyncMock()) as pub:
        msg = await bus.broadcast(sender_id="s", content="x")
        pub.assert_awaited_once_with(msg)


def test_repr_contains_status():
    bus = make_bus()
    r = repr(bus)
    assert "MessageBus" in r
    assert "connected" in r
    bus._ready = False
    assert "disconnected" in repr(bus)


def test_default_topics_defined():
    assert MessageBus.TOPIC_TASKS == "agents.tasks"
    assert MessageBus.TOPIC_RESULTS == "agents.results"
    assert MessageBus.TOPIC_BROADCAST == "agents.broadcast"
    assert len(MessageBus.DEFAULT_TOPICS) == 4
