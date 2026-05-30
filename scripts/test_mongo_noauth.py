import asyncio
import motor.motor_asyncio

async def test():
    urls_test = [
        ("SEM AUTH", "mongodb://localhost:27017/"),
        ("COM AUTH", "mongodb://admin:admin123@localhost:27017/?authSource=admin"),
    ]
    
    for label, url in urls_test:
        try:
            client = motor.motor_asyncio.AsyncIOMotorClient(
                url, serverSelectionTimeoutMS=3000
            )
            info = await client.server_info()
            print(f"  {label}: CONECTOU! Version: {info.get('version')}")
            try:
                dbs = await client.list_database_names()
                print(f"    Databases visiveis: {dbs}")
            except Exception as e2:
                print(f"    list_database_names erro: {e2}")
            client.close()
        except Exception as e:
            print(f"  {label}: {type(e).__name__}: {e}")

asyncio.run(test())
