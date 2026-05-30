from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    """
    Configurações da plataforma.
    """

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App
    APP_NAME: str = "Multi-Agent Platform"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Ollama (LLM Gratuito Local)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:1b"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_INTERNAL_SERVERS: str = "kafka:29092"
    KAFKA_GROUP_ID: str = "multi-agent-group"

    # MongoDB
    MONGODB_URL: str = "mongodb://admin:admin123@localhost:27017/?authSource=admin"
    MONGODB_DB_NAME: str = "multi_agent_db"

    # ElasticSearch
    ELASTICSEARCH_URL: str = "http://localhost:9200"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000


# Instância global de configurações
settings = Settings()
