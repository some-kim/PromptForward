"""Validation and normalization of Challenge Analyzer output."""

from __future__ import annotations

from app.models import ChallengeAnalysis, Rubric, RubricCriterion

MIN_CRITERIA = 4
MAX_CRITERIA = 8
MIN_CRITICAL = 1
MAX_CRITICAL = 4
TOTAL_WEIGHT = 100


class RubricValidationError(ValueError):
    pass


def validate_and_normalize_rubric(analysis: ChallengeAnalysis) -> Rubric:
    """Validate analyzer output, assign ids, and normalize weights to sum to 100."""
    criteria = analysis.criteria
    if not MIN_CRITERIA <= len(criteria) <= MAX_CRITERIA:
        raise RubricValidationError(
            f"Expected {MIN_CRITERIA} to {MAX_CRITERIA} criteria, got {len(criteria)}"
        )

    critical_count = sum(1 for c in criteria if c.critical)
    if not MIN_CRITICAL <= critical_count <= MAX_CRITICAL:
        raise RubricValidationError(
            f"Expected {MIN_CRITICAL} to {MAX_CRITICAL} critical criteria, got {critical_count}"
        )

    if any(c.weight <= 0 for c in criteria):
        raise RubricValidationError("Every weight must be a positive integer")

    weights = _normalize_weights([c.weight for c in criteria])

    return Rubric(
        criteria=[
            RubricCriterion(
                id=f"criterion_{index + 1}",
                category=criterion.category,
                description=criterion.description,
                weight=weight,
                critical=criterion.critical,
                region=criterion.region,
            )
            for index, (criterion, weight) in enumerate(zip(criteria, weights, strict=True))
        ]
    )


def _normalize_weights(weights: list[int]) -> list[int]:
    """Scale proportionally, round, then add any remainder to the largest weight."""
    total = sum(weights)
    scaled = [max(1, round(weight * TOTAL_WEIGHT / total)) for weight in weights]

    remainder = TOTAL_WEIGHT - sum(scaled)
    if remainder:
        largest = max(range(len(scaled)), key=lambda i: (scaled[i], -i))
        scaled[largest] += remainder
        if scaled[largest] <= 0:
            raise RubricValidationError("Weights cannot be normalized to sum to 100")

    return scaled
