"""Teste E2E: Orchestrator + MessageBus + Agentes Mock."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import app_logger as logger
from core.messaging.message_bus import BusMessage, MessageBus
from core.orchestration import (
    AgentInfo, AgentRegistry,
    OrchestratorAgent, Task, TaskStatus,
)
from core.orchestration.registry import AgentCapability


# MOCK AGENT
class MockAgent:
    """Agente simples que recebe tarefa e devolve resultado."""

    def __init__(self, agent_id: str, bus: MessageBus, delay: float = 0.1,
                 should_fail: bool = False, silent: bool = False):
        self.agent_id = agent_id
        self.bus = bus
        self.delay = delay
        self.should_fail = should_fail
        self.silent = silent 
        self.received_count = 0

    async def start(self):
        inbox = self.bus.agent_topic(self.agent_id)
        await self.bus.subscribe(inbox, self._handle)
        logger.info(f"[MockAgent:{self.agent_id}] Pronto | inbox={inbox}")

    async def _handle(self, msg: BusMessage):
        if msg.msg_type != "task":
            return
        self.received_count += 1
        task_id = msg.metadata.get("task_id")
        reply_to = msg.metadata.get("reply_to", "orchestrator")
        logger.info(f"[MockAgent:{self.agent_id}] Recebeu task={task_id[:8]} "
                    f"payload='{msg.content}'")

        await asyncio.sleep(self.delay)

        if self.silent:
            logger.info(f"[MockAgent:{self.agent_id}] SILENT - nao respondera")
            return

        # Responder
        if self.should_fail:
            content = f"erro simulado em {self.agent_id}"
            success = False
        else:
            content = f"[{self.agent_id}] processou: {msg.content.upper()}"
            success = True

        await self.bus.publish_to_agent(
            sender_id=self.agent_id,
            receiver_id=reply_to,
            content=content,
            msg_type="task_result",
            task_id=task_id,
            success=success,
        )


# MAIN
async def main() -> int:
    errors = 0
    bus = MessageBus()
    await bus.connect()
    registry = AgentRegistry()
    orch = OrchestratorAgent(registry=registry, bus=bus, default_timeout=5.0)
    await orch.start()

    # Registrar agentes
    researchers = [MockAgent(f"researcher-{i}", bus, delay=0.1) for i in range(1, 4)]
    coder       = MockAgent("coder-1", bus, delay=0.1)
    silent      = MockAgent("silent-1", bus, delay=0.0, silent=True)
    for r in researchers:
        await r.start()
    await coder.start()
    await silent.start()

    for r in researchers:
        await registry.register(AgentInfo(
            agent_id=r.agent_id, name=r.agent_id,
            capabilities=[AgentCapability.RESEARCH],
        ))
    await registry.register(AgentInfo(
        agent_id="coder-1", name="Coder",
        capabilities=[AgentCapability.CODING],
    ))
    await registry.register(AgentInfo(
        agent_id="silent-1", name="Silent",
        capabilities=["silent_cap"],
    ))

    # submissao simples
    logger.info("\n" + "=" * 60)
    logger.info("TESTE 1: submit_task simples (research)")
    logger.info("=" * 60)
    r1 = await orch.submit_task(Task(capability="research", payload="hello world"))
    logger.info(f"Resultado: {r1.model_dump()}")
    if r1.status != TaskStatus.COMPLETED:
        errors += 1; logger.error("FALHOU: status != COMPLETED")
    elif "HELLO WORLD" not in (r1.output or ""):
        errors += 1; logger.error(f"FALHOU: output inesperado: {r1.output}")
    else:
        logger.info("OK")

    # roteamento por capability
    logger.info("\n" + "=" * 60)
    logger.info("TESTE 2: roteamento por capability (coding)")
    logger.info("=" * 60)
    r2 = await orch.submit_task(Task(capability="coding", payload="def foo()"))
    logger.info(f"Resultado: agent={r2.agent_id} status={r2.status.value}")
    if r2.agent_id != "coder-1":
        errors += 1; logger.error(f"FALHOU: roteou para {r2.agent_id} em vez de coder-1")
    else:
        logger.info("OK")

    # tasks concorrentes
    logger.info("\n" + "=" * 60)
    logger.info("TESTE 3: 3 tasks concorrentes")
    logger.info("=" * 60)
    tasks = [
        orch.submit_task(Task(capability="research", payload=f"q{i}"))
        for i in range(3)
    ]
    results = await asyncio.gather(*tasks)
    ok_count = sum(1 for r in results if r.status == TaskStatus.COMPLETED)
    logger.info(f"Completed: {ok_count}/3")
    if ok_count != 3:
        errors += 1; logger.error("FALHOU: nem todas completaram")
    else:
        logger.info("OK")

    # NO_AGENT
    logger.info("\n" + "=" * 60)
    logger.info("TESTE 4: capability inexistente -> NO_AGENT")
    logger.info("=" * 60)
    r4 = await orch.submit_task(
        Task(capability="nao_existe", payload="x"),
        timeout=0.5, queue_timeout=0.5,
    )
    logger.info(f"Resultado: status={r4.status.value} error={r4.error}")
    if r4.status != TaskStatus.TIMEOUT:
        errors += 1; logger.error("FALHOU: deveria ser TIMEOUT (queue timeout)")
    else:
        logger.info("OK - capability inexistente expirou na fila")

    # TIMEOUT
    logger.info("\n" + "=" * 60)
    logger.info("TESTE 5: agente silent -> TIMEOUT")
    logger.info("=" * 60)
    r5 = await orch.submit_task(
        Task(capability="silent_cap", payload="ping"),
        timeout=1.5,
    )
    logger.info(f"Resultado: status={r5.status.value} duration={r5.duration_seconds}s")
    if r5.status != TaskStatus.TIMEOUT:
        errors += 1; logger.error("FALHOU: deveria ser TIMEOUT")
    else:
        logger.info("OK")

    silent_info = await registry.get("silent-1")
    if silent_info.status.value != "idle":
        errors += 1
        logger.error(f"FALHOU: silent-1 deveria estar IDLE, esta {silent_info.status.value}")
    else:
        logger.info("OK - agente liberado apos timeout")

    # STATS
    logger.info("\n" + "=" * 60)
    logger.info(f"Orchestrator stats: {orch.get_stats()}")
    logger.info(f"Registry stats: {await registry.stats()}")

    # Cleanup
    await orch.stop()
    await bus.disconnect()

    logger.info("\n" + "=" * 60)
    if errors == 0:
        logger.info("  TODOS OS TESTES E2E PASSARAM!")
    else:
        logger.error(f"  {errors} TESTE(S) FALHARAM")
    logger.info("=" * 60)
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


