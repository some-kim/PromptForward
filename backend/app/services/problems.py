"""The problem set: curriculum metadata on challenges, per-account progress, and coaching."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from app import db
from app.models import SKILL_INFO, SKILLS, SOLVED_SCORE, Problem
from app.services.attempts import LEARNING_GENERATION_LIMIT


def problem_of(challenge: dict[str, Any]) -> Problem | None:
    raw = challenge.get("problem")
    return Problem.model_validate(raw) if raw else None


async def progress_for(user_id: ObjectId | None) -> dict[str, dict[str, Any]]:
    """Per-challenge progress for one account, keyed by challenge id string."""
    if user_id is None:
        return {}
    cursor = db.problem_progress().find({"userId": user_id})
    return {str(entry["challengeId"]): entry async for entry in cursor}


async def record_problem_result(
    user_id: ObjectId, attempt: dict[str, Any], score: float, *, first_report: bool
) -> None:
    """Folds one scored attempt into the account's record for that problem.

    The attempt count only moves on the first report of an attempt; a retry that raises the
    score only raises the best.
    """
    challenge_id = attempt["challengeId"]
    update: dict[str, Any] = {
        "$max": {"bestScore": round(score)},
        "$setOnInsert": {"userId": user_id, "challengeId": challenge_id},
    }
    if first_report:
        update["$inc"] = {"attempts": 1}
    await db.problem_progress().find_one_and_update(
        {"_id": f"{user_id}:{challenge_id}"},
        update,
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


def status_of(entry: dict[str, Any] | None) -> str:
    if entry is None or int(entry.get("attempts", 0)) == 0:
        return "unsolved"
    return "solved" if int(entry.get("bestScore", 0)) >= SOLVED_SCORE else "attempted"


def problem_view(challenge: dict[str, Any], entry: dict[str, Any] | None) -> dict[str, Any]:
    problem = problem_of(challenge)
    assert problem is not None
    challenge_id = str(challenge["_id"])
    return {
        "id": challenge_id,
        "slug": problem.slug,
        "title": problem.title,
        "skill": problem.skill,
        "skillTitle": SKILL_INFO[problem.skill]["title"],
        "lesson": SKILL_INFO[problem.skill]["lesson"],
        "tests": problem.tests,
        "order": problem.order,
        "difficulty": challenge["difficulty"],
        "imageUrl": f"/api/challenges/{challenge_id}/image",
        "hintCount": len(problem.hints),
        "status": status_of(entry),
        "bestScore": int(entry["bestScore"]) if entry else None,
        "attempts": int(entry.get("attempts", 0)) if entry else 0,
    }


def skill_summary(problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for skill in SKILLS:
        mine = [problem for problem in problems if problem["skill"] == skill]
        summary.append(
            {
                "skill": skill,
                "title": SKILL_INFO[skill]["title"],
                "lesson": SKILL_INFO[skill]["lesson"],
                "total": len(mine),
                "solved": sum(1 for problem in mine if problem["status"] == "solved"),
                "attempted": sum(1 for problem in mine if problem["status"] == "attempted"),
            }
        )
    return summary


async def list_problems(user_id: ObjectId | None) -> dict[str, Any]:
    cursor = db.challenges().find(
        {"problem": {"$exists": True}},
        {"problem": 1, "difficulty": 1},
    )
    challenges = [challenge async for challenge in cursor]
    challenges.sort(key=lambda challenge: challenge["problem"]["order"])
    progress = await progress_for(user_id)
    problems = [
        problem_view(challenge, progress.get(str(challenge["_id"]))) for challenge in challenges
    ]
    return {"problems": problems, "skills": skill_summary(problems)}


def coaching_view(challenge: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any] | None:
    """What the coach may reveal for this attempt: unlocked hints, and the reference once earned.

    One hint unlocks per weak prompt. The reference prompt is the answer key, so it only appears
    after the problem is solved or every generation has been spent.
    """
    problem = problem_of(challenge)
    if problem is None:
        return None

    weak = sum(
        1 for entry in attempt.get("promptEvaluations", []) if not entry.get("passed", False)
    )
    scores = attempt.get("scores") or {}
    final = scores.get("final")
    solved = final is not None and final >= SOLVED_SCORE
    spent = attempt.get("reservedGenerations", 0) >= LEARNING_GENERATION_LIMIT
    submitted = attempt["status"] == "submitted"

    return {
        "slug": problem.slug,
        "title": problem.title,
        "skill": problem.skill,
        "skillTitle": SKILL_INFO[problem.skill]["title"],
        "lesson": SKILL_INFO[problem.skill]["lesson"],
        "tests": problem.tests,
        "hints": problem.hints[: min(weak, len(problem.hints))],
        "hintsRemaining": max(0, len(problem.hints) - weak),
        "solved": submitted and solved,
        "referencePrompt": problem.referencePrompt if submitted and (solved or spent) else None,
    }
