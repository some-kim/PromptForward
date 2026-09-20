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


def users() -> AsyncIOMotorCollection:
    return get_database()["users"]


def sessions() -> AsyncIOMotorCollection:
    return get_database()["sessions"]


def progress_events() -> AsyncIOMotorCollection:
    return get_database()["progress_events"]


def problem_progress() -> AsyncIOMotorCollection:
    return get_database()["problem_progress"]


def prompt_evaluations() -> AsyncIOMotorCollection:
    return get_database()["prompt_evaluations"]


async def ensure_indexes() -> None:
    await problem_progress().create_index("userId")
    await challenges().create_index(
        "problem.slug", name="problem_slug_unique", unique=True, sparse=True
    )
    await challenges().create_index("target.imageHash", unique=True)
    await attempts().create_index("challengeId")
    await attempts().create_index("gameId")
    await prompt_evaluations().create_index("challengeId")
    await users().create_index("username", unique=True)


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
