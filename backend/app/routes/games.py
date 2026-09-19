"""Game Mode: two players, one generation each, prompts never blocked."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.models import PromptEvaluation
from app.serializers import game_view, object_id
from app.services.attempts import (
    GAME_GENERATION_LIMIT,
    GenerationLimitReached,
    create_attempt,
    record_prompt_evaluation,
    release_generation,
    reserve_generation,
    run_generation,
    submit_attempt,
)
from app.services.challenges import rubric_of
from app.services.openai.client import LLMResponseError
from app.services.openai.prompt_evaluator import evaluate_prompt
from app.services.scoring.final_score import PlayerOutcome, pick_winner

router = APIRouter(prefix="/api/games", tags=["games"])

MAX_PROMPT_CHARS = 2000


class CreateGameRequest(BaseModel):
    userId: str
    displayName: str
    challengeId: str | None = None


class JoinGameRequest(BaseModel):
    userId: str
    displayName: str


class GenerateRequest(BaseModel):
    userId: str
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)


@router.post("", status_code=201)
async def create_game(body: CreateGameRequest) -> dict:
    challenge = await _pick_challenge(body.challengeId)

    game_id = ObjectId()
    attempt = await create_attempt(
        challenge_id=challenge["_id"],
        user_id=body.userId,
        display_name=body.displayName,
        mode="game",
        game_id=game_id,
    )

    game = {
        "_id": game_id,
        "challengeId": challenge["_id"],
        "players": [
            {"userId": body.userId, "displayName": body.displayName, "attemptId": attempt["_id"]}
        ],
        "winnerUserId": None,
        "status": "waiting",
        "createdAt": datetime.now(timezone.utc),
        "completedAt": None,
    }
    await db.games().insert_one(game)
    return await _view(game["_id"], body.userId)


@router.post("/{game_id}/join")
async def join_game(game_id: str, body: JoinGameRequest) -> dict:
    game = await _load(game_id)
    if any(player["userId"] == body.userId for player in game["players"]):
        return await _view(game["_id"], body.userId)

    attempt = await create_attempt(
        challenge_id=game["challengeId"],
        user_id=body.userId,
        display_name=body.displayName,
        mode="game",
        game_id=game["_id"],
    )

    joined = await db.games().find_one_and_update(
        {"_id": game["_id"], "status": "waiting", "players.1": {"$exists": False}},
        {
            "$push": {
                "players": {
                    "userId": body.userId,
                    "displayName": body.displayName,
                    "attemptId": attempt["_id"],
                }
            },
            "$set": {"status": "active"},
        },
        return_document=True,
    )
    if joined is None:
        await db.attempts().delete_one({"_id": attempt["_id"]})
        raise HTTPException(status_code=409, detail="This game already has two players")

    return await _view(game["_id"], body.userId)


@router.get("/{game_id}")
async def get_game(game_id: str, userId: str = Query(...)) -> dict:
    await _load(game_id)
    return await _view(object_id(game_id), userId)


@router.post("/{game_id}/generate")
async def generate_game_image(game_id: str, body: GenerateRequest) -> dict:
    game = await _load(game_id)
    if game["status"] != "active":
        raise HTTPException(status_code=409, detail="This game is not active")

    player = next((p for p in game["players"] if p["userId"] == body.userId), None)
    if player is None:
        raise HTTPException(status_code=404, detail="Player is not in this game")

    attempt = await db.attempts().find_one({"_id": player["attemptId"]})
    challenge = await db.challenges().find_one({"_id": game["challengeId"]})

    # An earlier call whose image succeeded but whose evaluation failed only needs the evaluation:
    # the player keeps that one image instead of being handed a second generation.
    unscored = next(
        (g for g in attempt.get("generations", []) if g.get("promptEvaluation") is None), None
    )
    if unscored is not None:
        return await _score_prompt(game, attempt, challenge, unscored)

    try:
        generation_number = await reserve_generation(
            attempt["_id"], limit=GAME_GENERATION_LIMIT, gate_prompt=None
        )
    except GenerationLimitReached as error:
        raise HTTPException(
            status_code=409, detail="You have already used your generation"
        ) from error

    # The prompt never blocks generation in Game Mode, so both run at once.
    evaluation_task = asyncio.create_task(evaluate_prompt(rubric_of(challenge), body.prompt))
    generation_task = asyncio.create_task(
        run_generation(
            attempt=attempt,
            challenge=challenge,
            prompt=body.prompt,
            generation_number=generation_number,
            prompt_evaluation=None,
        )
    )
    evaluation, generated = await asyncio.gather(
        evaluation_task, generation_task, return_exceptions=True
    )

    if isinstance(generated, BaseException):
        # No image was stored, so the slot is refunded and the player may try again.
        await release_generation(attempt["_id"])
        raise HTTPException(status_code=502, detail=str(generated)) from generated

    if isinstance(evaluation, BaseException):
        # The image is committed. Keep the slot used and let a retry score the prompt only.
        raise HTTPException(status_code=502, detail=str(evaluation)) from evaluation

    return await _finish_generation(game, attempt, generation_number, body.prompt, evaluation)


async def _score_prompt(
    game: dict[str, Any],
    attempt: dict[str, Any],
    challenge: dict[str, Any],
    generation: dict[str, Any],
) -> dict:
    prompt = generation["prompt"]
    try:
        evaluation = await evaluate_prompt(rubric_of(challenge), prompt)
    except LLMResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return await _finish_generation(game, attempt, generation["number"], prompt, evaluation)


async def _finish_generation(
    game: dict[str, Any],
    attempt: dict[str, Any],
    generation_number: int,
    prompt: str,
    evaluation: PromptEvaluation,
) -> dict:
    await record_prompt_evaluation(attempt["_id"], prompt, evaluation)
    await db.attempts().update_one(
        {"_id": attempt["_id"], "generations.number": generation_number},
        {"$set": {"generations.$.promptEvaluation": evaluation.model_dump()}},
    )
    await submit_attempt(attempt["_id"])
    await _complete_if_ready(game["_id"])

    return await _view(game["_id"], attempt["userId"])


async def _pick_challenge(challenge_id: str | None) -> dict[str, Any]:
    if challenge_id:
        identifier = object_id(challenge_id)
        challenge = await db.challenges().find_one({"_id": identifier}) if identifier else None
        if challenge is None:
            raise HTTPException(status_code=404, detail="Challenge not found")
        return challenge

    sampled = await db.challenges().aggregate([{"$sample": {"size": 1}}]).to_list(1)
    if not sampled:
        raise HTTPException(status_code=409, detail="No challenges have been seeded yet")
    return sampled[0]


async def _complete_if_ready(game_id: ObjectId) -> None:
    game = await db.games().find_one({"_id": game_id})
    if game["status"] == "completed" or len(game["players"]) < 2:
        return

    attempts = await _attempts_of(game)
    if any(attempt["status"] != "submitted" for attempt in attempts.values()):
        return

    outcomes = [
        PlayerOutcome(
            userId=attempt["userId"],
            finalScore=attempt["scores"]["final"] or 0,
            resultQuality=attempt["scores"]["resultQuality"] or 0,
            promptTokens=sum(g["usage"]["promptTokens"] for g in attempt["generations"]),
        )
        for attempt in attempts.values()
    ]

    await db.games().update_one(
        {"_id": game_id, "status": "active"},
        {
            "$set": {
                "status": "completed",
                "winnerUserId": pick_winner(outcomes),
                "completedAt": datetime.now(timezone.utc),
            }
        },
    )


async def _attempts_of(game: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ids = [player["attemptId"] for player in game["players"]]
    cursor = db.attempts().find({"_id": {"$in": ids}})
    return {str(attempt["_id"]): attempt async for attempt in cursor}


async def _view(game_id: ObjectId, viewer_id: str) -> dict:
    game = await db.games().find_one({"_id": game_id})
    return game_view(game, await _attempts_of(game), viewer_id)


async def _load(game_id: str) -> dict[str, Any]:
    identifier = object_id(game_id)
    game = await db.games().find_one({"_id": identifier}) if identifier else None
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game
