"""Model calls the product avoided, counted from what is stored rather than a running tally.

Three things save money here: a prompt is checked (a cheap text call) before an image is
generated and a failing prompt never reaches the image model; the same prompt on the same
target is evaluated once and served from the cache afterwards; and each target image is
analysed into its rubric once, not on every attempt.
"""

from __future__ import annotations

from typing import Any

from app import db
from app.services.evaluation_cache import normalize_prompt


async def _sum(collection, expression: dict[str, Any]) -> int:
    pipeline = [{"$group": {"_id": None, "total": {"$sum": expression}}}]
    rows = await collection.aggregate(pipeline).to_list(length=1)
    return int(rows[0]["total"]) if rows else 0


async def savings(*, generation_cost: float, evaluation_cost: float) -> dict[str, Any]:
    attempts = db.attempts()
    evaluations = db.prompt_evaluations()

    prompt_checks = await _sum(attempts, {"$size": {"$ifNull": ["$promptEvaluations", []]}})
    # A failed check only saved an image call if that prompt was never generated anyway
    # (Learning mode lets a learner generate a weak prompt after seeing the verdict).
    blocked_generations = 0
    async for attempt in attempts.find(
        {"promptEvaluations": {"$elemMatch": {"passed": {"$ne": True}}}},
        {"promptEvaluations.passed": 1, "promptEvaluations.prompt": 1, "generations.prompt": 1},
    ):
        generated = {normalize_prompt(g["prompt"]) for g in attempt.get("generations", [])}
        blocked_generations += sum(
            1
            for e in attempt.get("promptEvaluations", [])
            if e.get("passed") is not True and normalize_prompt(e["prompt"]) not in generated
        )
    generations = await _sum(attempts, {"$size": {"$ifNull": ["$generations", []]}})
    cached_evaluations = await evaluations.count_documents({})
    cache_hits = await _sum(evaluations, {"$ifNull": ["$hits", 0]})
    analyzed_targets = await db.challenges().count_documents({"analysis": {"$exists": True}})

    saved = blocked_generations * generation_cost + cache_hits * evaluation_cost
    spent = generations * generation_cost + cached_evaluations * evaluation_cost
    return {
        "promptChecks": prompt_checks,
        "blockedGenerations": blocked_generations,
        "generations": generations,
        "cachedEvaluations": cached_evaluations,
        "cacheHits": cache_hits,
        "analyzedTargets": analyzed_targets,
        "assumedCosts": {"generation": generation_cost, "evaluation": evaluation_cost},
        "estimatedSavedUsd": round(saved, 2),
        "estimatedSpentUsd": round(spent, 2),
        "savedShare": round(saved / (saved + spent), 3) if saved + spent else 0.0,
    }
