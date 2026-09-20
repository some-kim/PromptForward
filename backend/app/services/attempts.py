"""Attempt lifecycle shared by Learning Mode and Game Mode."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app import db
from app.models import PromptEvaluation, ResultEvaluation, Scores
from app.services.challenges import rubric_of
from app.services.dropbox.image_storage import download_image, store_generated_image
from app.services.meta.image_generator import closest_aspect_ratio, generate_image
from app.services.openai.result_evaluator import evaluate_result
from app.services.scoring.efficiency_score import efficiency_score
from app.services.scoring.final_score import final_score
from app.services.scoring.token_counter import count_prompt_tokens

LEARNING_GENERATION_LIMIT = 3
GAME_GENERATION_LIMIT = 1


class GenerationLimitReached(RuntimeError):
    pass


class GenerationFailed(RuntimeError):
    """Any failure that must refund the reserved slot."""


def now() -> datetime:
    return datetime.now(timezone.utc)


async def create_attempt(
    *,
    challenge_id: ObjectId,
    user_id: str,
    display_name: str | None,
    mode: str,
    game_id: ObjectId | None = None,
    account_id: ObjectId | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "challengeId": challenge_id,
        "gameId": game_id,
        "userId": user_id,
        # The signed-in account that opened the attempt, fixed at creation from the bearer token.
        "accountId": account_id,
        "displayName": display_name,
        "mode": mode,
        "status": "in_progress",
        # Capability token for this attempt's generated images: only handed to clients that are
        # already allowed to see them, which keeps image URLs private without a login.
        "imageToken": secrets.token_urlsafe(24),
        "promptEvaluations": [],
        "generations": [],
        "reservedGenerations": 0,
        "generationSequence": 0,
        "consumedEvaluationId": None,
        "selectedGeneration": None,
        "scores": Scores().model_dump(),
        "createdAt": now(),
    }
    result = await db.attempts().insert_one(doc)
    return {**doc, "_id": result.inserted_id}


async def record_prompt_evaluation(
    attempt_id: ObjectId, prompt: str, evaluation: PromptEvaluation
) -> None:
    """Store the evaluation and the gate state the server checks before generating."""
    entry = {
        "prompt": prompt,
        "promptTokens": count_prompt_tokens(prompt),
        **evaluation.model_dump(),
        "createdAt": now(),
    }
    await db.attempts().update_one(
        {"_id": attempt_id},
        {
            "$push": {"promptEvaluations": entry},
            "$set": {
                "lastEvaluation": {
                    "id": uuid.uuid4().hex,
                    "prompt": prompt,
                    "passed": evaluation.passed,
                }
            },
        },
    )


async def reserve_generation(attempt_id: ObjectId, *, limit: int, gate_prompt: str | None) -> int:
    """Atomically reserve a generation slot. Returns the generation number.

    `gate_prompt` enforces the Learning Mode server-side gate inside the same update: the most
    recent evaluation must have passed, must be for exactly this prompt, and must not already
    have been consumed by an earlier generation.

    The returned number comes from `generationSequence`, which only ever grows, so a refunded
    slot never reissues a number that an in-flight generation is already writing to.
    """
    query: dict[str, Any] = {"_id": attempt_id, "reservedGenerations": {"$lt": limit}}
    update: list[dict[str, Any]] = [
        {
            "$set": {
                "reservedGenerations": {"$add": ["$reservedGenerations", 1]},
                "generationSequence": {"$add": [{"$ifNull": ["$generationSequence", 0]}, 1]},
            }
        }
    ]
    if gate_prompt is not None:
        query["lastEvaluation.passed"] = True
        query["lastEvaluation.prompt"] = gate_prompt
        query["$expr"] = {"$ne": ["$lastEvaluation.id", "$consumedEvaluationId"]}
        update[0]["$set"]["consumedEvaluationId"] = "$lastEvaluation.id"

    updated = await db.attempts().find_one_and_update(query, update, return_document=True)
    if updated is None:
        raise GenerationLimitReached(
            "No generation slot available for this attempt, or the prompt has no unused "
            "passing evaluation"
        )
    return int(updated["generationSequence"])


async def release_generation(attempt_id: ObjectId, generation_number: int) -> None:
    """A failed generation never consumes a slot.

    The refund is conditional on that generation never being appended, so a request cancelled
    just after the image was committed keeps its slot instead of handing out a free extra one.
    """
    await db.attempts().update_one(
        {"_id": attempt_id, "generations.number": {"$ne": generation_number}},
        {"$inc": {"reservedGenerations": -1}},
    )


# Detached refunds keep a strong reference until they finish, or the loop may collect them.
_REFUNDS: set[asyncio.Task[None]] = set()


def release_generation_detached(attempt_id: ObjectId, generation_number: int) -> None:
    """Refund a slot from a task that is already cancelled, where awaiting is not an option."""
    task = asyncio.create_task(release_generation(attempt_id, generation_number))
    _REFUNDS.add(task)
    task.add_done_callback(_REFUNDS.discard)


async def run_generation(
    *,
    attempt: dict[str, Any],
    challenge: dict[str, Any],
    prompt: str,
    generation_number: int,
    prompt_evaluation: PromptEvaluation | None,
) -> dict[str, Any]:
    """Generate the image, store it, evaluate the result, and append the generation.

    Every provider failure surfaces as `GenerationFailed` so callers have a single exception to
    catch when refunding the reserved slot.
    """
    rubric = rubric_of(challenge)
    target = challenge["target"]

    try:
        generated = await generate_image(
            prompt, closest_aspect_ratio(target["width"], target["height"])
        )
        stored = await store_generated_image(
            str(attempt["_id"]), generation_number, generated.imageBytes, generated.mimeType
        )

        target_bytes = await download_image(target["dropboxPath"])
        result_evaluation: ResultEvaluation = await evaluate_result(
            rubric,
            target_bytes,
            target["mimeType"],
            generated.imageBytes,
            generated.mimeType,
        )
    except Exception as error:
        raise GenerationFailed(str(error)) from error

    generation: dict[str, Any] = {
        "number": generation_number,
        "prompt": prompt,
        "promptEvaluation": prompt_evaluation.model_dump() if prompt_evaluation else None,
        "usage": {"promptTokens": count_prompt_tokens(prompt)},
        "output": {
            "type": "image",
            "dropboxPath": stored.path,
            "mimeType": generated.mimeType,
            "provider": generated.provider,
            "model": generated.model,
            "generationTimeMs": generated.generationTimeMs,
        },
        "resultEvaluation": result_evaluation.model_dump(),
        "createdAt": now(),
    }

    try:
        await db.attempts().update_one(
            {"_id": attempt["_id"]}, {"$push": {"generations": generation}}
        )
    except Exception as error:
        raise GenerationFailed(str(error)) from error
    return generation


def select_generation(generations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Highest Result Quality wins; ties go to the earlier generation."""
    scored = [g for g in generations if g.get("resultEvaluation")]
    if not scored:
        return None
    return max(scored, key=lambda g: (g["resultEvaluation"]["resultQuality"], -g["number"]))


def score_attempt(
    attempt: dict[str, Any], generations: list[dict[str, Any]]
) -> tuple[Scores, int | None]:
    selected = select_generation(generations)
    if selected is None:
        return Scores(), None

    result_quality = selected["resultEvaluation"]["resultQuality"]
    prompt_quality = (selected.get("promptEvaluation") or {}).get("promptQuality")
    if prompt_quality is None:
        prompt_quality = _latest_prompt_quality(attempt, selected["prompt"])

    total_tokens = sum(g["usage"]["promptTokens"] for g in generations)
    failed_evaluations = sum(
        1 for e in attempt.get("promptEvaluations", []) if not e.get("passed", False)
    )

    efficiency = efficiency_score(
        total_prompt_tokens=total_tokens,
        failed_evaluations=failed_evaluations if attempt["mode"] == "learning" else 0,
        generation_count=len(generations),
        selected_result_quality=result_quality,
    )

    scores = Scores(
        resultQuality=result_quality,
        promptQuality=prompt_quality,
        efficiency=efficiency,
        final=final_score(result_quality, prompt_quality or 0, efficiency),
    )
    return scores, selected["number"]


def _latest_prompt_quality(attempt: dict[str, Any], prompt: str) -> float | None:
    for evaluation in reversed(attempt.get("promptEvaluations", [])):
        if evaluation["prompt"] == prompt:
            return evaluation["promptQuality"]
    return None


async def submit_attempt(attempt_id: ObjectId) -> dict[str, Any]:
    """Score the attempt and persist it, never letting a stale snapshot win.

    Overlapping Learning generations can finalize at once, so the write only applies while the
    attempt still holds exactly the generations the scores were computed from; otherwise the
    newer generation set is re-scored.
    """
    while True:
        attempt = await db.attempts().find_one({"_id": attempt_id})
        generations = attempt.get("generations", [])
        scores, selected = score_attempt(attempt, generations)
        updated = await db.attempts().find_one_and_update(
            {"_id": attempt_id, "generations": {"$size": len(generations)}},
            {
                "$set": {
                    "status": "submitted",
                    "scores": scores.model_dump(),
                    "selectedGeneration": selected,
                }
            },
            return_document=True,
        )
        if updated is not None:
            return updated


def resource_usage(attempt: dict[str, Any]) -> dict[str, int]:
    return {
        "promptTokens": sum(g["usage"]["promptTokens"] for g in attempt.get("generations", [])),
        "promptEvaluations": len(attempt.get("promptEvaluations", [])),
        "generations": len(attempt.get("generations", [])),
    }
