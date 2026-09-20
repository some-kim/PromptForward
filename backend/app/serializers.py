"""Client-facing views of stored documents. The rubric is never serialized: it is the answer key."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from bson import ObjectId

from app.models import CATEGORY_HINTS, DEFAULT_DIFFICULTY, CoverageJudgment, Rubric
from app.services.attempts import resource_usage


def object_id(value: str) -> ObjectId | None:
    return ObjectId(value) if ObjectId.is_valid(value) else None


def challenge_summary(challenge: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(challenge["_id"])
    return {
        "id": challenge_id,
        "type": challenge["type"],
        "difficulty": challenge.get("difficulty", DEFAULT_DIFFICULTY),
        "imageUrl": f"/api/challenges/{challenge_id}/image",
    }


def challenge_view(challenge: dict[str, Any]) -> dict[str, Any]:
    target = challenge["target"]
    return {
        **challenge_summary(challenge),
        "width": target["width"],
        "height": target["height"],
    }


def generation_view(attempt_id: str, token: str, generation: dict[str, Any]) -> dict[str, Any]:
    result_evaluation = generation.get("resultEvaluation") or {}
    prompt_evaluation = generation.get("promptEvaluation") or {}
    number = generation["number"]
    return {
        "number": number,
        "prompt": generation["prompt"],
        "imageUrl": f"/api/attempts/{attempt_id}/generations/{number}/image?token={quote(token)}",
        "promptQuality": prompt_evaluation.get("promptQuality"),
        "resultQuality": result_evaluation.get("resultQuality"),
        "resultFeedback": result_evaluation.get("feedback"),
        "promptTokens": generation["usage"]["promptTokens"],
    }


def prompt_evaluation_view(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "promptQuality": evaluation["promptQuality"],
        "targetCoverage": evaluation["targetCoverage"],
        "craftsmanship": evaluation["craftsmanshipScore"],
        "passed": evaluation["passed"],
        "feedback": evaluation["feedback"],
        "needsImprovement": evaluation["needsImprovement"],
        "promptTokens": evaluation.get("promptTokens"),
    }


def attention_view(rubric: Rubric, judgments: list[CoverageJudgment]) -> list[dict[str, Any]]:
    """Per-criterion regions of the target with how well the prompt covered them.

    Only located criteria appear, and only the category hint travels to the client: the rubric
    description is the answer key.
    """
    status_by_id = {judgment.id: judgment.status for judgment in judgments}
    return [
        {
            "id": criterion.id,
            "status": status_by_id[criterion.id],
            "category": criterion.category,
            "hint": CATEGORY_HINTS[criterion.category],
            "weight": criterion.weight,
            "region": criterion.region.model_dump(),
        }
        for criterion in rubric.criteria
        if criterion.region is not None and criterion.id in status_by_id
    ]


def attempt_view(attempt: dict[str, Any]) -> dict[str, Any]:
    attempt_id = str(attempt["_id"])
    evaluations = attempt.get("promptEvaluations", [])
    return {
        "id": attempt_id,
        "challengeId": str(attempt["challengeId"]),
        "gameId": str(attempt["gameId"]) if attempt.get("gameId") else None,
        "displayName": attempt.get("displayName"),
        "mode": attempt["mode"],
        "status": attempt["status"],
        "latestEvaluation": prompt_evaluation_view(evaluations[-1]) if evaluations else None,
        "generations": [
            generation_view(attempt_id, attempt.get("imageToken", ""), g)
            for g in attempt.get("generations", [])
        ],
        "generationsRemaining": _generations_remaining(attempt),
        "selectedGeneration": attempt.get("selectedGeneration"),
        "scores": attempt.get("scores"),
        "usage": resource_usage(attempt),
    }


def round_status(attempt: dict[str, Any]) -> str:
    """Where one image stands for one player, with nothing said about how it scored."""
    if attempt.get("generations"):
        return "ready"
    if attempt.get("lastError"):
        return "failed"
    if attempt.get("reservedGenerations", 0) > 0:
        return "working"
    return "empty"


def _round_view(
    index: int, challenge_id: Any, attempt: dict[str, Any] | None, *, reveal: bool
) -> dict[str, Any]:
    attempt = attempt or {}
    generation = (attempt.get("generations") or [None])[0]
    status = round_status(attempt) if attempt else "empty"
    view: dict[str, Any] = {
        "index": index,
        "challengeId": str(challenge_id),
        "targetImageUrl": f"/api/challenges/{challenge_id}/image",
        "status": status,
        "prompt": (generation or {}).get("prompt") or attempt.get("pendingPrompt"),
        "error": attempt.get("lastError") if status == "failed" else None,
    }
    if not reveal or not attempt:
        # Scores are the whole point of the reveal: nothing about them travels before the end,
        # not even to the player who wrote the prompt.
        return view

    scores = attempt.get("scores") or {}
    return {
        **view,
        "attemptId": str(attempt["_id"]),
        "imageUrl": (
            f"/api/attempts/{attempt['_id']}/generations/{generation['number']}/image"
            f"?token={quote(attempt.get('imageToken', ''))}"
            if generation
            else None
        ),
        "scores": {
            "final": scores.get("final") or 0,
            "resultQuality": scores.get("resultQuality") or 0,
            "promptQuality": scores.get("promptQuality") or 0,
            "efficiency": scores.get("efficiency") or 0,
        },
        "feedback": (generation or {}).get("resultEvaluation", {}).get("feedback"),
        "promptTokens": (generation or {}).get("usage", {}).get("promptTokens", 0),
    }


def battle_view(
    game: dict[str, Any],
    attempts_by_id: dict[str, dict[str, Any]],
    viewer_id: str,
    seconds_remaining: int | None,
) -> dict[str, Any]:
    completed = game["status"] == "completed"
    totals = {entry["userId"]: entry for entry in game.get("scoreboard", [])}
    per_player = game["settings"]["imagesPerPlayer"]

    players = []
    for player in game["players"]:
        # A player's id is never published: it is the only thing standing between an onlooker
        # and that player's prompts and image capability while the battle runs.
        is_you = player["userId"] == viewer_id
        rounds = [
            _round_view(
                index,
                challenge_id,
                attempts_by_id.get(str(attempt_id)),
                reveal=completed,
            )
            for index, (challenge_id, attempt_id) in enumerate(
                zip(game["challengeIds"], player["attemptIds"], strict=False)
            )
        ]
        outcome = totals.get(player["userId"], {})
        players.append(
            {
                "isYou": is_you,
                "displayName": player["displayName"],
                "imagesChosen": len(player["challengeIds"]),
                "usedDefaults": player["usedDefaults"],
                "ready": len(player["challengeIds"]) >= per_player,
                "submittedRounds": sum(1 for one in rounds if one["status"] == "ready"),
                "total": round(outcome["total"], 1) if completed and outcome else None,
                "promptTokens": outcome.get("promptTokens") if completed else None,
                "images": (
                    [
                        {
                            "challengeId": str(challenge_id),
                            "imageUrl": f"/api/challenges/{challenge_id}/image",
                        }
                        for challenge_id in player["challengeIds"]
                    ]
                    if is_you or completed
                    else []
                ),
                "rounds": rounds if is_you or completed else [],
            }
        )

    return {
        "id": str(game["_id"]),
        "code": game["code"],
        "status": game["status"],
        "settings": game["settings"],
        "totalRounds": len(game["challengeIds"]),
        "secondsRemaining": seconds_remaining,
        "winner": _winner_label(game, game.get("winnerUserId"), viewer_id),
        "players": players,
    }


def _winner_label(game: dict[str, Any], winner_id: str | None, viewer_id: str) -> str | None:
    if game["status"] != "completed":
        return None
    if winner_id is None:
        return "draw"
    return "you" if winner_id == viewer_id else "opponent"


def _generations_remaining(attempt: dict[str, Any]) -> int:
    limit = 3 if attempt["mode"] == "learning" else 1
    return max(0, limit - attempt.get("reservedGenerations", 0))
