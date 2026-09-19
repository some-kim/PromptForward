"""Unit tests for services/scoring, using the worked examples from docs/MVP_SPEC.md."""

from __future__ import annotations

import pytest

from app.models import (
    AnalyzedCriterion,
    ChallengeAnalysis,
    CoverageJudgment,
    Craftsmanship,
    PromptEvaluationResponse,
    ResultCriterionScore,
    ResultEvaluationResponse,
    Rubric,
    RubricCriterion,
)
from app.services.scoring.efficiency_score import efficiency_score
from app.services.scoring.final_score import PlayerOutcome, final_score, pick_winner
from app.services.scoring.prompt_score import (
    PromptEvaluationValidationError,
    craftsmanship_score,
    needs_improvement,
    passes,
    prompt_quality,
    score_prompt_evaluation,
    target_coverage,
)
from app.services.scoring.result_score import (
    ResultEvaluationValidationError,
    result_quality,
    score_result_evaluation,
)
from app.services.scoring.rubric import RubricValidationError, validate_and_normalize_rubric
from app.services.scoring.token_counter import count_prompt_tokens

EXAMPLE_RUBRIC = Rubric(
    criteria=[
        RubricCriterion(
            id="criterion_1",
            category="subject",
            description="yellow umbrella",
            weight=20,
            critical=True,
        ),
        RubricCriterion(
            id="criterion_2",
            category="composition",
            description="umbrella positioned near the center",
            weight=15,
            critical=True,
        ),
        RubricCriterion(
            id="criterion_3",
            category="environment",
            description="rainy city street at night",
            weight=20,
            critical=True,
        ),
        RubricCriterion(
            id="criterion_4",
            category="color",
            description="blue reflections on wet pavement",
            weight=15,
            critical=False,
        ),
        RubricCriterion(
            id="criterion_5",
            category="subject",
            description="multiple surrounding pedestrians",
            weight=15,
            critical=False,
        ),
        RubricCriterion(
            id="criterion_6",
            category="style",
            description="realistic photography",
            weight=15,
            critical=False,
        ),
    ]
)


def analyzed(weight: int, critical: bool = False, category: str = "subject") -> AnalyzedCriterion:
    return AnalyzedCriterion(
        category=category, description="something", weight=weight, critical=critical
    )


class TestRubricNormalization:
    def test_weights_are_normalized_to_100(self):
        analysis = ChallengeAnalysis(
            criteria=[analyzed(10, True), analyzed(10), analyzed(10), analyzed(10)]
        )
        rubric = validate_and_normalize_rubric(analysis)
        assert sum(c.weight for c in rubric.criteria) == 100
        assert [c.id for c in rubric.criteria] == [f"criterion_{i}" for i in range(1, 5)]

    def test_remainder_goes_to_largest_weight(self):
        analysis = ChallengeAnalysis(
            criteria=[analyzed(1, True), analyzed(1), analyzed(1), analyzed(7)]
        )
        rubric = validate_and_normalize_rubric(analysis)
        assert sum(c.weight for c in rubric.criteria) == 100
        assert max(c.weight for c in rubric.criteria) == rubric.criteria[3].weight

    def test_rejects_too_few_criteria(self):
        with pytest.raises(RubricValidationError):
            validate_and_normalize_rubric(
                ChallengeAnalysis(criteria=[analyzed(50, True), analyzed(50)])
            )

    def test_rejects_too_many_criteria(self):
        with pytest.raises(RubricValidationError):
            validate_and_normalize_rubric(
                ChallengeAnalysis(criteria=[analyzed(10, i == 0) for i in range(9)])
            )

    def test_rejects_no_critical_criteria(self):
        with pytest.raises(RubricValidationError):
            validate_and_normalize_rubric(
                ChallengeAnalysis(criteria=[analyzed(10) for _ in range(4)])
            )

    def test_rejects_too_many_critical_criteria(self):
        with pytest.raises(RubricValidationError):
            validate_and_normalize_rubric(
                ChallengeAnalysis(criteria=[analyzed(10, True) for _ in range(5)])
            )

    def test_rejects_non_positive_weight(self):
        with pytest.raises(RubricValidationError):
            validate_and_normalize_rubric(
                ChallengeAnalysis(
                    criteria=[analyzed(0, True), analyzed(10), analyzed(10), analyzed(10)]
                )
            )


class TestPromptScore:
    def test_target_coverage_uses_status_values(self):
        judgments = [
            CoverageJudgment(id="criterion_1", status="covered"),
            CoverageJudgment(id="criterion_2", status="partial"),
            CoverageJudgment(id="criterion_3", status="covered"),
            CoverageJudgment(id="criterion_4", status="missing"),
            CoverageJudgment(id="criterion_5", status="covered"),
            CoverageJudgment(id="criterion_6", status="covered"),
        ]
        # 20 + 7.5 + 20 + 0 + 15 + 15
        assert target_coverage(EXAMPLE_RUBRIC, judgments) == pytest.approx(77.5)

    def test_craftsmanship_weighting(self):
        craft = Craftsmanship(clarity=90, relevantSpecificity=84, spatialClarity=80, conciseness=92)
        # 27 + 25.2 + 20 + 13.8
        assert craftsmanship_score(craft) == pytest.approx(86.0)

    def test_prompt_quality_weighting(self):
        assert prompt_quality(82, 86) == pytest.approx(83.2)

    def test_passing_requires_threshold_and_no_missing_critical(self):
        all_covered = [CoverageJudgment(id=c.id, status="covered") for c in EXAMPLE_RUBRIC.criteria]
        assert passes(EXAMPLE_RUBRIC, 84, all_covered)
        assert not passes(EXAMPLE_RUBRIC, 64, all_covered)

        missing_critical = [
            CoverageJudgment(id=c.id, status="missing" if c.id == "criterion_2" else "covered")
            for c in EXAMPLE_RUBRIC.criteria
        ]
        assert not passes(EXAMPLE_RUBRIC, 95, missing_critical)

        missing_non_critical = [
            CoverageJudgment(id=c.id, status="missing" if c.id == "criterion_4" else "covered")
            for c in EXAMPLE_RUBRIC.criteria
        ]
        assert passes(EXAMPLE_RUBRIC, 85, missing_non_critical)

    def test_needs_improvement_is_phrased_by_category(self):
        judgments = [
            CoverageJudgment(id="criterion_1", status="covered"),
            CoverageJudgment(id="criterion_2", status="missing"),
            CoverageJudgment(id="criterion_3", status="covered"),
            CoverageJudgment(id="criterion_4", status="partial"),
            CoverageJudgment(id="criterion_5", status="covered"),
            CoverageJudgment(id="criterion_6", status="covered"),
        ]
        hints = needs_improvement(EXAMPLE_RUBRIC, judgments)
        assert hints == [
            "Describe where the main subject appears",
            "Mention the colors that matter",
        ]
        for criterion in EXAMPLE_RUBRIC.criteria:
            assert criterion.description not in " ".join(hints)

    def test_rejects_missing_or_extra_criteria(self):
        response = PromptEvaluationResponse(
            criteria=[CoverageJudgment(id="criterion_1", status="covered")],
            craftsmanship=Craftsmanship(
                clarity=90, relevantSpecificity=90, spatialClarity=90, conciseness=90
            ),
            feedback="...",
        )
        with pytest.raises(PromptEvaluationValidationError):
            score_prompt_evaluation(EXAMPLE_RUBRIC, response)

    def test_score_prompt_evaluation_end_to_end(self):
        response = PromptEvaluationResponse(
            criteria=[CoverageJudgment(id=c.id, status="covered") for c in EXAMPLE_RUBRIC.criteria],
            craftsmanship=Craftsmanship(
                clarity=90, relevantSpecificity=84, spatialClarity=80, conciseness=92
            ),
            feedback="Good coverage.",
        )
        evaluation = score_prompt_evaluation(EXAMPLE_RUBRIC, response)
        assert evaluation.targetCoverage == pytest.approx(100.0)
        assert evaluation.craftsmanshipScore == pytest.approx(86.0)
        assert evaluation.promptQuality == pytest.approx(95.8)
        assert evaluation.passed
        assert evaluation.needsImprovement == []


class TestResultScore:
    def test_result_quality_from_spec_example(self):
        scores = [
            ResultCriterionScore(id="criterion_1", score=100),
            ResultCriterionScore(id="criterion_2", score=85),
            ResultCriterionScore(id="criterion_3", score=90),
            ResultCriterionScore(id="criterion_4", score=70),
            ResultCriterionScore(id="criterion_5", score=80),
            ResultCriterionScore(id="criterion_6", score=95),
        ]
        # 20 + 12.75 + 18 + 10.5 + 12 + 14.25
        assert result_quality(EXAMPLE_RUBRIC, scores) == pytest.approx(87.5)

    def test_rejects_duplicate_entries(self):
        response = ResultEvaluationResponse(
            criteria=[ResultCriterionScore(id="criterion_1", score=100)] * 6,
            feedback="...",
        )
        with pytest.raises(ResultEvaluationValidationError):
            score_result_evaluation(EXAMPLE_RUBRIC, response)


class TestEfficiencyScore:
    def test_learning_mode_example_from_spec(self):
        # 2 generations -> -25, 1 failed evaluation -> -5, 165 tokens -> -15
        assert efficiency_score(
            total_prompt_tokens=165,
            failed_evaluations=1,
            generation_count=2,
            selected_result_quality=92,
        ) == pytest.approx(55)

    def test_game_mode_examples_from_spec(self):
        assert efficiency_score(74, 0, 1, 91) == pytest.approx(96)
        assert efficiency_score(43, 0, 1, 89) == pytest.approx(100)

    def test_token_penalty_is_capped(self):
        assert efficiency_score(10_000, 0, 1, 90) == pytest.approx(85)

    def test_evaluation_penalty_is_capped(self):
        assert efficiency_score(50, 10, 1, 90) == pytest.approx(80)

    def test_penalties_stack_and_clamp_at_zero(self):
        # 100 - 50 (2 extra generations) - 20 (evaluations) - 15 (tokens)
        assert efficiency_score(10_000, 10, 3, 90) == pytest.approx(15)
        assert efficiency_score(10_000, 10, 5, 90) == 0

    def test_quality_gate_zeroes_the_score(self):
        assert efficiency_score(10, 0, 1, 59.9) == 0
        assert efficiency_score(10, 0, 1, 60) == pytest.approx(100)


class TestFinalScore:
    def test_spec_game_examples(self):
        assert final_score(91, 86, 96) == pytest.approx(91.0)
        assert final_score(89, 80, 100) == pytest.approx(89.3)

    def test_winner_is_highest_final_score(self):
        players = [
            PlayerOutcome("p1", finalScore=91.0, resultQuality=91, promptTokens=74),
            PlayerOutcome("p2", finalScore=89.3, resultQuality=89, promptTokens=43),
        ]
        assert pick_winner(players) == "p1"

    def test_tie_breaks_on_result_quality_then_tokens(self):
        players = [
            PlayerOutcome("p1", finalScore=90.0, resultQuality=88, promptTokens=40),
            PlayerOutcome("p2", finalScore=90.0, resultQuality=91, promptTokens=80),
        ]
        assert pick_winner(players) == "p2"

        players = [
            PlayerOutcome("p1", finalScore=90.0, resultQuality=90, promptTokens=40),
            PlayerOutcome("p2", finalScore=90.0, resultQuality=90, promptTokens=80),
        ]
        assert pick_winner(players) == "p1"

    def test_full_tie_is_a_draw(self):
        players = [
            PlayerOutcome("p1", finalScore=90.0, resultQuality=90, promptTokens=50),
            PlayerOutcome("p2", finalScore=90.0, resultQuality=90, promptTokens=50),
        ]
        assert pick_winner(players) is None


class TestTokenCounter:
    def test_counts_prompt_text_only(self):
        assert count_prompt_tokens("") == 0
        assert count_prompt_tokens("A yellow umbrella in the rain") > 0

    def test_longer_prompts_cost_more_tokens(self):
        short = count_prompt_tokens("A yellow umbrella")
        long = count_prompt_tokens(
            "A realistic nighttime photograph of a yellow umbrella centered on a rainy city street"
        )
        assert long > short
