"""Create one challenge per problem in the curriculum manifest. Safe to re-run.

Each manifest entry names a Wikimedia Commons file; the image is downloaded once, stored under
the Dropbox challenges folder for its difficulty, analyzed, and saved with its problem metadata.
Re-running only refreshes the metadata of already-analyzed images, so it costs no analyzer calls.

Every reference prompt is then scored against its challenge's rubric with the prompt evaluator
(one cheap text call each) and a warning is printed when it would not pass on its own, so a
re-analysis that drifts away from the manifest is caught here rather than by a learner.

python -m scripts.seed_curriculum [path/to/problems.json] [--skip-check]
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
from app.services.challenges import create_challenge, rubric_of
from app.services.openai.prompt_evaluator import evaluate_prompt
from app.services.problems import SOLVED_SCORE

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


async def check_reference(entry: ManifestEntry, challenge: dict) -> None:
    evaluation = await evaluate_prompt(rubric_of(challenge), entry.referencePrompt)
    quality = round(evaluation.promptQuality)
    if evaluation.passed and quality >= SOLVED_SCORE:
        print(f"      reference prompt scores {quality}")
        return
    missed = ", ".join(evaluation.needsImprovement) or "-"
    print(
        f"      WARNING reference prompt scores {quality} (passed={evaluation.passed});"
        f" missing: {missed}"
    )


async def seed(manifest: Path, check_references: bool) -> None:
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
                if check_references:
                    await check_reference(entry, challenge)
            except Exception as error:  # noqa: BLE001 - one bad entry must not stop the seed
                print(f"  #{entry.order:02d} {entry.slug} -> failed: {error}")

    await close_client()


def main() -> None:
    try:
        get_config()
    except ConfigError as error:
        raise SystemExit(f"Configuration error: {error}") from error
    args = [arg for arg in sys.argv[1:] if arg != "--skip-check"]
    manifest = Path(args[0]) if args else MANIFEST
    asyncio.run(seed(manifest, check_references="--skip-check" not in sys.argv))


if __name__ == "__main__":
    main()
