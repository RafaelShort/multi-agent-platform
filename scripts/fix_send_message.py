import pathlib

path = pathlib.Path("core/agents/base_agent.py")
content = path.read_text(encoding="utf-8")

old = '''    async def send_message(self, receiver_id: str, content: str, **metadata) -> None:
        """Envia uma mensagem para outro agente via MessageBus."""
        if self._message_bus is None:
            if self.verbose:
                logger.warning(f"[{self.name}] MessageBus não configurado.")
            return
        msg = AgentMessage(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            content=content,
            metadata=metadata,
        )
        await self._message_bus.publish(msg)'''

new = '''    async def send_message(self, receiver_id: str, content: str, **metadata) -> None:
        """Envia uma mensagem para outro agente via MessageBus."""
        if self._message_bus is None:
            if self.verbose:
                logger.warning(f"[{self.name}] MessageBus não configurado.")
            return
        await self._message_bus.publish_to_agent(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            content=content,
            msg_type="task",
            **metadata,
        )'''

if old in content:
    content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print("✅ send_message() corrigido para usar publish_to_agent()")
else:
    print("❌ Trecho nao encontrado")
