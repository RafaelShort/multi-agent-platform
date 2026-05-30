"""Teste e2e: LLMAgent + OpenAIProvider apontando para Ollama local."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json

from core.llm.providers.openai_provider import OpenAIProvider
from core.llm.providers.base import ChatMessage
from core.logger import logger


async def test_direct_provider():
    logger.info("=" * 60)
    logger.info("TESTE 1: OpenAIProvider -> Ollama (direto)")
    logger.info("=" * 60)

    provider = OpenAIProvider(
        api_key="ollama",
        model="llama3.2:latest",
        base_url="http://localhost:11434/v1",
        timeout=60.0,
    )

    try:
        healthy = await provider.health_check()
        logger.info(f"health_check: {healthy}")

        messages = [
            ChatMessage(role="system", content="Voce e um assistente conciso. Responda em portugues."),
            ChatMessage(role="user", content="Diga 'ola mundo' e nada mais."),
        ]
        response = await provider.chat(messages, temperature=0.2, max_tokens=50)

        logger.info(f"content: {response.content!r}")
        logger.info(f"model: {response.model}")
        logger.info(f"tokens: prompt={response.prompt_tokens} completion={response.completion_tokens} total={response.total_tokens}")
        logger.info(f"latency: {response.latency_ms:.0f}ms")

        assert response.content, "content vazio"
        assert response.provider == "openai"
        logger.info("TESTE 1 OK")
        return True
    finally:
        await provider.close()


async def test_with_llm_agent():
    from core.messaging.message_bus import MessageBus
    from core.orchestration.orchestrator import OrchestratorAgent
    from core.orchestration.registry import AgentRegistry
    from core.agents.llm_agent import LLMAgent
    from core.orchestration.orchestrator import Task

    logger.info("=" * 60)
    logger.info("TESTE 2: LLMAgent + Ollama (e2e via orchestrator)")
    logger.info("=" * 60)

    bus = MessageBus()
    await bus.connect()
    registry = AgentRegistry()

    orch = OrchestratorAgent(bus=bus, registry=registry)
    await orch.start()

    provider = OpenAIProvider(
        api_key="ollama",
        model="llama3.2:latest",
        base_url="http://localhost:11434/v1",
        timeout=60.0,
    )

    agent = LLMAgent(
        agent_id="llama-1",
        bus=bus,
        registry=registry,
        provider=provider,
        capabilities=["chat"],
        default_system="Voce e um assistente direto. Responda em ate 2 frases.",
    )
    await agent.start()

    await asyncio.sleep(2)

    try:
        task = Task(
            capability="chat",
            payload=json.dumps({
                "prompt": "Qual a capital do Brasil? Responda em uma frase.",
                "temperature": 0.1,
                "max_tokens": 60,
            }),
        )
        result = await orch.submit_task(task, timeout=60.0)

        logger.info(f"status: {result.status}")
        if result.output:
            parsed = json.loads(result.output)
            logger.info(f"resposta: {parsed['content']!r}")
            logger.info(f"tokens: {parsed['tokens']}")
            logger.info(f"latency: {parsed['latency_ms']}ms")

        assert result.status == "completed", f"status={result.status} err={result.error}"
        assert "bras" in json.loads(result.output)["content"].lower()
        logger.info("TESTE 2 OK")
        return True
    finally:
        await agent.stop()
        await orch.stop()
        await bus.disconnect()
        await provider.close()


async def main():
    results = []
    try:
        results.append(await test_direct_provider())
        results.append(await test_with_llm_agent())
    except Exception as e:
        logger.exception(f"erro no teste: {e}")
        return 1

    if all(results):
        logger.info("=" * 60)
        logger.info("OLLAMA E2E: TODOS OK!")
        logger.info("=" * 60)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


