"""
LLM Provider abstraction.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Interface para qualquer backend de LLM."""

    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """Roda uma chamada de chat completion."""

    async def health_check(self) -> bool:
        """Override em providers reais (ex: ping no endpoint)."""
        return True

    async def close(self) -> None:
        """Override se precisar fechar HTTP client."""
        return None
