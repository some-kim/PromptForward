"""Challenge creation: hash, reuse stored analysis, analyze, store, persist."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app import db
from app.config import ANALYSIS_VERSION, get_config
from app.models import DEFAULT_DIFFICULTY, ChallengeSource, Difficulty, Problem, Rubric
from app.services.dropbox.image_storage import (
    delete_target_image,
    read_image_meta,
    store_target_image,
    store_user_image,
)
from app.services.openai.challenge_analyzer import analyze_challenge

logger = logging.getLogger(__name__)


def sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


async def create_challenge(
    image_bytes: bytes,
    difficulty: Difficulty = DEFAULT_DIFFICULTY,
    source: ChallengeSource = "curated",
    problem: Problem | None = None,
) -> dict[str, Any]:
    """Idempotent: a byte-identical image with a current analysis is returned unchanged.

    A player upload (`source="player"`) is stored outside the curated folder and stays out of
    the training pool. Curating is one way: an image a player uploaded is promoted into the
    curated folder and the training pool when it is later seeded as a target.

    Problem metadata is cheap to change, so it is refreshed without paying for a new analysis.
    A problem's slug is its identity: a new image for a known slug replaces that challenge in
    place, so progress recorded against it survives, and the retired image file is removed so
    the folder seeder cannot resurrect it as a plain target. An image already used by a different
    challenge cannot be taken over by a slug; that is a `ChallengeConflict`.
    """
    image_hash = sha256(image_bytes)

    existing = await _find_owner(image_hash, problem)
    same_image = existing is not None and existing["target"]["imageHash"] == image_hash
    promoting = same_image and source == "curated" and existing.get("source") == "player"
    fresh = same_image and existing.get("analysis", {}).get("version") == ANALYSIS_VERSION
    if fresh and not promoting:
        if problem is None:
            return existing
        labels = {"problem": problem.model_dump(), "difficulty": difficulty}
        await db.challenges().update_one({"_id": existing["_id"]}, {"$set": labels})
        return {**existing, **labels}

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
    if problem is not None:
        doc["problem"] = problem.model_dump()

    if existing:
        await db.challenges().update_one({"_id": existing["_id"]}, {"$set": doc})
        retired = existing["target"]
        if retired["dropboxPath"] != stored.path:
            try:
                await delete_target_image(retired["dropboxPath"])
            except Exception:  # noqa: BLE001 - already replaced in the DB; the file is litter
                logger.warning("Could not remove retired target %s", retired["dropboxPath"])
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
        winner = await _find_owner(image_hash, problem)
        if winner is None:
            raise
        return winner

    return {"_id": result.inserted_id, **doc, "createdAt": now}


class ChallengeConflict(ValueError):
    """The image belongs to one challenge and the slug to another."""


async def _find_owner(image_hash: str, problem: Problem | None) -> dict[str, Any] | None:
    """The one challenge this upload may update.

    Without a problem that is the image's owner. With one it is the slug's owner, and the image
    may not already belong to anything else: a slug never takes over another challenge.
    """
    by_image = await db.challenges().find_one({"target.imageHash": image_hash})
    if problem is None:
        return by_image
    by_slug = await db.challenges().find_one({"problem.slug": problem.slug})
    if by_image is not None and (by_slug is None or by_image["_id"] != by_slug["_id"]):
        raise ChallengeConflict(
            f"Image is already used by challenge {by_image['_id']}, "
            f"which is not problem '{problem.slug}'"
        )
    return by_slug


def rubric_of(challenge: dict[str, Any]) -> Rubric:
    return Rubric.model_validate(challenge["rubric"])
