"""Teste: RoundRobinStrategy distribui tasks igualmente."""
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import app_logger as logger
from core.messaging.message_bus import BusMessage, MessageBus
from core.orchestration import (
    AgentInfo, AgentRegistry, OrchestratorAgent, Task, TaskStatus,
    RoundRobinStrategy, LeastBusyStrategy,
)
from core.orchestration.registry import AgentCapability


class EchoAgent:
    def __init__(self, agent_id, bus):
        self.agent_id = agent_id
        self.bus = bus

    async def start(self):
        await self.bus.subscribe(self.bus.agent_topic(self.agent_id), self._handle)

    async def _handle(self, msg: BusMessage):
        if msg.msg_type != "task":
            return
        await asyncio.sleep(0.02)
        await self.bus.publish_to_agent(
            sender_id=self.agent_id,
            receiver_id=msg.metadata.get("reply_to", "orchestrator"),
            content=f"{self.agent_id}:done",
            msg_type="task_result",
            task_id=msg.metadata.get("task_id"),
            success=True,
        )


async def run_with(strategy, label, n_tasks=9):
    bus = MessageBus(); await bus.connect()
    reg = AgentRegistry()
    orch = OrchestratorAgent(registry=reg, bus=bus, strategy=strategy, default_timeout=5.0)
    await orch.start()

    for i in range(1, 4):
        ag = EchoAgent(f"agent-{i}", bus)
        await ag.start()
        await reg.register(AgentInfo(
            agent_id=ag.agent_id, name=ag.agent_id,
            capabilities=[AgentCapability.RESEARCH],
        ))

    results = []
    for i in range(n_tasks):
        r = await orch.submit_task(Task(capability="research", payload=f"t{i}"))
        results.append(r)

    dist = Counter(r.agent_id for r in results)
    logger.info(f"[{label}] Distribuicao: {dict(dist)}")

    await orch.stop()
    await bus.disconnect()
    return dist, results


async def main() -> int:
    errors = 0

    logger.info("=" * 60)
    logger.info("TESTE: RoundRobin com 9 tasks / 3 agentes => 3 cada")
    logger.info("=" * 60)
    dist, results = await run_with(RoundRobinStrategy(), "RR", n_tasks=9)
    if not all(r.status == TaskStatus.COMPLETED for r in results):
        errors += 1; logger.error("FALHOU: nem todas COMPLETED")
    elif sorted(dist.values()) != [3, 3, 3]:
        errors += 1; logger.error(f"FALHOU: distribuicao desigual {dict(dist)}")
    else:
        logger.info("OK - RR distribuiu igualmente")

    logger.info("\n" + "=" * 60)
    logger.info("TESTE: LeastBusy com 6 tasks / 3 agentes => 2 cada")
    logger.info("=" * 60)
    dist, results = await run_with(LeastBusyStrategy(), "LB", n_tasks=6)
    if not all(r.status == TaskStatus.COMPLETED for r in results):
        errors += 1; logger.error("FALHOU: nem todas COMPLETED")
    elif sorted(dist.values()) != [2, 2, 2]:
        errors += 1; logger.error(f"FALHOU: distribuicao desigual {dict(dist)}")
    else:
        logger.info("OK - LeastBusy distribuiu igualmente")

    logger.info("\n" + "=" * 60)
    if errors == 0:
        logger.info("  TESTES DE STRATEGY INTEGRADA: OK!")
    else:
        logger.error(f"  {errors} FALHARAM")
    logger.info("=" * 60)
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
