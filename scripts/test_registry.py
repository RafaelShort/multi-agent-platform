"""Testes do AgentRegistry."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orchestration import AgentRegistry, AgentInfo
from core.orchestration.registry import AgentStatusEnum, AgentCapability
from core.logger import app_logger as logger


async def main() -> int:
    errors = 0
    reg = AgentRegistry()

    logger.info("=" * 60)
    logger.info("TESTE 1: register()")
    logger.info("=" * 60)
    await reg.register(AgentInfo(
        agent_id="a1", name="Researcher-1",
        capabilities=[AgentCapability.RESEARCH, AgentCapability.SUMMARIZATION],
    ))
    await reg.register(AgentInfo(
        agent_id="a2", name="Coder-1",
        capabilities=[AgentCapability.CODING, AgentCapability.REVIEW],
    ))
    await reg.register(AgentInfo(
        agent_id="a3", name="Researcher-2",
        capabilities=[AgentCapability.RESEARCH],
    ))
    all_agents = await reg.list_all()
    assert len(all_agents) == 3
    logger.info("OK - 3 agentes registrados")

    logger.info("\nTESTE 2: get()")
    a1 = await reg.get("a1")
    assert a1 is not None and a1.name == "Researcher-1"
    assert await reg.get("inexistente") is None
    logger.info("OK - get() funciona")

    logger.info("\nTESTE 3: find_by_capability('research')")
    researchers = await reg.find_by_capability("research")
    assert len(researchers) == 2
    logger.info(f"OK - {len(researchers)} researchers encontrados")

    logger.info("\nTESTE 4: update_status() + only_available")
    await reg.update_status("a1", AgentStatusEnum.BUSY)
    available = await reg.find_by_capability("research", only_available=True)
    assert len(available) == 1 and available[0].agent_id == "a3"
    logger.info("OK - filtro de disponibilidade funciona")

    logger.info("\nTESTE 5: find_by_status(BUSY)")
    busy = await reg.find_by_status(AgentStatusEnum.BUSY)
    assert len(busy) == 1 and busy[0].agent_id == "a1"
    logger.info("OK - find_by_status funciona")

    logger.info("\nTESTE 6: heartbeat()")
    a3_before = await reg.get("a3")
    ts_before = a3_before.last_seen_at
    await asyncio.sleep(0.05)
    assert await reg.heartbeat("a3") is True
    a3_after = await reg.get("a3")
    assert a3_after.last_seen_at > ts_before
    logger.info("OK - heartbeat atualiza last_seen_at")

    logger.info("\nTESTE 7: unregister()")
    assert await reg.unregister("a2") is True
    assert await reg.unregister("a2") is False
    assert len(await reg.list_all()) == 2
    logger.info("OK - unregister funciona")

    logger.info("\nTESTE 8: stats()")
    stats = await reg.stats()
    logger.info(f"Stats: {stats}")
    assert stats["total_agents"] == 2
    assert stats["by_status"].get("busy") == 1
    assert stats["by_status"].get("idle") == 1
    assert stats["by_capability"].get("research") == 2
    logger.info("OK - stats corretas")

    logger.info("\n" + "=" * 60)
    logger.info("  TODOS OS TESTES DO REGISTRY PASSARAM!")
    logger.info("=" * 60)
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
