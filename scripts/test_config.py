import sys
sys.path.insert(0, ".")

from core.config import settings

print(f"Config OK: {settings.APP_NAME}")
print(f"  LLM:     {settings.OLLAMA_MODEL}")
print(f"  MongoDB: {settings.MONGODB_DB_NAME}")
print(f"  Kafka:   {settings.KAFKA_BOOTSTRAP_SERVERS}")
print(f"  ES:      {settings.ELASTICSEARCH_URL}")
