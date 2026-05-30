"""Testes unitarios do AgentRegistry (in-memory puro, sem backend)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from core.orchestration.registry import (
    AgentInfo,
    AgentRegistry,
    AgentStatusEnum,
    AgentCapability,
)

pytestmark = pytest.mark.unit


def make_info(agent_id="a1", name="Agent One", caps=None,
              status=AgentStatusEnum.IDLE) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id, name=name,
        capabilities=caps if caps is not None else ["research"],
        status=status,
    )


def test_agent_info_defaults():
    info = AgentInfo(agent_id="x", name="X")
    assert info.capabilities == []
    assert info.status == AgentStatusEnum.IDLE
    assert info.metadata == {}
    assert info.registered_at.tzinfo is not None
    assert info.last_seen_at.tzinfo is not None


def test_enums_values():
    assert AgentStatusEnum.IDLE.value == "idle"
    assert AgentStatusEnum.OFFLINE.value == "offline"
    assert AgentCapability.RESEARCH.value == "research"


async def test_register_and_get():
    reg = AgentRegistry()
    info = make_info("a1")
    await reg.register(info)
    got = await reg.get("a1")
    assert got is info
    assert got.agent_id == "a1"


async def test_get_missing_returns_none():
    reg = AgentRegistry()
    assert await reg.get("nope") is None


async def test_register_overwrites_same_id():
    reg = AgentRegistry()
    await reg.register(make_info("a1", name="First"))
    await reg.register(make_info("a1", name="Second"))
    got = await reg.get("a1")
    assert got.name == "Second"
    assert len(await reg.list_all()) == 1


async def test_list_all():
    reg = AgentRegistry()
    await reg.register(make_info("a1"))
    await reg.register(make_info("a2"))
    all_agents = await reg.list_all()
    assert len(all_agents) == 2
    assert {a.agent_id for a in all_agents} == {"a1", "a2"}


async def test_unregister_existing_returns_true():
    reg = AgentRegistry()
    await reg.register(make_info("a1"))
    assert await reg.unregister("a1") is True
    assert await reg.get("a1") is None


async def test_unregister_missing_returns_false():
    reg = AgentRegistry()
    assert await reg.unregister("ghost") is False


async def test_find_by_capability_only_idle_default():
    reg = AgentRegistry()
    await reg.register(make_info("a1", caps=["research"], status=AgentStatusEnum.IDLE))
    await reg.register(make_info("a2", caps=["research"], status=AgentStatusEnum.BUSY))
    # default only_available=True -> so IDLE
    found = await reg.find_by_capability("research")
    assert [a.agent_id for a in found] == ["a1"]


async def test_find_by_capability_include_busy_when_not_only_available():
    reg = AgentRegistry()
    await reg.register(make_info("a1", caps=["coding"], status=AgentStatusEnum.IDLE))
    await reg.register(make_info("a2", caps=["coding"], status=AgentStatusEnum.BUSY))
    await reg.register(make_info("a3", caps=["coding"], status=AgentStatusEnum.OFFLINE))
    found = await reg.find_by_capability("coding", only_available=False)
    ids = {a.agent_id for a in found}
    assert ids == {"a1", "a2"}  


async def test_find_by_capability_no_match():
    reg = AgentRegistry()
    await reg.register(make_info("a1", caps=["research"]))
    assert await reg.find_by_capability("nonexistent") == []


async def test_find_by_capability_matches_among_multiple_caps():
    reg = AgentRegistry()
    await reg.register(make_info("a1", caps=["research", "coding", "review"]))
    found = await reg.find_by_capability("review")
    assert [a.agent_id for a in found] == ["a1"]


async def test_find_by_status():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.IDLE))
    await reg.register(make_info("a2", status=AgentStatusEnum.BUSY))
    await reg.register(make_info("a3", status=AgentStatusEnum.BUSY))
    busy = await reg.find_by_status(AgentStatusEnum.BUSY)
    assert {a.agent_id for a in busy} == {"a2", "a3"}


async def test_update_status_existing():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.IDLE))
    before = (await reg.get("a1")).last_seen_at
    await asyncio.sleep(0.01)
    ok = await reg.update_status("a1", AgentStatusEnum.BUSY)
    assert ok is True
    info = await reg.get("a1")
    assert info.status == AgentStatusEnum.BUSY
    assert info.last_seen_at > before 


async def test_update_status_missing_returns_false():
    reg = AgentRegistry()
    assert await reg.update_status("ghost", AgentStatusEnum.BUSY) is False


async def test_heartbeat_updates_last_seen():
    reg = AgentRegistry()
    await reg.register(make_info("a1"))
    before = (await reg.get("a1")).last_seen_at
    await asyncio.sleep(0.01)
    ok = await reg.heartbeat("a1")
    assert ok is True
    assert (await reg.get("a1")).last_seen_at > before


async def test_heartbeat_missing_returns_false():
    reg = AgentRegistry()
    assert await reg.heartbeat("ghost") is False


async def test_heartbeat_does_not_change_status():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.BUSY))
    await reg.heartbeat("a1")
    assert (await reg.get("a1")).status == AgentStatusEnum.BUSY


async def test_monitor_marks_stale_as_offline():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.IDLE))
    # forca last_seen_at no passado distante
    (await reg.get("a1")).last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=100)

    await reg.start_monitor(heartbeat_timeout=0.05, check_interval=0.02)
    await asyncio.sleep(0.12) 
    await reg.stop_monitor()

    assert (await reg.get("a1")).status == AgentStatusEnum.OFFLINE


async def test_monitor_keeps_fresh_agent():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.IDLE))

    await reg.start_monitor(heartbeat_timeout=5.0, check_interval=0.02)
    await asyncio.sleep(0.08)
    await reg.stop_monitor()

    assert (await reg.get("a1")).status == AgentStatusEnum.IDLE


async def test_monitor_skips_already_offline():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.OFFLINE))
    (await reg.get("a1")).last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=100)

    await reg.start_monitor(heartbeat_timeout=0.05, check_interval=0.02)
    await asyncio.sleep(0.08)
    await reg.stop_monitor()

    assert (await reg.get("a1")).status == AgentStatusEnum.OFFLINE


async def test_start_monitor_idempotent():
    reg = AgentRegistry()
    await reg.start_monitor(heartbeat_timeout=1.0, check_interval=0.1)
    task1 = reg._monitor_task
    await reg.start_monitor(heartbeat_timeout=1.0, check_interval=0.1)
    task2 = reg._monitor_task
    assert task1 is task2 
    await reg.stop_monitor()


async def test_stop_monitor_without_start_is_safe():
    reg = AgentRegistry()
    await reg.stop_monitor()  

async def test_stats_total_agents():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.IDLE))
    await reg.register(make_info("a2", status=AgentStatusEnum.BUSY))
    stats = await reg.stats()
    assert stats["total_agents"] == 2


async def test_stats_by_status_breakdown():
    reg = AgentRegistry()
    await reg.register(make_info("a1", status=AgentStatusEnum.IDLE))
    await reg.register(make_info("a2", status=AgentStatusEnum.BUSY))
    await reg.register(make_info("a3", status=AgentStatusEnum.BUSY))
    stats = await reg.stats()
    assert stats["by_status"]["idle"] == 1
    assert stats["by_status"]["busy"] == 2


async def test_stats_by_capability_breakdown():
    reg = AgentRegistry()
    await reg.register(make_info("a1", caps=["research", "coding"]))
    await reg.register(make_info("a2", caps=["coding"]))
    stats = await reg.stats()
    assert stats["by_capability"]["coding"] == 2
    assert stats["by_capability"]["research"] == 1


async def test_stats_empty_registry():
    reg = AgentRegistry()
    stats = await reg.stats()
    assert stats["total_agents"] == 0
    assert stats["by_status"] == {}
    assert stats["by_capability"] == {}
