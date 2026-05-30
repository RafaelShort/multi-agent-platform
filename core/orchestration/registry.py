"""
Agent Registry

"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.logger import app_logger as logger


# MODELOS

class AgentCapability(str, Enum):
    """Capacidades padronizadas que um agente pode oferecer."""
    RESEARCH      = "research"
    SUMMARIZATION = "summarization"
    CODING        = "coding"
    REVIEW        = "review"
    PLANNING      = "planning"
    EXECUTION     = "execution"
    GENERAL       = "general"


class AgentStatusEnum(str, Enum):
    """Status operacional de um agente registrado."""
    IDLE    = "idle"
    BUSY    = "busy"
    OFFLINE = "offline"
    ERROR   = "error"


class AgentInfo(BaseModel):
    """Metadados de um agente registrado no Registry."""
    agent_id:     str
    name:         str
    capabilities: List[str] = Field(default_factory=list)
    status:       AgentStatusEnum = AgentStatusEnum.IDLE
    metadata:     Dict[str, Any] = Field(default_factory=dict)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# REGISTRY

class AgentRegistry:
    """
    Catalogo in-memory de agentes.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, AgentInfo] = {}
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_stop = asyncio.Event()
        self._heartbeat_timeout: float = 30.0
        self._monitor_interval: float = 5.0

    # CRUD

    async def register(self, info: AgentInfo) -> None:
        """Cadastra (ou substitui) um agente no registry."""
        async with self._lock:
            existed = info.agent_id in self._agents
            self._agents[info.agent_id] = info
            action = "atualizado" if existed else "registrado"
            logger.info(f"[Registry] Agente {action}: {info.name} ({info.agent_id}) "
                        f"| capabilities={info.capabilities}")

    async def unregister(self, agent_id: str) -> bool:
        """Remove agente do registry. Retorna True se removido."""
        async with self._lock:
            removed = self._agents.pop(agent_id, None)
            if removed:
                logger.info(f"[Registry] Agente removido: {removed.name} ({agent_id})")
                return True
            return False

    async def get(self, agent_id: str) -> Optional[AgentInfo]:
        """Busca agente por ID."""
        async with self._lock:
            return self._agents.get(agent_id)

    async def list_all(self) -> List[AgentInfo]:
        """Lista todos os agentes registrados."""
        async with self._lock:
            return list(self._agents.values())

    # Busca

    async def find_by_capability(
        self,
        capability: str,
        only_available: bool = True,
    ) -> List[AgentInfo]:
        """
        Retorna agentes que possuem a capacidade requisitada.
        """
        async with self._lock:
            results = [
                info for info in self._agents.values()
                if capability in info.capabilities
            ]
            if only_available:
                results = [a for a in results if a.status == AgentStatusEnum.IDLE]
            else:
                # mesmo sem only_available, nunca devolver OFFLINE
                results = [a for a in results if a.status != AgentStatusEnum.OFFLINE]
            return results

    async def find_by_status(self, status: AgentStatusEnum) -> List[AgentInfo]:
        """Retorna agentes em determinado status."""
        async with self._lock:
            return [a for a in self._agents.values() if a.status == status]

    # Atualizacoes

    async def update_status(self, agent_id: str, status: AgentStatusEnum) -> bool:
        """Atualiza status de um agente. Retorna True se atualizado."""
        async with self._lock:
            info = self._agents.get(agent_id)
            if not info:
                logger.warning(f"[Registry] update_status: agent_id desconhecido: {agent_id}")
                return False
            info.status = status
            info.last_seen_at = datetime.now(timezone.utc)
            return True

    async def heartbeat(self, agent_id: str) -> bool:
        """Atualiza last_seen_at (keep-alive)."""
        async with self._lock:
            info = self._agents.get(agent_id)
            if not info:
                return False
            info.last_seen_at = datetime.now(timezone.utc)
            return True

    # Heartbeat Monitor

    async def start_monitor(
        self,
        heartbeat_timeout: float = 30.0,
        check_interval: float = 5.0,
    ) -> None:
        """Inicia loop que marca como OFFLINE agentes sem heartbeat recente."""
        if self._monitor_task and not self._monitor_task.done():
            logger.warning("[Registry] Monitor ja em execucao")
            return
        self._heartbeat_timeout = heartbeat_timeout
        self._monitor_interval = check_interval
        self._monitor_stop.clear()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"[Registry] HeartbeatMonitor iniciado | timeout={heartbeat_timeout}s "
            f"interval={check_interval}s"
        )

    async def stop_monitor(self) -> None:
        """Encerra o loop de monitoramento."""
        self._monitor_stop.set()
        if self._monitor_task:
            try:
                await asyncio.wait_for(self._monitor_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._monitor_task.cancel()
            self._monitor_task = None
        logger.info("[Registry] HeartbeatMonitor encerrado")

    async def _monitor_loop(self) -> None:
        from datetime import timedelta
        while not self._monitor_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._monitor_stop.wait(),
                    timeout=self._monitor_interval,
                )
                break 
            except asyncio.TimeoutError:
                pass

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=self._heartbeat_timeout)
            marked = []
            async with self._lock:
                for info in self._agents.values():
                    if (
                        info.status != AgentStatusEnum.OFFLINE
                        and info.last_seen_at < cutoff
                    ):
                        info.status = AgentStatusEnum.OFFLINE
                        marked.append(info.agent_id)
            for aid in marked:
                logger.warning(f"[Registry] Agente {aid} marcado OFFLINE (sem heartbeat)")

    # Stats
    async def stats(self) -> Dict[str, Any]:
        """Retorna estatisticas agregadas do registry."""
        async with self._lock:
            total = len(self._agents)
            by_status: Dict[str, int] = {}
            by_capability: Dict[str, int] = {}
            for info in self._agents.values():
                by_status[info.status.value] = by_status.get(info.status.value, 0) + 1
                for cap in info.capabilities:
                    by_capability[cap] = by_capability.get(cap, 0) + 1
            return {
                "total_agents": total,
                "by_status": by_status,
                "by_capability": by_capability,
            }
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_stop = asyncio.Event()
        self._heartbeat_timeout: float = 30.0
        self._monitor_interval: float = 5.0





