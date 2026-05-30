"""
AgentMemory — Memória persistente dos agentes via MongoDB.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from core.config import settings
from core.logger import app_logger as logger

# MODELOS DE DADOS

class MemoryEntry(BaseModel):
    """Entrada de memória de um agente."""
    agent_id:   str
    key:        str
    value:      Any
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    metadata:   Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ConversationRecord(BaseModel):
    """Registro de uma mensagem no histórico de conversação."""
    role:       str            
    content:    str
    timestamp:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata:   Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# AGENT MEMORY

class AgentMemory:
    """
    Memória persistente para agentes usando MongoDB.
    """

    MEMORIES_COLLECTION      = "agent_memories"
    CONVERSATIONS_COLLECTION = "agent_conversations"

    def __init__(
        self,
        mongodb_url:    Optional[str] = None,
        database_name:  Optional[str] = None,
    ):
        self._url:      str = mongodb_url   or settings.MONGODB_URL
        self._db_name:  str = database_name or settings.MONGODB_DB_NAME

        self._client:   Optional[AsyncIOMotorClient]   = None
        self._db:       Optional[AsyncIOMotorDatabase] = None
        self._ready:    bool = False

        logger.info(
            f"💾 AgentMemory criado | "
            f"db={self._db_name} | "
            f"url={self._url.split('@')[-1]}"   
        )

    # CONEXÃO

    async def connect(self) -> None:
        """Conecta ao MongoDB e garante índices."""
        if self._ready:
            return

        try:
            self._client = AsyncIOMotorClient(
                self._url,
                serverSelectionTimeoutMS=5000,
            )
            self._db = self._client[self._db_name]

            # Validar conexão
            await self._client.admin.command("ping")

            # Criar índices
            await self._ensure_indexes()

            self._ready = True
            logger.success(
                f"✅ AgentMemory conectado | "
                f"db={self._db_name}"
            )

        except Exception as e:
            logger.error(f"❌ AgentMemory falhou ao conectar: {e}")
            raise

    async def disconnect(self) -> None:
        """Fecha a conexão com o MongoDB."""
        if self._client:
            self._client.close()
            self._ready = False
            logger.info("💾 AgentMemory desconectado.")

    async def _ensure_indexes(self) -> None:
        """Cria índices necessários para performance."""
        memories = self._db[self.MEMORIES_COLLECTION]
        conversations = self._db[self.CONVERSATIONS_COLLECTION]

        # Índice composto: agent_id + key
        await memories.create_index(
            [("agent_id", 1), ("key", 1)],
            unique=True,
            name="idx_agent_key",
        )

        # Índice TTL: remove entradas expiradas automaticamente
        await memories.create_index(
            "expires_at",
            expireAfterSeconds=0,
            sparse=True,
            name="idx_ttl_expires",
        )

        # Índice para busca por agente
        await memories.create_index("agent_id", name="idx_agent_id")

        # Índice para conversações: agent_id + session_id
        await conversations.create_index(
            [("agent_id", 1), ("session_id", 1)],
            name="idx_conv_agent_session",
        )

        logger.info("📑 Índices MongoDB criados/verificados.")

    def _check_ready(self) -> None:
        """Verifica se a conexão está ativa."""
        if not self._ready:
            raise RuntimeError(
                "AgentMemory não está conectado. "
                "Chame await memory.connect() antes de usar."
            )

    # MEMÓRIA CHAVE-VALOR

    async def store(
        self,
        agent_id:   str,
        key:        str,
        value:      Any,
        ttl_seconds: Optional[int] = None,
        metadata:   Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Persiste um dado na memória do agente.
        """
        self._check_ready()

        now = datetime.now(timezone.utc)
        expires_at = (
            now + timedelta(seconds=ttl_seconds)
            if ttl_seconds else None
        )

        # Serializar value para garantir compatibilidade com MongoDB
        serialized_value = self._serialize(value)

        document = {
            "agent_id":   agent_id,
            "key":        key,
            "value":      serialized_value,
            "updated_at": now,
            "expires_at": expires_at,
            "metadata":   metadata or {},
        }

        collection = self._db[self.MEMORIES_COLLECTION]

        # Upsert: cria se não existir, atualiza se existir
        await collection.update_one(
            {"agent_id": agent_id, "key": key},
            {
                "$set": document,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

        logger.debug(f"💾 [{agent_id[:8]}] Memória salva: {key}")

    async def retrieve(
        self,
        agent_id: str,
        key:      str,
    ) -> Optional[Any]:
        """
        Recupera um dado da memória do agente.
        """
        self._check_ready()

        collection = self._db[self.MEMORIES_COLLECTION]
        doc = await collection.find_one(
            {"agent_id": agent_id, "key": key}
        )

        if doc is None:
            logger.debug(f"💾 [{agent_id[:8]}] Memória não encontrada: {key}")
            return None

        # Verificar expiração manualmente
        if doc.get("expires_at"):
            if doc["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                await self.delete(agent_id, key)
                return None

        return self._deserialize(doc["value"])

    async def retrieve_all(
        self,
        agent_id: str,
        key_pattern: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Recupera todas as memórias de um agente.
        """
        self._check_ready()

        collection = self._db[self.MEMORIES_COLLECTION]

        query: Dict[str, Any] = {"agent_id": agent_id}
        if key_pattern:
            # Converter padrão glob para regex MongoDB
            regex = key_pattern.replace("*", ".*").replace("?", ".")
            query["key"] = {"$regex": f"^{regex}$"}

        cursor = collection.find(query)
        result: Dict[str, Any] = {}

        async for doc in cursor:
            if doc.get("expires_at"):
                if doc["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    continue
            result[doc["key"]] = self._deserialize(doc["value"])

        logger.debug(
            f"💾 [{agent_id[:8]}] retrieve_all: "
            f"{len(result)} entradas encontradas"
            + (f" (filtro: {key_pattern})" if key_pattern else "")
        )
        return result

    async def delete(self, agent_id: str, key: str) -> bool:
        """
        Remove uma entrada da memória.
        """
        self._check_ready()

        collection = self._db[self.MEMORIES_COLLECTION]
        result = await collection.delete_one(
            {"agent_id": agent_id, "key": key}
        )

        deleted = result.deleted_count > 0
        if deleted:
            logger.debug(f"💾 [{agent_id[:8]}] Memória removida: {key}")
        return deleted

    async def clear_agent_memory(self, agent_id: str) -> int:
        """
        Remove TODAS as memórias de um agente.
        """
        self._check_ready()

        collection = self._db[self.MEMORIES_COLLECTION]
        result = await collection.delete_many({"agent_id": agent_id})
        count = result.deleted_count

        logger.info(f"💾 [{agent_id[:8]}] Memória limpa: {count} entradas removidas.")
        return count

    # HISTÓRICO DE CONVERSAÇÃO

    async def save_conversation(
        self,
        agent_id:   str,
        session_id: str,
        messages:   List[ConversationRecord],
    ) -> None:
        """
        Persiste o histórico de conversação de uma sessão.
        """
        self._check_ready()

        collection = self._db[self.CONVERSATIONS_COLLECTION]

        serialized = [
            {
                "role":      msg.role,
                "content":   msg.content,
                "timestamp": msg.timestamp,
                "metadata":  msg.metadata,
            }
            for msg in messages
        ]

        await collection.update_one(
            {"agent_id": agent_id, "session_id": session_id},
            {
                "$set": {
                    "messages":   serialized,
                    "updated_at": datetime.now(timezone.utc),
                    "count":      len(messages),
                },
                "$setOnInsert": {
                    "created_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )

        logger.debug(
            f"💬 [{agent_id[:8]}] Conversa salva: "
            f"session={session_id} | {len(messages)} msgs"
        )

    async def load_conversation(
        self,
        agent_id:   str,
        session_id: str,
    ) -> List[ConversationRecord]:
        """
        Carrega o histórico de conversação de uma sessão.
        """
        self._check_ready()

        collection = self._db[self.CONVERSATIONS_COLLECTION]
        doc = await collection.find_one(
            {"agent_id": agent_id, "session_id": session_id}
        )

        if doc is None:
            return []

        records = []
        for msg in doc.get("messages", []):
            records.append(
                ConversationRecord(
                    role=msg["role"],
                    content=msg["content"],
                    timestamp=msg.get("timestamp", datetime.now(timezone.utc)),
                    metadata=msg.get("metadata", {}),
                )
            )

        logger.debug(
            f"💬 [{agent_id[:8]}] Conversa carregada: "
            f"session={session_id} | {len(records)} msgs"
        )
        return records

    async def list_sessions(self, agent_id: str) -> List[str]:
        """Lista todas as sessões de conversação de um agente."""
        self._check_ready()

        collection = self._db[self.CONVERSATIONS_COLLECTION]
        cursor = collection.find(
            {"agent_id": agent_id},
            {"session_id": 1}
        )

        sessions = []
        async for doc in cursor:
            sessions.append(doc["session_id"])

        return sessions

    async def delete_conversation(
        self,
        agent_id:   str,
        session_id: str,
    ) -> bool:
        """Remove o histórico de uma sessão."""
        self._check_ready()

        collection = self._db[self.CONVERSATIONS_COLLECTION]
        result = await collection.delete_one(
            {"agent_id": agent_id, "session_id": session_id}
        )
        return result.deleted_count > 0

    # ESTATÍSTICAS

    async def get_stats(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna estatísticas de uso da memória.
        """
        self._check_ready()

        memories_col      = self._db[self.MEMORIES_COLLECTION]
        conversations_col = self._db[self.CONVERSATIONS_COLLECTION]

        query = {"agent_id": agent_id} if agent_id else {}

        total_memories      = await memories_col.count_documents(query)
        total_conversations = await conversations_col.count_documents(query)

        return {
            "agent_id":           agent_id or "all",
            "total_memories":     total_memories,
            "total_conversations": total_conversations,
            "database":           self._db_name,
            "collections": {
                "memories":      self.MEMORIES_COLLECTION,
                "conversations": self.CONVERSATIONS_COLLECTION,
            },
        }

    # SERIALIZAÇÃO

    @staticmethod
    def _serialize(value: Any) -> Any:
        """Converte value para formato compatível com MongoDB."""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _deserialize(value: Any) -> Any:
        """Recupera value do formato MongoDB."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value
        return value

    # CONTEXT MANAGER

    async def __aenter__(self) -> "AgentMemory":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._ready else "disconnected"
        return f"AgentMemory(db={self._db_name!r}, status={status!r})"
