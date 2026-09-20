"""Final score (Game Mode only) and winner selection."""

from __future__ import annotations

from dataclasses import dataclass

RESULT_QUALITY_WEIGHT = 0.70
PROMPT_QUALITY_WEIGHT = 0.15
EFFICIENCY_WEIGHT = 0.15


def final_score(result_quality: float, prompt_quality: float, efficiency: float) -> float:
    return (
        result_quality * RESULT_QUALITY_WEIGHT
        + prompt_quality * PROMPT_QUALITY_WEIGHT
        + efficiency * EFFICIENCY_WEIGHT
    )


@dataclass(frozen=True)
class PlayerOutcome:
    userId: str
    finalScore: float
    resultQuality: float
    promptTokens: int


def pick_winner(players: list[PlayerOutcome]) -> str | None:
    """Highest final score wins; ties break on result quality, then fewer prompt tokens."""
    if not players:
        return None

    def rank(player: PlayerOutcome) -> tuple[float, float, int]:
        return (player.finalScore, player.resultQuality, -player.promptTokens)

    ranked = sorted(players, key=rank, reverse=True)
    if len(ranked) > 1 and rank(ranked[0]) == rank(ranked[1]):
        return None
    return ranked[0].userId
