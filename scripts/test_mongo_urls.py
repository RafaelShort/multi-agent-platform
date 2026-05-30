import asyncio
import motor.motor_asyncio

urls = [
    "mongodb://admin:admin123@localhost:27017/?authSource=admin",
    "mongodb://admin:admin123@127.0.0.1:27017/?authSource=admin",
    "mongodb://admin:admin123@localhost:27017/admin",
    "mongodb://admin:admin123@127.0.0.1:27017/admin",
    "mongodb://admin:admin123@localhost:27017/",
]

async def test_url(url):
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(
            url,
            serverSelectionTimeoutMS=5000
        )
        result = await client.admin.command("ping")
        dbs = await client.list_database_names()
        print(f"  OK    {url}")
        print(f"         Databases: {dbs}")
        client.close()
        return True
    except Exception as e:
        print(f"  ERRO  {url}")
        print(f"         {type(e).__name__}: {e}")
        return False

async def main():
    print("\nTestando variacoes de URL MongoDB:\n")
    for url in urls:
        await test_url(url)
        print()

asyncio.run(main())
