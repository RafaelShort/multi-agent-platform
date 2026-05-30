"""
Routing Strategies
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from core.orchestration.registry import AgentInfo


# INTERFACE

class RoutingStrategy(ABC):
    """Interface para politicas de selecao de agente."""

    @abstractmethod
    async def choose(
        self,
        capability: str,
        candidates: List[AgentInfo],
    ) -> Optional[AgentInfo]:
        """
        Retorna o agente escolhido ou None se nenhum disponivel.
        """
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


# IMPLEMENTACOES

class FirstAvailableStrategy(RoutingStrategy):
    """Sempre escolhe o primeiro da lista. Baseline / determinista."""

    async def choose(self, capability, candidates):
        return candidates[0] if candidates else None


class RoundRobinStrategy(RoutingStrategy):
    """
    Round-robin por capability.
    """

    def __init__(self) -> None:
        self._cursors: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def choose(self, capability, candidates):
        if not candidates:
            return None
        async with self._lock:
            cursor = self._cursors.get(capability, 0)
            # Ordena por agent_id para garantir ordem estavel entre chamadas
            sorted_candidates = sorted(candidates, key=lambda a: a.agent_id)
            chosen = sorted_candidates[cursor % len(sorted_candidates)]
            self._cursors[capability] = (cursor + 1) % max(len(sorted_candidates), 1)
            return chosen


class LeastBusyStrategy(RoutingStrategy):
    """
    Escolhe o agente com menor numero de tasks em andamento.
    """

    def __init__(self) -> None:
        self._dispatch_count: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def choose(self, capability, candidates):
        if not candidates:
            return None
        async with self._lock:
            chosen = min(
                candidates,
                key=lambda a: self._dispatch_count.get(a.agent_id, 0),
            )
            self._dispatch_count[chosen.agent_id] = (
                self._dispatch_count.get(chosen.agent_id, 0) + 1
            )
            return chosen

    def get_counts(self) -> Dict[str, int]:
        return dict(self._dispatch_count)
