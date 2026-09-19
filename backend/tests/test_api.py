"""API tests against a local MongoDB, with the OpenAI, Meta, and Dropbox providers mocked."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import (
    CoverageJudgment,
    Craftsmanship,
    GeneratedImage,
    ImageMeta,
    PromptEvaluationResponse,
    ResultCriterionScore,
    ResultEvaluationResponse,
    Rubric,
    RubricCriterion,
    StoredFile,
)
from app.services.scoring.prompt_score import score_prompt_evaluation
from app.services.scoring.result_score import score_result_evaluation
from tests.conftest import png_bytes

RUBRIC = Rubric(
    criteria=[
        RubricCriterion(
            id="criterion_1",
            category="subject",
            description="yellow umbrella",
            weight=40,
            critical=True,
        ),
        RubricCriterion(
            id="criterion_2",
            category="environment",
            description="rainy street at night",
            weight=30,
            critical=True,
        ),
        RubricCriterion(
            id="criterion_3",
            category="color",
            description="blue reflections",
            weight=15,
            critical=False,
        ),
        RubricCriterion(
            id="criterion_4",
            category="style",
            description="realistic photo",
            weight=15,
            critical=False,
        ),
    ]
)


def coverage(statuses: list[str]) -> list[CoverageJudgment]:
    return [
        CoverageJudgment(id=criterion.id, status=status)
        for criterion, status in zip(RUBRIC.criteria, statuses, strict=True)
    ]


def prompt_evaluation(statuses: list[str], score: int = 90):
    return score_prompt_evaluation(
        RUBRIC,
        PromptEvaluationResponse(
            criteria=coverage(statuses),
            craftsmanship=Craftsmanship(
                clarity=score, relevantSpecificity=score, spatialClarity=score, conciseness=score
            ),
            feedback="Feedback.",
        ),
    )


@pytest.fixture
async def client(monkeypatch, database):
    from app.routes import challenges as challenges_route
    from app.routes import games as games_route
    from app.routes import images as images_route
    from app.routes import learning as learning_route
    from app.services import attempts as attempts_service
    from app.services import challenges as challenges_service

    async def fake_analyze(image_bytes: bytes, mime_type: str) -> Rubric:
        return RUBRIC

    async def fake_store_target(image_bytes, image_hash, mime_type) -> StoredFile:
        return StoredFile(id=f"id:{image_hash}", path=f"/PromptForward/Challenges/{image_hash}.png")

    async def fake_store_generated(attempt_id, number, image_bytes) -> StoredFile:
        return StoredFile(
            id=f"id:{attempt_id}:{number}",
            path=f"/PromptForward/Generated/{attempt_id}/{number}.png",
        )

    async def fake_generate_image(prompt: str, aspect_ratio: str) -> GeneratedImage:
        return GeneratedImage(
            imageBytes=png_bytes(color="blue"),
            mimeType="image/png",
            provider="meta",
            model="test-muse",
            generationTimeMs=10,
        )

    async def fake_download(path: str) -> bytes:
        return png_bytes()

    async def fake_evaluate_result(rubric, *_args):
        return score_result_evaluation(
            rubric,
            ResultEvaluationResponse(
                criteria=[ResultCriterionScore(id=c.id, score=90) for c in rubric.criteria],
                feedback="Close match.",
            ),
        )

    monkeypatch.setattr(challenges_service, "analyze_challenge", fake_analyze)
    monkeypatch.setattr(challenges_service, "store_target_image", fake_store_target)
    monkeypatch.setattr(
        challenges_service,
        "read_image_meta",
        lambda _: ImageMeta(width=64, height=32, mimeType="image/png"),
    )
    monkeypatch.setattr(attempts_service, "generate_image", fake_generate_image)
    monkeypatch.setattr(attempts_service, "store_generated_image", fake_store_generated)
    monkeypatch.setattr(attempts_service, "download_image", fake_download)
    monkeypatch.setattr(attempts_service, "evaluate_result", fake_evaluate_result)
    monkeypatch.setattr(challenges_route, "download_image", fake_download)
    monkeypatch.setattr(images_route, "download_image", fake_download)

    async def strong_prompt_evaluation(rubric, prompt: str):
        if len(prompt) < 40:
            return prompt_evaluation(["missing", "partial", "missing", "covered"], score=50)
        return prompt_evaluation(["covered", "covered", "covered", "covered"])

    monkeypatch.setattr(learning_route, "evaluate_prompt", strong_prompt_evaluation)
    monkeypatch.setattr(games_route, "evaluate_prompt", strong_prompt_evaluation)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def create_challenge(client: AsyncClient, color: str = "yellow") -> str:
    response = await client.post(
        "/api/challenges", files={"image": ("target.png", png_bytes(color=color), "image/png")}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


WEAK_PROMPT = "A yellow umbrella"
STRONG_PROMPT = (
    "A realistic nighttime photograph of a yellow umbrella centered on a rainy city street "
    "with blue reflections on the wet pavement"
)


class TestChallenges:
    async def test_upload_is_idempotent_for_identical_bytes(self, client):
        first = await create_challenge(client)
        second = await create_challenge(client)
        assert first == second

    async def test_challenge_responses_never_expose_the_rubric(self, client):
        challenge_id = await create_challenge(client)

        listed = await client.get("/api/challenges")
        detail = await client.get(f"/api/challenges/{challenge_id}")

        assert "rubric" not in listed.text
        assert "rubric" not in detail.text
        assert "yellow umbrella" not in detail.text

    async def test_target_image_is_served(self, client):
        challenge_id = await create_challenge(client)
        response = await client.get(f"/api/challenges/{challenge_id}/image")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"


class TestLearningMode:
    async def test_failing_evaluation_blocks_generation(self, client):
        challenge_id = await create_challenge(client)
        attempt = await client.post(
            "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
        )
        attempt_id = attempt.json()["id"]

        evaluation = await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": WEAK_PROMPT}
        )
        assert evaluation.status_code == 200
        body = evaluation.json()
        assert body["passed"] is False
        assert body["needsImprovement"]
        assert "yellow umbrella" not in evaluation.text

        blocked = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": WEAK_PROMPT}
        )
        assert blocked.status_code == 409

    async def test_generation_requires_the_evaluated_prompt(self, client):
        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]

        await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": STRONG_PROMPT}
        )

        edited = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate",
            json={"prompt": STRONG_PROMPT + " at dusk"},
        )
        assert edited.status_code == 409

    async def test_passing_evaluation_then_generation_scores_the_attempt(self, client):
        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]

        await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": WEAK_PROMPT}
        )
        passed = await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": STRONG_PROMPT}
        )
        assert passed.json()["passed"] is True

        generated = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        assert generated.status_code == 200
        body = generated.json()
        assert body["status"] == "submitted"
        assert body["scores"]["resultQuality"] == pytest.approx(90)
        assert body["scores"]["final"] is None
        assert body["scores"]["efficiency"] > 0
        assert body["usage"]["generations"] == 1
        assert body["usage"]["promptEvaluations"] == 2
        assert len(body["generations"]) == 1

    async def test_generation_limit_is_enforced(self, client):
        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]

        for index in range(3):
            prompt = f"{STRONG_PROMPT} take {index}"
            await client.post(
                f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": prompt}
            )
            response = await client.post(
                f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": prompt}
            )
            assert response.status_code == 200

        prompt = f"{STRONG_PROMPT} take 4"
        await client.post(f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": prompt})
        exhausted = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": prompt}
        )
        assert exhausted.status_code == 409


class TestGameMode:
    async def test_full_game_produces_a_winner(self, client):
        challenge_id = await create_challenge(client)
        player_one, player_two = str(uuid.uuid4()), str(uuid.uuid4())

        created = await client.post(
            "/api/games",
            json={"userId": player_one, "displayName": "Kris", "challengeId": challenge_id},
        )
        assert created.status_code == 201
        game_id = created.json()["id"]
        assert created.json()["status"] == "waiting"

        joined = await client.post(
            f"/api/games/{game_id}/join", json={"userId": player_two, "displayName": "Sam"}
        )
        assert joined.json()["status"] == "active"

        first = await client.post(
            f"/api/games/{game_id}/generate", json={"userId": player_one, "prompt": STRONG_PROMPT}
        )
        assert first.status_code == 200
        assert first.json()["status"] == "active"

        # A second generation for the same player is refused.
        repeat = await client.post(
            f"/api/games/{game_id}/generate", json={"userId": player_one, "prompt": STRONG_PROMPT}
        )
        assert repeat.status_code == 409

        second = await client.post(
            f"/api/games/{game_id}/generate",
            json={"userId": player_two, "prompt": STRONG_PROMPT + " with pedestrians"},
        )
        assert second.status_code == 200

        final = await client.get(f"/api/games/{game_id}", params={"userId": player_one})
        body = final.json()
        assert body["status"] == "completed"
        assert body["winnerUserId"] in {player_one, player_two, None}
        for player in body["players"]:
            attempt = player["attempt"]
            assert attempt["scores"]["final"] is not None
            assert attempt["scores"]["efficiency"] > 0

    async def test_third_player_is_rejected(self, client):
        challenge_id = await create_challenge(client)
        game_id = (
            await client.post(
                "/api/games",
                json={"userId": "p1", "displayName": "Kris", "challengeId": challenge_id},
            )
        ).json()["id"]

        await client.post(f"/api/games/{game_id}/join", json={"userId": "p2", "displayName": "Sam"})
        third = await client.post(
            f"/api/games/{game_id}/join", json={"userId": "p3", "displayName": "Alex"}
        )
        assert third.status_code == 409

    async def test_opponent_details_are_hidden_until_completion(self, client):
        challenge_id = await create_challenge(client)
        game_id = (
            await client.post(
                "/api/games",
                json={"userId": "p1", "displayName": "Kris", "challengeId": challenge_id},
            )
        ).json()["id"]
        await client.post(f"/api/games/{game_id}/join", json={"userId": "p2", "displayName": "Sam"})

        await client.post(
            f"/api/games/{game_id}/generate", json={"userId": "p1", "prompt": STRONG_PROMPT}
        )

        as_opponent = await client.get(f"/api/games/{game_id}", params={"userId": "p2"})
        opponent = next(p for p in as_opponent.json()["players"] if p["userId"] == "p1")
        assert "generations" not in opponent["attempt"]
        assert opponent["attempt"]["status"] == "submitted"
        assert STRONG_PROMPT not in as_opponent.text
