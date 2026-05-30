import pathlib

path = pathlib.Path("core/messaging/message_bus.py")
content = path.read_text(encoding="utf-8")

old = '''    async def subscribe(self, topic, handler: MessageHandler) -> None:
        self._check_ready()
        topics = [topic] if isinstance(topic, str) else topic
        for t in topics:'''

new = '''    async def subscribe(self, topic, handler: MessageHandler) -> None:
        self._check_ready()
        topics = [topic] if isinstance(topic, str) else topic

        # Garantir que todos os topicos existem ANTES de registrar o consumer
        await self._ensure_topics(topics)

        for t in topics:'''

if old in content:
    content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print("✅ Fix aplicado em subscribe()")
else:
    print("❌ Trecho nao encontrado!")
    # Mostrar contexto para debug
    for i, line in enumerate(content.splitlines(), 1):
        if "async def subscribe" in line:
            print(f"Linha {i}: {line}")
