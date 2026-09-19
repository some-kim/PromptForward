"""Create a challenge for every image under the Dropbox challenges folder. Safe to re-run.

The `easy/`, `medium/`, and `hard/` subfolder an image sits in becomes its difficulty.

python -m scripts.seed_challenges
"""

from __future__ import annotations

import asyncio

from app.config import ConfigError, get_config
from app.db import close_client, ensure_indexes
from app.services.challenges import create_challenge
from app.services.dropbox.image_storage import download_image, list_challenge_images


async def seed() -> None:
    config = get_config()
    images = await list_challenge_images()
    print(f"Found {len(images)} image(s) in {config.dropbox.challenges_folder}")

    await ensure_indexes()

    for path, difficulty in images:
        try:
            image_bytes = await download_image(path)
            challenge = await create_challenge(image_bytes, difficulty)
            criteria = len(challenge["rubric"]["criteria"])
            print(f"  {path} -> {difficulty} challenge {challenge['_id']} ({criteria} criteria)")
        except Exception as error:  # noqa: BLE001 - one bad image must not stop the seed
            print(f"  {path} -> failed: {error}")

    await close_client()


def main() -> None:
    try:
        get_config()
    except ConfigError as error:
        raise SystemExit(f"Configuration error: {error}") from error
    asyncio.run(seed())


if __name__ == "__main__":
    main()
