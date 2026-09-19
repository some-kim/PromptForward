"""Deterministic Efficiency score. One function for both modes, no AI evaluator."""

from __future__ import annotations

BASELINE_TOKENS = 50
MAX_TOKEN_PENALTY = 15
TOKENS_PER_PENALTY_POINT = 5
MAX_EVALUATION_PENALTY = 20
EVALUATION_PENALTY_PER_FAILURE = 5
GENERATION_PENALTY = 25
QUALITY_GATE = 60


def efficiency_score(
    total_prompt_tokens: int,
    failed_evaluations: int,
    generation_count: int,
    selected_result_quality: float,
) -> float:
    token_penalty = min(
        MAX_TOKEN_PENALTY,
        max(0, total_prompt_tokens - BASELINE_TOKENS) // TOKENS_PER_PENALTY_POINT,
    )
    evaluation_penalty = min(
        MAX_EVALUATION_PENALTY, failed_evaluations * EVALUATION_PENALTY_PER_FAILURE
    )

    efficiency = 100
    efficiency -= (generation_count - 1) * GENERATION_PENALTY
    efficiency -= evaluation_penalty
    efficiency -= token_penalty
    efficiency = max(0, efficiency)

    if selected_result_quality < QUALITY_GATE:
        return 0

    return float(efficiency)
