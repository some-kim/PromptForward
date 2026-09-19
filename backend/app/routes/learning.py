"""Learning Mode: evaluate the prompt first, then generate behind a server-enforced gate."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.models import PromptEvaluation
from app.serializers import attempt_view, object_id, prompt_evaluation_view
from app.services.attempts import (
    LEARNING_GENERATION_LIMIT,
    GenerationFailed,
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
from app.services.scoring.token_counter import count_prompt_tokens

router = APIRouter(prefix="/api/learning", tags=["learning"])

MAX_PROMPT_CHARS = 2000


class CreateAttemptRequest(BaseModel):
    challengeId: str
    userId: str
    displayName: str | None = None


class PromptRequest(BaseModel):
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)


@router.post("/attempts", status_code=201)
async def create_learning_attempt(body: CreateAttemptRequest) -> dict:
    challenge_id = object_id(body.challengeId)
    challenge = await db.challenges().find_one({"_id": challenge_id}) if challenge_id else None
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    attempt = await create_attempt(
        challenge_id=challenge["_id"],
        user_id=body.userId,
        display_name=body.displayName,
        mode="learning",
    )
    return attempt_view(attempt)


@router.get("/attempts/{attempt_id}")
async def get_learning_attempt(attempt_id: str) -> dict:
    return attempt_view(await _load(attempt_id))


@router.post("/attempts/{attempt_id}/evaluate")
async def evaluate_learning_prompt(attempt_id: str, body: PromptRequest) -> dict:
    attempt = await _load(attempt_id)
    challenge = await db.challenges().find_one({"_id": attempt["challengeId"]})

    try:
        evaluation = await evaluate_prompt(rubric_of(challenge), body.prompt)
    except LLMResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    await record_prompt_evaluation(attempt["_id"], body.prompt, evaluation)
    return {
        **prompt_evaluation_view(
            {**evaluation.model_dump(), "promptTokens": count_prompt_tokens(body.prompt)}
        ),
        "generationsRemaining": max(
            0, LEARNING_GENERATION_LIMIT - attempt.get("reservedGenerations", 0)
        ),
    }


@router.post("/attempts/{attempt_id}/generate")
async def generate_learning_image(attempt_id: str, body: PromptRequest) -> dict:
    attempt = await _load(attempt_id)
    challenge = await db.challenges().find_one({"_id": attempt["challengeId"]})

    try:
        generation_number = await reserve_generation(
            attempt["_id"], limit=LEARNING_GENERATION_LIMIT, gate_prompt=body.prompt
        )
    except GenerationLimitReached as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    evaluations = attempt.get("promptEvaluations", [])
    prompt_evaluation = _evaluation_model(evaluations[-1]) if evaluations else None

    try:
        await run_generation(
            attempt=attempt,
            challenge=challenge,
            prompt=body.prompt,
            generation_number=generation_number,
            prompt_evaluation=prompt_evaluation,
        )
    except GenerationFailed as error:
        await release_generation(attempt["_id"])
        raise HTTPException(status_code=502, detail=str(error)) from error

    return attempt_view(await submit_attempt(attempt["_id"]))


def _evaluation_model(entry: dict) -> PromptEvaluation:
    return PromptEvaluation.model_validate(
        {
            key: value
            for key, value in entry.items()
            if key not in {"prompt", "promptTokens", "createdAt"}
        }
    )


async def _load(attempt_id: str) -> dict:
    identifier = object_id(attempt_id)
    attempt = (
        await db.attempts().find_one({"_id": identifier, "mode": "learning"})
        if identifier
        else None
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt
