"""Challenge creation: hash, reuse stored analysis, analyze, store, persist."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app import db
from app.config import ANALYSIS_VERSION, get_config
from app.models import DEFAULT_DIFFICULTY, ChallengeSource, Difficulty, Rubric
from app.services.dropbox.image_storage import (
    read_image_meta,
    store_target_image,
    store_user_image,
)
from app.services.openai.challenge_analyzer import analyze_challenge


def sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


async def create_challenge(
    image_bytes: bytes,
    difficulty: Difficulty = DEFAULT_DIFFICULTY,
    source: ChallengeSource = "curated",
) -> dict[str, Any]:
    """Idempotent: a byte-identical image with a current analysis is returned unchanged.

    A player upload (`source="player"`) is stored outside the curated folder and stays out of
    the training pool. Curating is one way: an image a player uploaded is promoted into the
    curated folder and the training pool when it is later seeded as a target.
    """
    image_hash = sha256(image_bytes)

    existing = await db.challenges().find_one({"target.imageHash": image_hash})
    promoting = bool(existing) and source == "curated" and existing.get("source") == "player"
    fresh = bool(existing) and existing.get("analysis", {}).get("version") == ANALYSIS_VERSION
    if fresh and not promoting:
        return existing

    # An image that is already curated stays curated, and so stays in the curated folder: a
    # player uploading the same bytes must not move it out of the pool defaults are dealt from.
    effective_source: ChallengeSource = (
        "curated"
        if source == "curated" or (existing or {}).get("source") == "curated"
        else "player"
    )

    meta = read_image_meta(image_bytes)
    rubric: Rubric = await analyze_challenge(image_bytes, meta.mimeType)
    stored = (
        await store_user_image(image_bytes, image_hash, meta.mimeType)
        if effective_source == "player"
        else await store_target_image(image_bytes, image_hash, meta.mimeType, difficulty)
    )

    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "type": "image",
        "difficulty": difficulty,
        "source": effective_source,
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
        # A concurrent upload won the race; curating still has to promote what it inserted.
        if source == "curated":
            promoted = await db.challenges().find_one_and_update(
                {"target.imageHash": image_hash, "source": "player"},
                {"$set": doc},
                return_document=True,
            )
            if promoted is not None:
                return promoted
        return await db.challenges().find_one({"target.imageHash": image_hash})

    return {"_id": result.inserted_id, **doc, "createdAt": now}


def rubric_of(challenge: dict[str, Any]) -> Rubric:
    return Rubric.model_validate(challenge["rubric"])
