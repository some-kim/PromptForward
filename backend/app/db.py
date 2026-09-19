"""MongoDB connection and indexes."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.config import get_config

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_config().mongo.uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[get_config().mongo.db_name]


def challenges() -> AsyncIOMotorCollection:
    return get_database()["challenges"]


def attempts() -> AsyncIOMotorCollection:
    return get_database()["attempts"]


def games() -> AsyncIOMotorCollection:
    return get_database()["games"]


async def ensure_indexes() -> None:
    await challenges().create_index("target.imageHash", unique=True)
    await attempts().create_index("challengeId")
    await attempts().create_index("gameId")


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
