"""Result Evaluator: compares the generated image with the target image per rubric criterion."""

from __future__ import annotations

import json

from app.config import get_config
from app.models import ResultEvaluation, ResultEvaluationResponse, Rubric
from app.services.openai.client import image_data_url, parse_structured
from app.services.scoring.result_score import score_result_evaluation, validate_scores

SYSTEM_PROMPT = """\
You compare a generated image with a target image, one rubric criterion at a time.

The first image is the target. The second image is the generated image.

For every rubric criterion, return an integer score from 0 to 100 describing how well the
generated image reproduces that specific characteristic of the target. Judge only that
characteristic; ignore \
differences the criterion does not mention.

Then write 1 to 3 sentences of feedback on the largest differences. Return no overall similarity \
score; weighting is computed elsewhere.
"""


async def evaluate_result(
    rubric: Rubric,
    target_image: bytes,
    target_mime_type: str,
    generated_image: bytes,
    generated_mime_type: str,
) -> ResultEvaluation:
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
        model=config.openai.result_evaluator_model,
        system_prompt=SYSTEM_PROMPT,
        content=[
            {"type": "text", "text": f"Rubric:\n{rubric_json}"},
            {"type": "text", "text": "Target image:"},
            {
                "type": "image_url",
                "image_url": {"url": image_data_url(target_image, target_mime_type)},
            },
            {"type": "text", "text": "Generated image:"},
            {
                "type": "image_url",
                "image_url": {"url": image_data_url(generated_image, generated_mime_type)},
            },
        ],
        schema=ResultEvaluationResponse,
        validate=lambda parsed: validate_scores(rubric, parsed.criteria),
    )
    return score_result_evaluation(rubric, response)
