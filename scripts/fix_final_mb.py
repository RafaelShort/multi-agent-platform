import pathlib, uuid

# Corrigir message_bus.py
mb_path = pathlib.Path("core/messaging/message_bus.py")
content = mb_path.read_text(encoding="utf-8")

# Revert earliest para latest
if '"auto.offset.reset":  "earliest"' in content:
    content = content.replace(
        '"auto.offset.reset":  "earliest"',
        '"auto.offset.reset":  "latest"'
    )
    print("✅ auto.offset.reset = latest")
elif '"auto.offset.reset":  "latest"' in content:
    print("ℹ️  auto.offset.reset ja e latest")
else:
    print("❌ auto.offset.reset nao encontrado!")
    for i, l in enumerate(content.splitlines(), 1):
        if "offset.reset" in l:
            print(f"  L{i}: {l.strip()}")

mb_path.write_text(content, encoding="utf-8")

# Verificar assigned_set
checks = [
    ("assigned_set",                        "assigned_set presente"),
    ("all(t in assigned_set",               "verifica todos os topicos"),
    ("auto.offset.reset.*latest",           "latest confirmado"),
    ("_ensure_topics(topics)",              "ensure_topics em subscribe"),
    ("run_coroutine_threadsafe",            "thread-safe handler"),
]
import re
for pattern, label in checks:
    ok = "✅" if re.search(pattern, content) else "❌"
    print(f"{ok} {label}")

# Reescrever test com group_id unico
test_content = '''"""
Teste completo do MessageBus.
"""
import asyncio
import sys
import time as _time
import uuid as _uuid
sys.path.insert(0, ".")

from core.messaging.message_bus import MessageBus, BusMessage
from core.agents.base_agent import BaseAgent, AgentResult
from core.logger import app_logger as logger

# group_id unico por run — sem offsets compartilhados entre testes
TEST_GROUP_ID = "test-" + _uuid.uuid4().hex[:8]


async def wait_for(lst, count=1, timeout=10.0, label=""):
    """Aguarda ate que lst tenha count itens ou timeout expire."""
    start = _time.monotonic()
    while len(lst) < count:
        if _time.monotonic() - start >= timeout:
            logger.warning(f"wait_for TIMEOUT | label={label} | got={len(lst)} want={count}")
            return False
        await asyncio.sleep(0.05)
    return True


class MessagingAgent(BaseAgent):
    name = "MessagingAgent"
    role = "Agente de teste para validacao do MessageBus"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.received_messages: list = []

    async def run(self, task: str, context=None) -> AgentResult:
        await self.send_message(
            receiver_id="agent-receiver-001",
            content=f"Executando: {task}",
            source="MessagingAgent",
        )
        return self.success_result(output="Mensagem enviada para agent-receiver-001")

    async def on_message(self, msg: BusMessage) -> None:
        self.received_messages.append(msg)
        logger.info(
            f"Mensagem recebida | "
            f"sender={msg.sender_id[:8]} | content={msg.content[:60]}"
        )


async def main():
    logger.info("=" * 55)
    logger.info("  TESTE DO MESSAGE BUS")
    logger.info(f"  group_id={TEST_GROUP_ID}")
    logger.info("=" * 55)

    async with MessageBus(group_id=TEST_GROUP_ID) as bus:

        # 1. Conexao
        assert bus._ready
        logger.info("OK 1. Conexao com Kafka estabelecida")

        # 2. Topicos padrao
        stats = await bus.get_stats()
        for topic in MessageBus.DEFAULT_TOPICS:
            assert topic in stats["topics"], f"Topico {topic} nao encontrado"
        padrao = [t for t in stats["topics"] if t.startswith("agents.")]
        logger.info(f"OK 2. Topicos padrao: {padrao}")

        # 3. Topico customizado
        await bus.create_topic("test.custom.topic")
        stats = await bus.get_stats()
        assert "test.custom.topic" in stats["topics"]
        logger.info("OK 3. Topico customizado criado")

        # 4. Serializacao BusMessage
        msg = BusMessage(
            topic=MessageBus.TOPIC_TASKS,
            sender_id="agent-sender-001",
            receiver_id="agent-receiver-001",
            content="Teste de serializacao",
            msg_type="task",
            metadata={"prioridade": "alta", "retry": 0},
        )
        restored = BusMessage.from_json(msg.to_json())
        assert restored.message_id == msg.message_id
        assert restored.content == msg.content
        assert restored.metadata["prioridade"] == "alta"
        logger.info("OK 4. Serializacao/deserializacao BusMessage OK")

        # 5. Publish e Subscribe
        received: list = []

        async def test_handler(m: BusMessage) -> None:
            received.append(m)
            logger.info(f"   Handler recebeu: {m.content[:50]}")

        await bus.subscribe(MessageBus.TOPIC_TASKS, test_handler)

        for i in range(1, 4):
            await bus.publish(BusMessage(
                topic=MessageBus.TOPIC_TASKS,
                sender_id="test-sender",
                receiver_id="*",
                content=f"Mensagem de teste #{i}",
                msg_type="task",
            ))

        ok = await wait_for(received, count=3, timeout=10.0, label="step5")
        assert ok and len(received) == 3, f"Esperado 3, recebido {len(received)}"
        assert received[0].content == "Mensagem de teste #1"
        assert received[2].content == "Mensagem de teste #3"
        logger.info(f"OK 5. Publish/Subscribe: {len(received)} mensagens recebidas")

        # 6. publish_to_agent
        agent_received: list = []

        async def agent_handler(m: BusMessage) -> None:
            agent_received.append(m)

        receiver_id = "agent-target-" + _uuid.uuid4().hex[:6]
        agent_topic = bus.agent_topic(receiver_id)

        await bus.subscribe(agent_topic, agent_handler)
        await bus.publish_to_agent(
            sender_id="orchestrator",
            receiver_id=receiver_id,
            content="Tarefa exclusiva para voce",
            msg_type="task",
            priority="high",
        )

        ok = await wait_for(agent_received, count=1, timeout=10.0, label="step6")
        assert ok and len(agent_received) == 1, f"Esperado 1, recebido {len(agent_received)}"
        assert agent_received[0].receiver_id == receiver_id
        assert agent_received[0].metadata.get("priority") == "high"
        logger.info(f"OK 6. publish_to_agent(): topico={agent_topic}")

        # 7. broadcast
        broadcast_received: list = []

        async def broadcast_handler(m: BusMessage) -> None:
            broadcast_received.append(m)

        await bus.subscribe(MessageBus.TOPIC_BROADCAST, broadcast_handler)
        await bus.broadcast(
            sender_id="orchestrator",
            content="Sistema iniciando - todos os agentes em standby",
            event="system_start",
        )

        ok = await wait_for(broadcast_received, count=1, timeout=10.0, label="step7")
        assert ok and len(broadcast_received) == 1, f"Esperado 1, recebido {len(broadcast_received)}"
        assert broadcast_received[0].receiver_id == "*"
        assert broadcast_received[0].msg_type == "broadcast"
        logger.info(f"OK 7. broadcast(): recebido por {len(broadcast_received)} handler(s)")

        # 8. Multiplos handlers no mesmo topico
        results_a: list = []
        results_b: list = []

        async def handler_a(m: BusMessage): results_a.append(m)
        async def handler_b(m: BusMessage): results_b.append(m)

        await bus.subscribe(MessageBus.TOPIC_RESULTS, handler_a)
        await bus.subscribe(MessageBus.TOPIC_RESULTS, handler_b)

        await bus.publish(BusMessage(
            topic=MessageBus.TOPIC_RESULTS,
            sender_id="worker-agent",
            receiver_id="orchestrator",
            content="Resultado processado com sucesso",
            msg_type="result",
        ))

        ok_a = await wait_for(results_a, count=1, timeout=10.0, label="step8a")
        ok_b = await wait_for(results_b, count=1, timeout=10.0, label="step8b")
        assert ok_a and len(results_a) == 1, f"handler_a: esperado 1, recebido {len(results_a)}"
        assert ok_b and len(results_b) == 1, f"handler_b: esperado 1, recebido {len(results_b)}"
        logger.info("OK 8. Multiplos handlers no mesmo topico funcionando")

        # 9. Integracao BaseAgent + MessageBus
        sender   = MessagingAgent(agent_id="sender-agent-001",   verbose=False)
        receiver = MessagingAgent(agent_id="agent-receiver-001", verbose=False)

        receiver_topic = bus.agent_topic("agent-receiver-001")
        await bus.subscribe(receiver_topic, receiver.on_message)
        sender.set_message_bus(bus)

        await sender.execute("Processar lote de dados")

        ok = await wait_for(receiver.received_messages, count=1, timeout=10.0, label="step9")
        assert ok and len(receiver.received_messages) == 1
        assert "Processar lote de dados" in receiver.received_messages[0].content
        logger.info("OK 9. Integracao BaseAgent+MessageBus: sender->receiver OK")

        # 10. Estatisticas finais
        final_stats = await bus.get_stats()
        logger.info("OK 10. Stats finais:")
        logger.info(f"       Publicadas: {final_stats['messages']['published']}")
        logger.info(f"       Consumidas: {final_stats['messages']['consumed']}")
        logger.info(f"       Erros:      {final_stats['messages']['errors']}")
        assert final_stats["messages"]["published"] > 0
        assert final_stats["messages"]["consumed"]  > 0
        assert final_stats["messages"]["errors"]   == 0

    logger.info("=" * 55)
    logger.info("  TODOS OS TESTES PASSARAM!")
    logger.info("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
'''

pathlib.Path("scripts/test_message_bus.py").write_text(test_content, encoding="utf-8")
print(f"✅ test atualizado com group_id unico")
print(f"   Linhas: {len(test_content.splitlines())}")
