"""Challenge creation: hash, reuse stored analysis, analyze, store, persist."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app import db
from app.config import ANALYSIS_VERSION, get_config
from app.models import DEFAULT_DIFFICULTY, Difficulty, Problem, Rubric
from app.services.dropbox.image_storage import read_image_meta, store_target_image
from app.services.openai.challenge_analyzer import analyze_challenge


def sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


async def create_challenge(
    image_bytes: bytes,
    difficulty: Difficulty = DEFAULT_DIFFICULTY,
    problem: Problem | None = None,
) -> dict[str, Any]:
    """Idempotent: a byte-identical image with a current analysis is returned unchanged.

    Problem metadata is cheap to change, so it is refreshed without paying for a new analysis.
    A problem's slug is its identity: a new image for a known slug replaces that challenge in
    place, so progress recorded against it survives. An image already used by a different
    challenge cannot be taken over by a slug; that is a `ChallengeConflict`.
    """
    image_hash = sha256(image_bytes)

    existing = await _find_owner(image_hash, problem)
    if (
        existing is not None
        and existing["target"]["imageHash"] == image_hash
        and existing.get("analysis", {}).get("version") == ANALYSIS_VERSION
    ):
        if problem is None:
            return existing
        labels = {"problem": problem.model_dump(), "difficulty": difficulty}
        await db.challenges().update_one({"_id": existing["_id"]}, {"$set": labels})
        return {**existing, **labels}

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
    if problem is not None:
        doc["problem"] = problem.model_dump()

    if existing:
        await db.challenges().update_one({"_id": existing["_id"]}, {"$set": doc})
        return {**existing, **doc}

    try:
        result = await db.challenges().insert_one({**doc, "createdAt": now})
    except DuplicateKeyError:
        # Lost a race with an identical upload (same image or same slug): adopt the winner.
        winner = await _find_owner(image_hash, problem)
        if winner is None:
            raise
        return winner

    return {"_id": result.inserted_id, **doc, "createdAt": now}


class ChallengeConflict(ValueError):
    """The image belongs to one challenge and the slug to another."""


async def _find_owner(image_hash: str, problem: Problem | None) -> dict[str, Any] | None:
    """The one challenge this upload may update: the slug's owner, else the image's owner."""
    by_image = await db.challenges().find_one({"target.imageHash": image_hash})
    if problem is None:
        return by_image
    by_slug = await db.challenges().find_one({"problem.slug": problem.slug})
    if by_slug is None:
        return by_image
    if by_image is not None and by_image["_id"] != by_slug["_id"]:
        raise ChallengeConflict(
            f"Image is already used by challenge {by_image['_id']}; "
            f"problem '{problem.slug}' is challenge {by_slug['_id']}"
        )
    return by_slug


def rubric_of(challenge: dict[str, Any]) -> Rubric:
    return Rubric.model_validate(challenge["rubric"])
