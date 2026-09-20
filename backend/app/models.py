"""Pydantic models shared by services, routes, and persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CriterionCategory = Literal[
    "subject",
    "action",
    "environment",
    "composition",
    "spatial",
    "color",
    "lighting",
    "style",
    "mood",
]

CoverageStatus = Literal["covered", "partial", "missing"]

# Difficulty labels the target image, not the scoring: every challenge is scored the same way.
Difficulty = Literal["easy", "medium", "hard"]
DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "medium", "hard")
DEFAULT_DIFFICULTY: Difficulty = "medium"

# A skill names the prompt-writing habit a problem isolates. Problems are the curriculum;
# an unlabeled challenge is still a valid random target.
Skill = Literal[
    "subject",
    "attributes",
    "setting",
    "lighting",
    "style",
    "composition",
    "multi_subject",
    "concision",
]
SKILLS: tuple[Skill, ...] = (
    "subject",
    "attributes",
    "setting",
    "lighting",
    "style",
    "composition",
    "multi_subject",
    "concision",
)

SKILL_INFO: dict[str, dict[str, str]] = {
    "subject": {
        "title": "Subject specificity",
        "lesson": "Name exactly what is in the frame. 'A dog' loses to 'a golden retriever puppy'.",
    },
    "attributes": {
        "title": "Attributes & materials",
        "lesson": "Colour, texture, material and age are what make a subject recognisable.",
    },
    "setting": {
        "title": "Setting & environment",
        "lesson": "Where the subject is matters as much as what it is: surface, background, place.",
    },
    "lighting": {
        "title": "Lighting & mood",
        "lesson": "Time of day, light direction and weather decide the whole feel of an image.",
    },
    "style": {
        "title": "Style & medium",
        "lesson": "Photo, watercolour, pixel art or oil paint: say it, or the model will guess.",
    },
    "composition": {
        "title": "Composition & framing",
        "lesson": "Camera angle, distance and where the subject sits in the frame.",
    },
    "multi_subject": {
        "title": "Multi-subject scenes",
        "lesson": "Every subject needs its own description and its relation to the others.",
    },
    "concision": {
        "title": "Concision",
        "lesson": "Say everything that matters and nothing else; filler words cost tokens.",
    },
}

# A problem is solved once its combined score clears this bar.
SOLVED_SCORE = 70


class Problem(BaseModel):
    """Curriculum metadata attached to a challenge."""

    slug: str
    title: str
    skill: Skill
    order: int
    # One line on what a prompt must get right to pass this problem.
    tests: str
    # Revealed one at a time after each weak prompt.
    hints: list[str]
    # Revealed once the problem is solved or every generation is spent.
    referencePrompt: str


CATEGORY_HINTS: dict[str, str] = {
    "subject": "Describe the main subject",
    "action": "Describe what is happening",
    "environment": "Describe where the scene takes place",
    "composition": "Describe where the main subject appears",
    "spatial": "Describe how the elements relate to one another",
    "color": "Mention the colors that matter",
    "lighting": "Include the important lighting",
    "style": "State the style or medium",
    "mood": "Convey the mood",
}


class Region(BaseModel):
    """Where a criterion lives in the target image, as fractions of width and height."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class RubricCriterion(BaseModel):
    id: str
    category: CriterionCategory
    description: str
    weight: int
    critical: bool
    # Absent on challenges seeded before the attention heatmap existed.
    region: Region | None = None


class Rubric(BaseModel):
    criteria: list[RubricCriterion]


class AnalyzedCriterion(BaseModel):
    """A criterion as returned by the Challenge Analyzer, before backend normalization."""

    category: CriterionCategory
    description: str
    weight: int
    critical: bool
    region: Region


class ChallengeAnalysis(BaseModel):
    criteria: list[AnalyzedCriterion]


class Craftsmanship(BaseModel):
    clarity: int = Field(ge=0, le=100)
    relevantSpecificity: int = Field(ge=0, le=100)
    spatialClarity: int = Field(ge=0, le=100)
    conciseness: int = Field(ge=0, le=100)


class CoverageJudgment(BaseModel):
    id: str
    status: CoverageStatus


class PromptEvaluationResponse(BaseModel):
    """Raw Prompt Evaluator LLM output. The LLM computes no scores."""

    criteria: list[CoverageJudgment]
    craftsmanship: Craftsmanship
    feedback: str


class PromptEvaluation(BaseModel):
    """Prompt evaluation after backend scoring."""

    criteria: list[CoverageJudgment]
    craftsmanship: Craftsmanship
    targetCoverage: float
    craftsmanshipScore: float
    promptQuality: float
    feedback: str
    needsImprovement: list[str]
    passed: bool


class ResultCriterionScore(BaseModel):
    id: str
    score: int = Field(ge=0, le=100)


class ResultEvaluationResponse(BaseModel):
    """Raw Result Evaluator LLM output."""

    criteria: list[ResultCriterionScore]
    feedback: str


class ResultEvaluation(BaseModel):
    criteria: list[ResultCriterionScore]
    resultQuality: float
    feedback: str


class GeneratedImage(BaseModel):
    imageBytes: bytes
    mimeType: str
    provider: str
    model: str
    generationTimeMs: int


class StoredFile(BaseModel):
    id: str
    path: str


class ImageMeta(BaseModel):
    width: int
    height: int
    mimeType: str


class Scores(BaseModel):
    resultQuality: float | None = None
    promptQuality: float | None = None
    efficiency: float | None = None
    final: float | None = None


class ResourceUsage(BaseModel):
    promptTokens: int
    promptEvaluations: int
    generations: int


class TimestampedModel(BaseModel):
    createdAt: datetime
