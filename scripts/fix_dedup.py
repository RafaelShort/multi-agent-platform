import pathlib

path = pathlib.Path("core/messaging/message_bus.py")
content = path.read_text(encoding="utf-8")

# Procurar a logica do else (resubscribe) e adicionar check
old = '''        if not self._consuming:
            self._consumer.subscribe(all_topics, on_assign=on_assign)
            logger.info(f"📥 Consumer subscrito em: {all_topics}")
            self._consuming = True
            self._consume_running.set()
            loop = asyncio.get_running_loop()
            self._consumer_thread = threading.Thread(
                target=self._consume_loop_sync,
                args=(loop,),
                daemon=True,
                name="kafka-consumer",
            )
            self._consumer_thread.start()
        else:
            self._resubscribe_queue.put({"topics": all_topics, "on_assign": on_assign})'''

new = '''        if not self._consuming:
            self._consumer.subscribe(all_topics, on_assign=on_assign)
            logger.info(f"📥 Consumer subscrito em: {all_topics}")
            self._subscribed_topics = set(all_topics)
            self._consuming = True
            self._consume_running.set()
            loop = asyncio.get_running_loop()
            self._consumer_thread = threading.Thread(
                target=self._consume_loop_sync,
                args=(loop,),
                daemon=True,
                name="kafka-consumer",
            )
            self._consumer_thread.start()
        else:
            # Se a lista de topicos nao mudou, NAO resubscrever
            # (evita rebalance desnecessario que pode perder mensagens)
            current = getattr(self, "_subscribed_topics", set())
            if set(all_topics) == current:
                logger.info(f"📥 Topico ja subscrito, handler apenas adicionado")
                # Sinalizar imediatamente (consumer ja tem particoes atribuidas)
                assigned_event.set()
            else:
                self._subscribed_topics = set(all_topics)
                self._resubscribe_queue.put({"topics": all_topics, "on_assign": on_assign})'''

if old in content:
    content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print("✅ Fix aplicado: deduplicacao de resubscribe")
else:
    print("❌ Trecho nao encontrado")
    for i, l in enumerate(content.splitlines(), 1):
        if "_resubscribe_queue.put" in l or "Consumer subscrito em" in l:
            print(f"  L{i}: {l.rstrip()}")

# Verificacao
content2 = path.read_text(encoding="utf-8")
checks = [
    "_subscribed_topics",
    "Topico ja subscrito",
    "set(all_topics) == current",
]
for c in checks:
    ok = "✅" if c in content2 else "❌"
    print(f"{ok} {c}")
