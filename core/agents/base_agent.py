"""
BaseAgent: classe base para agentes da plataforma.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple

from core.logger import app_logger as logger
from core.messaging.message_bus import BusMessage, MessageBus
from core.orchestration.registry import (
    AgentInfo,
    AgentRegistry,
    AgentStatusEnum,
)


class BaseAgent(ABC):
    """Classe base para todos os agentes."""

    def __init__(
        self,
        agent_id: str,
        bus: MessageBus,
        registry: AgentRegistry,
        name: Optional[str] = None,
        heartbeat_interval: float = 10.0,
    ) -> None:
        self.agent_id = agent_id
        self.name = name or agent_id
        self.bus = bus
        self.registry = registry
        self.heartbeat_interval = heartbeat_interval

        self._hb_task: Optional[asyncio.Task] = None
        self._hb_stop = asyncio.Event()
        self._running = False
        self._processed = 0
        self._errors = 0

    # API publica

    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """Lista de capabilities oferecidas por este agente."""

    @abstractmethod
    async def handle_task(self, msg: BusMessage) -> Tuple[Any, bool]:
        """
        Processa uma task. Retorna (output, success).
        Levantar excecao => success=False, output=str(exc).
        """

    async def start(self) -> None:
        """Registra no Registry, subscreve no inbox e inicia heartbeat."""
        if self._running:
            logger.warning(f"[{self.agent_id}] start() chamado mas ja esta rodando")
            return

        topic = self.bus.agent_topic(self.agent_id)
        await self.bus.subscribe(topic, self._dispatch)

        await self.registry.register(AgentInfo(
            agent_id=self.agent_id,
            name=self.name,
            capabilities=self.capabilities,
        ))

        self._hb_stop.clear()
        self._hb_task = asyncio.create_task(self._heartbeat_loop())
        self._running = True
        logger.info(
            f"[{self.agent_id}] Agente iniciado | capabilities={self.capabilities}"
        )

    async def stop(self) -> None:
        """Encerra heartbeat e marca OFFLINE no registry."""
        if not self._running:
            return
        self._hb_stop.set()
        if self._hb_task:
            try:
                await asyncio.wait_for(self._hb_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._hb_task.cancel()
            self._hb_task = None

        await self.registry.update_status(self.agent_id, AgentStatusEnum.OFFLINE)
        self._running = False
        logger.info(
            f"[{self.agent_id}] Agente encerrado | "
            f"processed={self._processed} errors={self._errors}"
        )

    # Internos

    async def _heartbeat_loop(self) -> None:
        while not self._hb_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._hb_stop.wait(), timeout=self.heartbeat_interval
                )
                break
            except asyncio.TimeoutError:
                pass
            try:
                await self.registry.heartbeat(self.agent_id)
            except Exception as exc:
                logger.error(f"[{self.agent_id}] heartbeat falhou: {exc}")

    async def _dispatch(self, msg: BusMessage) -> None:
        """Roteia mensagens recebidas por msg_type."""
        try:
            if msg.msg_type == "task":
                await self._handle_task_msg(msg)
            else:
                await self.on_other_message(msg)
        except Exception as exc:
            self._errors += 1
            logger.exception(f"[{self.agent_id}] erro no dispatch: {exc}")

    async def _handle_task_msg(self, msg: BusMessage) -> None:
        await self.registry.update_status(self.agent_id, AgentStatusEnum.BUSY)
        task_id = msg.metadata.get("task_id")
        reply_to = msg.metadata.get("reply_to", "orchestrator")
        success = True
        output: Any = None
        try:
            output, success = await self.handle_task(msg)
        except Exception as exc:
            self._errors += 1
            success = False
            output = f"{type(exc).__name__}: {exc}"
            logger.exception(f"[{self.agent_id}] handle_task levantou excecao")
        finally:
            await self.registry.update_status(self.agent_id, AgentStatusEnum.IDLE)

        self._processed += 1
        await self.bus.publish_to_agent(
            sender_id=self.agent_id,
            receiver_id=reply_to,
            content=output,
            msg_type="task_result",
            task_id=task_id,
            success=success,
        )

    async def on_other_message(self, msg: BusMessage) -> None:
        """Hook para subclasses tratarem msg_types nao-task. Default: ignora."""
        logger.debug(
            f"[{self.agent_id}] msg ignorada | type={msg.msg_type} from={msg.sender_id}"
        )

    # Stats

    def get_stats(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "processed": self._processed,
            "errors": self._errors,
        }
