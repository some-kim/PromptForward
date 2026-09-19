"""Client-facing views of stored documents. The rubric is never serialized: it is the answer key."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.services.attempts import resource_usage


def object_id(value: str) -> ObjectId | None:
    return ObjectId(value) if ObjectId.is_valid(value) else None


def challenge_summary(challenge: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(challenge["_id"])
    return {
        "id": challenge_id,
        "type": challenge["type"],
        "imageUrl": f"/api/challenges/{challenge_id}/image",
    }


def challenge_view(challenge: dict[str, Any]) -> dict[str, Any]:
    target = challenge["target"]
    return {
        **challenge_summary(challenge),
        "width": target["width"],
        "height": target["height"],
    }


def generation_view(attempt_id: str, generation: dict[str, Any]) -> dict[str, Any]:
    result_evaluation = generation.get("resultEvaluation") or {}
    prompt_evaluation = generation.get("promptEvaluation") or {}
    return {
        "number": generation["number"],
        "prompt": generation["prompt"],
        "imageUrl": f"/api/attempts/{attempt_id}/generations/{generation['number']}/image",
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


def attempt_view(attempt: dict[str, Any]) -> dict[str, Any]:
    attempt_id = str(attempt["_id"])
    evaluations = attempt.get("promptEvaluations", [])
    return {
        "id": attempt_id,
        "challengeId": str(attempt["challengeId"]),
        "gameId": str(attempt["gameId"]) if attempt.get("gameId") else None,
        "userId": attempt["userId"],
        "displayName": attempt.get("displayName"),
        "mode": attempt["mode"],
        "status": attempt["status"],
        "latestEvaluation": prompt_evaluation_view(evaluations[-1]) if evaluations else None,
        "generations": [generation_view(attempt_id, g) for g in attempt.get("generations", [])],
        "generationsRemaining": _generations_remaining(attempt),
        "selectedGeneration": attempt.get("selectedGeneration"),
        "scores": attempt.get("scores"),
        "usage": resource_usage(attempt),
    }


def opponent_view(attempt: dict[str, Any], *, reveal: bool) -> dict[str, Any]:
    if reveal:
        return attempt_view(attempt)
    return {
        "id": str(attempt["_id"]),
        "userId": attempt["userId"],
        "displayName": attempt.get("displayName"),
        "status": attempt["status"],
    }


def game_view(
    game: dict[str, Any], attempts_by_id: dict[str, dict[str, Any]], viewer_id: str
) -> dict[str, Any]:
    completed = game["status"] == "completed"
    players = []
    for player in game["players"]:
        attempt = attempts_by_id.get(str(player["attemptId"]))
        if attempt is None:
            continue
        reveal = completed or player["userId"] == viewer_id
        players.append(
            {
                "userId": player["userId"],
                "displayName": player["displayName"],
                "attempt": opponent_view(attempt, reveal=reveal),
            }
        )

    return {
        "id": str(game["_id"]),
        "challengeId": str(game["challengeId"]),
        "status": game["status"],
        "winnerUserId": game.get("winnerUserId"),
        "players": players,
    }


def _generations_remaining(attempt: dict[str, Any]) -> int:
    limit = 3 if attempt["mode"] == "learning" else 1
    return max(0, limit - attempt.get("reservedGenerations", 0))
