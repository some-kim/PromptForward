"""Battle Mode: two players, a shared pool of images, one timed prompt per image.

A battle is joined with a short code. Each player brings `imagesPerPlayer` images — uploaded or
filled in from the curated pool — and both players then prompt every image in the combined pool
against a single clock. Nothing about how a prompt scored is revealed until the battle is over.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app import db
from app.models import BattleSettings, PromptEvaluation
from app.services.attempts import (
    GAME_GENERATION_LIMIT,
    GenerationLimitReached,
    create_attempt,
    record_prompt_evaluation,
    release_generation,
    reserve_generation,
    run_generation,
    submit_attempt,
)
from app.services.challenges import rubric_of
from app.services.openai.prompt_evaluator import evaluate_prompt
from app.services.scoring.final_score import PlayerOutcome, pick_winner

# No I, O, 0 or 1: the code is read out loud and typed by hand.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
CODE_ATTEMPTS = 10

# A prompt sent as the clock runs out still counts: the buzzer is enforced on the server, and
# the grace covers the round trip rather than the player's thinking time.
SUBMIT_GRACE_SECONDS = 3


class BattleError(RuntimeError):
    """A request that is not allowed in the battle's current state."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """MongoDB hands datetimes back naive, so they are re-tagged as UTC before comparison."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def new_code() -> str:
    return "".join(random.choices(CODE_ALPHABET, k=CODE_LENGTH))


async def create_battle(
    *, user_id: str, display_name: str, settings: BattleSettings, use_defaults: bool
) -> dict[str, Any]:
    document = {
        "code": new_code(),
        "hostUserId": user_id,
        "settings": settings.model_dump(),
        "players": [_new_player(user_id, display_name)],
        "challengeIds": [],
        "status": "waiting",
        "winnerUserId": None,
        "scoreboard": [],
        "createdAt": now(),
        "startedAt": None,
        "endsAt": None,
        "completedAt": None,
    }

    for _ in range(CODE_ATTEMPTS):
        try:
            result = await db.games().insert_one(document)
        except DuplicateKeyError:
            document["code"] = new_code()
            continue
        game = {**document, "_id": result.inserted_id}
        if not use_defaults:
            return game
        try:
            return await fill_with_defaults(game, user_id)
        except BattleError:
            # The host never learns this battle's id, so it would sit unreachable on its code.
            await db.games().delete_one({"_id": result.inserted_id, "status": "waiting"})
            raise

    raise BattleError("Could not allocate a battle code, try again", status=503)


def _new_player(user_id: str, display_name: str) -> dict[str, Any]:
    return {
        "userId": user_id,
        "displayName": display_name,
        "challengeIds": [],
        "usedDefaults": False,
        "attemptIds": [],
    }


async def load_battle(game_id: str) -> dict[str, Any]:
    identifier = ObjectId(game_id) if ObjectId.is_valid(game_id) else None
    game = await db.games().find_one({"_id": identifier}) if identifier else None
    if game is None:
        raise BattleError("Battle not found", status=404)
    return game


async def load_by_code(code: str) -> dict[str, Any]:
    game = await db.games().find_one({"code": code.strip().upper()})
    if game is None:
        raise BattleError("No battle has that code", status=404)
    return game


async def join_battle(*, code: str, user_id: str, display_name: str) -> dict[str, Any]:
    game = await load_by_code(code)
    if any(player["userId"] == user_id for player in game["players"]):
        return game
    if game["status"] != "waiting":
        raise BattleError("That battle has already started")

    joined = await db.games().find_one_and_update(
        {"_id": game["_id"], "status": "waiting", "players.1": {"$exists": False}},
        {"$push": {"players": _new_player(user_id, display_name)}},
        return_document=True,
    )
    if joined is None:
        raise BattleError("That battle already has two players")
    return joined


async def add_image(game: dict[str, Any], user_id: str, challenge_id: ObjectId) -> dict[str, Any]:
    """Add one image to the player's side of the pool, never past the agreed count."""
    limit = game["settings"]["imagesPerPlayer"]
    updated = await db.games().find_one_and_update(
        {
            "_id": game["_id"],
            "status": "waiting",
            "players": {
                "$elemMatch": {"userId": user_id, f"challengeIds.{limit - 1}": {"$exists": False}}
            },
        },
        {
            "$push": {"players.$.challengeIds": challenge_id},
            "$set": {"players.$.usedDefaults": False},
        },
        return_document=True,
    )
    if updated is None:
        raise BattleError(f"You have already chosen {limit} images")
    return await start_if_ready(updated)


async def remove_image(
    game: dict[str, Any], user_id: str, challenge_id: ObjectId
) -> dict[str, Any]:
    updated = await db.games().find_one_and_update(
        {"_id": game["_id"], "status": "waiting", "players.userId": user_id},
        {"$pull": {"players.$.challengeIds": challenge_id}},
        return_document=True,
    )
    if updated is None:
        raise BattleError("Images can only change before the battle starts")
    return updated


async def fill_with_defaults(game: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Fill the player's remaining slots from the curated pool."""
    player = _player_of(game, user_id)
    held = len(player["challengeIds"])
    missing = game["settings"]["imagesPerPlayer"] - held
    if missing <= 0:
        return game

    taken = [challenge_id for one in game["players"] for challenge_id in one["challengeIds"]]
    sampled = (
        await db.challenges()
        .aggregate(
            [
                {"$match": {"source": {"$ne": "player"}, "_id": {"$nin": taken}}},
                {"$sample": {"size": missing}},
                {"$project": {"_id": 1}},
            ]
        )
        .to_list(missing)
    )
    if len(sampled) < missing:
        raise BattleError("Not enough images have been seeded to fill the battle")

    # Conditional on the count this fill was computed from, so two fills cannot both append.
    updated = await db.games().find_one_and_update(
        {
            "_id": game["_id"],
            "status": "waiting",
            "players": {"$elemMatch": {"userId": user_id, "challengeIds": {"$size": held}}},
        },
        {
            "$push": {"players.$.challengeIds": {"$each": [one["_id"] for one in sampled]}},
            "$set": {"players.$.usedDefaults": True},
        },
        return_document=True,
    )
    if updated is None:
        raise BattleError("Your images changed while filling, try again")
    return await start_if_ready(updated)


async def start_if_ready(game: dict[str, Any]) -> dict[str, Any]:
    """Start once both players have brought their images: the clock runs from here."""
    per_player = game["settings"]["imagesPerPlayer"]
    if game["status"] != "waiting" or len(game["players"]) < 2:
        return game
    if any(len(player["challengeIds"]) < per_player for player in game["players"]):
        return game

    pool = [challenge_id for player in game["players"] for challenge_id in player["challengeIds"]]
    random.shuffle(pool)

    # Attempts first: a client polling the moment the battle flips to active must never find an
    # active battle whose rounds do not exist yet.
    attempts_by_player = {
        player["userId"]: [
            await create_attempt(
                challenge_id=challenge_id,
                user_id=player["userId"],
                display_name=player["displayName"],
                mode="game",
                game_id=game["_id"],
            )
            for challenge_id in pool
        ]
        for player in game["players"]
    }

    started = now()
    players = [
        {
            **player,
            "attemptIds": [attempt["_id"] for attempt in attempts_by_player[player["userId"]]],
        }
        for player in game["players"]
    ]
    updated = await db.games().find_one_and_update(
        {"_id": game["_id"], "status": "waiting"},
        {
            "$set": {
                "status": "active",
                "challengeIds": pool,
                "players": players,
                "startedAt": started,
                "endsAt": started + timedelta(seconds=game["settings"]["durationSeconds"]),
            }
        },
        return_document=True,
    )
    if updated is None:
        # Another request started the battle first; these attempts belong to no round.
        ids = [attempt["_id"] for group in attempts_by_player.values() for attempt in group]
        await db.attempts().delete_many({"_id": {"$in": ids}})
        return await db.games().find_one({"_id": game["_id"]})
    return updated


def _player_of(game: dict[str, Any], user_id: str) -> dict[str, Any]:
    player = next((one for one in game["players"] if one["userId"] == user_id), None)
    if player is None:
        raise BattleError("You are not in this battle", status=404)
    return player


def seconds_remaining(game: dict[str, Any], at: datetime | None = None) -> int | None:
    ends_at = _aware(game.get("endsAt"))
    if ends_at is None:
        return None
    return max(0, int((ends_at - (at or now())).total_seconds()))


async def submit_round(
    game: dict[str, Any], user_id: str, index: int, prompt: str
) -> dict[str, Any]:
    """Take a prompt for one image and start its generation in the background.

    The player is not held up by the provider: the round reports as working and the battle
    finishes once every started round has landed.
    """
    if game["status"] != "active":
        raise BattleError("This battle is not running")

    ends_at = _aware(game["endsAt"])
    if ends_at is not None and now() > ends_at + timedelta(seconds=SUBMIT_GRACE_SECONDS):
        await finish_if_ready(game["_id"])
        raise BattleError("Time is up")

    player = _player_of(game, user_id)
    if not 0 <= index < len(player["attemptIds"]):
        raise BattleError("No such image in this battle", status=404)

    attempt_id = player["attemptIds"][index]
    try:
        generation_number = await reserve_generation(
            attempt_id, limit=GAME_GENERATION_LIMIT, gate_prompt=None
        )
    except GenerationLimitReached as error:
        raise BattleError("You have already prompted this image") from error

    # The prompt is echoed back to its author while the round works, before the generation
    # that carries it exists.
    await db.attempts().update_one(
        {"_id": attempt_id}, {"$set": {"lastError": None, "pendingPrompt": prompt}}
    )
    _track(
        game["_id"],
        _run_round(
            game_id=game["_id"],
            attempt_id=attempt_id,
            challenge_id=game["challengeIds"][index],
            prompt=prompt,
            generation_number=generation_number,
        ),
    )
    return await db.games().find_one({"_id": game["_id"]})


# In-flight rounds per battle. A battle whose clock ran out still waits for these, so a player
# who submitted on the buzzer keeps the image they paid for.
_ROUNDS: dict[str, set[asyncio.Task[None]]] = {}


def _track(game_id: ObjectId, coroutine: Any) -> None:
    key = str(game_id)
    task = asyncio.create_task(coroutine)
    _ROUNDS.setdefault(key, set()).add(task)

    def _done(finished: asyncio.Task[None]) -> None:
        pending = _ROUNDS.get(key)
        if pending is None:
            return
        pending.discard(finished)
        if not pending:
            _ROUNDS.pop(key, None)

    task.add_done_callback(_done)


def rounds_in_flight(game_id: ObjectId) -> int:
    return len(_ROUNDS.get(str(game_id), ()))


async def drain_rounds(game_id: ObjectId | str) -> None:
    """Wait until every round started for this battle has landed."""
    while pending := _ROUNDS.get(str(game_id)):
        await asyncio.gather(*list(pending), return_exceptions=True)


async def _run_round(
    *,
    game_id: ObjectId,
    attempt_id: ObjectId,
    challenge_id: ObjectId,
    prompt: str,
    generation_number: int,
) -> None:
    attempt = await db.attempts().find_one({"_id": attempt_id})
    challenge = await db.challenges().find_one({"_id": challenge_id})

    evaluation, generated = await asyncio.gather(
        evaluate_prompt(rubric_of(challenge), prompt),
        run_generation(
            attempt=attempt,
            challenge=challenge,
            prompt=prompt,
            generation_number=generation_number,
            prompt_evaluation=None,
        ),
        return_exceptions=True,
    )

    if isinstance(generated, BaseException):
        # Nothing was stored, so the slot goes back and the player may prompt this image again.
        await release_generation(attempt_id, generation_number)
        await db.attempts().update_one({"_id": attempt_id}, {"$set": {"lastError": str(generated)}})
        return

    if isinstance(evaluation, BaseException):
        # The image stands. Prompt quality is simply missing from this round's score.
        await db.attempts().update_one(
            {"_id": attempt_id}, {"$set": {"lastError": str(evaluation)}}
        )
    else:
        await _store_evaluation(attempt_id, generation_number, prompt, evaluation)

    await submit_attempt(attempt_id)
    await finish_if_ready(game_id)


async def _store_evaluation(
    attempt_id: ObjectId, generation_number: int, prompt: str, evaluation: PromptEvaluation
) -> None:
    await record_prompt_evaluation(attempt_id, prompt, evaluation)
    await db.attempts().update_one(
        {"_id": attempt_id, "generations.number": generation_number},
        {"$set": {"generations.$.promptEvaluation": evaluation.model_dump()}},
    )


async def attempts_of(game: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ids = [attempt_id for player in game["players"] for attempt_id in player["attemptIds"]]
    cursor = db.attempts().find({"_id": {"$in": ids}})
    return {str(attempt["_id"]): attempt async for attempt in cursor}


async def finish_if_ready(game_id: ObjectId) -> dict[str, Any]:
    """Complete the battle once both players are done, or once the clock has run out."""
    game = await db.games().find_one({"_id": game_id})
    if game["status"] != "active":
        return game

    attempts = await attempts_of(game)
    everyone_finished = bool(attempts) and all(
        attempt["status"] == "submitted" for attempt in attempts.values()
    )
    # The same deadline `submit_round` accepts against, so a poll cannot close the grace window.
    ends_at = _aware(game.get("endsAt"))
    expired = ends_at is not None and now() > ends_at + timedelta(seconds=SUBMIT_GRACE_SECONDS)
    if not everyone_finished and not (expired and rounds_in_flight(game_id) == 0):
        return game

    scoreboard = [_player_outcome(player, attempts) for player in game["players"]]
    winner = pick_winner(
        [
            PlayerOutcome(
                userId=entry["userId"],
                finalScore=entry["total"],
                resultQuality=entry["resultQuality"],
                promptTokens=entry["promptTokens"],
            )
            for entry in scoreboard
        ]
    )

    completed = await db.games().find_one_and_update(
        {"_id": game_id, "status": "active"},
        {
            "$set": {
                "status": "completed",
                "scoreboard": scoreboard,
                "winnerUserId": winner,
                "completedAt": now(),
            }
        },
        return_document=True,
    )
    return completed or await db.games().find_one({"_id": game_id})


def _player_outcome(player: dict[str, Any], attempts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A player's battle score: the average of their rounds, with a skipped image worth zero."""
    rounds = [attempts.get(str(attempt_id)) or {} for attempt_id in player["attemptIds"]]
    scores = [(one.get("scores") or {}) for one in rounds]
    count = max(1, len(rounds))
    return {
        "userId": player["userId"],
        # Unrounded: the winner is picked from these, and rounding can collapse a real gap.
        "total": sum(score.get("final") or 0 for score in scores) / count,
        "resultQuality": sum(score.get("resultQuality") or 0 for score in scores) / count,
        "promptTokens": sum(
            generation["usage"]["promptTokens"]
            for one in rounds
            for generation in one.get("generations", [])
        ),
    }
