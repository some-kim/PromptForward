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
from urllib.parse import urlparse

import httpx

from app.config import get_config
from app.models import GeneratedImage
from app.services.dropbox.image_storage import EXTENSION_BY_MIME

# Muse Image takes the ratio as a "WxH" size string; the generator picks the real resolution.
SUPPORTED_ASPECT_RATIOS: dict[str, float] = {
    "1024x1024": 1.0,
    "1536x1024": 3 / 2,
    "1024x1536": 2 / 3,
    "1792x1024": 16 / 9,
    "1024x1792": 9 / 16,
}


SUPPORTED_IMAGE_MIME_TYPES = frozenset(EXTENSION_BY_MIME)
MAX_REDIRECTS = 3


class ImageGenerationError(RuntimeError):
    """Provider failure, timeout, or safety refusal. Never consumes a generation."""


def closest_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "1024x1024"
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
        "size": aspect_ratio,
        "response_format": "b64_json",
        "output_format": "png",
        # A prompt should be judged on its own words, not on references the model searched for.
        "tool_enablement": {
            "enable_image_search": False,
            "enable_web_search": False,
            "enable_shell": False,
        },
    }

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=config.meta.timeout_ms / 1000, follow_redirects=False
        ) as client:
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
    output_format = body.get("output_format") or "png"
    mime_type = (
        item.get("mime_type") or f"image/{'jpeg' if output_format == 'jpg' else output_format}"
    )

    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"]), mime_type

    if item.get("url"):
        return await _download_image(client, item["url"], mime_type)

    raise ImageGenerationError(f"Meta image generation returned an unreadable image: {item}")


async def _download_image(client: httpx.AsyncClient, url: str, mime_type: str) -> tuple[bytes, str]:
    """Fetch an image URL, revalidating the host on every redirect hop."""
    for _ in range(MAX_REDIRECTS + 1):
        if not _is_provider_url(url):
            raise ImageGenerationError(f"Meta returned an image URL outside the provider: {url}")
        downloaded = await client.get(url)
        if downloaded.is_redirect:
            location = downloaded.headers.get("location")
            if not location:
                raise ImageGenerationError(f"Meta redirected the image URL without a target: {url}")
            url = str(downloaded.url.join(location))
            continue
        downloaded.raise_for_status()
        return downloaded.content, _image_mime(downloaded.headers.get("content-type"), mime_type)

    raise ImageGenerationError(f"Meta redirected the image URL too many times: {url}")


def _image_mime(header: str | None, fallback: str) -> str:
    """Content-Type carries parameters and sometimes octet-stream, which storage rejects."""
    declared = (header or "").split(";", 1)[0].strip().lower()
    return declared if declared in SUPPORTED_IMAGE_MIME_TYPES else fallback


def _is_provider_url(url: str) -> bool:
    """Only https URLs served by the configured provider host are fetched.

    The response body is untrusted input: without this a redirected or compromised endpoint
    could make the backend fetch internal addresses.
    """
    parsed = urlparse(url)
    provider = urlparse(get_config().meta.base_url).hostname
    if parsed.scheme != "https" or not parsed.hostname or not provider:
        return False
    return parsed.hostname == provider or parsed.hostname.endswith(f".{provider}")
