import asyncio

from pymongo.asynchronous.database import AsyncDatabase

from app.database import (
    close_database_clients,
    get_ingestion_database,
    get_read_database,
)


async def ping(name: str, database: AsyncDatabase) -> bool:
    try:
        await database.command({"ping": 1})
        print(f"{name}: connected")
        return True
    except Exception as error:
        print(f"{name}: unavailable ({type(error).__name__})")
        return False


async def main() -> int:
    try:
        results = await asyncio.gather(
            ping("ingestion", get_ingestion_database()),
            ping("reader", get_read_database()),
        )
        return 0 if all(results) else 1
    finally:
        await close_database_clients()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
