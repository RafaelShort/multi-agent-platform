import pathlib

path = pathlib.Path("core/agents/base_agent.py")
content = path.read_text(encoding="utf-8")

old = '''class AgentMessage(BaseModel):
    """Mensagem padronizada entre agentes."""
    message_id:   str       = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id:    str       = Field(..., description="ID do agente remetente")
    receiver_id:  str       = Field(..., description="ID do agente destinatário")
    content:      str       = Field(..., description="Conteúdo da mensagem")
    metadata:     Dict[str, Any] = Field(default_factory=dict)
    timestamp:    datetime  = Field(default_factory=lambda: datetime.now(timezone.utc))
    reply_to:     Optional[str] = Field(None, description="message_id da mensagem original")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


'''

if old in content:
    content = content.replace(old, "")
    path.write_text(content, encoding="utf-8")
    print("✅ AgentMessage removido")
    print(f"   Tamanho: {len(content.splitlines())} linhas")
else:
    print("❌ Bloco nao encontrado exatamente")
