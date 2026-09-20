"""Challenge creation: hash, reuse stored analysis, analyze, store, persist."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app import db
from app.config import ANALYSIS_VERSION, get_config
from app.models import DEFAULT_DIFFICULTY, Difficulty, Rubric
from app.services.dropbox.image_storage import read_image_meta, store_target_image
from app.services.openai.challenge_analyzer import analyze_challenge


def sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


async def create_challenge(
    image_bytes: bytes, difficulty: Difficulty = DEFAULT_DIFFICULTY
) -> dict[str, Any]:
    """Idempotent: a byte-identical image with a current analysis is returned unchanged."""
    image_hash = sha256(image_bytes)

    existing = await db.challenges().find_one({"target.imageHash": image_hash})
    if existing and existing.get("analysis", {}).get("version") == ANALYSIS_VERSION:
        return existing

    meta = read_image_meta(image_bytes)
    rubric: Rubric = await analyze_challenge(image_bytes, meta.mimeType)
    stored = await store_target_image(image_bytes, image_hash, meta.mimeType, difficulty)

    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "type": "image",
        "difficulty": difficulty,
        "target": {
            "dropboxFileId": stored.id,
            "dropboxPath": stored.path,
            "imageHash": image_hash,
            "mimeType": meta.mimeType,
            "width": meta.width,
            "height": meta.height,
        },
        "rubric": rubric.model_dump(),
        "analysis": {
            "provider": "openai",
            "model": get_config().openai.challenge_analyzer_model,
            "version": ANALYSIS_VERSION,
            "analyzedAt": now,
        },
        "updatedAt": now,
    }

    if existing:
        await db.challenges().update_one({"_id": existing["_id"]}, {"$set": doc})
        return {**existing, **doc}

    try:
        result = await db.challenges().insert_one({**doc, "createdAt": now})
    except DuplicateKeyError:
        return await db.challenges().find_one({"target.imageHash": image_hash})

    return {"_id": result.inserted_id, **doc, "createdAt": now}


def rubric_of(challenge: dict[str, Any]) -> Rubric:
    return Rubric.model_validate(challenge["rubric"])
