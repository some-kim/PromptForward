"""Reuse prompt evaluations: the same prompt on the same target always gets the same score.

The evaluator is deterministic in what it is asked to do but not in what it returns, so
learners who resubmit a prompt would otherwise see the score drift by a point or two and pay
for a model call each time. The cache key is the challenge, its target image and analysis
version (a new rubric invalidates old scores), the evaluator model, and the prompt with
whitespace normalised. Concurrent misses all return whichever evaluation was stored first.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from app import db
from app.config import get_config
from app.models import PromptEvaluation
from app.services.challenges import rubric_of
from app.services.openai.prompt_evaluator import evaluate_prompt


def normalize_prompt(prompt: str) -> str:
    return " ".join(prompt.split())


def cache_key(challenge: dict[str, Any], prompt: str) -> str:
    parts = [
        str(challenge["_id"]),
        str(challenge["target"]["imageHash"]),
        str(challenge.get("analysis", {}).get("version")),
        get_config().openai.prompt_evaluator_model,
        normalize_prompt(prompt),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


async def evaluate_prompt_cached(challenge: dict[str, Any], prompt: str) -> PromptEvaluation:
    key = cache_key(challenge, prompt)
    cached = await db.prompt_evaluations().find_one_and_update({"_id": key}, {"$inc": {"hits": 1}})
    if cached is not None:
        return PromptEvaluation.model_validate(cached["evaluation"])

    evaluation = await evaluate_prompt(rubric_of(challenge), prompt)
    challenge_id: ObjectId = challenge["_id"]
    stored = await db.prompt_evaluations().find_one_and_update(
        {"_id": key},
        {
            "$setOnInsert": {
                "challengeId": challenge_id,
                "prompt": normalize_prompt(prompt),
                "evaluation": evaluation.model_dump(),
                "hits": 0,
                "createdAt": datetime.now(timezone.utc),
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return PromptEvaluation.model_validate(stored["evaluation"])
