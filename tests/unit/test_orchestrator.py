"""Testes unitarios do OrchestratorAgent (registry+bus mockados)."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestration.orchestrator import (
    OrchestratorAgent, Task, TaskResult, TaskStatus,
)
from core.orchestration.registry import AgentInfo, AgentStatusEnum

pytestmark = pytest.mark.unit


def make_agent(agent_id: str) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        name=f"Agent {agent_id}",
        capabilities=["research"],
        status=AgentStatusEnum.IDLE,
    )


def result_msg(task_id, success=True, sender="a1", content="answer"):
    return SimpleNamespace(
        msg_type="task_result",
        metadata={"task_id": task_id, "success": success},
        sender_id=sender,
        content=content,
        message_id="msg-123",
    )


@pytest.fixture
def registry():
    r = AsyncMock()
    r.find_by_capability = AsyncMock(return_value=[])
    r.update_status = AsyncMock(return_value=True)
    return r


@pytest.fixture
def bus():
    b = AsyncMock()
    b.agent_topic = MagicMock(return_value="agent.orchestrator")
    b.subscribe = AsyncMock()
    b.publish_to_agent = AsyncMock()
    return b


@pytest.fixture
def orch(registry, bus):
    return OrchestratorAgent(
        registry=registry, bus=bus,
        default_timeout=1.0, queue_timeout=1.0,
    )


def test_task_defaults():
    t = Task(capability="research", payload="hi")
    assert t.task_id
    assert t.capability == "research"
    assert t.payload == "hi"
    assert t.metadata == {}
    assert isinstance(t.created_at, datetime)


def test_task_unique_ids():
    a = Task(capability="c", payload="p")
    b = Task(capability="c", payload="p")
    assert a.task_id != b.task_id


def test_task_result_defaults():
    r = TaskResult(task_id="x", status=TaskStatus.COMPLETED)
    assert r.agent_id is None
    assert r.output is None
    assert r.error is None
    assert r.duration_seconds == 0.0
    assert r.queued_seconds == 0.0


def test_task_status_values():
    assert TaskStatus.NO_AGENT.value == "no_agent_available"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.TIMEOUT.value == "timeout"


def test_compute_duration_missing_returns_zero(orch):
    assert orch._compute_duration("nope") == 0.0


def test_compute_duration_with_start(orch):
    orch._task_start["t"] = datetime.now(timezone.utc) - timedelta(seconds=2)
    assert orch._compute_duration("t") >= 1.9


def test_compute_queued_missing_returns_zero(orch):
    assert orch._compute_queued("nope") == 0.0
    # so start presente, sem enqueue -> 0.0
    orch._task_start["t"] = datetime.now(timezone.utc)
    assert orch._compute_queued("t") == 0.0


def test_compute_queued_with_values(orch):
    eq = datetime.now(timezone.utc)
    orch._task_enqueue["t"] = eq
    orch._task_start["t"] = eq + timedelta(seconds=1.5)
    assert orch._compute_queued("t") == pytest.approx(1.5, abs=0.01)


def test_get_stats_initial(orch):
    s = orch.get_stats()
    assert s["submitted"] == 0
    assert s["pending"] == 0
    assert s["queue_sizes"] == {}


def test_get_stats_reflects_state(orch):
    orch._pending["t"] = MagicMock()
    orch._queues["research"] = deque([("x", "y", "z")])
    s = orch.get_stats()
    assert s["pending"] == 1
    assert s["queue_sizes"] == {"research": 1}


async def test_cleanup_frees_agent(orch, registry):
    orch._task_to_agent["t"] = "a1"
    orch._pending["t"] = MagicMock()
    orch._task_start["t"] = datetime.now(timezone.utc)
    orch._task_enqueue["t"] = datetime.now(timezone.utc)
    await orch._cleanup_task("t", free_agent=True)
    registry.update_status.assert_awaited_once_with("a1", AgentStatusEnum.IDLE)
    assert "t" not in orch._pending
    assert "t" not in orch._task_to_agent
    assert "t" not in orch._task_start
    assert "t" not in orch._task_enqueue
    assert orch._wakeup.is_set()


async def test_cleanup_no_free_agent(orch, registry):
    orch._task_to_agent["t"] = "a1"
    await orch._cleanup_task("t", free_agent=False)
    registry.update_status.assert_not_awaited()
    assert "t" not in orch._task_to_agent


async def test_cleanup_unknown_task_safe(orch, registry):
    await orch._cleanup_task("nope", free_agent=True)
    registry.update_status.assert_not_awaited()


async def test_try_dispatch_no_candidates(orch, registry):
    registry.find_by_capability.return_value = []
    fut = asyncio.get_running_loop().create_future()
    ok = await orch._try_dispatch(
        Task(capability="research", payload="hi"), fut, datetime.now(timezone.utc)
    )
    assert ok is False


async def test_try_dispatch_strategy_returns_none(orch, registry):
    registry.find_by_capability.return_value = [make_agent("a")]
    orch.strategy = MagicMock()
    orch.strategy.choose = AsyncMock(return_value=None)
    fut = asyncio.get_running_loop().create_future()
    ok = await orch._try_dispatch(
        Task(capability="research", payload="hi"), fut, datetime.now(timezone.utc)
    )
    assert ok is False


async def test_try_dispatch_success(orch, registry, bus):
    registry.find_by_capability.return_value = [make_agent("a1")]
    task = Task(capability="research", payload="do it", metadata={"foo": "bar"})
    fut = asyncio.get_running_loop().create_future()
    ok = await orch._try_dispatch(task, fut, datetime.now(timezone.utc))
    assert ok is True
    registry.update_status.assert_awaited_once_with("a1", AgentStatusEnum.BUSY)
    bus.publish_to_agent.assert_awaited_once()
    kwargs = bus.publish_to_agent.await_args.kwargs
    assert kwargs["receiver_id"] == "a1"
    assert kwargs["task_id"] == task.task_id
    assert kwargs["capability"] == "research"
    assert kwargs["reply_to"] == orch.AGENT_ID
    assert kwargs["foo"] == "bar"
    assert orch._pending[task.task_id] is fut
    assert orch._task_to_agent[task.task_id] == "a1"


async def test_try_dispatch_publish_error_resolves_failed(orch, registry, bus):
    registry.find_by_capability.return_value = [make_agent("a1")]
    bus.publish_to_agent.side_effect = RuntimeError("kafka down")
    task = Task(capability="research", payload="x")
    fut = asyncio.get_running_loop().create_future()
    ok = await orch._try_dispatch(task, fut, datetime.now(timezone.utc))
    assert ok is True  
    assert fut.done()
    res = fut.result()
    assert res.status == TaskStatus.FAILED
    assert "kafka down" in res.error
    registry.update_status.assert_any_await("a1", AgentStatusEnum.IDLE)


async def test_on_result_wrong_msg_type(orch):
    msg = SimpleNamespace(msg_type="other", metadata={}, sender_id="a", content="x", message_id="m1")
    await orch._on_result(msg) 


async def test_on_result_no_task_id(orch):
    msg = SimpleNamespace(msg_type="task_result", metadata={}, sender_id="a", content="x", message_id="m2")
    await orch._on_result(msg)


async def test_on_result_unknown_task(orch):
    await orch._on_result(result_msg("nope")) 


async def test_on_result_already_done(orch):
    fut = asyncio.get_running_loop().create_future()
    fut.set_result(TaskResult(task_id="t", status=TaskStatus.COMPLETED))
    orch._pending["t"] = fut
    await orch._on_result(result_msg("t")) 


async def test_on_result_success(orch, registry):
    fut = asyncio.get_running_loop().create_future()
    orch._pending["t"] = fut
    orch._task_to_agent["t"] = "a1"
    orch._task_start["t"] = datetime.now(timezone.utc)
    orch._task_enqueue["t"] = datetime.now(timezone.utc)
    await orch._on_result(result_msg("t", success=True, sender="a1", content="answer"))
    res = fut.result()
    assert res.status == TaskStatus.COMPLETED
    assert res.output == "answer"
    assert res.error is None
    assert res.agent_id == "a1"
    registry.update_status.assert_awaited_with("a1", AgentStatusEnum.IDLE)
    assert "t" not in orch._pending


async def test_on_result_failure(orch):
    fut = asyncio.get_running_loop().create_future()
    orch._pending["t"] = fut
    orch._task_to_agent["t"] = "a1"
    orch._task_start["t"] = datetime.now(timezone.utc)
    orch._task_enqueue["t"] = datetime.now(timezone.utc)
    await orch._on_result(result_msg("t", success=False, content="boom"))
    res = fut.result()
    assert res.status == TaskStatus.FAILED
    assert res.error == "boom"
    assert res.output is None


async def test_remove_from_queue_removes_one(orch):
    t1 = Task(capability="c", payload="1")
    t2 = Task(capability="c", payload="2")
    et = datetime.now(timezone.utc)
    fut = MagicMock()
    orch._queues["c"] = deque([(t1, fut, et), (t2, fut, et)])
    await orch._remove_from_queue(t1.task_id)
    remaining = [t.task_id for (t, f, e) in orch._queues["c"]]
    assert remaining == [t2.task_id]


async def test_remove_from_queue_empties_and_pops_cap(orch):
    t1 = Task(capability="c", payload="1")
    orch._queues["c"] = deque([(t1, MagicMock(), datetime.now(timezone.utc))])
    await orch._remove_from_queue(t1.task_id)
    assert "c" not in orch._queues


async def test_remove_from_queue_missing_safe(orch):
    await orch._remove_from_queue("nope") 


async def test_drain_queues_dispatches_queued(orch, registry, bus):
    task = Task(capability="research", payload="p")
    fut = asyncio.get_running_loop().create_future()
    orch._queues["research"] = deque([(task, fut, datetime.now(timezone.utc))])
    registry.find_by_capability.return_value = [make_agent("a1")]
    await orch._drain_queues()
    assert "research" not in orch._queues
    bus.publish_to_agent.assert_awaited_once()
    assert task.task_id in orch._pending


async def test_drain_queues_keeps_when_no_agent(orch, registry):
    task = Task(capability="research", payload="p")
    fut = asyncio.get_running_loop().create_future()
    orch._queues["research"] = deque([(task, fut, datetime.now(timezone.utc))])
    registry.find_by_capability.return_value = []
    await orch._drain_queues()
    assert orch._queues["research"] 


async def test_start_subscribes_and_idempotent(orch, bus):
    await orch.start()
    assert orch._started
    bus.subscribe.assert_awaited_once()
    await orch.start() 
    bus.subscribe.assert_awaited_once()
    await orch.stop()


async def test_stop_cancels_pending(orch):
    await orch.start()
    fut = asyncio.get_running_loop().create_future()
    orch._pending["t"] = fut
    await orch.stop()
    assert fut.cancelled()
    assert orch._started is False


async def test_submit_task_not_started_raises(orch):
    with pytest.raises(RuntimeError):
        await orch.submit_task(Task(capability="c", payload="p"))


async def test_submit_task_immediate_completed(orch):
    orch._started = True

    async def fake_dispatch(task, fut, et):
        fut.set_result(TaskResult(
            task_id=task.task_id, status=TaskStatus.COMPLETED, output="ok"
        ))
        return True

    orch._try_dispatch = fake_dispatch
    res = await orch.submit_task(Task(capability="c", payload="p"))
    assert res.status == TaskStatus.COMPLETED
    assert orch._stats["submitted"] == 1
    assert orch._stats["completed"] == 1


async def test_submit_task_failed_result_counts(orch):
    orch._started = True

    async def fake_dispatch(task, fut, et):
        fut.set_result(TaskResult(
            task_id=task.task_id, status=TaskStatus.FAILED, error="x"
        ))
        return True

    orch._try_dispatch = fake_dispatch
    res = await orch.submit_task(Task(capability="c", payload="p"))
    assert res.status == TaskStatus.FAILED
    assert orch._stats["failed"] == 1


async def test_submit_task_timeout_status_counts(orch):
    orch._started = True

    async def fake_dispatch(task, fut, et):
        fut.set_result(TaskResult(task_id=task.task_id, status=TaskStatus.TIMEOUT))
        return True

    orch._try_dispatch = fake_dispatch
    res = await orch.submit_task(Task(capability="c", payload="p"))
    assert res.status == TaskStatus.TIMEOUT
    assert orch._stats["timeout"] == 1


async def test_submit_task_queued_then_total_timeout(orch):
    orch._started = True
    orch.default_timeout = 0.05
    orch.queue_timeout = 0.05

    async def fake_dispatch(task, fut, et):
        return False 

    orch._try_dispatch = fake_dispatch
    res = await orch.submit_task(Task(capability="c", payload="p"))
    assert res.status == TaskStatus.TIMEOUT
    assert orch._stats["queued"] == 1
    assert orch._stats["queue_timeout"] == 1

