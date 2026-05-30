"""
LLMAgent: agente que processa tasks via LLMProvider.
"""
from __future__ import annotations


import json
from typing import Any, List, Optional, Tuple

from core.agents.base_agent import BaseAgent
from core.llm.providers.base import ChatMessage, LLMProvider
from core.logger import app_logger as logger
from core.messaging.message_bus import BusMessage, MessageBus
from core.orchestration.registry import AgentRegistry


class LLMAgent(BaseAgent):
    """Agente generico que delega tasks pra um LLMProvider."""

    def __init__(
        self,
        agent_id: str,
        bus: MessageBus,
        registry: AgentRegistry,
        provider: LLMProvider,
        *,
        capabilities: Optional[List[str]] = None,
        default_system: Optional[str] = None,
        default_model: Optional[str] = None,
        default_temperature: float = 0.7,
        default_max_tokens: Optional[int] = None,
        heartbeat_interval: float = 5.0,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            bus=bus,
            registry=registry,
            heartbeat_interval=heartbeat_interval,
        )
        self.provider = provider
        self._capabilities = capabilities or ["chat"]
        self.default_system = default_system
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self._llm_calls = 0
        self._llm_errors = 0
        self._total_tokens = 0

    @property
    def capabilities(self) -> List[str]:
        return self._capabilities

    # Payload parsing

    def _build_messages(self, payload: Any) -> Tuple[List[ChatMessage], dict]:
        """
        Normaliza payload em (messages, options).

        Options pode conter: model, temperature, max_tokens.
        """
        options: dict = {}
        messages: List[ChatMessage] = []

        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    payload = parsed
            except (json.JSONDecodeError, ValueError):
                pass

        if isinstance(payload, str):
            if self.default_system:
                messages.append(ChatMessage(role="system", content=self.default_system))
            messages.append(ChatMessage(role="user", content=payload))
            return messages, options

        if isinstance(payload, dict):
            for key in ("model", "temperature", "max_tokens"):
                if key in payload and payload[key] is not None:
                    options[key] = payload[key]

            system = payload.get("system") or self.default_system

            if "messages" in payload and payload["messages"]:
                raw = payload["messages"]
                if system and not any(m.get("role") == "system" for m in raw):
                    messages.append(ChatMessage(role="system", content=system))
                for m in raw:
                    messages.append(
                        ChatMessage(
                            role=m.get("role", "user"),
                            content=str(m.get("content", "")),
                        )
                    )
                return messages, options

            if "prompt" in payload:
                if system:
                    messages.append(ChatMessage(role="system", content=system))
                messages.append(ChatMessage(role="user", content=str(payload["prompt"])))
                return messages, options

        raise ValueError(
            f"Payload invalido para LLMAgent: tipo={type(payload).__name__}. "
            "Esperado str, {'prompt': ...} ou {'messages': [...]}"
        )

    # Task handler

    async def handle_task(self, msg: BusMessage) -> Tuple[Any, bool]:
        payload = msg.content
        capability = msg.metadata.get("capability", "chat")

        try:
            messages, options = self._build_messages(payload)
        except ValueError as exc:
            logger.warning(f"[{self.agent_id}] Payload invalido: {exc}")
            return f"InvalidPayload: {exc}", False

        model = options.get("model", self.default_model)
        temperature = options.get("temperature", self.default_temperature)
        max_tokens = options.get("max_tokens", self.default_max_tokens)

        self._llm_calls += 1
        try:
            response = await self.provider.chat(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            self._llm_errors += 1
            logger.exception(
                f"[{self.agent_id}] Provider {self.provider.name} falhou (capability={capability})"
            )
            return f"LLMProviderError: {type(exc).__name__}: {exc}", False

        self._total_tokens += response.total_tokens

        logger.info(
            f"[{self.agent_id}] LLM ok | provider={response.provider} model={response.model} "
            f"tokens={response.total_tokens} latency={response.latency_ms:.1f}ms"
        )

        output = {
            "content": response.content,
            "model": response.model,
            "provider": response.provider,
            "tokens": {
                "prompt": response.prompt_tokens,
                "completion": response.completion_tokens,
                "total": response.total_tokens,
            },
            "latency_ms": round(response.latency_ms, 2),
        }
        return json.dumps(output, ensure_ascii=False), True

    # Lifecycle override

    async def stop(self) -> None:
        await super().stop()
        try:
            await self.provider.close()
        except Exception:
            logger.exception(f"[{self.agent_id}] erro ao fechar provider")

    def get_stats(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "provider": self.provider.name,
            "llm_calls": self._llm_calls,
            "llm_errors": self._llm_errors,
            "total_tokens": self._total_tokens,
        }


