"""
Script de verificação da infraestrutura.
"""
import asyncio
import sys
import os

# Garante que o projeto está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import app_logger as logger
from core.config import settings


# VERIFICAÇÕES

async def check_ollama() -> bool:
    """Verifica conexão com o Ollama (LLM local)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    logger.success(f"✅ Ollama OK! Modelos: {models}")
                else:
                    logger.warning("⚠️  Ollama rodando, mas nenhum modelo baixado ainda.")
                    logger.info(f"   Execute: ollama pull {settings.OLLAMA_MODEL}")
                return True
            logger.error(f"❌ Ollama status: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ollama inacessível: {e}")
        logger.info("   Instale o Ollama em: https://ollama.ai")
        return False


async def check_mongodb() -> bool:
    """Verifica conexão com o MongoDB."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5000
        )
        result = await client.admin.command("ping")
        if result.get("ok") == 1.0:
            logger.success("✅ MongoDB OK!")
            # Testa criação de uma collection de teste
            db = client[settings.MONGODB_DB_NAME]
            await db.test_collection.insert_one({"test": "connection", "source": "infra_check"})
            await db.test_collection.delete_many({"source": "infra_check"})
            logger.info("   Leitura/escrita no MongoDB funcionando.")
        client.close()
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB falhou: {e}")
        logger.info("   Verifique se o container map_mongodb está rodando.")
        return False


async def check_elasticsearch() -> bool:
    """Verifica conexão com o ElasticSearch."""
    try:
        from elasticsearch import AsyncElasticsearch
        es = AsyncElasticsearch(settings.ELASTICSEARCH_URL, request_timeout=10)
        info = await es.info()
        version = info["version"]["number"]
        health = await es.cluster.health()
        status = health["status"]
        logger.success(f"✅ ElasticSearch OK! Versão: {version} | Status cluster: {status}")
        await es.close()
        return True
    except Exception as e:
        logger.error(f"❌ ElasticSearch falhou: {e}")
        logger.info("   Verifique se o container map_elasticsearch está rodando.")
        logger.info("   ElasticSearch demora ~60s para inicializar.")
        return False


def check_kafka() -> bool:
    """Verifica conexão com o Kafka."""
    try:
        from confluent_kafka.admin import AdminClient
        admin = AdminClient({
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "socket.timeout.ms": 5000,
        })
        metadata = admin.list_topics(timeout=10)
        topics = list(metadata.topics.keys())
        logger.success(f"✅ Kafka OK! Tópicos existentes: {topics if topics else '(nenhum ainda)'}")
        return True
    except Exception as e:
        logger.error(f"❌ Kafka falhou: {e}")
        logger.info("   Verifique se o container map_kafka está rodando.")
        return False


# MAIN

async def main():
    logger.info("=" * 55)
    logger.info("  🔍 VERIFICAÇÃO DE INFRAESTRUTURA")
    logger.info(f"  Projeto: {settings.APP_NAME}")
    logger.info("=" * 55)

    results = {}

    logger.info("\n🔌 Testando Ollama...")
    results["Ollama (LLM)"] = await check_ollama()

    logger.info("\n🔌 Testando MongoDB...")
    results["MongoDB"] = await check_mongodb()

    logger.info("\n🔌 Testando ElasticSearch...")
    results["ElasticSearch"] = await check_elasticsearch()

    logger.info("\n🔌 Testando Kafka...")
    results["Kafka"] = check_kafka()

    # Resumo
    logger.info("\n" + "=" * 55)
    logger.info("  📊 RESUMO DOS TESTES")
    logger.info("=" * 55)

    passed = 0
    for service, ok in results.items():
        icon = "✅" if ok else "❌"
        status = "PASSOU" if ok else "FALHOU"
        logger.info(f"  {icon} {service:<20} {status}")
        if ok:
            passed += 1

    total = len(results)
    logger.info("=" * 55)

    if passed == total:
        logger.success(f"\n🎉 TUDO OK! {passed}/{total} serviços funcionando.")
        logger.info("   Você está pronto para a FASE 2!")
    else:
        logger.warning(f"\n⚠️  {passed}/{total} serviços OK.")
        logger.info("   Verifique os erros acima antes de continuar.")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
