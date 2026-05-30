"""MockProvider: provider deterministico para testes offline."""
from __future__ import annotations

import asyncio
import time
from typing import List, Optional

from core.llm.providers.base import ChatMessage, LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    """
    Echo-style provider.
    """

    name = "mock"

    def __init__(
        self,
        prefix: str = "[mock] ",
        simulated_latency: float = 0.01,
        fail_mode: bool = False,
        model: str = "mock-v1",
    ) -> None:
        self.prefix = prefix
        self.simulated_latency = simulated_latency
        self.fail_mode = fail_mode
        self.model = model
        self._calls = 0

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        self._calls += 1
        start = time.perf_counter()

        if self.simulated_latency > 0:
            await asyncio.sleep(self.simulated_latency)

        if self.fail_mode:
            raise RuntimeError("MockProvider em fail_mode")

        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "(no user message)",
        )
        content = f"{self.prefix}{last_user}"

        prompt_tokens = sum(len(m.content.split()) for m in messages)
        completion_tokens = len(content.split())
        latency_ms = (time.perf_counter() - start) * 1000

        return LLMResponse(
            content=content,
            model=model or self.model,
            provider=self.name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            raw={"calls": self._calls},
        )

    @property
    def calls(self) -> int:
        return self._calls
