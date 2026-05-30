"""Teste: TaskQueue + Dispatcher (back-pressure)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import app_logger as logger
from core.messaging.message_bus import BusMessage, MessageBus
from core.orchestration import (
    AgentInfo, AgentRegistry, OrchestratorAgent, Task, TaskStatus,
    RoundRobinStrategy,
)
from core.orchestration.registry import AgentCapability


class SlowAgent:
    def __init__(self, agent_id, bus, delay=0.3):
        self.agent_id = agent_id
        self.bus = bus
        self.delay = delay
        self.processed = 0

    async def start(self):
        await self.bus.subscribe(self.bus.agent_topic(self.agent_id), self._h)

    async def _h(self, msg: BusMessage):
        if msg.msg_type != "task":
            return
        self.processed += 1
        await asyncio.sleep(self.delay)
        await self.bus.publish_to_agent(
            sender_id=self.agent_id,
            receiver_id=msg.metadata.get("reply_to", "orchestrator"),
            content=f"{self.agent_id}:done",
            msg_type="task_result",
            task_id=msg.metadata.get("task_id"),
            success=True,
        )


async def main() -> int:
    errors = 0

    bus = MessageBus(); await bus.connect()
    reg = AgentRegistry()
    orch = OrchestratorAgent(
        registry=reg, bus=bus,
        strategy=RoundRobinStrategy(),
        default_timeout=10.0, queue_timeout=15.0,
    )
    await orch.start()

    agents = [SlowAgent(f"slow-{i}", bus, delay=0.3) for i in range(1, 3)]
    for a in agents:
        await a.start()
        await reg.register(AgentInfo(
            agent_id=a.agent_id, name=a.agent_id,
            capabilities=[AgentCapability.RESEARCH],
        ))

    logger.info("=" * 60)
    logger.info("TESTE 1: 10 tasks concorrentes / 2 agentes => fila drena")
    logger.info("=" * 60)
    coros = [
        orch.submit_task(Task(capability="research", payload=f"t{i}"))
        for i in range(10)
    ]
    results = await asyncio.gather(*coros)
    ok = sum(1 for r in results if r.status == TaskStatus.COMPLETED)
    logger.info(f"Completed: {ok}/10")
    logger.info(f"Por agente: slow-1={agents[0].processed} slow-2={agents[1].processed}")
    queued_count = sum(1 for r in results if r.queued_seconds > 0.05)
    logger.info(f"Tasks que esperaram na fila (>50ms): {queued_count}")

    if ok != 10:
        errors += 1; logger.error("FALHOU: nem todas completaram")
    elif agents[0].processed + agents[1].processed != 10:
        errors += 1; logger.error("FALHOU: contadores nao batem")
    elif queued_count < 6:
        errors += 1; logger.error(f"FALHOU: poucas enfileiradas ({queued_count})")
    else:
        logger.info("OK - fila drenou corretamente sob back-pressure")

    logger.info("\n" + "=" * 60)
    logger.info("TESTE 2: capability sem agente => queue_timeout")
    logger.info("=" * 60)
    r = await orch.submit_task(
        Task(capability="inexistente", payload="x"),
        timeout=0.3, queue_timeout=0.3,
    )
    logger.info(f"status={r.status.value} queued={r.queued_seconds:.2f}s")
    if r.status != TaskStatus.TIMEOUT:
        errors += 1; logger.error("FALHOU: deveria ser TIMEOUT")
    else:
        logger.info("OK - expirou na fila")

    logger.info("\n" + "=" * 60)
    logger.info("TESTE 3: enfileira sem agente -> registra agente -> drena")
    logger.info("=" * 60)
    fut = asyncio.create_task(orch.submit_task(
        Task(capability="late_cap", payload="ola"),
        timeout=5.0, queue_timeout=5.0,
    ))
    await asyncio.sleep(0.2)
    late = SlowAgent("late-1", bus, delay=0.05)
    await late.start()
    await reg.register(AgentInfo(
        agent_id="late-1", name="late-1", capabilities=["late_cap"],
    ))
    orch._wakeup.set()

    r3 = await fut
    logger.info(f"status={r3.status.value} agent={r3.agent_id} queued={r3.queued_seconds:.2f}s")
    if r3.status != TaskStatus.COMPLETED:
        errors += 1; logger.error("FALHOU: deveria completar apos agente surgir")
    elif r3.queued_seconds < 0.15:
        errors += 1; logger.error("FALHOU: deveria ter ficado na fila")
    else:
        logger.info("OK - dispatcher drenou apos agente disponivel")

    logger.info(f"\nStats finais: {orch.get_stats()}")

    await orch.stop()
    await bus.disconnect()

    logger.info("\n" + "=" * 60)
    if errors == 0:
        logger.info("  TESTES DE QUEUE/BACK-PRESSURE: TODOS OK!")
    else:
        logger.error(f"  {errors} FALHARAM")
    logger.info("=" * 60)
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
