"""Prompt Evaluator: judges rubric coverage and craftsmanship. It never sees the target image."""

from __future__ import annotations

import json

from app.config import get_config
from app.models import PromptEvaluation, PromptEvaluationResponse, Rubric
from app.services.openai.client import parse_structured
from app.services.scoring.prompt_score import score_prompt_evaluation, validate_coverage

SYSTEM_PROMPT = """\
You evaluate how well a user's image-generation prompt would recreate a target image you cannot \
see. You are given the rubric describing the target.

For every rubric criterion, return exactly one status:
- covered: the prompt communicates this characteristic
- partial: the prompt gestures at it but leaves it ambiguous
- missing: the prompt does not communicate it

Then rate the prompt itself from 0 to 100 on clarity, relevantSpecificity, spatialClarity, and \
conciseness. Reward useful visual information; do not reward filler words such as "masterpiece", \
"ultra detailed", or "high quality".

Finally write 1 to 3 sentences of feedback describing what is weak. Never rewrite the prompt,
never \
supply replacement wording, and never quote the rubric descriptions back to the user.

Return no scores other than the craftsmanship ratings; all weighting is computed elsewhere.
"""


async def evaluate_prompt(rubric: Rubric, prompt: str) -> PromptEvaluation:
    config = get_config()
    rubric_json = json.dumps(
        [
            {
                "id": criterion.id,
                "category": criterion.category,
                "description": criterion.description,
            }
            for criterion in rubric.criteria
        ],
        indent=2,
    )

    response = await parse_structured(
        model=config.openai.prompt_evaluator_model,
        system_prompt=SYSTEM_PROMPT,
        content=[
            {"type": "text", "text": f"Rubric:\n{rubric_json}\n\nUser prompt:\n{prompt}"},
        ],
        schema=PromptEvaluationResponse,
        validate=lambda parsed: validate_coverage(rubric, parsed.criteria),
    )
    return score_prompt_evaluation(rubric, response)
