"""Challenge listing, metadata, target image bytes, and the dev-only upload endpoint."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app import db
from app.config import get_config
from app.models import DEFAULT_DIFFICULTY, Difficulty, Problem, Skill
from app.serializers import challenge_summary, challenge_view, object_id
from app.services.challenges import ChallengeConflict, create_challenge
from app.services.dropbox.image_storage import download_image

router = APIRouter(prefix="/api/challenges", tags=["challenges"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.get("")
async def list_challenges(
    difficulty: Difficulty | None = Query(None), skill: Skill | None = Query(None)
) -> list[dict]:
    query: dict = {}
    if difficulty:
        query["difficulty"] = difficulty
    if skill:
        query["problem.skill"] = skill
    else:
        query["problem"] = None
    cursor = db.challenges().find(query, {"target": 1, "type": 1, "difficulty": 1, "problem": 1})
    return [challenge_summary(challenge) async for challenge in cursor]


@router.get("/{challenge_id}")
async def get_challenge(challenge_id: str) -> dict:
    return challenge_view(await _load(challenge_id))


@router.get("/{challenge_id}/image")
async def get_challenge_image(challenge_id: str) -> Response:
    challenge = await _load(challenge_id)
    image = await download_image(challenge["target"]["dropboxPath"])
    return Response(content=image, media_type=challenge["target"]["mimeType"])


@router.post("", status_code=201)
async def upload_challenge(
    image: UploadFile = File(...),
    difficulty: Difficulty = Form(DEFAULT_DIFFICULTY),
    problem: str | None = Form(None, description="Problem metadata as JSON"),
) -> dict:
    if get_config().is_production:
        raise HTTPException(status_code=404, detail="Not found")

    metadata: Problem | None = None
    if problem:
        try:
            metadata = Problem.model_validate_json(problem)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    image_bytes = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Target images are limited to 10 MB")

    try:
        challenge = await create_challenge(image_bytes, difficulty, metadata)
    except ChallengeConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return challenge_view(challenge)


async def _load(challenge_id: str) -> dict:
    identifier = object_id(challenge_id)
    challenge = await db.challenges().find_one({"_id": identifier}) if identifier else None
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge
