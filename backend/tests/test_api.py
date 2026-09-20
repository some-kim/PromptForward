"""API tests against a local MongoDB, with the OpenAI, Meta, and Dropbox providers mocked."""

from __future__ import annotations

import asyncio
import hashlib
import json
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
from app.services.dropbox.image_storage import extension_for
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
    from app.routes import images as images_route
    from app.services import attempts as attempts_service
    from app.services import challenges as challenges_service
    from app.services import evaluation_cache

    async def fake_analyze(image_bytes: bytes, mime_type: str) -> Rubric:
        return RUBRIC

    async def fake_store_target(image_bytes, image_hash, mime_type, difficulty) -> StoredFile:
        return StoredFile(
            id=f"id:{image_hash}",
            path=f"/PromptForward/Challenges/{difficulty}/{image_hash}.png",
        )

    async def fake_store_generated(attempt_id, number, image_bytes, mime_type) -> StoredFile:
        extension = extension_for(mime_type)
        return StoredFile(
            id=f"id:{attempt_id}:{number}",
            path=f"/PromptForward/Generated/{attempt_id}/{number}.{extension}",
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

    deleted_targets: list[str] = []

    async def fake_delete_target(path: str) -> None:
        deleted_targets.append(path)

    monkeypatch.setattr(challenges_service, "analyze_challenge", fake_analyze)
    monkeypatch.setattr(challenges_service, "store_target_image", fake_store_target)
    monkeypatch.setattr(challenges_service, "delete_target_image", fake_delete_target)
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

    monkeypatch.setattr(evaluation_cache, "evaluate_prompt", strong_prompt_evaluation)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        async_client.deleted_targets = deleted_targets
        yield async_client


async def create_challenge(
    client: AsyncClient, color: str = "yellow", difficulty: str | None = None
) -> str:
    response = await client.post(
        "/api/challenges",
        files={"image": ("target.png", png_bytes(color=color), "image/png")},
        data={"difficulty": difficulty} if difficulty else None,
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

    async def test_challenges_can_be_listed_by_difficulty(self, client):
        easy_id = await create_challenge(client, color="yellow", difficulty="easy")
        await create_challenge(client, color="green", difficulty="hard")

        easy = (await client.get("/api/challenges", params={"difficulty": "easy"})).json()
        assert [challenge["id"] for challenge in easy] == [easy_id]
        assert easy[0]["difficulty"] == "easy"
        assert len((await client.get("/api/challenges")).json()) == 2

    async def test_uploads_default_to_medium(self, client):
        await create_challenge(client)
        listed = (await client.get("/api/challenges")).json()
        assert listed[0]["difficulty"] == "medium"

    async def test_target_image_is_served(self, client):
        challenge_id = await create_challenge(client)
        response = await client.get(f"/api/challenges/{challenge_id}/image")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"


class TestLearningMode:
    async def test_same_prompt_on_same_target_is_scored_once(self, client, monkeypatch):
        from app.services import evaluation_cache

        calls: list[str] = []
        real_evaluate = evaluation_cache.evaluate_prompt

        async def counting_evaluate(rubric, prompt: str):
            calls.append(prompt)
            return await real_evaluate(rubric, prompt)

        monkeypatch.setattr(evaluation_cache, "evaluate_prompt", counting_evaluate)
        challenge_id = await create_challenge(client)
        other_challenge_id = await create_challenge(client, color="green")

        async def evaluate(target: str, prompt: str) -> dict:
            attempt = await client.post(
                "/api/learning/attempts", json={"challengeId": target, "userId": "player-1"}
            )
            response = await client.post(
                f"/api/learning/attempts/{attempt.json()['id']}/evaluate", json={"prompt": prompt}
            )
            assert response.status_code == 200
            return response.json()

        first = await evaluate(challenge_id, WEAK_PROMPT)
        second = await evaluate(challenge_id, f"  {WEAK_PROMPT}\n")  # whitespace is ignored
        assert first["promptQuality"] == second["promptQuality"]
        assert calls == [WEAK_PROMPT]

        await evaluate(challenge_id, STRONG_PROMPT)
        await evaluate(other_challenge_id, WEAK_PROMPT)  # a different target is a new score
        assert calls == [WEAK_PROMPT, STRONG_PROMPT, WEAK_PROMPT]

    async def test_weak_prompt_still_generates_and_scores_both(self, client):
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

        generated = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": WEAK_PROMPT}
        )
        assert generated.status_code == 200
        scores = generated.json()["scores"]
        assert scores["promptQuality"] is not None
        assert scores["resultQuality"] is not None
        assert scores["final"] is not None

    async def test_an_unchecked_prompt_is_evaluated_while_generating(self, client):
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
        assert edited.status_code == 200
        body = edited.json()
        assert body["scores"]["promptQuality"] is not None
        assert body["usage"]["promptEvaluations"] == 2

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
        assert body["scores"]["final"] is not None
        assert body["scores"]["efficiency"] > 0
        assert body["usage"]["generations"] == 1
        assert body["usage"]["promptEvaluations"] == 2
        assert len(body["generations"]) == 1

    async def test_concurrent_generations_each_take_their_own_slot(self, client):
        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]
        await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": STRONG_PROMPT}
        )

        first, second = await asyncio.gather(
            client.post(
                f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
            ),
            client.post(
                f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
            ),
        )
        assert [first.status_code, second.status_code] == [200, 200]
        assert len(second.json()["generations"]) == 2

    async def test_failed_generation_refunds_the_slot_without_reusing_its_number(
        self, client, monkeypatch
    ):
        from app.services import attempts as attempts_service

        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]

        working_store = attempts_service.store_generated_image

        async def failing_store(*_args):
            raise RuntimeError("Dropbox is down")

        monkeypatch.setattr(attempts_service, "store_generated_image", failing_store)
        await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": STRONG_PROMPT}
        )
        failed = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        assert failed.status_code == 502

        monkeypatch.setattr(attempts_service, "store_generated_image", working_store)
        retry_prompt = f"{STRONG_PROMPT} retry"
        await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": retry_prompt}
        )
        retried = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": retry_prompt}
        )
        assert retried.status_code == 200
        body = retried.json()
        assert body["usage"]["generations"] == 1
        assert body["generations"][0]["number"] == 2
        assert body["generationsRemaining"] == 2

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

    async def test_unreachable_evaluator_refuses_the_generation_and_refunds_the_slot(
        self, client, monkeypatch
    ):
        from app.services import evaluation_cache
        from app.services.openai.client import LLMResponseError

        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]

        working_evaluate = evaluation_cache.evaluate_prompt

        async def failing_evaluate(rubric, prompt):
            raise LLMResponseError("OpenAI is down")

        monkeypatch.setattr(evaluation_cache, "evaluate_prompt", failing_evaluate)
        failed = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        assert failed.status_code == 502

        monkeypatch.setattr(evaluation_cache, "evaluate_prompt", working_evaluate)
        retried = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        assert retried.status_code == 200
        assert retried.json()["scores"]["promptQuality"] is not None
        assert retried.json()["generationsRemaining"] == 2

    async def test_failed_submission_finalizes_the_stored_generation(self, client, monkeypatch):
        from app.routes import learning as learning_route

        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]

        working_submit = learning_route.submit_attempt

        async def failing_submit(_attempt_id):
            raise RuntimeError("scoring is down")

        monkeypatch.setattr(learning_route, "submit_attempt", failing_submit)
        with pytest.raises(RuntimeError):
            await client.post(
                f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
            )

        monkeypatch.setattr(learning_route, "submit_attempt", working_submit)
        retried = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        assert retried.status_code == 200
        body = retried.json()
        assert body["status"] == "submitted"
        assert body["usage"]["generations"] == 1
        assert body["generationsRemaining"] == 2


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
        assert body["winner"] in {"you", "opponent", "draw"}
        for player in body["players"]:
            attempt = player["attempt"]
            assert attempt["scores"]["final"] is not None
            assert attempt["scores"]["efficiency"] > 0

    async def test_failed_evaluation_does_not_buy_a_second_image(self, client, monkeypatch):
        from app.services import evaluation_cache
        from app.services.openai.client import LLMResponseError

        challenge_id = await create_challenge(client)
        game_id = (
            await client.post(
                "/api/games",
                json={"userId": "p1", "displayName": "Kris", "challengeId": challenge_id},
            )
        ).json()["id"]
        await client.post(f"/api/games/{game_id}/join", json={"userId": "p2", "displayName": "Sam"})

        working_evaluate = evaluation_cache.evaluate_prompt

        async def failing_evaluate(rubric, prompt):
            raise LLMResponseError("OpenAI is down")

        monkeypatch.setattr(evaluation_cache, "evaluate_prompt", failing_evaluate)
        failed = await client.post(
            f"/api/games/{game_id}/generate", json={"userId": "p1", "prompt": STRONG_PROMPT}
        )
        assert failed.status_code == 502

        monkeypatch.setattr(evaluation_cache, "evaluate_prompt", working_evaluate)
        retried = await client.post(
            f"/api/games/{game_id}/generate", json={"userId": "p1", "prompt": "a different prompt"}
        )
        assert retried.status_code == 200
        mine = next(p for p in retried.json()["players"] if p["isYou"])
        assert len(mine["attempt"]["generations"]) == 1
        assert mine["attempt"]["generations"][0]["prompt"] == STRONG_PROMPT
        assert mine["attempt"]["scores"]["promptQuality"] is not None

    async def test_failed_submission_can_be_retried(self, client, monkeypatch):
        from app.routes import games as games_route

        challenge_id = await create_challenge(client)
        game_id = (
            await client.post(
                "/api/games",
                json={"userId": "p1", "displayName": "Kris", "challengeId": challenge_id},
            )
        ).json()["id"]
        await client.post(f"/api/games/{game_id}/join", json={"userId": "p2", "displayName": "Sam"})

        working_submit = games_route.submit_attempt

        async def failing_submit(attempt_id):
            raise RuntimeError("Mongo is down")

        monkeypatch.setattr(games_route, "submit_attempt", failing_submit)
        with pytest.raises(RuntimeError):
            await client.post(
                f"/api/games/{game_id}/generate", json={"userId": "p1", "prompt": STRONG_PROMPT}
            )

        monkeypatch.setattr(games_route, "submit_attempt", working_submit)
        retried = await client.post(
            f"/api/games/{game_id}/generate", json={"userId": "p1", "prompt": STRONG_PROMPT}
        )
        assert retried.status_code == 200
        mine = next(p for p in retried.json()["players"] if p["isYou"])
        assert len(mine["attempt"]["generations"]) == 1
        assert mine["attempt"]["status"] == "submitted"

    async def test_oversized_prompts_are_rejected(self, client):
        challenge_id = await create_challenge(client)
        game_id = (
            await client.post(
                "/api/games",
                json={"userId": "p1", "displayName": "Kris", "challengeId": challenge_id},
            )
        ).json()["id"]
        await client.post(f"/api/games/{game_id}/join", json={"userId": "p2", "displayName": "Sam"})

        oversized = await client.post(
            f"/api/games/{game_id}/generate", json={"userId": "p1", "prompt": "x" * 2001}
        )
        assert oversized.status_code == 422

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
        opponent = next(p for p in as_opponent.json()["players"] if not p["isYou"])
        assert "generations" not in opponent["attempt"]
        assert opponent["attempt"]["status"] == "submitted"
        assert STRONG_PROMPT not in as_opponent.text

        assert "imageUrl" not in as_opponent.text
        peek = await client.get(
            f"/api/attempts/{opponent['attempt']['id']}/generations/1/image",
            params={"token": "guessed"},
        )
        assert peek.status_code == 403

        as_owner = await client.get(f"/api/games/{game_id}", params={"userId": "p1"})
        mine = next(p for p in as_owner.json()["players"] if p["isYou"])
        image = await client.get(mine["attempt"]["generations"][0]["imageUrl"])
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

    async def test_player_ids_are_never_published(self, client):
        challenge_id = await create_challenge(client)
        game_id = (
            await client.post(
                "/api/games",
                json={"userId": "secret-alice", "displayName": "Kris", "challengeId": challenge_id},
            )
        ).json()["id"]
        await client.post(
            f"/api/games/{game_id}/join", json={"userId": "secret-bob", "displayName": "Sam"}
        )
        await client.post(
            f"/api/games/{game_id}/generate",
            json={"userId": "secret-alice", "prompt": STRONG_PROMPT},
        )

        as_opponent = await client.get(f"/api/games/{game_id}", params={"userId": "secret-bob"})
        assert "secret-alice" not in as_opponent.text


class TestAccounts:
    async def test_signup_login_and_progress(self, client):
        signup = await client.post(
            "/api/auth/signup",
            json={"username": "Kris", "password": "hunter2hunter2", "displayName": "Kris"},
        )
        assert signup.status_code == 201
        token = signup.json()["token"]
        assert signup.json()["user"]["username"] == "kris"
        assert signup.json()["user"]["progress"]["xp"] == 0

        headers = {"Authorization": f"Bearer {token}"}
        progress = await client.post(
            "/api/auth/progress",
            json={"attemptId": "attempt-1", "score": 91.4, "generations": 2},
            headers=headers,
        )
        assert progress.json() == {
            "xp": 91,
            "attempts": 1,
            "generations": 2,
            "streak": 1,
            "lastPlayedDay": progress.json()["lastPlayedDay"],
        }

        # The stats belong to the account, so a fresh session sees them.
        login = await client.post(
            "/api/auth/login", json={"username": "kris", "password": "hunter2hunter2"}
        )
        assert login.status_code == 200
        me = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {login.json()['token']}"}
        )
        assert me.json()["progress"]["xp"] == 91

    async def test_duplicate_username_and_wrong_password_are_rejected(self, client):
        await client.post(
            "/api/auth/signup", json={"username": "kris", "password": "hunter2hunter2"}
        )
        again = await client.post(
            "/api/auth/signup", json={"username": "KRIS", "password": "otherpassword"}
        )
        assert again.status_code == 400

        wrong = await client.post(
            "/api/auth/login", json={"username": "kris", "password": "wrongpassword"}
        )
        assert wrong.status_code == 401

    async def test_reporting_the_same_attempt_twice_adjusts_it(self, client):
        signup = await client.post(
            "/api/auth/signup", json={"username": "kris", "password": "hunter2hunter2"}
        )
        headers = {"Authorization": f"Bearer {signup.json()['token']}"}

        first = await client.post(
            "/api/auth/progress",
            json={"attemptId": "attempt-1", "score": 40, "generations": 1},
            headers=headers,
        )
        assert (first.json()["xp"], first.json()["attempts"]) == (40, 1)

        # A retry of the same attempt replaces its contribution instead of adding another attempt.
        retried = await client.post(
            "/api/auth/progress",
            json={"attemptId": "attempt-1", "score": 80, "generations": 2},
            headers=headers,
        )
        assert retried.json()["xp"] == 80
        assert retried.json()["attempts"] == 1
        assert retried.json()["generations"] == 2

        other = await client.post(
            "/api/auth/progress",
            json={"attemptId": "attempt-2", "score": 10, "generations": 1},
            headers=headers,
        )
        assert (other.json()["xp"], other.json()["attempts"]) == (90, 2)

    async def test_progress_requires_a_session(self, client):
        anonymous = await client.post(
            "/api/auth/progress", json={"attemptId": "a", "score": 50, "generations": 1}
        )
        assert anonymous.status_code == 401

        bogus = await client.get("/api/auth/me", headers={"Authorization": "Bearer nope"})
        assert bogus.status_code == 401

    async def test_logout_ends_the_session(self, client):
        token = (
            await client.post(
                "/api/auth/signup", json={"username": "kris", "password": "hunter2hunter2"}
            )
        ).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert (await client.post("/api/auth/logout", headers=headers)).status_code == 204
        assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


PROBLEM = {
    "slug": "umbrella-in-the-rain",
    "title": "Umbrella in the rain",
    "skill": "setting",
    "order": 3,
    "tests": "Naming the street and the weather, not just the umbrella.",
    "hints": ["Where is the umbrella?", "What time of day is it, and what is the weather?"],
    "referencePrompt": STRONG_PROMPT,
}


async def create_problem(client: AsyncClient, color: str = "yellow", **overrides) -> str:
    response = await client.post(
        "/api/challenges",
        files={"image": ("target.png", png_bytes(color=color), "image/png")},
        data={"difficulty": "easy", "problem": json.dumps({**PROBLEM, **overrides})},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestProblems:
    async def test_problem_metadata_is_listed_without_hints_or_reference(self, client):
        problem_id = await create_problem(client)
        await create_challenge(client, color="green")

        listed = (await client.get("/api/problems")).json()
        assert [problem["id"] for problem in listed["problems"]] == [problem_id]
        problem = listed["problems"][0]
        assert problem["title"] == "Umbrella in the rain"
        assert problem["skill"] == "setting"
        assert problem["status"] == "unsolved"
        assert problem["bestScore"] is None
        assert problem["hintCount"] == 2
        assert "Where is the umbrella" not in listed and STRONG_PROMPT not in str(listed)
        setting = next(skill for skill in listed["skills"] if skill["skill"] == "setting")
        assert (setting["total"], setting["solved"]) == (1, 0)

        by_skill = (await client.get("/api/challenges", params={"skill": "setting"})).json()
        assert [challenge["id"] for challenge in by_skill] == [problem_id]
        assert by_skill[0]["problem"]["title"] == "Umbrella in the rain"

    async def test_relabeling_an_existing_image_does_not_reanalyze(self, client):
        first = await create_problem(client)
        second = await create_problem(client, title="Renamed")
        assert first == second
        detail = (await client.get(f"/api/challenges/{first}")).json()
        assert detail["problem"]["title"] == "Renamed"

    async def test_hints_unlock_per_weak_prompt_and_reference_after_solving(self, client):
        problem_id = await create_problem(client)
        created = await client.post(
            "/api/learning/attempts", json={"challengeId": problem_id, "userId": "player-1"}
        )
        coaching = created.json()["coaching"]
        assert coaching["hints"] == []
        assert coaching["hintsRemaining"] == 2
        assert coaching["referencePrompt"] is None
        attempt_id = created.json()["id"]

        weak = await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": WEAK_PROMPT}
        )
        assert weak.json()["coaching"]["hints"] == ["Where is the umbrella?"]
        assert weak.json()["coaching"]["referencePrompt"] is None

        strong = await client.post(
            f"/api/learning/attempts/{attempt_id}/evaluate", json={"prompt": STRONG_PROMPT}
        )
        assert len(strong.json()["coaching"]["hints"]) == 1

        generated = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        coaching = generated.json()["coaching"]
        assert coaching["solved"] is True
        assert coaching["referencePrompt"] == STRONG_PROMPT

    async def test_problems_stay_out_of_the_training_pool(self, client):
        plain_id = await create_challenge(client, color="blue", difficulty="easy")
        await create_problem(client)
        listed = (await client.get("/api/challenges", params={"difficulty": "easy"})).json()
        assert [challenge["id"] for challenge in listed] == [plain_id]

    async def test_a_new_image_for_a_slug_replaces_the_problem_in_place(self, client):
        problem_id = await create_problem(client, color="yellow")
        replaced_id = await create_problem(client, color="blue")
        assert replaced_id == problem_id
        listed = (await client.get("/api/problems")).json()
        assert [problem["id"] for problem in listed["problems"]] == [problem_id]
        # The retired file is gone, so the folder seeder cannot bring it back as a plain target.
        old_hash = hashlib.sha256(png_bytes(color="yellow")).hexdigest()
        assert client.deleted_targets == [f"/PromptForward/Challenges/easy/{old_hash}.png"]

    async def test_a_slug_cannot_take_over_another_challenges_image(self, client):
        plain_id = await create_challenge(client, color="blue")
        problem_id = await create_problem(client, color="yellow")
        response = await client.post(
            "/api/challenges",
            files={"image": ("target.png", png_bytes(color="blue"), "image/png")},
            data={"difficulty": "easy", "problem": json.dumps(PROBLEM)},
        )
        assert response.status_code == 409
        listed = (await client.get("/api/problems")).json()
        assert [problem["id"] for problem in listed["problems"]] == [problem_id]
        assert (await client.get(f"/api/challenges/{plain_id}")).json()["problem"] is None

    async def test_progress_marks_problems_solved_per_account(self, client):
        problem_id = await create_problem(client)
        signup = await client.post(
            "/api/auth/signup", json={"username": "kris", "password": "hunter2hunter2"}
        )
        headers = {"Authorization": f"Bearer {signup.json()['token']}"}
        attempt_id = (
            await client.post(
                "/api/learning/attempts",
                json={"challengeId": problem_id, "userId": signup.json()["user"]["id"]},
                headers=headers,
            )
        ).json()["id"]

        # An attempt that has not been scored yet earns nothing, whatever the client claims.
        await client.post(
            "/api/auth/progress",
            json={"attemptId": attempt_id, "score": 99, "generations": 1},
            headers=headers,
        )
        listed = (await client.get("/api/problems", headers=headers)).json()
        assert listed["problems"][0]["status"] == "unsolved"

        weak = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": WEAK_PROMPT}
        )
        weak_final = round(weak.json()["scores"]["final"])
        await client.post(
            "/api/auth/progress",
            json={"attemptId": attempt_id, "score": 99, "generations": 1},
            headers=headers,
        )
        listed = (await client.get("/api/problems", headers=headers)).json()
        assert listed["problems"][0]["status"] == ("solved" if weak_final >= 70 else "attempted")
        assert listed["problems"][0]["bestScore"] == weak_final
        assert listed["problems"][0]["attempts"] == 1

        # A retry of the same attempt raises the best score without counting twice.
        strong = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        strong_final = round(strong.json()["scores"]["final"])
        assert strong_final >= 70
        for _ in range(2):
            await client.post(
                "/api/auth/progress",
                json={"attemptId": attempt_id, "score": strong_final, "generations": 2},
                headers=headers,
            )
        listed = (await client.get("/api/problems", headers=headers)).json()
        assert listed["problems"][0]["status"] == "solved"
        assert listed["problems"][0]["bestScore"] == max(weak_final, strong_final)
        assert listed["problems"][0]["attempts"] == 1
        setting = next(skill for skill in listed["skills"] if skill["skill"] == "setting")
        assert setting["solved"] == 1

        anonymous = (await client.get("/api/problems")).json()
        assert anonymous["problems"][0]["status"] == "unsolved"

    async def test_only_own_learning_attempts_on_problems_count_as_progress(self, client):
        problem_id = await create_problem(client)
        plain_id = await create_challenge(client, color="blue")
        signup = await client.post(
            "/api/auth/signup", json={"username": "kris", "password": "hunter2hunter2"}
        )
        headers = {"Authorization": f"Bearer {signup.json()['token']}"}
        me = signup.json()["user"]["id"]

        async def solved_attempt(challenge_id: str, auth: dict[str, str]) -> str:
            attempt_id = (
                await client.post(
                    "/api/learning/attempts",
                    json={"challengeId": challenge_id, "userId": me},
                    headers=auth,
                )
            ).json()["id"]
            response = await client.post(
                f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
            )
            assert response.json()["scores"]["final"] >= 70
            return attempt_id

        # An anonymous attempt claiming my id on the problem, and my own attempt on a random target.
        theirs = await solved_attempt(problem_id, {})
        random_practice = await solved_attempt(plain_id, headers)
        for attempt_id in (theirs, random_practice):
            await client.post(
                "/api/auth/progress",
                json={"attemptId": attempt_id, "score": 90, "generations": 1},
                headers=headers,
            )
        listed = (await client.get("/api/problems", headers=headers)).json()
        assert listed["problems"][0]["status"] == "unsolved"
        assert listed["problems"][0]["attempts"] == 0

        mine = await solved_attempt(problem_id, headers)
        await client.post(
            "/api/auth/progress",
            json={"attemptId": mine, "score": 90, "generations": 1},
            headers=headers,
        )
        listed = (await client.get("/api/problems", headers=headers)).json()
        assert listed["problems"][0]["status"] == "solved"
        assert listed["problems"][0]["attempts"] == 1

    async def test_a_new_slug_cannot_relabel_an_existing_challenge(self, client):
        plain_id = await create_challenge(client, color="blue")
        response = await client.post(
            "/api/challenges",
            files={"image": ("target.png", png_bytes(color="blue"), "image/png")},
            data={"difficulty": "easy", "problem": json.dumps(PROBLEM)},
        )
        assert response.status_code == 409
        assert (await client.get("/api/problems")).json()["problems"] == []
        assert (await client.get(f"/api/challenges/{plain_id}")).json()["problem"] is None
