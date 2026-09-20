"""The images a player owns: uploaded once, reusable in any battle they play."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app import db
from app.services.challenges import create_challenge


def _key(user_id: str, challenge_id: ObjectId) -> str:
    return f"{user_id}:{challenge_id}"


async def save_image(user_id: str, image_bytes: bytes) -> dict[str, Any]:
    """Analyze and store an uploaded image, then attach it to the account."""
    challenge = await create_challenge(image_bytes, source="player")
    await db.user_images().update_one(
        {"_id": _key(user_id, challenge["_id"])},
        {
            "$setOnInsert": {
                "userId": user_id,
                "challengeId": challenge["_id"],
                "createdAt": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    return challenge


async def list_images(user_id: str) -> list[dict[str, Any]]:
    owned = db.user_images().find({"userId": user_id}).sort("createdAt", -1)
    ids = [entry["challengeId"] async for entry in owned]
    if not ids:
        return []

    by_id = {
        challenge["_id"]: challenge
        async for challenge in db.challenges().find({"_id": {"$in": ids}})
    }
    return [by_id[challenge_id] for challenge_id in ids if challenge_id in by_id]


async def owns_image(user_id: str, challenge_id: ObjectId) -> bool:
    return await db.user_images().find_one({"_id": _key(user_id, challenge_id)}) is not None


async def forget_image(user_id: str, challenge_id: ObjectId) -> None:
    """Drop the image from the account. The challenge itself stays: past battles still show it."""
    await db.user_images().delete_one({"_id": _key(user_id, challenge_id)})
