"""Image generation through the Meta Model API (Muse Image).

Text-to-image only: the target image is never sent to the generator.

The request/response shape follows the OpenAI-compatible images API that the Meta Model API
exposes (`POST {base}/images/generations`, responses carrying either `b64_json` or `url`).
Provider specifics stay behind `generate_image` so another provider can be swapped in.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from app.config import get_config
from app.models import GeneratedImage

SUPPORTED_ASPECT_RATIOS: dict[str, float] = {
    "1:1": 1.0,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
}


class ImageGenerationError(RuntimeError):
    """Provider failure, timeout, or safety refusal. Never consumes a generation."""


def closest_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "1:1"
    target = width / height
    return min(
        SUPPORTED_ASPECT_RATIOS, key=lambda name: abs(SUPPORTED_ASPECT_RATIOS[name] - target)
    )


async def generate_image(prompt: str, aspect_ratio: str) -> GeneratedImage:
    config = get_config()
    payload: dict[str, Any] = {
        "model": config.meta.image_model,
        "prompt": prompt,
        "n": 1,
        "aspect_ratio": aspect_ratio,
        "response_format": "b64_json",
    }

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=config.meta.timeout_ms / 1000) as client:
            response = await client.post(
                f"{config.meta.base_url}/images/generations",
                headers={"Authorization": f"Bearer {config.meta.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            image_bytes, mime_type = await _extract_image(client, body)
    except httpx.HTTPStatusError as error:
        raise ImageGenerationError(
            f"Meta image generation failed with {error.response.status_code}: {error.response.text}"
        ) from error
    except httpx.HTTPError as error:
        raise ImageGenerationError(f"Meta image generation failed: {error}") from error

    return GeneratedImage(
        imageBytes=image_bytes,
        mimeType=mime_type,
        provider="meta",
        model=config.meta.image_model,
        generationTimeMs=int((time.monotonic() - started) * 1000),
    )


async def _extract_image(client: httpx.AsyncClient, body: dict[str, Any]) -> tuple[bytes, str]:
    items = body.get("data") or []
    if not items:
        raise ImageGenerationError(f"Meta image generation returned no image: {body}")

    item = items[0]
    mime_type = item.get("mime_type") or "image/png"

    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"]), mime_type

    if item.get("url"):
        downloaded = await client.get(item["url"])
        downloaded.raise_for_status()
        return downloaded.content, downloaded.headers.get("content-type", mime_type)

    raise ImageGenerationError(f"Meta image generation returned an unreadable image: {item}")
