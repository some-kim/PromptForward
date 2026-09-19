"""Challenge listing, metadata, target image bytes, and the dev-only upload endpoint."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app import db
from app.config import get_config
from app.serializers import challenge_summary, challenge_view, object_id
from app.services.challenges import create_challenge
from app.services.dropbox.image_storage import download_image

router = APIRouter(prefix="/api/challenges", tags=["challenges"])


@router.get("")
async def list_challenges() -> list[dict]:
    cursor = db.challenges().find({}, {"target": 1, "type": 1})
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
async def upload_challenge(image: UploadFile = File(...)) -> dict:
    if get_config().is_production:
        raise HTTPException(status_code=404, detail="Not found")
    challenge = await create_challenge(await image.read())
    return challenge_view(challenge)


async def _load(challenge_id: str) -> dict:
    identifier = object_id(challenge_id)
    challenge = await db.challenges().find_one({"_id": identifier}) if identifier else None
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge
