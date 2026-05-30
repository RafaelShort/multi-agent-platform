"""Teste E2E: BaseAgent + heartbeat + auto-OFFLINE."""
import asyncio
import sys
from pathlib import Path
from typing import Any, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agents import BaseAgent
from core.logger import app_logger as logger
from core.messaging.message_bus import BusMessage, MessageBus
from core.orchestration import (
    AgentRegistry, OrchestratorAgent, RoundRobinStrategy, Task, TaskStatus,
)
from core.orchestration.registry import AgentStatusEnum


class EchoAgent(BaseAgent):
    @property
    def capabilities(self) -> List[str]:
        return ["echo"]

    async def handle_task(self, msg: BusMessage) -> Tuple[Any, bool]:
        await asyncio.sleep(0.05)
        return f"echo:{msg.content}", True


class FailingAgent(BaseAgent):
    @property
    def capabilities(self) -> List[str]:
        return ["fail"]

    async def handle_task(self, msg: BusMessage) -> Tuple[Any, bool]:
        raise RuntimeError("boom!")


class ZombieAgent(BaseAgent):
    """Agente que para de mandar heartbeat (simula trava)."""
    @property
    def capabilities(self) -> List[str]:
        return ["zombie"]

    async def handle_task(self, msg: BusMessage) -> Tuple[Any, bool]:
        return "ok", True

    async def freeze(self) -> None:
        """Para o heartbeat sem chamar stop (simula processo travado)."""
        self._hb_stop.set()
        if self._hb_task:
            await asyncio.wait_for(self._hb_task, timeout=2.0)
            self._hb_task = None


async def main() -> int:
    errors = 0
    bus = MessageBus(); await bus.connect()
    reg = AgentRegistry()
    await reg.start_monitor(heartbeat_timeout=2.0, check_interval=0.5)

    orch = OrchestratorAgent(
        registry=reg, bus=bus, strategy=RoundRobinStrategy(),
        default_timeout=10.0, queue_timeout=10.0,
    )
    await orch.start()

    echo = EchoAgent(agent_id="echo-1", bus=bus, registry=reg, heartbeat_interval=0.5)
    fail = FailingAgent(agent_id="fail-1", bus=bus, registry=reg, heartbeat_interval=0.5)
    zomb = ZombieAgent(agent_id="zomb-1", bus=bus, registry=reg, heartbeat_interval=0.5)
    for a in (echo, fail, zomb):
        await a.start()

    logger.info("=" * 60)
    logger.info("TESTE 1: BaseAgent processa task com sucesso")
    logger.info("=" * 60)
    r = await orch.submit_task(Task(capability="echo", payload="hello"))
    logger.info(f"status={r.status.value} output={r.output}")
    if r.status != TaskStatus.COMPLETED or r.output != "echo:hello":
        errors += 1; logger.error("FALHOU")
    else:
        logger.info("OK")

    logger.info("\n" + "=" * 60)
    logger.info("TESTE 2: excecao no handle_task => FAILED")
    logger.info("=" * 60)
    r = await orch.submit_task(Task(capability="fail", payload="x"))
    logger.info(f"status={r.status.value} output={r.output} error={r.error}")
    if r.status != TaskStatus.FAILED or not r.error or "boom" not in r.error:
        errors += 1; logger.error("FALHOU")
    else:
        logger.info("OK")

    logger.info("\n" + "=" * 60)
    logger.info("TESTE 3: heartbeat mantem agente vivo apos 3s")
    logger.info("=" * 60)
    await asyncio.sleep(3.0)
    info = await reg.get("echo-1")
    logger.info(f"echo-1 status={info.status.value}")
    if info.status == AgentStatusEnum.OFFLINE:
        errors += 1; logger.error("FALHOU: virou OFFLINE com heartbeat ativo")
    else:
        logger.info("OK")

    logger.info("\n" + "=" * 60)
    logger.info("TESTE 4: zombie para heartbeat => marcado OFFLINE")
    logger.info("=" * 60)
    await zomb.freeze()
    logger.info("zomb-1 congelado. Aguardando deteccao (timeout=2s, check=0.5s)...")
    await asyncio.sleep(3.5)
    info = await reg.get("zomb-1")
    logger.info(f"zomb-1 status={info.status.value}")
    if info.status != AgentStatusEnum.OFFLINE:
        errors += 1; logger.error("FALHOU: deveria estar OFFLINE")
    else:
        logger.info("OK")

    logger.info("\n" + "=" * 60)
    logger.info("TESTE 5: capability so com agente OFFLINE => TIMEOUT")
    logger.info("=" * 60)
    r = await orch.submit_task(
        Task(capability="zombie", payload="x"),
        timeout=1.0, queue_timeout=1.0,
    )
    logger.info(f"status={r.status.value}")
    if r.status != TaskStatus.TIMEOUT:
        errors += 1; logger.error("FALHOU: deveria expirar (sem agente vivo)")
    else:
        logger.info("OK")

    for a in (echo, fail):
        await a.stop()
    await orch.stop()
    await reg.stop_monitor()
    await bus.disconnect()

    logger.info("\n" + "=" * 60)
    if errors == 0:
        logger.info("  BASE AGENT + HEARTBEAT: TODOS OK!")
    else:
        logger.error(f"  {errors} FALHARAM")
    logger.info("=" * 60)
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


