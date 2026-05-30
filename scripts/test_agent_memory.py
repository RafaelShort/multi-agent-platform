"""
Teste completo do AgentMemory.
"""
import asyncio
import sys
sys.path.insert(0, ".")

from core.memory.agent_memory import AgentMemory, ConversationRecord
from core.agents.base_agent import BaseAgent, AgentResult
from core.logger import app_logger as logger


# Agente de teste com memória
class MemoryAgent(BaseAgent):
    """Agente que usa memória para lembrar contexto."""
    name = "MemoryAgent"
    role = "Agente com memoria persistente para testes"

    async def run(self, task: str, context=None) -> AgentResult:
        # Salvar a tarefa na memória
        await self.remember("ultima_tarefa", task)
        await self.remember("contador", (await self.recall("contador") or 0) + 1)
        return self.success_result(output=f"Tarefa registrada: {task}")


# Testes
async def main():
    logger.info("=" * 55)
    logger.info("  🧪 TESTE DO AGENT MEMORY")
    logger.info("=" * 55)

    AGENT_ID   = "test-agent-memory-001"
    SESSION_ID = "session-test-001"

    async with AgentMemory() as memory:

        # Limpar dados anteriores
        await memory.clear_agent_memory(AGENT_ID)
        await memory.delete_conversation(AGENT_ID, SESSION_ID)
        logger.info("✅ 1. Limpeza inicial concluída")

        # store() e retrieve() básico
        await memory.store(AGENT_ID, "nome",   "Rafael")
        await memory.store(AGENT_ID, "cidade", "São Paulo")
        await memory.store(AGENT_ID, "score",  42)
        await memory.store(AGENT_ID, "ativo",  True)
        await memory.store(AGENT_ID, "dados",  {"modelo": "llama3.2", "versao": 3})

        assert await memory.retrieve(AGENT_ID, "nome")   == "Rafael"
        assert await memory.retrieve(AGENT_ID, "cidade") == "São Paulo"
        assert await memory.retrieve(AGENT_ID, "score")  == 42
        assert await memory.retrieve(AGENT_ID, "ativo")  == True
        dados = await memory.retrieve(AGENT_ID, "dados")
        assert dados["modelo"] == "llama3.2"
        logger.info("✅ 2. store() e retrieve() — todos os tipos funcionando")

        # Upsert 
        await memory.store(AGENT_ID, "score", 100)
        assert await memory.retrieve(AGENT_ID, "score") == 100
        logger.info("✅ 3. Upsert funcionando")

        # retrieve() de chave inexistente
        val = await memory.retrieve(AGENT_ID, "chave_inexistente")
        assert val is None
        logger.info("✅ 4. retrieve() de chave inexistente retorna None")

        # retrieve_all()
        all_memories = await memory.retrieve_all(AGENT_ID)
        assert len(all_memories) == 5
        assert "nome" in all_memories
        logger.info(f"✅ 5. retrieve_all(): {len(all_memories)} entradas — {list(all_memories.keys())}")

        # retrieve_all() com filtro
        await memory.store(AGENT_ID, "pref_tema",  "dark")
        await memory.store(AGENT_ID, "pref_idioma", "pt-BR")

        prefs = await memory.retrieve_all(AGENT_ID, key_pattern="pref_*")
        assert len(prefs) == 2
        assert "pref_tema"   in prefs
        assert "pref_idioma" in prefs
        logger.info(f"✅ 6. retrieve_all(key_pattern): {prefs}")

        # TTL
        await memory.store(AGENT_ID, "temp_token", "abc123", ttl_seconds=1)
        token = await memory.retrieve(AGENT_ID, "temp_token")
        assert token == "abc123"
        logger.info("✅ 7. TTL — token salvo com sucesso")

        # delete()
        deleted = await memory.delete(AGENT_ID, "nome")
        assert deleted == True
        assert await memory.retrieve(AGENT_ID, "nome") is None
        deleted_again = await memory.delete(AGENT_ID, "nome")
        assert deleted_again == False
        logger.info("✅ 8. delete() funcionando")

        # save_conversation() e load_conversation()
        messages = [
            ConversationRecord(role="system",  content="Você é um assistente útil."),
            ConversationRecord(role="human",   content="Qual é a capital do Brasil?"),
            ConversationRecord(role="ai",      content="A capital do Brasil é Brasília."),
            ConversationRecord(role="human",   content="E a do Japão?"),
            ConversationRecord(role="ai",      content="A capital do Japão é Tóquio."),
        ]

        await memory.save_conversation(AGENT_ID, SESSION_ID, messages)
        loaded = await memory.load_conversation(AGENT_ID, SESSION_ID)

        assert len(loaded) == 5
        assert loaded[0].role    == "system"
        assert loaded[2].content == "A capital do Brasil é Brasília."
        assert loaded[4].role    == "ai"
        logger.info(f"✅ 9. save/load_conversation(): {len(loaded)} mensagens persistidas")

        # list_sessions()
        await memory.save_conversation(AGENT_ID, "session-002", messages[:2])
        sessions = await memory.list_sessions(AGENT_ID)
        assert SESSION_ID  in sessions
        assert "session-002" in sessions
        logger.info(f"✅ 10. list_sessions(): {sessions}")

        # Integração com BaseAgent
        agent = MemoryAgent(agent_id="memory-agent-001", verbose=True)
        agent.set_memory(memory)

        await agent.execute("Processar relatório financeiro")
        await agent.execute("Analisar dados de vendas")

        ultima = await memory.retrieve("memory-agent-001", "ultima_tarefa")
        contador = await memory.retrieve("memory-agent-001", "contador")

        assert ultima   == "Analisar dados de vendas"
        assert contador == 2
        logger.info(f"✅ 11. Integração BaseAgent+Memory: ultima={ultima!r} | contador={contador}")

        # get_stats()
        stats = await memory.get_stats(AGENT_ID)
        logger.info(f"✅ 12. Stats: {stats}")
        assert stats["total_memories"] > 0

        # clear_agent_memory()
        removed = await memory.clear_agent_memory(AGENT_ID)
        assert removed > 0
        remaining = await memory.retrieve_all(AGENT_ID)
        assert len(remaining) == 0
        logger.info(f"✅ 13. clear_agent_memory(): {removed} entradas removidas")

    logger.info("\n" + "=" * 55)
    logger.info("  🎉 TODOS OS TESTES PASSARAM!")
    logger.info("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
