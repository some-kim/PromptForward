"""Learning Mode: score the prompt, generate whatever it describes, score the image too."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.models import PromptEvaluation
from app.routes.auth import optional_user
from app.serializers import attempt_view, attention_view, object_id, prompt_evaluation_view
from app.services.attempts import (
    LEARNING_GENERATION_LIMIT,
    GenerationFailed,
    GenerationLimitReached,
    create_attempt,
    record_prompt_evaluation,
    release_generation,
    release_generation_detached,
    reserve_generation,
    run_generation,
    submit_attempt,
)
from app.services.challenges import rubric_of
from app.services.evaluation_cache import evaluate_prompt_cached
from app.services.openai.client import LLMResponseError
from app.services.problems import coaching_view
from app.services.scoring.token_counter import count_prompt_tokens

router = APIRouter(prefix="/api/learning", tags=["learning"])

MAX_PROMPT_CHARS = 2000
MAX_IDENTITY_CHARS = 120


class CreateAttemptRequest(BaseModel):
    challengeId: str
    userId: str = Field(max_length=MAX_IDENTITY_CHARS)
    displayName: str | None = Field(default=None, max_length=MAX_IDENTITY_CHARS)


class PromptRequest(BaseModel):
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)


@router.post("/attempts", status_code=201)
async def create_learning_attempt(
    body: CreateAttemptRequest, user: dict | None = Depends(optional_user)
) -> dict:
    challenge_id = object_id(body.challengeId)
    challenge = await db.challenges().find_one({"_id": challenge_id}) if challenge_id else None
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    attempt = await create_attempt(
        challenge_id=challenge["_id"],
        user_id=body.userId,
        display_name=body.displayName,
        mode="learning",
        account_id=user["_id"] if user else None,
    )
    return _coached_view(attempt, challenge)


@router.get("/attempts/{attempt_id}")
async def get_learning_attempt(attempt_id: str) -> dict:
    attempt = await _load(attempt_id)
    challenge = await db.challenges().find_one({"_id": attempt["challengeId"]})
    return _coached_view(attempt, challenge)


@router.post("/attempts/{attempt_id}/evaluate")
async def evaluate_learning_prompt(attempt_id: str, body: PromptRequest) -> dict:
    attempt = await _load(attempt_id)
    challenge = await db.challenges().find_one({"_id": attempt["challengeId"]})
    rubric = rubric_of(challenge)

    try:
        evaluation = await evaluate_prompt_cached(challenge, body.prompt)
    except LLMResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    await record_prompt_evaluation(attempt["_id"], body.prompt, evaluation)
    return {
        **prompt_evaluation_view(
            {**evaluation.model_dump(), "promptTokens": count_prompt_tokens(body.prompt)}
        ),
        "attention": attention_view(rubric, evaluation.criteria),
        "generationsRemaining": max(
            0, LEARNING_GENERATION_LIMIT - attempt.get("reservedGenerations", 0)
        ),
        "coaching": coaching_view(challenge, await _load(attempt_id)),
    }


@router.post("/attempts/{attempt_id}/generate")
async def generate_learning_image(attempt_id: str, body: PromptRequest) -> dict:
    attempt = await _load(attempt_id)
    challenge = await db.challenges().find_one({"_id": attempt["challengeId"]})

    if _awaiting_submission(attempt):
        # The image being finalized was made from the stored prompt, not whatever the client
        # sends with the retry.
        finalized_prompt = attempt["generations"][-1]["prompt"]
        return _generated_view(await submit_attempt(attempt["_id"]), challenge, finalized_prompt)

    # A weak prompt still generates: the lesson is seeing what it produces, and the score keeps
    # prompt quality and image quality side by side.
    try:
        generation_number = await reserve_generation(
            attempt["_id"], limit=LEARNING_GENERATION_LIMIT, gate_prompt=None
        )
    except GenerationLimitReached as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    # Everything past the reservation shares one refund boundary: a slot is only spent on an
    # image that actually landed.
    try:
        prompt_evaluation = await _evaluation_for(attempt, challenge, body.prompt)
        await run_generation(
            attempt=attempt,
            challenge=challenge,
            prompt=body.prompt,
            generation_number=generation_number,
            prompt_evaluation=prompt_evaluation,
        )
    except GenerationFailed as error:
        await release_generation(attempt["_id"], generation_number)
        raise HTTPException(status_code=502, detail=str(error)) from error
    except asyncio.CancelledError:
        # A disconnected client must not burn a generation; the refund runs detached because
        # this task is already being torn down.
        release_generation_detached(attempt["_id"], generation_number)
        raise
    except Exception:
        await release_generation(attempt["_id"], generation_number)
        raise

    return _generated_view(await submit_attempt(attempt["_id"]), challenge, body.prompt)


def _generated_view(attempt: dict, challenge: dict, prompt: str) -> dict:
    """The scored attempt plus the prompt's own evaluation, so one press shows both."""
    view = _coached_view(attempt, challenge)
    for entry in reversed(attempt.get("promptEvaluations", [])):
        if entry["prompt"] == prompt:
            evaluation = _evaluation_model(entry)
            view["promptEvaluation"] = {
                **prompt_evaluation_view(
                    {**evaluation.model_dump(), "promptTokens": count_prompt_tokens(prompt)}
                ),
                "attention": attention_view(rubric_of(challenge), evaluation.criteria),
            }
            break
    return view


def _coached_view(attempt: dict, challenge: dict) -> dict:
    return {**attempt_view(attempt), "coaching": coaching_view(challenge, attempt)}


def _awaiting_submission(attempt: dict) -> bool:
    """An image landed but its scoring never did, so the retry only has to finalize it.

    Every reservation is accounted for by a stored generation here, so nothing is still being
    generated and pressing generate again would pay for a second image of the same attempt.
    """
    generations = attempt.get("generations", [])
    return (
        bool(generations)
        and attempt["status"] != "submitted"
        and attempt.get("reservedGenerations", 0) == len(generations)
    )


async def _evaluation_for(attempt: dict, challenge: dict, prompt: str) -> PromptEvaluation:
    """The evaluation for exactly this prompt, scoring it now if the client skipped the check.

    A weak prompt is fine, an unreachable evaluator is not: an image scored against a missing
    prompt quality would read as zero, so the generation is refused instead.
    """
    for entry in reversed(attempt.get("promptEvaluations", [])):
        if entry["prompt"] == prompt:
            return _evaluation_model(entry)

    try:
        evaluation = await evaluate_prompt_cached(challenge, prompt)
    except LLMResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    await record_prompt_evaluation(attempt["_id"], prompt, evaluation)
    return evaluation


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
