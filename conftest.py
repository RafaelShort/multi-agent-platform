"""Configuracao global de testes + helpers de mock."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
import pytest

from core.llm.providers.openai_provider import OpenAIProvider


def make_mock_provider(handler, **kwargs) -> OpenAIProvider:
    """Cria um OpenAIProvider com httpx.MockTransport injetado.
    """
    kwargs.setdefault("api_key", "test-key")
    kwargs.setdefault("base_url", "http://mock/v1")
    kwargs.setdefault("backoff_base", 0.0) 
    provider = OpenAIProvider(**kwargs)
    provider._client = httpx.AsyncClient(
        base_url=provider.base_url,
        transport=httpx.MockTransport(handler),
    )
    return provider


@pytest.fixture
def mock_provider_factory():
    """Factory que cria providers mockados e fecha todos no teardown."""
    created: list[OpenAIProvider] = []

    def _factory(handler, **kwargs):
        p = make_mock_provider(handler, **kwargs)
        created.append(p)
        return p

    yield _factory
