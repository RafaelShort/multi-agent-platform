"""Testes unitarios do BusMessage."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.messaging.message_bus import BusMessage

pytestmark = pytest.mark.unit


def test_minimal_construction():
    m = BusMessage(topic="t", sender_id="s", content="hi")
    assert m.receiver_id == "*"
    assert m.msg_type == "task"
    assert m.metadata == {}
    assert m.reply_to is None
    assert isinstance(m.message_id, str) and len(m.message_id) > 0
    assert m.timestamp.tzinfo is not None  


def test_unique_message_ids():
    a = BusMessage(topic="t", sender_id="s", content="x")
    b = BusMessage(topic="t", sender_id="s", content="x")
    assert a.message_id != b.message_id


def test_custom_fields():
    m = BusMessage(
        topic="agents.tasks", sender_id="orch", receiver_id="agent-1",
        content="do it", msg_type="task_result",
        metadata={"task_id": "t1", "success": True}, reply_to="orch",
    )
    assert m.receiver_id == "agent-1"
    assert m.metadata["task_id"] == "t1"
    assert m.reply_to == "orch"


def test_to_json_is_valid_json():
    m = BusMessage(topic="t", sender_id="s", content="hi")
    data = json.loads(m.to_json())
    assert data["topic"] == "t"
    assert data["sender_id"] == "s"
    assert data["content"] == "hi"
    assert isinstance(data["timestamp"], str) 


def test_to_json_timestamp_is_iso():
    ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    m = BusMessage(topic="t", sender_id="s", content="x", timestamp=ts)
    data = json.loads(m.to_json())
    assert data["timestamp"] == ts.isoformat()


def test_to_json_preserves_unicode():
    m = BusMessage(topic="t", sender_id="s", content="ola, ç ã é 日本語 🚀")
    data = json.loads(m.to_json())
    assert data["content"] == "ola, ç ã é 日本語 🚀"
    assert "日本語" in m.to_json()


def test_from_json_str_roundtrip():
    original = BusMessage(
        topic="agents.tasks", sender_id="orch", receiver_id="a1",
        content="payload", msg_type="task",
        metadata={"task_id": "t1", "nested": {"k": [1, 2, 3]}},
    )
    restored = BusMessage.from_json(original.to_json())
    assert restored.message_id == original.message_id
    assert restored.topic == original.topic
    assert restored.content == original.content
    assert restored.metadata == original.metadata
    assert restored.timestamp == original.timestamp


def test_from_json_accepts_bytes():
    m = BusMessage(topic="t", sender_id="s", content="bytes test")
    raw_bytes = m.to_json().encode("utf-8")
    restored = BusMessage.from_json(raw_bytes)
    assert restored.content == "bytes test"
    assert restored.topic == "t"


def test_from_json_parses_timestamp_to_datetime():
    m = BusMessage(topic="t", sender_id="s", content="x")
    restored = BusMessage.from_json(m.to_json())
    assert isinstance(restored.timestamp, datetime)
    assert restored.timestamp.tzinfo is not None


def test_from_json_unicode_roundtrip():
    m = BusMessage(topic="t", sender_id="s", content="acentuação çãé 🚀")
    restored = BusMessage.from_json(m.to_json())
    assert restored.content == "acentuação çãé 🚀"


def test_from_json_invalid_raises():
    with pytest.raises(json.JSONDecodeError):
        BusMessage.from_json("{not valid json")


def test_from_json_missing_required_field_raises():
    with pytest.raises(Exception):  
        BusMessage.from_json(json.dumps({"topic": "t"}))


def test_double_roundtrip_stable():
    m = BusMessage(topic="t", sender_id="s", content="stable")
    once = BusMessage.from_json(m.to_json())
    twice = BusMessage.from_json(once.to_json())
    assert once.to_json() == twice.to_json()
