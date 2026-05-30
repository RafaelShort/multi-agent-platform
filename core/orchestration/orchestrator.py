"""
OrchestratorAgent
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.logger import app_logger as logger
from core.messaging.message_bus import BusMessage, MessageBus
from core.orchestration.registry import (
    AgentRegistry,
    AgentStatusEnum,
)
from core.orchestration.strategies import (
    RoutingStrategy,
    RoundRobinStrategy,
)


# MODELOS

class TaskStatus(str, Enum):
    PENDING    = "pending"
    QUEUED     = "queued"
    DISPATCHED = "dispatched"
    COMPLETED  = "completed"
    FAILED     = "failed"
    TIMEOUT    = "timeout"
    NO_AGENT   = "no_agent_available"


class Task(BaseModel):
    task_id:    str = Field(default_factory=lambda: str(uuid.uuid4()))
    capability: str
    payload:    str
    metadata:   Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskResult(BaseModel):
    task_id:  str
    status:   TaskStatus
    agent_id: Optional[str] = None
    output:   Optional[str] = None
    error:    Optional[str] = None
    duration_seconds: float = 0.0
    queued_seconds:   float = 0.0


# ORCHESTRATOR

class OrchestratorAgent:
    AGENT_ID = "orchestrator"
    RESULT_MSG_TYPE = "task_result"

    def __init__(
        self,
        registry: AgentRegistry,
        bus: MessageBus,
        default_timeout: float = 30.0,
        queue_timeout: float = 60.0,
        strategy: Optional[RoutingStrategy] = None,
    ) -> None:
        self.registry = registry
        self.bus = bus
        self.default_timeout = default_timeout
        self.queue_timeout = queue_timeout
        self.strategy: RoutingStrategy = strategy or RoundRobinStrategy()

        # Estado de tasks em execucao
        self._pending: Dict[str, asyncio.Future[TaskResult]] = {}
        self._task_to_agent: Dict[str, str] = {}
        self._task_start:   Dict[str, datetime] = {}
        self._task_enqueue: Dict[str, datetime] = {}

        # Filas por capability
        self._queues: Dict[str, deque] = {}
        self._queue_lock = asyncio.Lock()

        # Evento que acorda o dispatcher quando ha mudancas
        self._wakeup = asyncio.Event()
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._shutdown = False

        self._started = False
        self._stats = {
            "submitted": 0, "completed": 0, "failed": 0,
            "timeout": 0, "queued": 0, "queue_timeout": 0,
        }

    # LIFECYCLE

    async def start(self) -> None:
        if self._started:
            return
        inbox = self.bus.agent_topic(self.AGENT_ID)
        await self.bus.subscribe(inbox, self._on_result)
        self._shutdown = False
        self._dispatcher_task = asyncio.create_task(self._dispatcher_loop())
        self._started = True
        logger.info(
            f"[Orchestrator] Iniciado | inbox={inbox} | "
            f"strategy={self.strategy.name} | queue_timeout={self.queue_timeout}s"
        )

    async def stop(self) -> None:
        self._shutdown = True
        self._wakeup.set()
        if self._dispatcher_task:
            try:
                await asyncio.wait_for(self._dispatcher_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._dispatcher_task.cancel()

        # Cancelar pending
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.cancel()
        # Cancelar enfileiradas
        async with self._queue_lock:
            for q in self._queues.values():
                for _, fut, _ in q:
                    if not fut.done():
                        fut.cancel()
            self._queues.clear()

        self._pending.clear()
        self._task_to_agent.clear()
        self._task_start.clear()
        self._started = False
        logger.info(f"[Orchestrator] Encerrado | stats={self._stats}")

    # SUBMISSAO

    async def submit_task(
        self,
        task: Task,
        timeout: Optional[float] = None,
        queue_timeout: Optional[float] = None,
    ) -> TaskResult:
        if not self._started:
            raise RuntimeError("Orchestrator nao iniciado. Chame start() antes.")

        timeout = timeout if timeout is not None else self.default_timeout
        q_timeout = queue_timeout if queue_timeout is not None else self.queue_timeout
        self._stats["submitted"] += 1

        loop = asyncio.get_running_loop()
        result_fut: asyncio.Future[TaskResult] = loop.create_future()
        enqueue_time = datetime.now(timezone.utc)

        # Tenta dispatch imediato
        dispatched = await self._try_dispatch(task, result_fut, enqueue_time)

        if not dispatched:
            async with self._queue_lock:
                self._queues.setdefault(task.capability, deque()).append(
                    (task, result_fut, enqueue_time)
                )
            self._stats["queued"] += 1
            logger.info(
                f"[Orchestrator] Task {task.task_id[:8]} ENFILEIRADA "
                f"(capability={task.capability}, queue_size="
                f"{len(self._queues[task.capability])})"
            )

        total_timeout = q_timeout + timeout
        try:
            result = await asyncio.wait_for(result_fut, timeout=total_timeout)
            if result.status == TaskStatus.COMPLETED:
                self._stats["completed"] += 1
            elif result.status == TaskStatus.TIMEOUT:
                self._stats["timeout"] += 1
            elif result.status in (TaskStatus.FAILED, TaskStatus.NO_AGENT):
                self._stats["failed"] += 1
            return result
        except asyncio.TimeoutError:
            # Estourou queue+exec timeout
            await self._remove_from_queue(task.task_id)
            await self._cleanup_task(task.task_id, free_agent=True)
            self._stats["queue_timeout"] += 1
            queued_for = (datetime.now(timezone.utc) - enqueue_time).total_seconds()
            logger.warning(
                f"[Orchestrator] Task {task.task_id[:8]} expirou na fila "
                f"apos {queued_for:.1f}s"
            )
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.TIMEOUT,
                error=f"Total timeout ({total_timeout}s) na fila/exec",
                queued_seconds=queued_for,
            )

    # DISPATCH

    async def _try_dispatch(
        self,
        task: Task,
        result_fut: asyncio.Future[TaskResult],
        enqueue_time: datetime,
    ) -> bool:
        """Tenta despachar. Retorna True se conseguiu."""
        candidates = await self.registry.find_by_capability(
            task.capability, only_available=True
        )
        if not candidates:
            return False

        chosen = await self.strategy.choose(task.capability, candidates)
        if chosen is None:
            return False

        await self.registry.update_status(chosen.agent_id, AgentStatusEnum.BUSY)

        self._pending[task.task_id] = result_fut
        self._task_to_agent[task.task_id] = chosen.agent_id
        self._task_start[task.task_id] = datetime.now(timezone.utc)
        self._task_enqueue[task.task_id] = enqueue_time

        queued_for = (datetime.now(timezone.utc) - enqueue_time).total_seconds()
        logger.info(
            f"[Orchestrator] Task {task.task_id[:8]} -> {chosen.agent_id} "
            f"| capability={task.capability} | queued={queued_for:.3f}s"
        )

        try:
            await self.bus.publish_to_agent(
                sender_id=self.AGENT_ID,
                receiver_id=chosen.agent_id,
                content=task.payload,
                msg_type="task",
                task_id=task.task_id,
                capability=task.capability,
                reply_to=self.AGENT_ID,
                **task.metadata,
            )
            return True
        except Exception as exc:
            logger.exception(f"[Orchestrator] Dispatch falhou: {task.task_id}")
            await self._cleanup_task(task.task_id, free_agent=True)
            if not result_fut.done():
                result_fut.set_result(TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    agent_id=chosen.agent_id,
                    error=f"Dispatch failed: {exc}",
                ))
            return True  

    async def _dispatcher_loop(self) -> None:
        """Background loop que drena filas quando ha sinal de wakeup."""
        logger.info("[Orchestrator] Dispatcher loop iniciado")
        while not self._shutdown:
            try:
                await self._wakeup.wait()
                self._wakeup.clear()
                if self._shutdown:
                    break
                await self._drain_queues()
            except Exception:
                logger.exception("[Orchestrator] Erro no dispatcher loop")
        logger.info("[Orchestrator] Dispatcher loop encerrado")

    async def _drain_queues(self) -> None:
        """Tenta despachar uma task de cada fila (FIFO por capability)."""
        async with self._queue_lock:
            capabilities = list(self._queues.keys())

        for cap in capabilities:
            while True:
                async with self._queue_lock:
                    q = self._queues.get(cap)
                    if not q:
                        break
                    task, fut, enqueue_time = q[0]  

                # Tenta dispatch
                dispatched = await self._try_dispatch(task, fut, enqueue_time)
                if dispatched:
                    async with self._queue_lock:
                        q = self._queues.get(cap)
                        if q and q[0][0].task_id == task.task_id:
                            q.popleft()
                            if not q:
                                self._queues.pop(cap, None)
                else:
                    break

    async def _remove_from_queue(self, task_id: str) -> None:
        async with self._queue_lock:
            for cap, q in list(self._queues.items()):
                new_q = deque((t, f, e) for (t, f, e) in q if t.task_id != task_id)
                if len(new_q) != len(q):
                    self._queues[cap] = new_q
                    if not new_q:
                        self._queues.pop(cap, None)
                    return

    # RESULTADOS

    async def _on_result(self, msg: BusMessage) -> None:
        if msg.msg_type != self.RESULT_MSG_TYPE:
            return

        task_id = msg.metadata.get("task_id")
        if not task_id:
            logger.warning(f"[Orchestrator] Resultado sem task_id: {msg.message_id}")
            return

        fut = self._pending.get(task_id)
        if not fut or fut.done():
            logger.debug(f"[Orchestrator] Resultado para task desconhecida: {task_id}")
            return

        success = bool(msg.metadata.get("success", True))
        duration = self._compute_duration(task_id)
        queued = self._compute_queued(task_id)

        result = TaskResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED if success else TaskStatus.FAILED,
            agent_id=msg.sender_id,
            output=msg.content if success else None,
            error=None if success else msg.content,
            duration_seconds=duration,
            queued_seconds=queued,
        )

        logger.info(
            f"[Orchestrator] Resultado | task={task_id[:8]} agent={msg.sender_id} "
            f"status={result.status.value} duration={duration:.3f}s"
        )

        fut.set_result(result)
        await self._cleanup_task(task_id, free_agent=True)

    # HELPERS

    async def _cleanup_task(self, task_id: str, free_agent: bool) -> None:
        agent_id = self._task_to_agent.pop(task_id, None)
        self._pending.pop(task_id, None)
        self._task_start.pop(task_id, None)
        self._task_enqueue.pop(task_id, None)
        if free_agent and agent_id:
            await self.registry.update_status(agent_id, AgentStatusEnum.IDLE)
            self._wakeup.set()

    def _compute_queued(self, task_id: str) -> float:
        eq = self._task_enqueue.get(task_id)
        st = self._task_start.get(task_id)
        if not eq or not st:
            return 0.0
        return (st - eq).total_seconds()

    def _compute_duration(self, task_id: str) -> float:
        start = self._task_start.get(task_id)
        if not start:
            return 0.0
        return (datetime.now(timezone.utc) - start).total_seconds()

    def get_stats(self) -> Dict[str, Any]:
        queue_sizes = {cap: len(q) for cap, q in self._queues.items()}
        return {
            **self._stats,
            "pending": len(self._pending),
            "queue_sizes": queue_sizes,
        }

