"""Prompt Quality scoring. The LLM judges criteria; all math happens here."""

from __future__ import annotations

from app.models import (
    CATEGORY_HINTS,
    CoverageJudgment,
    Craftsmanship,
    PromptEvaluation,
    PromptEvaluationResponse,
    Rubric,
)

STATUS_VALUE: dict[str, float] = {"covered": 1.0, "partial": 0.5, "missing": 0.0}

CLARITY_WEIGHT = 0.30
RELEVANT_SPECIFICITY_WEIGHT = 0.30
SPATIAL_CLARITY_WEIGHT = 0.25
CONCISENESS_WEIGHT = 0.15

TARGET_COVERAGE_WEIGHT = 0.70
CRAFTSMANSHIP_WEIGHT = 0.30

PASS_THRESHOLD = 70


class PromptEvaluationValidationError(ValueError):
    pass


def validate_coverage(rubric: Rubric, judgments: list[CoverageJudgment]) -> None:
    """The response must contain exactly one entry for every rubric id and no others."""
    expected = [criterion.id for criterion in rubric.criteria]
    received = [judgment.id for judgment in judgments]
    if sorted(received) != sorted(expected) or len(set(received)) != len(received):
        raise PromptEvaluationValidationError(
            f"Expected exactly one judgment per rubric id {expected}, got {received}"
        )


def target_coverage(rubric: Rubric, judgments: list[CoverageJudgment]) -> float:
    status_by_id = {judgment.id: judgment.status for judgment in judgments}
    return sum(
        criterion.weight * STATUS_VALUE[status_by_id[criterion.id]] for criterion in rubric.criteria
    )


def craftsmanship_score(craftsmanship: Craftsmanship) -> float:
    return (
        craftsmanship.clarity * CLARITY_WEIGHT
        + craftsmanship.relevantSpecificity * RELEVANT_SPECIFICITY_WEIGHT
        + craftsmanship.spatialClarity * SPATIAL_CLARITY_WEIGHT
        + craftsmanship.conciseness * CONCISENESS_WEIGHT
    )


def prompt_quality(coverage: float, craftsmanship: float) -> float:
    return coverage * TARGET_COVERAGE_WEIGHT + craftsmanship * CRAFTSMANSHIP_WEIGHT


def passes(rubric: Rubric, quality: float, judgments: list[CoverageJudgment]) -> bool:
    status_by_id = {judgment.id: judgment.status for judgment in judgments}
    return quality >= PASS_THRESHOLD and all(
        status_by_id[criterion.id] != "missing"
        for criterion in rubric.criteria
        if criterion.critical
    )


def needs_improvement(rubric: Rubric, judgments: list[CoverageJudgment]) -> list[str]:
    """Phrase gaps by category. Never expose the rubric description; that is the answer key."""
    status_by_id = {judgment.id: judgment.status for judgment in judgments}
    hints: list[str] = []
    for criterion in rubric.criteria:
        if status_by_id[criterion.id] == "covered":
            continue
        hint = CATEGORY_HINTS[criterion.category]
        if hint not in hints:
            hints.append(hint)
    return hints


def score_prompt_evaluation(rubric: Rubric, response: PromptEvaluationResponse) -> PromptEvaluation:
    validate_coverage(rubric, response.criteria)

    coverage = target_coverage(rubric, response.criteria)
    craft = craftsmanship_score(response.craftsmanship)
    quality = prompt_quality(coverage, craft)

    return PromptEvaluation(
        criteria=response.criteria,
        craftsmanship=response.craftsmanship,
        targetCoverage=coverage,
        craftsmanshipScore=craft,
        promptQuality=quality,
        feedback=response.feedback,
        needsImprovement=needs_improvement(rubric, response.criteria),
        passed=passes(rubric, quality, response.criteria),
    )
