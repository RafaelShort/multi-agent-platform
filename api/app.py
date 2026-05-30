"""api/app.py — API REST com personas editaveis (system por requisicao)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.logger import app_logger as logger
from core.bootstrap import build_platform, Platform
from core.orchestration import Task, TaskStatus


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., min_length=1)
    temperature: float = 0.7
    max_tokens: int = 512
    capability: str = "chat"
    system: Optional[str] = None  # sobrescreve a personalidade por requisicao


class ChatResponse(BaseModel):
    content: str
    status: str
    agent_id: Optional[str] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class AgentInfoOut(BaseModel):
    agent_id: str
    name: str
    emoji: str
    description: str
    temperature: float
    system: str          # prompt padrao (para o editor pre-preencher)
    status: str
    capabilities: List[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[api] Subindo plataforma...")
    platform: Platform = await build_platform()
    app.state.platform = platform
    logger.info("[api] Plataforma pronta. API no ar.")
    try:
        yield
    finally:
        logger.info("[api] Encerrando plataforma...")
        await platform.stop()


app = FastAPI(title="Multi-Agent Platform API", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_platform() -> Platform:
    platform = getattr(app.state, "platform", None)
    if platform is None:
        raise HTTPException(status_code=503, detail="Plataforma nao inicializada")
    return platform


@app.get("/api/health")
async def health() -> dict:
    platform = getattr(app.state, "platform", None)
    return {
        "status": "ok" if platform else "starting",
        "agents": len(platform.agents) if platform else 0,
    }


@app.get("/api/agents", response_model=List[AgentInfoOut])
async def list_agents() -> List[AgentInfoOut]:
    platform = get_platform()
    persona_by_id = {p.id: p for p in platform.personas}
    registered = await platform.registry.find_by_capability("chat", only_available=False)

    out: List[AgentInfoOut] = []
    for a in registered:
        p = persona_by_id.get(a.agent_id)
        out.append(AgentInfoOut(
            agent_id=a.agent_id,
            name=p.name if p else a.agent_id,
            emoji=p.emoji if p else "🤖",
            description=p.description if p else "",
            temperature=p.temperature if p else 0.7,
            system=p.system if p else "",
            status=getattr(a.status, "value", str(a.status)),
            capabilities=list(a.capabilities),
        ))
    return out


@app.get("/api/stats")
async def stats() -> dict:
    platform = get_platform()
    return platform.orchestrator.get_stats()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    platform = get_platform()

    body = {
        "messages": [m.model_dump() for m in req.messages],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
    }
    if req.system:
        body["system"] = req.system
    payload = json.dumps(body, ensure_ascii=False)

    task = Task(capability=req.capability, payload=payload)
    result = await platform.orchestrator.submit_task(task, timeout=90.0)

    if result.status == TaskStatus.COMPLETED and result.output:
        parsed = json.loads(result.output)
        return ChatResponse(
            content=parsed.get("content", ""),
            status="completed",
            agent_id=result.agent_id,
            total_tokens=parsed.get("tokens", {}).get("total"),
            latency_ms=parsed.get("latency_ms"),
        )

    return ChatResponse(
        content="",
        status=getattr(result.status, "value", str(result.status)),
        agent_id=result.agent_id,
        error=result.error or "Task nao completou",
    )
