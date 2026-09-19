"""Generated image bytes, streamed from Dropbox."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app import db
from app.serializers import object_id
from app.services.dropbox.image_storage import download_image

router = APIRouter(prefix="/api/attempts", tags=["images"])


@router.get("/{attempt_id}/generations/{number}/image")
async def get_generated_image(attempt_id: str, number: int, userId: str = Query(...)) -> Response:
    identifier = object_id(attempt_id)
    attempt = await db.attempts().find_one({"_id": identifier}) if identifier else None
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    if attempt["userId"] != userId and not await _game_completed(attempt):
        raise HTTPException(status_code=403, detail="This image is not yours to see yet")

    generation = next((g for g in attempt["generations"] if g["number"] == number), None)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")

    image = await download_image(generation["output"]["dropboxPath"])
    return Response(content=image, media_type=generation["output"].get("mimeType", "image/png"))


async def _game_completed(attempt: dict) -> bool:
    """Opponent images stay private until the game is over."""
    if not attempt.get("gameId"):
        return False
    game = await db.games().find_one({"_id": attempt["gameId"]}, {"status": 1})
    return bool(game and game["status"] == "completed")
