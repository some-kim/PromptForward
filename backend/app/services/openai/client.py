"""Shared OpenAI access: one client, structured outputs, one retry on invalid output."""

from __future__ import annotations

import base64
import functools
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import get_config

TResponse = TypeVar("TResponse", bound=BaseModel)

TEMPERATURE = 0.0


class LLMResponseError(RuntimeError):
    """Raised when the model returns output that fails backend validation twice."""


@functools.lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_config().openai.api_key)


def image_data_url(image_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def parse_structured(
    *,
    model: str,
    system_prompt: str,
    content: list[dict[str, Any]],
    schema: type[TResponse],
    validate: Any = None,
) -> TResponse:
    """Call the model with an enforced JSON schema, validating in backend code.

    `validate` is an optional callable applied to the parsed response; anything it raises
    is treated as invalid output. Invalid output is retried exactly once.
    """
    client = get_client()
    last_error: Exception | None = None

    for _ in range(2):
        try:
            completion = await client.beta.chat.completions.parse(
                model=model,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                response_format=schema,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise LLMResponseError("Model returned no parsed content")
            if validate is not None:
                validate(parsed)
            return parsed
        except (ValidationError, ValueError, LLMResponseError) as error:
            last_error = error

    raise LLMResponseError(f"Model returned invalid output twice: {last_error}")
