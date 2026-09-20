"""MongoDB connection and indexes."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

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


def users() -> AsyncIOMotorCollection:
    return get_database()["users"]


def sessions() -> AsyncIOMotorCollection:
    return get_database()["sessions"]


def progress_events() -> AsyncIOMotorCollection:
    return get_database()["progress_events"]


def user_images() -> AsyncIOMotorCollection:
    return get_database()["user_images"]


async def ensure_indexes() -> None:
    await challenges().create_index("target.imageHash", unique=True)
    await attempts().create_index("challengeId")
    await attempts().create_index("gameId")
    await users().create_index("username", unique=True)
    # Partial: games from before Battle Mode have no code, and they would all collide on null.
    await _replace_index(
        games(), "code", unique=True, partialFilterExpression={"code": {"$type": "string"}}
    )
    # The standings walk reads completed battles in the order they finished.
    await games().create_index([("status", 1), ("completedAt", 1)])
    await user_images().create_index("userId")


async def _replace_index(collection: AsyncIOMotorCollection, key: str, **options: object) -> None:
    """Create the index, rebuilding one of the same name that was defined differently."""
    try:
        await collection.create_index(key, **options)
    except OperationFailure as failure:
        if failure.code not in (85, 86):  # IndexOptionsConflict, IndexKeySpecsConflict
            raise
        try:
            await collection.drop_index(f"{key}_1")
        except OperationFailure as dropped:
            if dropped.code != 27:  # IndexNotFound: another instance migrated it first
                raise
        await collection.create_index(key, **options)


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
