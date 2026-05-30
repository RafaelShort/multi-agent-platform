"""
cli.py — Chat interativo no terminal com a plataforma multi-agente.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8") 
except Exception:
    pass

import asyncio
import json

from core.bootstrap import build_platform
from core.orchestration import Task, TaskStatus


async def ainput(prompt: str = "") -> str:
    """input() sem bloquear o event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


def banner() -> None:
    print("=" * 60)
    print("  Multi-Agent Platform — CLI de Chat")
    print("  Comandos: /stats  /agents  /clear  /help  /quit")
    print("=" * 60)


async def show_stats(platform) -> None:
    print("\n--- ORCHESTRATOR STATS ---")
    for k, v in platform.orchestrator.get_stats().items():
        print(f"  {k}: {v}")
    print("--------------------------\n")


async def show_agents(platform) -> None:
    agents = await platform.registry.find_by_capability("chat", only_available=False)
    print("\n--- AGENTES (capability=chat) ---")
    if not agents:
        print("  (nenhum)")
    for a in agents:
        status = getattr(a.status, "value", a.status)
        print(f"  {a.agent_id} | status={status} | caps={a.capabilities}")
    print("---------------------------------\n")


async def chat_loop(platform) -> None:
    history: list[dict] = []
    print("\nDigite sua mensagem (ou /help):\n")

    while True:
        try:
            text = (await ainput("voce> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue

        # Comandos
        if text in ("/quit", "/exit"):
            break
        if text == "/help":
            print("  /stats /agents /clear /quit")
            continue
        if text == "/stats":
            await show_stats(platform)
            continue
        if text == "/agents":
            await show_agents(platform)
            continue
        if text == "/clear":
            history.clear()
            print("  (historico limpo)\n")
            continue

        # Monta payload multi-turn
        history.append({"role": "user", "content": text})
        payload = json.dumps({
            "messages": history,
            "temperature": 0.7,
            "max_tokens": 512,
        })

        task = Task(capability="chat", payload=payload)
        print("  ...pensando...", flush=True)

        result = await platform.orchestrator.submit_task(task, timeout=90.0)

        if result.status == TaskStatus.COMPLETED and result.output:
            parsed = json.loads(result.output)
            content = parsed.get("content", "")
            tokens = parsed.get("tokens", {})
            latency = parsed.get("latency_ms", 0)
            history.append({"role": "assistant", "content": content})
            print(f"\nbot> {content}")
            print(f"     [tokens={tokens.get('total', '?')} | {latency}ms | agent={result.agent_id}]\n")
        else:
            if history and history[-1]["role"] == "user":
                history.pop()
            print(f"\n[ERRO] status={result.status.value} :: {result.error}\n")


async def main() -> int:
    banner()
    print("\nSubindo plataforma (Kafka + Orchestrator + LLMAgent)...")
    try:
        platform = await build_platform(num_chat_agents=1)
    except Exception as exc:
        print(f"\n[FALHA AO SUBIR] {type(exc).__name__}: {exc}")
        print("Verifique: 'docker compose up -d kafka' e 'ollama serve'.")
        return 1

    print("Plataforma pronta!\n")
    try:
        await chat_loop(platform)
    finally:
        print("\nEncerrando...")
        await platform.stop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Ate logo!")
        sys.exit(0)

