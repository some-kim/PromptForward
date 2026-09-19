"""Test configuration: real MongoDB, mocked OpenAI, Meta, and Dropbox providers."""

from __future__ import annotations

import io
import os

import pytest

TEST_ENV = {
    "OPENAI_API_KEY": "test",
    "OPENAI_CHALLENGE_ANALYZER_MODEL": "test-analyzer",
    "OPENAI_PROMPT_EVALUATOR_MODEL": "test-prompt-evaluator",
    "OPENAI_RESULT_EVALUATOR_MODEL": "test-result-evaluator",
    "META_API_KEY": "test",
    "META_API_BASE_URL": "https://meta.test/v1",
    "META_IMAGE_MODEL": "test-muse",
    "MONGODB_URI": os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017"),
    "MONGODB_DB_NAME": "promptforward_test",
    "DROPBOX_APP_KEY": "test",
    "DROPBOX_APP_SECRET": "test",
    "DROPBOX_REFRESH_TOKEN": "test",
    "DROPBOX_CHALLENGES_FOLDER": "/PromptForward/Challenges",
    "DROPBOX_GENERATED_FOLDER": "/PromptForward/Generated",
    "APP_ENV": "development",
}

for name, value in TEST_ENV.items():
    os.environ.setdefault(name, value)


def png_bytes(width: int = 64, height: int = 32, color: str = "yellow") -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
async def database():
    from app import db

    await db.ensure_indexes()
    yield db.get_database()
    for name in ("challenges", "attempts", "games", "users", "sessions", "progress_events"):
        await db.get_database()[name].delete_many({})
    # Each test runs in its own event loop, so the client cannot be shared between them.
    await db.close_client()
