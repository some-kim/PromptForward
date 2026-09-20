"""A player's own battle images: upload, list, and drop."""

from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.serializers import challenge_summary
from app.services.dropbox.image_storage import ImageStorageError
from app.services.library import forget_image, list_images, save_image

router = APIRouter(prefix="/api/library", tags=["library"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IDENTITY_CHARS = 120


@router.get("/images")
async def get_images(userId: str = Query(..., max_length=MAX_IDENTITY_CHARS)) -> list[dict]:
    return [challenge_summary(challenge) for challenge in await list_images(userId)]


@router.post("/images", status_code=201)
async def upload_image(
    userId: str = Form(..., max_length=MAX_IDENTITY_CHARS),
    image: UploadFile = File(...),
) -> dict:
    image_bytes = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Battle images are limited to 10 MB")

    try:
        challenge = await save_image(userId, image_bytes)
    except ImageStorageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return challenge_summary(challenge)


@router.delete("/images/{challenge_id}", status_code=204)
async def delete_image(
    challenge_id: str, userId: str = Query(..., max_length=MAX_IDENTITY_CHARS)
) -> None:
    if not ObjectId.is_valid(challenge_id):
        raise HTTPException(status_code=404, detail="Image not found")
    await forget_image(userId, ObjectId(challenge_id))
