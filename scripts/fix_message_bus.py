import sys
sys.path.insert(0, ".")

# Ler o arquivo atual
with open("core/messaging/message_bus.py", "r", encoding="utf-8") as f:
    content = f.read()

# Substituir _ensure_topics com versao robusta
old = '''        def _create():
            existing = self._admin.list_topics(timeout=5).topics
            to_create = [
                NewTopic(t, num_partitions=num_partitions, replication_factor=1)
                for t in topics
                if t not in existing
            ]
            if not to_create:
                return []

            futures = self._admin.create_topics(to_create)
            created = []
            for topic, future in futures.items():
                try:
                    future.result()
                    created.append(topic)
                except KafkaException as e:
                    # Ignorar erro de tópico já existente
                    if "TOPIC_ALREADY_EXISTS" not in str(e):
                        logger.warning(f"Aviso ao criar tópico {topic}: {e}")
            return created'''

new = '''        def _create():
            import time
            existing = self._admin.list_topics(timeout=5).topics
            to_create = [
                NewTopic(t, num_partitions=num_partitions, replication_factor=1)
                for t in topics
                if t not in existing
            ]
            if not to_create:
                return []

            futures = self._admin.create_topics(to_create)
            created = []
            for topic, future in futures.items():
                try:
                    future.result()
                    created.append(topic)
                except KafkaException as e:
                    # Ignorar erro de tópico já existente
                    if "TOPIC_ALREADY_EXISTS" not in str(e):
                        logger.warning(f"Aviso ao criar tópico {topic}: {e}")

            # Aguardar propagacao do metadata no Kafka (evita race condition)
            if created:
                for attempt in range(20):   # até 10 segundos
                    time.sleep(0.5)
                    current = self._admin.list_topics(timeout=5).topics
                    if all(t in current for t in created):
                        break
                    if attempt == 19:
                        logger.warning(
                            f"Timeout aguardando propagacao dos topicos: {created}"
                        )

            return created'''

if old in content:
    content = content.replace(old, new)
    with open("core/messaging/message_bus.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Fix aplicado com sucesso!")
else:
    print("ERRO: trecho nao encontrado — verifique o arquivo manualmente.")
