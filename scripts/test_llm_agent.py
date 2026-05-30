import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
"""
E2E: Orchestrator -> LLMAgent -> MockProvider.
"""
import asyncio

import json
import sys
from typing import Any

from core.agents import LLMAgent
from core.llm import MockProvider
from core.logger import app_logger as logger
from core.messaging.message_bus import MessageBus
from core.orchestration.orchestrator import OrchestratorAgent, Task, TaskStatus
from core.orchestration.registry import AgentRegistry


def section(title: str) -> None:
    logger.info("\n" + "=" * 60)
    logger.info(title)
    logger.info("=" * 60)


async def main() -> int:
    bus = MessageBus(bootstrap_servers="localhost:9092")
    await bus.connect()

    reg = AgentRegistry()
    await reg.start_monitor(heartbeat_timeout=5.0, check_interval=1.0)

    orch = OrchestratorAgent(bus=bus, registry=reg, queue_timeout=10.0)
    await orch.start()

    # provider que funciona
    good = MockProvider(prefix="[mock-good] ", simulated_latency=0.02)
    chat_agent = LLMAgent(
        agent_id="chat-1",
        bus=bus,
        registry=reg,
        provider=good,
        capabilities=["chat"],
        default_system="Voce e um assistente util.",
        heartbeat_interval=2.0,
    )
    await chat_agent.start()

    bad = MockProvider(fail_mode=True)
    broken_agent = LLMAgent(
        agent_id="broken-1",
        bus=bus,
        registry=reg,
        provider=bad,
        capabilities=["broken"],
        heartbeat_interval=2.0,
    )
    await broken_agent.start()

    await asyncio.sleep(1.5) 

    failures = 0

    async def run(name: str, task: Task, expect_status: TaskStatus, check=None) -> None:
        nonlocal failures
        section(name)
        r = await orch.submit_task(task, timeout=15.0)
        logger.info(
            f"status={r.status.value} "
            f"output={str(r.output)[:200] if r.output else None} "
            f"error={r.error}"
        )
        ok = r.status == expect_status and (check is None or check(r))
        logger.info("OK" if ok else "FALHOU")
        if not ok:
            failures += 1

    await run(
        "TESTE 1: payload string => COMPLETED",
        Task(capability="chat", payload="ola mundo"),
        TaskStatus.COMPLETED,
        check=lambda r: "ola mundo" in json.loads(r.output)["content"]
                        and json.loads(r.output)["provider"] == "mock"
                        and json.loads(r.output)["tokens"]["total"] > 0,
    )

    await run(
        "TESTE 2: dict {prompt, system, temperature} => COMPLETED",
        Task(
            capability="chat",
            payload=json.dumps({
                "prompt": "resuma multiagentes",
                "system": "Voce e um pesquisador.",
                "temperature": 0.2,
            }),
        ),
        TaskStatus.COMPLETED,
        check=lambda r: r.output and "resuma multiagentes" in json.loads(r.output)["content"],
    )

    await run(
        "TESTE 3: messages multi-turn => COMPLETED",
        Task(
            capability="chat",
            payload=json.dumps({
                "messages": [
                    {"role": "system", "content": "responda curto"},
                    {"role": "user", "content": "oi"},
                    {"role": "assistant", "content": "ola!"},
                    {"role": "user", "content": "tudo bem?"},
                ]
            }),
        ),
        TaskStatus.COMPLETED,
        check=lambda r: r.output and "tudo bem?" in json.loads(r.output)["content"],
    )

    await run(
        "TESTE 4: payload invalido (int) => FAILED com InvalidPayload",
        Task(capability="chat", payload=json.dumps({"foo": "bar"})),  # dict sem prompt/messages
        TaskStatus.FAILED,
        check=lambda r: r.error and "InvalidPayload" in r.error,
    )

    await run(
        "TESTE 5: provider em fail_mode => FAILED com LLMProviderError",
        Task(capability="broken", payload="qualquer"),
        TaskStatus.FAILED,
        check=lambda r: r.error and "LLMProviderError" in r.error,
    )

    section("STATS")
    logger.info(f"chat-1   stats: {chat_agent.get_stats()}")
    logger.info(f"broken-1 stats: {broken_agent.get_stats()}")
    logger.info(f"orch     stats: {orch._stats}")

    await chat_agent.stop()
    await broken_agent.stop()
    await orch.stop()
    await reg.stop_monitor()
    await bus.disconnect()

    section("RESULTADO FINAL")
    if failures == 0:
        logger.info("  LLM AGENT E2E: TODOS OK!")
        return 0
    logger.error(f"  {failures} FALHARAM")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))





