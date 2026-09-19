"""Generated image bytes, streamed from Dropbox."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app import db
from app.serializers import object_id
from app.services.dropbox.image_storage import download_image

router = APIRouter(prefix="/api/attempts", tags=["images"])


@router.get("/{attempt_id}/generations/{number}/image")
async def get_generated_image(attempt_id: str, number: int) -> Response:
    identifier = object_id(attempt_id)
    attempt = await db.attempts().find_one({"_id": identifier}) if identifier else None
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    generation = next((g for g in attempt["generations"] if g["number"] == number), None)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")

    image = await download_image(generation["output"]["dropboxPath"])
    return Response(content=image, media_type="image/png")
