"""
bootstrap.py — Monta a plataforma multi-agente pronta para uso.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

from core.logger import app_logger as logger
from core.messaging.message_bus import MessageBus
from core.orchestration import AgentRegistry, OrchestratorAgent
from core.orchestration.strategies import RoundRobinStrategy
from core.agents.llm_agent import LLMAgent
from core.llm.providers.openai_provider import OpenAIProvider
from core.personas import Persona, PERSONAS


@dataclass
class Platform:
    bus: MessageBus
    registry: AgentRegistry
    orchestrator: OrchestratorAgent
    agents: List[LLMAgent] = field(default_factory=list)
    personas: List[Persona] = field(default_factory=list)

    async def stop(self) -> None:
        for a in self.agents:
            try:
                await a.stop()
            except Exception:
                logger.exception(f"Falha ao parar agent {a.agent_id}")
        try:
            await self.orchestrator.stop()
        except Exception:
            logger.exception("Falha ao parar orchestrator")
        try:
            await self.bus.disconnect()
        except Exception:
            logger.exception("Falha ao desconectar bus")
        logger.info("[bootstrap] Plataforma encerrada.")


async def build_platform(
    *,
    personas: Optional[List[Persona]] = None,
    ollama_model: str = "llama3.2:latest",
    ollama_base_url: str = "http://localhost:11434/v1",
    num_chat_agents: Optional[int] = None,  
    default_timeout: float = 90.0,
    queue_timeout: float = 30.0,
    warmup_seconds: float = 1.5,
) -> Platform:
    personas = personas if personas is not None else PERSONAS

    logger.info("[bootstrap] Conectando MessageBus...")
    bus = MessageBus()
    await bus.connect()

    registry = AgentRegistry()

    logger.info("[bootstrap] Iniciando Orchestrator...")
    orch = OrchestratorAgent(
        registry=registry,
        bus=bus,
        strategy=RoundRobinStrategy(),
        default_timeout=default_timeout,
        queue_timeout=queue_timeout,
    )
    await orch.start()

    agents: List[LLMAgent] = []
    for p in personas:
        provider = OpenAIProvider(
            api_key="ollama",
            model=ollama_model,
            base_url=ollama_base_url,
            timeout=default_timeout,
        )
        agent = LLMAgent(
            agent_id=p.id,
            bus=bus,
            registry=registry,
            provider=provider,
            capabilities=["chat", p.id],  
            default_system=p.system,
        )
        await agent.start()
        agents.append(agent)
        logger.info(f"[bootstrap] Agent {p.emoji} {p.name} ({p.id}) pronto.")

    if warmup_seconds:
        await asyncio.sleep(warmup_seconds)

    logger.info(f"[bootstrap] Plataforma pronta com {len(agents)} persona(s).")
    return Platform(
        bus=bus, registry=registry, orchestrator=orch,
        agents=agents, personas=personas,
    )
