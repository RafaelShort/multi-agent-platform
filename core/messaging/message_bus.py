from __future__ import annotations

import asyncio
import json
import queue as stdlib_queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import BaseModel, Field

from core.config import settings
from core.logger import app_logger as logger


MessageHandler = Callable[["BusMessage"], Coroutine[Any, Any, None]]


class BusMessage(BaseModel):
    message_id:  str      = Field(default_factory=lambda: str(uuid.uuid4()))
    topic:       str      = Field(...)
    sender_id:   str      = Field(...)
    receiver_id: str      = Field("*")
    content:     str      = Field(...)
    msg_type:    str      = Field("task")
    metadata:    Dict[str, Any] = Field(default_factory=dict)
    timestamp:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reply_to:    Optional[str] = Field(None)

    def to_json(self) -> str:
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw) -> "BusMessage":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class MessageBus:
    TOPIC_TASKS     = "agents.tasks"
    TOPIC_RESULTS   = "agents.results"
    TOPIC_EVENTS    = "agents.events"
    TOPIC_BROADCAST = "agents.broadcast"
    DEFAULT_TOPICS  = ["agents.tasks", "agents.results", "agents.events", "agents.broadcast"]

    def __init__(self, bootstrap_servers=None, group_id=None, client_id=None):
        self._servers   = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self._group_id  = group_id or "multi-agent-platform"
        self._client_id = client_id or ("map-client-" + uuid.uuid4().hex[:8])

        self._producer = None
        self._consumer = None
        self._admin    = None

        self._handlers: Dict[str, List[MessageHandler]] = {}
        self._consumer_thread   = None
        self._consume_running   = threading.Event()
        self._resubscribe_queue = stdlib_queue.Queue()
        self._consuming         = False
        self._ready             = False
        self._stats             = {"published": 0, "consumed": 0, "errors": 0}

        logger.info(f"📨 MessageBus criado | servers={self._servers} | group={self._group_id}")

    async def connect(self) -> None:
        if self._ready:
            return
        try:
            self._admin = AdminClient({
                "bootstrap.servers": self._servers,
                "socket.timeout.ms": 10000,
            })
            self._producer = Producer({
                "bootstrap.servers": self._servers,
                "client.id":         self._client_id,
                "acks":              "all",
                "retries":           3,
                "retry.backoff.ms":  500,
                "socket.timeout.ms": 10000,
            })
            self._consumer = Consumer({
                "bootstrap.servers":  self._servers,
                "group.id":           self._group_id,
                "client.id":          self._client_id + "-consumer",
                "auto.offset.reset":  "latest",
                "enable.auto.commit": True,
                "socket.timeout.ms":  10000,
            })
            await self._ensure_topics(self.DEFAULT_TOPICS)
            self._ready = True
            logger.success(f"✅ MessageBus conectado | servers={self._servers}")
        except Exception as e:
            logger.error(f"❌ MessageBus falhou ao conectar: {e}")
            raise

    async def disconnect(self) -> None:
        self._consuming = False
        self._consume_running.clear()
        if self._consumer_thread and self._consumer_thread.is_alive():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._consumer_thread.join(timeout=5.0))
        elif self._consumer:
            try:
                self._consumer.close()
            except Exception:
                pass
        if self._producer:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._producer.flush, 5)
        self._ready = False
        logger.info(f"📨 MessageBus desconectado | stats={self._stats}")

    def _check_ready(self) -> None:
        if not self._ready:
            raise RuntimeError("MessageBus nao conectado. Chame await bus.connect().")

    async def _ensure_topics(self, topics: List[str], num_partitions: int = 1) -> None:
        loop = asyncio.get_running_loop()

        def _create():
            existing = self._admin.list_topics(timeout=5).topics
            to_create = [
                NewTopic(t, num_partitions=num_partitions, replication_factor=1)
                for t in topics if t not in existing
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
                    if "TOPIC_ALREADY_EXISTS" not in str(e):
                        logger.warning(f"Aviso ao criar topico {topic}: {e}")
            if created:
                for _ in range(20):
                    time.sleep(0.5)
                    current = self._admin.list_topics(timeout=5).topics
                    if all(t in current for t in created):
                        break
            return created

        created = await loop.run_in_executor(None, _create)
        if created:
            logger.info(f"📑 Topicos criados: {created}")

    async def create_topic(self, name: str, num_partitions: int = 1) -> None:
        self._check_ready()
        await self._ensure_topics([name], num_partitions)

    def agent_topic(self, agent_id: str) -> str:
        return f"agent.{agent_id}"

    async def publish(self, message: BusMessage) -> None:
        self._check_ready()
        payload = message.to_json().encode("utf-8")
        key     = message.receiver_id.encode("utf-8")
        topic   = message.topic
        loop    = asyncio.get_running_loop()

        def _produce():
            self._producer.produce(
                topic=topic, value=payload, key=key,
                on_delivery=self._delivery_callback,
            )
            self._producer.poll(0)

        try:
            await loop.run_in_executor(None, _produce)
            self._stats["published"] += 1
            logger.debug(f"📤 Publicado | topic={topic} | sender={message.sender_id[:8]}")
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Erro ao publicar: {e}")
            raise

    async def publish_to_agent(
        self, sender_id, receiver_id, content, msg_type="task", **metadata
    ) -> BusMessage:
        self._check_ready()
        topic = self.agent_topic(receiver_id)
        await self._ensure_topics([topic])
        msg = BusMessage(
            topic=topic, sender_id=sender_id, receiver_id=receiver_id,
            content=content, msg_type=msg_type, metadata=metadata,
        )
        await self.publish(msg)
        return msg

    async def broadcast(self, sender_id: str, content: str, **metadata) -> BusMessage:
        self._check_ready()
        msg = BusMessage(
            topic=self.TOPIC_BROADCAST, sender_id=sender_id,
            receiver_id="*", content=content, msg_type="broadcast", metadata=metadata,
        )
        await self.publish(msg)
        return msg

    def _delivery_callback(self, err, msg) -> None:
        if err:
            self._stats["errors"] += 1
            logger.error(f"❌ Falha na entrega: {err}")

    async def subscribe(self, topic, handler: MessageHandler) -> None:
        self._check_ready()
        topics = [topic] if isinstance(topic, str) else topic

        # Garantir que todos os topicos existem ANTES de registrar o consumer
        await self._ensure_topics(topics)

        for t in topics:
            if t not in self._handlers:
                self._handlers[t] = []
            self._handlers[t].append(handler)
            logger.info(f"📥 Handler registrado | topic={t}")

        all_topics     = list(self._handlers.keys())
        assigned_event = threading.Event()
        assigned_set   = set()

        def on_assign(consumer, partitions):
            for p in partitions:
                assigned_set.add(p.topic)
            # Sinalizar apenas quando TODOS os topicos tiverem particoes
            if all(t in assigned_set for t in all_topics):
                assigned_event.set()

        if not self._consuming:
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
            current = getattr(self, "_subscribed_topics", set())
            if set(all_topics) == current:
                logger.info(f"📥 Topico ja subscrito, handler apenas adicionado")
                assigned_event.set()
            else:
                self._subscribed_topics = set(all_topics)
                self._resubscribe_queue.put({"topics": all_topics, "on_assign": on_assign})

        loop = asyncio.get_running_loop()
        assigned = await loop.run_in_executor(None, lambda: assigned_event.wait(timeout=15.0))
        if assigned:
            await asyncio.sleep(0.5)
            logger.info(f"📥 Consumer pronto | topicos: {all_topics}")
        else:
            logger.warning(f"⚠️ Timeout aguardando particoes: {all_topics}")

    def _consume_loop_sync(self, loop: asyncio.AbstractEventLoop) -> None:
        logger.info("🔄 Consumer thread iniciada.")
        while self._consume_running.is_set():
            try:
                cmd        = self._resubscribe_queue.get_nowait()
                new_topics = cmd["topics"]
                self._consumer.subscribe(new_topics, on_assign=cmd["on_assign"])
                logger.info(f"🔄 Resubscrito em: {new_topics}")
            except stdlib_queue.Empty:
                pass

            try:
                msg = self._consumer.poll(timeout=0.1)
            except Exception as e:
                logger.error(f"❌ Erro no poll: {e}")
                continue

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    err_str = str(msg.error())
                    logger.error(f"❌ Erro Kafka: {err_str}")
                    self._stats["errors"] += 1
                continue

            try:
                bus_msg = BusMessage.from_json(msg.value())
            except Exception as e:
                logger.error(f"❌ Erro ao deserializar: {e}")
                continue

            topic    = msg.topic()
            handlers = self._handlers.get(topic, [])

            if handlers:
                self._stats["consumed"] += 1
                for handler in handlers:
                    future = asyncio.run_coroutine_threadsafe(handler(bus_msg), loop)

                    def _on_done(f, h=handler):
                        try:
                            f.result()
                        except Exception as exc:
                            self._stats["errors"] += 1
                            logger.error(f"❌ Erro no handler {h.__name__}: {exc}")

                    future.add_done_callback(_on_done)
            else:
                logger.warning(f"⚠️ Mensagem sem handler | topic={topic}")

        try:
            self._consumer.close()
        except Exception:
            pass
        logger.info("🔄 Consumer thread encerrada.")

    async def get_stats(self) -> Dict[str, Any]:
        self._check_ready()
        loop     = asyncio.get_running_loop()
        metadata = await loop.run_in_executor(None, lambda: self._admin.list_topics(timeout=5))
        topics   = [t for t in metadata.topics if not t.startswith("__")]
        return {
            "status":        "connected" if self._ready else "disconnected",
            "servers":       self._servers,
            "group_id":      self._group_id,
            "topics":        topics,
            "subscriptions": list(self._handlers.keys()),
            "handlers":      {t: len(h) for t, h in self._handlers.items()},
            "consuming":     self._consuming,
            "messages": {
                "published": self._stats["published"],
                "consumed":  self._stats["consumed"],
                "errors":    self._stats["errors"],
            },
        }

    async def __aenter__(self) -> "MessageBus":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._ready else "disconnected"
        return (
            f"MessageBus(servers={self._servers!r}, status={status!r}, "
            f"published={self._stats['published']}, consumed={self._stats['consumed']})"
        )
