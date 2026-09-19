"""Attempt lifecycle shared by Learning Mode and Game Mode."""

from __future__ import annotations

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


def now() -> datetime:
    return datetime.now(timezone.utc)


async def create_attempt(
    *,
    challenge_id: ObjectId,
    user_id: str,
    display_name: str | None,
    mode: str,
    game_id: ObjectId | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "challengeId": challenge_id,
        "gameId": game_id,
        "userId": user_id,
        "displayName": display_name,
        "mode": mode,
        "status": "in_progress",
        "promptEvaluations": [],
        "generations": [],
        "reservedGenerations": 0,
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
            "$set": {"lastEvaluation": {"prompt": prompt, "passed": evaluation.passed}},
        },
    )


async def reserve_generation(attempt_id: ObjectId, *, limit: int, gate_prompt: str | None) -> int:
    """Atomically reserve a generation slot. Returns the generation number.

    `gate_prompt` enforces the Learning Mode server-side gate inside the same update: the most
    recent evaluation must have passed and must be for exactly this prompt.
    """
    query: dict[str, Any] = {"_id": attempt_id, "reservedGenerations": {"$lt": limit}}
    if gate_prompt is not None:
        query["lastEvaluation.passed"] = True
        query["lastEvaluation.prompt"] = gate_prompt

    updated = await db.attempts().find_one_and_update(
        query, {"$inc": {"reservedGenerations": 1}}, return_document=True
    )
    if updated is None:
        raise GenerationLimitReached(
            "No generation slot available for this attempt, or the prompt did not pass"
        )
    return int(updated["reservedGenerations"])


async def release_generation(attempt_id: ObjectId) -> None:
    """A failed generation never consumes a slot."""
    await db.attempts().update_one({"_id": attempt_id}, {"$inc": {"reservedGenerations": -1}})


async def run_generation(
    *,
    attempt: dict[str, Any],
    challenge: dict[str, Any],
    prompt: str,
    generation_number: int,
    prompt_evaluation: PromptEvaluation | None,
) -> dict[str, Any]:
    """Generate the image, store it, evaluate the result, and append the generation."""
    rubric = rubric_of(challenge)
    target = challenge["target"]

    generated = await generate_image(
        prompt, closest_aspect_ratio(target["width"], target["height"])
    )
    stored = await store_generated_image(
        str(attempt["_id"]), generation_number, generated.imageBytes
    )

    target_bytes = await download_image(target["dropboxPath"])
    result_evaluation: ResultEvaluation = await evaluate_result(
        rubric,
        target_bytes,
        target["mimeType"],
        generated.imageBytes,
        generated.mimeType,
    )

    generation: dict[str, Any] = {
        "number": generation_number,
        "prompt": prompt,
        "promptEvaluation": prompt_evaluation.model_dump() if prompt_evaluation else None,
        "usage": {"promptTokens": count_prompt_tokens(prompt)},
        "output": {
            "type": "image",
            "dropboxPath": stored.path,
            "provider": generated.provider,
            "model": generated.model,
            "generationTimeMs": generated.generationTimeMs,
        },
        "resultEvaluation": result_evaluation.model_dump(),
        "createdAt": now(),
    }

    await db.attempts().update_one({"_id": attempt["_id"]}, {"$push": {"generations": generation}})
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
        final=(
            final_score(result_quality, prompt_quality or 0, efficiency)
            if attempt["mode"] == "game"
            else None
        ),
    )
    return scores, selected["number"]


def _latest_prompt_quality(attempt: dict[str, Any], prompt: str) -> float | None:
    for evaluation in reversed(attempt.get("promptEvaluations", [])):
        if evaluation["prompt"] == prompt:
            return evaluation["promptQuality"]
    return None


async def submit_attempt(attempt_id: ObjectId) -> dict[str, Any]:
    attempt = await db.attempts().find_one({"_id": attempt_id})
    scores, selected = score_attempt(attempt, attempt.get("generations", []))
    await db.attempts().update_one(
        {"_id": attempt_id},
        {
            "$set": {
                "status": "submitted",
                "scores": scores.model_dump(),
                "selectedGeneration": selected,
            }
        },
    )
    return await db.attempts().find_one({"_id": attempt_id})


def resource_usage(attempt: dict[str, Any]) -> dict[str, int]:
    return {
        "promptTokens": sum(g["usage"]["promptTokens"] for g in attempt.get("generations", [])),
        "promptEvaluations": len(attempt.get("promptEvaluations", [])),
        "generations": len(attempt.get("generations", [])),
    }
