"""Result Quality scoring from per-criterion LLM judgments."""

from __future__ import annotations

from app.models import ResultCriterionScore, ResultEvaluation, ResultEvaluationResponse, Rubric


class ResultEvaluationValidationError(ValueError):
    pass


def validate_scores(rubric: Rubric, scores: list[ResultCriterionScore]) -> None:
    expected = [criterion.id for criterion in rubric.criteria]
    received = [score.id for score in scores]
    if sorted(received) != sorted(expected) or len(set(received)) != len(received):
        raise ResultEvaluationValidationError(
            f"Expected exactly one score per rubric id {expected}, got {received}"
        )


def result_quality(rubric: Rubric, scores: list[ResultCriterionScore]) -> float:
    score_by_id = {score.id: score.score for score in scores}
    return sum(
        criterion.weight * (score_by_id[criterion.id] / 100) for criterion in rubric.criteria
    )


def score_result_evaluation(rubric: Rubric, response: ResultEvaluationResponse) -> ResultEvaluation:
    validate_scores(rubric, response.criteria)
    return ResultEvaluation(
        criteria=response.criteria,
        resultQuality=result_quality(rubric, response.criteria),
        feedback=response.feedback,
    )
