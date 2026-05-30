"""Testes unitarios das Routing Strategies (logica pura, sem backend)."""
from __future__ import annotations

import pytest

from core.orchestration.strategies import (
    RoutingStrategy,
    FirstAvailableStrategy,
    RoundRobinStrategy,
    LeastBusyStrategy,
)
from core.orchestration.registry import AgentInfo, AgentStatusEnum

pytestmark = pytest.mark.unit


def make_agent(agent_id: str) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        name=f"Agent {agent_id}",
        capabilities=["research"],
        status=AgentStatusEnum.IDLE,
    )


def test_strategy_name_is_class_name():
    assert FirstAvailableStrategy().name == "FirstAvailableStrategy"
    assert RoundRobinStrategy().name == "RoundRobinStrategy"
    assert LeastBusyStrategy().name == "LeastBusyStrategy"


async def test_first_available_returns_first():
    strat = FirstAvailableStrategy()
    agents = [make_agent("a"), make_agent("b"), make_agent("c")]
    chosen = await strat.choose("research", agents)
    assert chosen.agent_id == "a"


async def test_first_available_empty_returns_none():
    strat = FirstAvailableStrategy()
    assert await strat.choose("research", []) is None


async def test_first_available_single_candidate():
    strat = FirstAvailableStrategy()
    chosen = await strat.choose("research", [make_agent("solo")])
    assert chosen.agent_id == "solo"


async def test_round_robin_rotates():
    strat = RoundRobinStrategy()
    agents = [make_agent("a"), make_agent("b"), make_agent("c")]
    picks = [(await strat.choose("research", agents)).agent_id for _ in range(4)]
    # ordenado por agent_id: a, b, c -> rotaciona e volta
    assert picks == ["a", "b", "c", "a"]


async def test_round_robin_empty_returns_none():
    strat = RoundRobinStrategy()
    assert await strat.choose("research", []) is None


async def test_round_robin_is_order_stable_regardless_of_input_order():
    strat = RoundRobinStrategy()
    agents_shuffled = [make_agent("c"), make_agent("a"), make_agent("b")]
    first = await strat.choose("research", agents_shuffled)
    assert first.agent_id == "a" 


async def test_round_robin_independent_cursor_per_capability():
    strat = RoundRobinStrategy()
    agents = [make_agent("a"), make_agent("b")]
    x1 = (await strat.choose("research", agents)).agent_id
    y1 = (await strat.choose("coding", agents)).agent_id
    x2 = (await strat.choose("research", agents)).agent_id
    assert x1 == "a"
    assert y1 == "a"  
    assert x2 == "b"   


async def test_round_robin_single_candidate_always_same():
    strat = RoundRobinStrategy()
    agents = [make_agent("solo")]
    picks = [(await strat.choose("research", agents)).agent_id for _ in range(3)]
    assert picks == ["solo", "solo", "solo"]


async def test_least_busy_empty_returns_none():
    strat = LeastBusyStrategy()
    assert await strat.choose("research", []) is None


async def test_least_busy_picks_least_dispatched():
    strat = LeastBusyStrategy()
    agents = [make_agent("a"), make_agent("b"), make_agent("c")]
    p1 = (await strat.choose("research", agents)).agent_id
    p2 = (await strat.choose("research", agents)).agent_id
    p3 = (await strat.choose("research", agents)).agent_id
    p4 = (await strat.choose("research", agents)).agent_id
    assert p1 == "a"
    assert p2 == "b"
    assert p3 == "c"
    assert p4 == "a"


async def test_least_busy_increments_count_on_choice():
    strat = LeastBusyStrategy()
    agents = [make_agent("a"), make_agent("b")]
    await strat.choose("research", agents)
    await strat.choose("research", agents)
    counts = strat.get_counts()
    assert counts["a"] == 1
    assert counts["b"] == 1


async def test_least_busy_get_counts_returns_copy():
    strat = LeastBusyStrategy()
    agents = [make_agent("a")]
    await strat.choose("research", agents)
    counts = strat.get_counts()
    counts["a"] = 999  
    assert strat.get_counts()["a"] == 1 


async def test_least_busy_single_candidate_accumulates():
    strat = LeastBusyStrategy()
    agents = [make_agent("solo")]
    for _ in range(3):
        await strat.choose("research", agents)
    assert strat.get_counts()["solo"] == 3

def test_routing_strategy_is_abstract():
    with pytest.raises(TypeError):
        RoutingStrategy() 
