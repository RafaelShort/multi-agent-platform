"""Testes unitarios das routing strategies."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import app_logger as logger
from core.orchestration.registry import AgentInfo, AgentCapability
from core.orchestration.strategies import (
    FirstAvailableStrategy,
    RoundRobinStrategy,
    LeastBusyStrategy,
)


def make_agents(ids):
    return [
        AgentInfo(agent_id=i, name=i, capabilities=[AgentCapability.RESEARCH])
        for i in ids
    ]


async def main() -> int:
    errors = 0

    # FirstAvailable
    logger.info("=" * 60)
    logger.info("TESTE 1: FirstAvailableStrategy")
    logger.info("=" * 60)
    s = FirstAvailableStrategy()
    agents = make_agents(["a", "b", "c"])
    chosen = [(await s.choose("research", agents)).agent_id for _ in range(5)]
    logger.info(f"Escolhidos: {chosen}")
    if chosen != ["a"] * 5:
        errors += 1; logger.error("FALHOU: deveria escolher 'a' sempre")
    else:
        logger.info("OK")

    # RoundRobin
    logger.info("\nTESTE 2: RoundRobinStrategy (6 escolhas, 3 agentes)")
    s = RoundRobinStrategy()
    agents = make_agents(["a", "b", "c"])
    chosen = [(await s.choose("research", agents)).agent_id for _ in range(6)]
    logger.info(f"Escolhidos: {chosen}")
    if chosen != ["a", "b", "c", "a", "b", "c"]:
        errors += 1; logger.error("FALHOU: ordem RR incorreta")
    else:
        logger.info("OK")

    # RR isola por capability
    logger.info("\nTESTE 3: RR cursores independentes por capability")
    s = RoundRobinStrategy()
    a1 = make_agents(["x", "y"])
    await s.choose("cap1", a1)  # x
    await s.choose("cap1", a1)  # y
    pick = await s.choose("cap2", a1)  # cursor cap2=0 -> x
    logger.info(f"cap2 primeira escolha: {pick.agent_id}")
    if pick.agent_id != "x":
        errors += 1; logger.error("FALHOU: cap2 deveria comecar do zero")
    else:
        logger.info("OK")

    # LeastBusy
    logger.info("\nTESTE 4: LeastBusyStrategy (5 escolhas, 3 agentes)")
    s = LeastBusyStrategy()
    agents = make_agents(["a", "b", "c"])
    chosen = [(await s.choose("research", agents)).agent_id for _ in range(5)]
    logger.info(f"Escolhidos: {chosen}")
    logger.info(f"Counts: {s.get_counts()}")
    counts = s.get_counts()
    if sorted(counts.values()) != [1, 2, 2]:
        errors += 1; logger.error(f"FALHOU: distribuicao {sorted(counts.values())}")
    else:
        logger.info("OK")

    # lista vazia
    logger.info("\nTESTE 5: candidates vazio -> None")
    for s in [FirstAvailableStrategy(), RoundRobinStrategy(), LeastBusyStrategy()]:
        r = await s.choose("x", [])
        if r is not None:
            errors += 1; logger.error(f"FALHOU: {s.name} deveria retornar None")
    logger.info("OK - todas as strategies retornam None para lista vazia")

    logger.info("\n" + "=" * 60)
    if errors == 0:
        logger.info("  TODOS OS TESTES DE STRATEGIES PASSARAM!")
    else:
        logger.error(f"  {errors} TESTE(S) FALHARAM")
    logger.info("=" * 60)
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
