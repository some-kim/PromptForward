"""API tests against a local MongoDB, with the OpenAI, Meta, and Dropbox providers mocked."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from bson import ObjectId
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
from app.services.dropbox.image_storage import (
    ImageStorageError,
    extension_for,
    read_image_meta,
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
    from app.routes import images as images_route
    from app.routes import learning as learning_route
    from app.services import attempts as attempts_service
    from app.services import battles as battles_service
    from app.services import challenges as challenges_service

    async def fake_analyze(image_bytes: bytes, mime_type: str) -> Rubric:
        return RUBRIC

    async def fake_store_target(image_bytes, image_hash, mime_type, difficulty) -> StoredFile:
        return StoredFile(
            id=f"id:{image_hash}",
            path=f"/PromptForward/Challenges/{difficulty}/{image_hash}.png",
        )

    async def fake_store_user_image(image_bytes, image_hash, mime_type) -> StoredFile:
        return StoredFile(
            id=f"id:user:{image_hash}",
            path=f"/PromptForward/Generated/user-images/{image_hash}.png",
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

    monkeypatch.setattr(challenges_service, "analyze_challenge", fake_analyze)
    monkeypatch.setattr(challenges_service, "store_target_image", fake_store_target)
    monkeypatch.setattr(challenges_service, "store_user_image", fake_store_user_image)
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
    monkeypatch.setattr(battles_service, "evaluate_prompt", strong_prompt_evaluation)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
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


COLORS = ["yellow", "blue", "green", "red", "purple", "orange", "pink", "brown"]
WEAK_PROMPT = "A yellow umbrella"
STRONG_PROMPT = (
    "A realistic nighttime photograph of a yellow umbrella centered on a rainy city street "
    "with blue reflections on the wet pavement"
)


async def seed_defaults(client: AsyncClient, count: int) -> list[str]:
    """Curated images the battle falls back on when a player brings none of their own."""
    return [await create_challenge(client, color=color) for color in COLORS[:count]]


async def upload_image(client: AsyncClient, user_id: str, color: str) -> str:
    response = await client.post(
        "/api/library/images",
        files={"image": ("mine.png", png_bytes(color=color), "image/png")},
        data={"userId": user_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def quick_battle(
    client: AsyncClient,
    *,
    images_per_player: int,
    duration: int = 120,
    host: str | None = None,
    guest: str | None = None,
) -> tuple[str, str, str]:
    """An active battle where both sides took default images."""
    host, guest = host or str(uuid.uuid4()), guest or str(uuid.uuid4())
    created = await client.post(
        "/api/games",
        json={
            "userId": host,
            "displayName": "Kris",
            "settings": {"durationSeconds": duration, "imagesPerPlayer": images_per_player},
            "useDefaultImages": True,
        },
    )
    assert created.status_code == 201, created.text
    battle = created.json()
    await client.post(
        "/api/games/join",
        json={"code": battle["code"], "userId": guest, "displayName": "Sam"},
    )
    started = await client.post(f"/api/games/{battle['id']}/default-images", json={"userId": guest})
    assert started.json()["status"] == "active", started.text
    return battle["id"], host, guest


async def drain(battle_id: str) -> None:
    """Wait for the rounds running in the background, which the API does not block on."""
    from app.services.battles import drain_rounds

    await drain_rounds(battle_id)


class TestChallenges:
    async def test_upload_is_idempotent_for_identical_bytes(self, client):
        first = await create_challenge(client)
        second = await create_challenge(client)
        assert first == second

    async def test_a_players_image_joins_training_once_it_is_curated(self, client):
        player = str(uuid.uuid4())
        uploaded = await client.post(
            "/api/library/images",
            files={"image": ("mine.png", png_bytes(color="purple"), "image/png")},
            data={"userId": player},
        )
        curated = await client.post(
            "/api/challenges",
            files={"image": ("seed.png", png_bytes(color="purple"), "image/png")},
        )
        assert curated.json()["id"] == uploaded.json()["id"]

        training = await client.get("/api/challenges")
        assert curated.json()["id"] in {one["id"] for one in training.json()}

    async def test_reuploading_a_stale_curated_image_leaves_it_curated(self, client):
        from app import db

        challenge_id = await create_challenge(client, color="brown")
        # A re-analysis is forced, which is the path that rewrites where the image is stored.
        await db.challenges().update_one(
            {"_id": ObjectId(challenge_id)}, {"$set": {"analysis.version": "stale"}}
        )

        await client.post(
            "/api/library/images",
            files={"image": ("mine.png", png_bytes(color="brown"), "image/png")},
            data={"userId": str(uuid.uuid4())},
        )

        challenge = await db.challenges().find_one({"_id": ObjectId(challenge_id)})
        assert challenge["source"] == "curated"
        assert challenge["target"]["dropboxPath"].startswith("/PromptForward/Challenges/")

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
        from app.routes import learning as learning_route
        from app.services.openai.client import LLMResponseError

        challenge_id = await create_challenge(client)
        attempt_id = (
            await client.post(
                "/api/learning/attempts", json={"challengeId": challenge_id, "userId": "player-1"}
            )
        ).json()["id"]

        working_evaluate = learning_route.evaluate_prompt

        async def failing_evaluate(rubric, prompt):
            raise LLMResponseError("OpenAI is down")

        monkeypatch.setattr(learning_route, "evaluate_prompt", failing_evaluate)
        failed = await client.post(
            f"/api/learning/attempts/{attempt_id}/generate", json={"prompt": STRONG_PROMPT}
        )
        assert failed.status_code == 502

        monkeypatch.setattr(learning_route, "evaluate_prompt", working_evaluate)
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


class TestBattleMode:
    async def test_a_full_battle_scores_every_image_for_both_players(self, client):
        await seed_defaults(client, 4)
        host, guest = str(uuid.uuid4()), str(uuid.uuid4())

        created = await client.post(
            "/api/games",
            json={
                "userId": host,
                "displayName": "Kris",
                "settings": {"durationSeconds": 120, "imagesPerPlayer": 2},
                "useDefaultImages": True,
            },
        )
        assert created.status_code == 201, created.text
        battle = created.json()
        assert battle["status"] == "waiting"
        assert battle["settings"] == {"durationSeconds": 120, "imagesPerPlayer": 2}
        code, battle_id = battle["code"], battle["id"]

        joined = await client.post(
            "/api/games/join", json={"code": code.lower(), "userId": guest, "displayName": "Sam"}
        )
        assert joined.json()["status"] == "waiting"

        started = await client.post(
            f"/api/games/{battle_id}/default-images", json={"userId": guest}
        )
        body = started.json()
        # Both sides brought two images, so all four are prompted by both players.
        assert body["status"] == "active"
        assert body["totalRounds"] == 4
        assert 0 < body["secondsRemaining"] <= 120

        for user_id, prompt in ((host, STRONG_PROMPT), (guest, STRONG_PROMPT + " and neon signs")):
            for index in range(4):
                answered = await client.post(
                    f"/api/games/{battle_id}/rounds/{index}/prompt",
                    json={"userId": user_id, "prompt": prompt},
                )
                assert answered.status_code == 200, answered.text
        await drain(battle_id)

        final = (await client.get(f"/api/games/{battle_id}", params={"userId": host})).json()
        assert final["status"] == "completed"
        assert final["winner"] in {"you", "opponent", "draw"}
        for player in final["players"]:
            assert player["total"] > 0
            assert len(player["rounds"]) == 4
            for one in player["rounds"]:
                assert one["status"] == "ready"
                assert one["scores"]["final"] > 0
                assert one["imageUrl"] is not None
        # Every generated image is fetchable for the side-by-side result screen.
        image = await client.get(final["players"][0]["rounds"][0]["imageUrl"])
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

    async def test_nothing_about_scores_is_revealed_before_the_battle_ends(self, client):
        await seed_defaults(client, 4)
        battle_id, host, guest = await quick_battle(client, images_per_player=2)

        await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        await drain(battle_id)

        mid = await client.get(f"/api/games/{battle_id}", params={"userId": host})
        body = mid.json()
        assert body["status"] == "active"
        assert "scores" not in mid.text
        # No generated image is reachable either: only the targets everyone already sees.
        assert "/api/attempts/" not in mid.text
        mine = next(player for player in body["players"] if player["isYou"])
        assert mine["total"] is None
        assert mine["rounds"][0]["status"] == "ready"
        assert mine["rounds"][0]["prompt"] == STRONG_PROMPT

        opponent = next(player for player in body["players"] if not player["isYou"])
        assert opponent["rounds"] == []
        assert body["winner"] is None

    async def test_an_image_can_only_be_prompted_once(self, client):
        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(client, images_per_player=2)

        first = await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        assert first.status_code == 200
        repeat = await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT + " again"},
        )
        assert repeat.status_code == 409
        await drain(battle_id)

    async def test_a_failed_round_can_be_prompted_again(self, client, monkeypatch):
        from app.services import attempts as attempts_service

        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(client, images_per_player=2)

        working_generate = attempts_service.generate_image

        async def failing_generate(prompt, aspect_ratio):
            raise RuntimeError("Meta is down")

        monkeypatch.setattr(attempts_service, "generate_image", failing_generate)
        await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        await drain(battle_id)

        failed = (await client.get(f"/api/games/{battle_id}", params={"userId": host})).json()
        mine = next(player for player in failed["players"] if player["isYou"])
        assert mine["rounds"][0]["status"] == "failed"
        assert mine["rounds"][0]["error"]

        monkeypatch.setattr(attempts_service, "generate_image", working_generate)
        retried = await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        assert retried.status_code == 200
        await drain(battle_id)
        again = (await client.get(f"/api/games/{battle_id}", params={"userId": host})).json()
        mine = next(player for player in again["players"] if player["isYou"])
        assert mine["rounds"][0]["status"] == "ready"

    async def test_the_clock_closes_the_battle_and_unanswered_images_score_zero(self, client):
        from app.services.battles import now

        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(client, images_per_player=2)

        await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        await drain(battle_id)

        from app import db

        await db.games().update_one(
            {"_id": ObjectId(battle_id)}, {"$set": {"endsAt": now() - timedelta(seconds=30)}}
        )

        late = await client.post(
            f"/api/games/{battle_id}/rounds/1/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        assert late.status_code == 409
        assert "Time is up" in late.text

        final = (await client.get(f"/api/games/{battle_id}", params={"userId": host})).json()
        assert final["status"] == "completed"
        assert final["secondsRemaining"] == 0
        mine = next(player for player in final["players"] if player["isYou"])
        # One of two images answered, so the battle total is half of that round's score.
        assert mine["rounds"][1]["status"] == "empty"
        assert mine["rounds"][1]["scores"]["final"] == 0
        assert 0 < mine["total"] < mine["rounds"][0]["scores"]["final"]

    async def test_a_battle_that_cannot_be_filled_is_not_left_behind(self, client):
        from app import db

        await seed_defaults(client, 1)
        created = await client.post(
            "/api/games",
            json={
                "userId": "kris",
                "displayName": "Kris",
                "settings": {"durationSeconds": 120, "imagesPerPlayer": 3},
                "useDefaultImages": True,
            },
        )
        assert created.status_code == 409, created.text
        assert await db.games().count_documents({}) == 0

    async def test_games_from_before_battle_mode_do_not_block_startup(self, client):
        from app import db

        await db.games().insert_many([{"status": "completed"}, {"status": "completed"}])
        await db.ensure_indexes()

        battle = await client.post("/api/games", json={"userId": "kris", "displayName": "Kris"})
        assert battle.status_code == 201, battle.text

    async def test_settings_outside_the_allowed_range_are_rejected(self, client):
        for settings in (
            {"durationSeconds": 30, "imagesPerPlayer": 3},
            {"durationSeconds": 900, "imagesPerPlayer": 3},
            {"durationSeconds": 180, "imagesPerPlayer": 1},
            {"durationSeconds": 180, "imagesPerPlayer": 8},
        ):
            response = await client.post(
                "/api/games",
                json={"userId": "p1", "displayName": "Kris", "settings": settings},
            )
            assert response.status_code == 422, settings

    async def test_default_settings_are_three_minutes_and_three_images(self, client):
        created = await client.post("/api/games", json={"userId": "p1", "displayName": "Kris"})
        assert created.json()["settings"] == {"durationSeconds": 180, "imagesPerPlayer": 3}

    async def test_an_unknown_code_and_a_third_player_are_refused(self, client):
        await seed_defaults(client, 4)
        missing = await client.post(
            "/api/games/join", json={"code": "ZZZZZZ", "userId": "p3", "displayName": "Alex"}
        )
        assert missing.status_code == 404

        battle_id, host, _ = await quick_battle(client, images_per_player=2)
        code = (await client.get(f"/api/games/{battle_id}", params={"userId": host})).json()["code"]
        third = await client.post(
            "/api/games/join", json={"code": code, "userId": "p3", "displayName": "Alex"}
        )
        assert third.status_code == 409

    async def test_player_ids_are_never_published(self, client):
        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(
            client, images_per_player=2, host="secret-alice", guest="secret-bob"
        )
        await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        await drain(battle_id)

        as_opponent = await client.get(f"/api/games/{battle_id}", params={"userId": "secret-bob"})
        assert "secret-alice" not in as_opponent.text


class TestBattleImages:
    async def test_uploaded_images_belong_to_the_account_and_stay_out_of_training(self, client):
        player = str(uuid.uuid4())
        uploaded = await client.post(
            "/api/library/images",
            files={"image": ("mine.png", png_bytes(color="purple"), "image/png")},
            data={"userId": player},
        )
        assert uploaded.status_code == 201, uploaded.text
        challenge_id = uploaded.json()["id"]

        listed = await client.get("/api/library/images", params={"userId": player})
        assert [image["id"] for image in listed.json()] == [challenge_id]

        # Another account never sees it, and the training pool never offers it.
        other = await client.get("/api/library/images", params={"userId": "someone-else"})
        assert other.json() == []
        training = await client.get("/api/challenges")
        assert challenge_id not in {one["id"] for one in training.json()}

        dropped = await client.delete(
            f"/api/library/images/{challenge_id}", params={"userId": player}
        )
        assert dropped.status_code == 204
        assert (await client.get("/api/library/images", params={"userId": player})).json() == []

    def test_a_file_that_is_not_an_image_is_rejected(self):
        with pytest.raises(ImageStorageError):
            read_image_meta(b"not an image at all")

    async def test_uploaded_images_are_battled_alongside_the_opponents(self, client):
        await seed_defaults(client, 4)
        host, guest = str(uuid.uuid4()), str(uuid.uuid4())
        mine = await upload_image(client, host, "purple")
        theirs = await upload_image(client, guest, "green")

        battle_id = (
            await client.post(
                "/api/games",
                json={
                    "userId": host,
                    "displayName": "Kris",
                    "settings": {"durationSeconds": 60, "imagesPerPlayer": 2},
                },
            )
        ).json()["id"]
        code = (await client.get(f"/api/games/{battle_id}", params={"userId": host})).json()["code"]
        await client.post(
            "/api/games/join", json={"code": code, "userId": guest, "displayName": "Sam"}
        )

        added = await client.post(
            f"/api/games/{battle_id}/images", json={"userId": host, "challengeId": mine}
        )
        assert added.status_code == 200
        me = next(player for player in added.json()["players"] if player["isYou"])
        assert [image["challengeId"] for image in me["images"]] == [mine]
        assert me["ready"] is False

        # An image somebody else owns cannot be dragged into the pool.
        stolen = await client.post(
            f"/api/games/{battle_id}/images", json={"userId": host, "challengeId": theirs}
        )
        assert stolen.status_code == 403

        dropped = await client.delete(
            f"/api/games/{battle_id}/images/{mine}", params={"userId": host}
        )
        assert dropped.json()["players"][0]["imagesChosen"] == 0

        await client.post(
            f"/api/games/{battle_id}/images", json={"userId": host, "challengeId": mine}
        )
        await client.post(f"/api/games/{battle_id}/default-images", json={"userId": host})
        await client.post(
            f"/api/games/{battle_id}/images", json={"userId": guest, "challengeId": theirs}
        )
        running = await client.post(
            f"/api/games/{battle_id}/default-images", json={"userId": guest}
        )
        assert running.json()["status"] == "active"
        assert running.json()["totalRounds"] == 4

    async def test_a_player_cannot_bring_more_images_than_agreed(self, client):
        player = str(uuid.uuid4())
        first = await upload_image(client, player, "purple")
        second = await upload_image(client, player, "green")
        third = await upload_image(client, player, "red")

        battle_id = (
            await client.post(
                "/api/games",
                json={
                    "userId": player,
                    "displayName": "Kris",
                    "settings": {"durationSeconds": 60, "imagesPerPlayer": 2},
                },
            )
        ).json()["id"]
        for challenge_id in (first, second):
            added = await client.post(
                f"/api/games/{battle_id}/images",
                json={"userId": player, "challengeId": challenge_id},
            )
            assert added.status_code == 200
        extra = await client.post(
            f"/api/games/{battle_id}/images", json={"userId": player, "challengeId": third}
        )
        assert extra.status_code == 409

    async def test_filling_with_defaults_twice_at_once_never_overfills(self, client):
        await seed_defaults(client, 8)
        player = str(uuid.uuid4())
        battle_id = (
            await client.post(
                "/api/games",
                json={
                    "userId": player,
                    "displayName": "Kris",
                    "settings": {"durationSeconds": 60, "imagesPerPlayer": 4},
                },
            )
        ).json()["id"]

        await asyncio.gather(
            *[
                client.post(f"/api/games/{battle_id}/default-images", json={"userId": player})
                for _ in range(3)
            ]
        )

        battle = (await client.get(f"/api/games/{battle_id}", params={"userId": player})).json()
        assert battle["players"][0]["imagesChosen"] == 4

    async def test_an_image_removed_while_starting_is_not_put_back(self, client):
        from app import db
        from app.services import battles

        await seed_defaults(client, 4)
        host, guest = str(uuid.uuid4()), str(uuid.uuid4())
        created = await client.post(
            "/api/games",
            json={
                "userId": host,
                "displayName": "Kris",
                "settings": {"durationSeconds": 60, "imagesPerPlayer": 2},
                "useDefaultImages": True,
            },
        )
        battle_id = created.json()["id"]
        await client.post(
            "/api/games/join",
            json={"code": created.json()["code"], "userId": guest, "displayName": "Sam"},
        )
        mine = await upload_image(client, guest, "purple")
        theirs = await upload_image(client, guest, "green")
        for challenge_id in (mine, theirs):
            await client.post(
                f"/api/games/{battle_id}/images",
                json={"userId": guest, "challengeId": challenge_id},
            )
        # The battle started on the second image, so it is wound back to the instant before.
        await db.games().update_one(
            {"_id": ObjectId(battle_id)},
            {"$set": {"status": "waiting", "startedAt": None, "endsAt": None, "challengeIds": []}},
        )
        stale = await battles.load_battle(battle_id)

        dropped = await client.delete(
            f"/api/games/{battle_id}/images/{theirs}", params={"userId": guest}
        )
        assert dropped.status_code == 200

        started = await battles.start_if_ready(stale)
        assert started["status"] == "waiting"
        assert [player["challengeIds"] for player in started["players"]][1] == [ObjectId(mine)]

    async def test_a_round_whose_scoring_fails_is_retried(self, client, monkeypatch):
        from app import db
        from app.services import attempts as attempts_service
        from app.services import battles

        monkeypatch.setattr(battles, "FINALIZE_BACKOFF_SECONDS", 0)
        calls = 0

        async def flaky_submit(attempt_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("mongo went away")
            return await attempts_service.submit_attempt(attempt_id)

        monkeypatch.setattr(battles, "submit_attempt", flaky_submit)

        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(client, images_per_player=2)
        await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        await drain(battle_id)

        game = await db.games().find_one({"_id": ObjectId(battle_id)})
        player = next(one for one in game["players"] if one["userId"] == host)
        attempt = await db.attempts().find_one({"_id": player["attemptIds"][0]})
        assert calls == 2
        assert attempt["status"] == "submitted"
        assert attempt["scores"]["final"] > 0

    async def test_defaults_come_from_dropbox_challenges_not_uploads(self, client):
        from app import db

        seeded = await seed_defaults(client, 4)
        host, guest = str(uuid.uuid4()), str(uuid.uuid4())
        uploaded = await upload_image(client, host, "purple")

        created = await client.post(
            "/api/games",
            json={
                "userId": host,
                "displayName": "Kris",
                "settings": {"durationSeconds": 60, "imagesPerPlayer": 2},
                "useDefaultImages": True,
            },
        )
        battle_id = created.json()["id"]
        await client.post(
            "/api/games/join",
            json={"code": created.json()["code"], "userId": guest, "displayName": "Sam"},
        )
        await client.post(f"/api/games/{battle_id}/default-images", json={"userId": guest})

        game = await db.games().find_one({"_id": ObjectId(battle_id)})
        chosen = {str(one) for player in game["players"] for one in player["challengeIds"]}
        assert chosen <= set(seeded)
        assert uploaded not in chosen

    async def test_defaults_match_lowercased_dropbox_paths(self, client):
        from app import db

        seeded = await seed_defaults(client, 2)
        await db.challenges().update_many(
            {"_id": {"$in": [ObjectId(one) for one in seeded]}},
            [{"$set": {"target.dropboxPath": {"$toLower": "$target.dropboxPath"}}}],
        )
        host = str(uuid.uuid4())

        created = await client.post(
            "/api/games",
            json={
                "userId": host,
                "displayName": "Kris",
                "settings": {"durationSeconds": 60, "imagesPerPlayer": 2},
                "useDefaultImages": True,
            },
        )

        assert created.status_code == 201
        game = await db.games().find_one({"_id": ObjectId(created.json()["id"])})
        assert {str(one) for one in game["players"][0]["challengeIds"]} == set(seeded)

    async def test_a_retried_round_records_its_evaluation_once(self, client, monkeypatch):
        from app import db
        from app.services import battles

        monkeypatch.setattr(battles, "FINALIZE_BACKOFF_SECONDS", 0)
        calls = 0
        original = battles._attach_evaluation

        async def flaky_attach(attempt_id, generation_number, evaluation):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("mongo went away")
            return await original(attempt_id, generation_number, evaluation)

        monkeypatch.setattr(battles, "_attach_evaluation", flaky_attach)

        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(client, images_per_player=2)
        await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": STRONG_PROMPT},
        )
        await drain(battle_id)

        game = await db.games().find_one({"_id": ObjectId(battle_id)})
        player = next(one for one in game["players"] if one["userId"] == host)
        attempt = await db.attempts().find_one({"_id": player["attemptIds"][0]})
        assert calls == 2
        assert len(attempt["promptEvaluations"]) == 1
        assert attempt["generations"][0]["promptEvaluation"] is not None

    async def test_oversized_prompts_are_rejected(self, client):
        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(client, images_per_player=2)
        oversized = await client.post(
            f"/api/games/{battle_id}/rounds/0/prompt",
            json={"userId": host, "prompt": "x" * 2001},
        )
        assert oversized.status_code == 422


async def completed_battle(
    *,
    players: list[tuple[str, str]],
    totals: dict[str, float],
    winner: str | None,
    finished_at,
) -> None:
    """A battle already in the books, written the way finish_if_ready leaves one."""
    from app import db
    from app.services.battles import new_code

    await db.games().insert_one(
        {
            "code": new_code(),
            "hostUserId": players[0][0],
            "settings": {"durationSeconds": 120, "imagesPerPlayer": 2},
            "players": [
                {
                    "userId": user_id,
                    "displayName": name,
                    "challengeIds": [],
                    "usedDefaults": True,
                    "attemptIds": [],
                }
                for user_id, name in players
            ],
            "challengeIds": [],
            "status": "completed",
            "winnerUserId": winner,
            "scoreboard": [
                {"userId": user_id, "total": totals[user_id], "resultQuality": 0, "promptTokens": 0}
                for user_id, _ in players
            ],
            "createdAt": finished_at,
            "startedAt": finished_at,
            "endsAt": finished_at,
            "completedAt": finished_at,
        }
    )


class TestStandings:
    async def test_leaderboard_ranks_by_wins_and_tracks_streaks(self, client):
        from app.services.battles import now

        kris, sam = str(uuid.uuid4()), str(uuid.uuid4())
        start = now() - timedelta(hours=3)
        for index, winner in enumerate([kris, kris, sam]):
            await completed_battle(
                players=[(kris, "Kris"), (sam, "Sam")],
                totals={kris: 80, sam: 40},
                winner=winner,
                finished_at=start + timedelta(minutes=index),
            )

        standings = (await client.get("/api/standings", params={"userId": kris})).json()
        first, second = standings["leaderboard"]

        assert (first["displayName"], first["wins"], first["losses"]) == ("Kris", 2, 1)
        assert first["isYou"] is True
        assert first["winRate"] == pytest.approx(66.7)
        assert first["averageScore"] == pytest.approx(80)
        # The last battle was a loss, so they are on a losing run; the best win run stands.
        assert first["streak"] == {"result": "loss", "length": 1}
        assert (first["currentStreak"], first["bestStreak"]) == (0, 2)

        assert (second["displayName"], second["wins"]) == ("Sam", 1)
        assert second["streak"] == {"result": "win", "length": 1}
        assert (second["currentStreak"], second["bestStreak"]) == (1, 1)

    async def test_a_run_of_draws_is_its_own_streak(self, client):
        from app.services.battles import now

        kris, sam = str(uuid.uuid4()), str(uuid.uuid4())
        start = now() - timedelta(hours=2)
        for index in range(2):
            await completed_battle(
                players=[(kris, "Kris"), (sam, "Sam")],
                totals={kris: 60, sam: 60},
                winner=None,
                finished_at=start + timedelta(minutes=index),
            )

        standings = (await client.get("/api/standings", params={"userId": kris})).json()
        assert standings["you"]["draws"] == 2
        assert standings["you"]["streak"] == {"result": "draw", "length": 2}
        assert (standings["you"]["currentStreak"], standings["you"]["bestStreak"]) == (0, 0)

    async def test_head_to_head_is_read_from_the_viewers_side(self, client):
        from app.services.battles import now

        kris, sam, ada = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        finished = now() - timedelta(hours=1)
        await completed_battle(
            players=[(kris, "Kris"), (sam, "Sam")],
            totals={kris: 70, sam: 50},
            winner=kris,
            finished_at=finished,
        )
        await completed_battle(
            players=[(kris, "Kris"), (ada, "Ada")],
            totals={kris: 30, ada: 90},
            winner=ada,
            finished_at=finished + timedelta(minutes=1),
        )

        mine = (await client.get("/api/standings", params={"userId": kris})).json()
        assert {one["opponent"]: (one["wins"], one["losses"]) for one in mine["headToHead"]} == {
            "Sam": (1, 0),
            "Ada": (0, 1),
        }

        theirs = (await client.get("/api/standings", params={"userId": sam})).json()
        assert theirs["headToHead"] == [
            {
                "opponent": "Kris",
                "wins": 0,
                "losses": 1,
                "draws": 0,
                "lastResult": "loss",
                "lastPlayedAt": theirs["headToHead"][0]["lastPlayedAt"],
            }
        ]

    async def test_a_battle_counts_once_it_has_finished(self, client):
        from app.services.battles import now

        await seed_defaults(client, 4)
        battle_id, host, _ = await quick_battle(client, images_per_player=2)

        before = (await client.get("/api/standings", params={"userId": host})).json()
        assert before["leaderboard"] == [] and before["you"] is None

        from app import db

        await db.games().update_one(
            {"_id": ObjectId(battle_id)}, {"$set": {"endsAt": now() - timedelta(seconds=30)}}
        )
        assert (await client.get(f"/api/games/{battle_id}", params={"userId": host})).json()[
            "status"
        ] == "completed"

        after = (await client.get("/api/standings", params={"userId": host})).json()
        assert after["you"]["battles"] == 1
        assert len(after["leaderboard"]) == 2


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
