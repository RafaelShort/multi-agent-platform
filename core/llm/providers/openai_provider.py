"""OpenAIProvider: chat completions compativel com OpenAI API.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import List, Optional

import httpx

from core.llm.providers.base import ChatMessage, LLMProvider, LLMResponse
from core.logger import logger


class LLMProviderError(Exception):
    """Erro generico do provider apos esgotar retries."""


class OpenAIProvider(LLMProvider):
    """Cliente async para OpenAI Chat Completions API."""

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        organization: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAIProvider requer api_key (param ou env OPENAI_API_KEY)"
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.backoff_base = backoff_base

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if organization:
            headers["OpenAI-Organization"] = organization

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )
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
        used_model = model or self.model

        payload = {
            "model": used_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v

        start = time.perf_counter()
        data = await self._request_with_retry("/chat/completions", payload)
        latency_ms = (time.perf_counter() - start) * 1000

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            usage = data.get("usage", {}) or {}
        except (KeyError, IndexError, TypeError) as e:
            raise LLMProviderError(f"Resposta inesperada da API: {e}") from e

        return LLMResponse(
            content=content,
            model=data.get("model", used_model),
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            latency_ms=latency_ms,
            raw=data,
        )

    async def _request_with_retry(self, path: str, payload: dict) -> dict:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await self._client.post(path, json=payload)

                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        request=resp.request,
                        response=resp,
                    )

                if resp.status_code >= 400:
                    raise LLMProviderError(
                        f"HTTP {resp.status_code}: {resp.text[:300]}"
                    )

                return resp.json()

            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last_exc = e
                if attempt >= self.max_retries:
                    break
                delay = self.backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    f"[OpenAIProvider] tentativa {attempt}/{self.max_retries} "
                    f"falhou ({e.__class__.__name__}), retry em {delay:.2f}s"
                )
                await asyncio.sleep(delay)

        raise LLMProviderError(
            f"Falha apos {self.max_retries} tentativas: {last_exc}"
        ) from last_exc

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"[OpenAIProvider] health_check falhou: {e}")
            return False

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def calls(self) -> int:
        return self._calls
