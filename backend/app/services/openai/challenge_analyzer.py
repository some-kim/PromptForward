"""Challenge Analyzer: turns a target image into a weighted challenge rubric."""

from __future__ import annotations

from app.config import get_config
from app.models import ChallengeAnalysis, Rubric
from app.services.openai.client import image_data_url, parse_structured
from app.services.scoring.rubric import validate_and_normalize_rubric

SYSTEM_PROMPT = """\
You analyze a target image so another person can recreate it from a text prompt alone.

Return 4 to 8 criteria describing only the characteristics that meaningfully affect recreating \
this image. Skip categories that do not matter for this image.

Each criterion has:
- category: one of subject, action, environment, composition, spatial, color, lighting, style, mood
- description: a short, concrete, visually checkable phrase (e.g. "yellow umbrella near the center")
- weight: a positive integer reflecting how much this matters relative to the other criteria
- critical: true only for characteristics without which the recreation clearly fails

Mark between 1 and 4 criteria as critical. Do not describe incidental details, and do not
produce ids.
"""


async def analyze_challenge(image_bytes: bytes, mime_type: str) -> Rubric:
    config = get_config()
    analysis = await parse_structured(
        model=config.openai.challenge_analyzer_model,
        system_prompt=SYSTEM_PROMPT,
        content=[
            {"type": "text", "text": "Analyze this target image."},
            {"type": "image_url", "image_url": {"url": image_data_url(image_bytes, mime_type)}},
        ],
        schema=ChallengeAnalysis,
        validate=validate_and_normalize_rubric,
    )
    return validate_and_normalize_rubric(analysis)
