"""Battle Mode routes: create or join by code, bring images, prompt against the clock."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.models import BattleSettings
from app.serializers import battle_view
from app.services.battles import (
    BattleError,
    add_image,
    attempts_of,
    create_battle,
    fill_with_defaults,
    finish_if_ready,
    join_battle,
    load_battle,
    remove_image,
    seconds_remaining,
    submit_round,
)
from app.services.library import owns_image

router = APIRouter(prefix="/api/games", tags=["games"])

MAX_PROMPT_CHARS = 2000
MAX_IDENTITY_CHARS = 120
MAX_CODE_CHARS = 12


class CreateGameRequest(BaseModel):
    userId: str = Field(max_length=MAX_IDENTITY_CHARS)
    displayName: str = Field(max_length=MAX_IDENTITY_CHARS)
    settings: BattleSettings = BattleSettings()
    # A quick battle fills the host's side from the curated pool right away.
    useDefaultImages: bool = False


class JoinGameRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)
    userId: str = Field(max_length=MAX_IDENTITY_CHARS)
    displayName: str = Field(max_length=MAX_IDENTITY_CHARS)


class PlayerRequest(BaseModel):
    userId: str = Field(max_length=MAX_IDENTITY_CHARS)


class ImageRequest(PlayerRequest):
    challengeId: str = Field(max_length=64)


class PromptRequest(PlayerRequest):
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)


@router.post("", status_code=201)
async def create_game(body: CreateGameRequest) -> dict:
    game = await _guard(
        create_battle(
            user_id=body.userId,
            display_name=body.displayName,
            settings=body.settings,
            use_defaults=body.useDefaultImages,
        )
    )
    return await _view(game, body.userId)


@router.post("/join")
async def join_game(body: JoinGameRequest) -> dict:
    game = await _guard(
        join_battle(code=body.code, user_id=body.userId, display_name=body.displayName)
    )
    return await _view(game, body.userId)


@router.get("/{game_id}")
async def get_game(game_id: str, userId: str = Query(...)) -> dict:
    game = await _guard(load_battle(game_id))
    # Polling is what notices the buzzer: a battle nobody returns to still ends on its own once
    # someone looks at it.
    if game["status"] == "active":
        game = await finish_if_ready(game["_id"])
    return await _view(game, userId)


@router.post("/{game_id}/images")
async def add_game_image(game_id: str, body: ImageRequest) -> dict:
    game = await _guard(load_battle(game_id))
    challenge_id = _object_id(body.challengeId)
    if not await owns_image(body.userId, challenge_id):
        raise HTTPException(status_code=403, detail="That image is not in your library")

    return await _view(await _guard(add_image(game, body.userId, challenge_id)), body.userId)


@router.delete("/{game_id}/images/{challenge_id}")
async def remove_game_image(game_id: str, challenge_id: str, userId: str = Query(...)) -> dict:
    game = await _guard(load_battle(game_id))
    updated = await _guard(remove_image(game, userId, _object_id(challenge_id)))
    return await _view(updated, userId)


@router.post("/{game_id}/default-images")
async def use_default_images(game_id: str, body: PlayerRequest) -> dict:
    game = await _guard(load_battle(game_id))
    return await _view(await _guard(fill_with_defaults(game, body.userId)), body.userId)


@router.post("/{game_id}/rounds/{index}/prompt")
async def prompt_round(game_id: str, index: int, body: PromptRequest) -> dict:
    game = await _guard(load_battle(game_id))
    updated = await _guard(submit_round(game, body.userId, index, body.prompt))
    return await _view(updated, body.userId)


def _object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=404, detail="Image not found")
    return ObjectId(value)


async def _guard(awaitable: Any) -> dict[str, Any]:
    try:
        return await awaitable
    except BattleError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


async def _view(game: dict[str, Any], viewer_id: str) -> dict:
    fresh = await db.games().find_one({"_id": game["_id"]})
    return battle_view(fresh, await attempts_of(fresh), viewer_id, seconds_remaining(fresh))
