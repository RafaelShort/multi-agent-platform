import asyncio
import motor.motor_asyncio

# Mesma URL do .env
MONGODB_URL = "mongodb://admin:admin123@localhost:27017/?authSource=admin"

async def test():
    print(f"Tentando conectar: {MONGODB_URL}")
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGODB_URL,
            serverSelectionTimeoutMS=5000
        )
        result = await client.admin.command("ping")
        print(f"OK: {result}")
        
        # Listar databases
        dbs = await client.list_database_names()
        print(f"Databases: {dbs}")
        
    except Exception as e:
        print(f"ERRO: {type(e).__name__}: {e}")

asyncio.run(test())
