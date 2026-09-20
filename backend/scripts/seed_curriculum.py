"""Create one challenge per problem in the curriculum manifest. Safe to re-run.

Each manifest entry names a Wikimedia Commons file; the image is downloaded once, stored under
the Dropbox challenges folder for its difficulty, analyzed, and saved with its problem metadata.
Re-running only refreshes the metadata of already-analyzed images, so it costs no analyzer calls.

python -m scripts.seed_curriculum [path/to/problems.json]
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.parse
from pathlib import Path

import httpx
from pydantic import BaseModel

from app.config import ConfigError, get_config
from app.db import close_client, ensure_indexes
from app.models import Difficulty, Problem
from app.services.challenges import create_challenge

MANIFEST = Path(__file__).resolve().parents[1] / "curriculum" / "problems.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
IMAGE_WIDTH = 1280
# Wikimedia rejects generic user agents; theirs must name the project and a contact.
USER_AGENT = "PromptForwardSeed/1.0 (https://github.com/some-kim/PromptForward) python-httpx"


class Source(BaseModel):
    commons: str
    license: str


class ManifestEntry(Problem):
    difficulty: Difficulty
    source: Source

    def problem(self) -> Problem:
        return Problem.model_validate(self.model_dump(include=set(Problem.model_fields)))


def load_manifest(path: Path) -> list[ManifestEntry]:
    entries = [ManifestEntry.model_validate(item) for item in json.loads(path.read_text())]
    slugs = [entry.slug for entry in entries]
    if len(set(slugs)) != len(slugs):
        raise SystemExit("Manifest has duplicate slugs")
    return entries


async def fetch_commons_image(client: httpx.AsyncClient, title: str) -> bytes:
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": IMAGE_WIDTH,
        }
    )
    info = (await client.get(f"{COMMONS_API}?{query}")).raise_for_status().json()
    pages = list(info["query"]["pages"].values())
    if not pages or "imageinfo" not in pages[0]:
        raise ValueError(f"Commons file not found: {title}")
    url = pages[0]["imageinfo"][0]["thumburl"]
    return (await client.get(url)).raise_for_status().content


async def seed(manifest: Path) -> None:
    entries = load_manifest(manifest)
    print(f"Seeding {len(entries)} problem(s) from {manifest}")
    await ensure_indexes()

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
    ) as client:
        for entry in entries:
            try:
                image_bytes = await fetch_commons_image(client, entry.source.commons)
                challenge = await create_challenge(image_bytes, entry.difficulty, entry.problem())
                criteria = len(challenge["rubric"]["criteria"])
                print(
                    f"  #{entry.order:02d} {entry.slug} [{entry.skill}/{entry.difficulty}]"
                    f" -> {challenge['_id']} ({criteria} criteria)"
                )
            except Exception as error:  # noqa: BLE001 - one bad entry must not stop the seed
                print(f"  #{entry.order:02d} {entry.slug} -> failed: {error}")

    await close_client()


def main() -> None:
    try:
        get_config()
    except ConfigError as error:
        raise SystemExit(f"Configuration error: {error}") from error
    manifest = Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFEST
    asyncio.run(seed(manifest))


if __name__ == "__main__":
    main()
