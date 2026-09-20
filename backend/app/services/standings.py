"""Battle standings: the leaderboard, the viewer's match history, and win streaks.

Everything here is derived from completed battles rather than kept in a running tally, so a
battle that is finished, replayed, or removed never leaves the records disagreeing with the
games they are counted from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app import db

Result = Literal["win", "loss", "draw"]


@dataclass
class _Record:
    """One player's running tally as their battles are walked oldest to newest."""

    display_name: str
    wins: int = 0
    losses: int = 0
    draws: int = 0
    score_total: float = 0.0
    # The run of identical results they are on now, win or otherwise, and their best win run.
    streak_result: Result | None = None
    streak_length: int = 0
    best_streak: int = 0
    last_played_at: datetime | None = None

    @property
    def battles(self) -> int:
        return self.wins + self.losses + self.draws

    def add(self, result: Result, score: float, played_at: datetime | None) -> None:
        if result == "win":
            self.wins += 1
        elif result == "loss":
            self.losses += 1
        else:
            self.draws += 1
        self.score_total += score
        self.streak_length = self.streak_length + 1 if result == self.streak_result else 1
        self.streak_result = result
        if result == "win":
            self.best_streak = max(self.best_streak, self.streak_length)
        self.last_played_at = played_at or self.last_played_at


def _result_of(game: dict[str, Any], user_id: str) -> Result:
    winner = game.get("winnerUserId")
    if winner is None:
        return "draw"
    return "win" if winner == user_id else "loss"


async def _records(viewer_id: str) -> tuple[dict[str, _Record], list[dict[str, Any]]]:
    """Walk every completed battle oldest first, tallying both players as it goes.

    The same walk collects the viewer's own battles, newest last, as their match history.

    Only battles count: a pre-Battle game kept its scores on the attempts, so counting one
    would add a battle worth zero to both players' averages.
    """
    records: dict[str, _Record] = {}
    history: list[dict[str, Any]] = []
    cursor = (
        db.games()
        .find(
            {
                "status": "completed",
                "players.1": {"$exists": True},
                "code": {"$type": "string"},
                "scoreboard": {"$type": "array"},
            },
            {
                "players.userId": 1,
                "players.displayName": 1,
                "scoreboard": 1,
                "winnerUserId": 1,
                "completedAt": 1,
            },
        )
        .sort("completedAt", 1)
    )

    async for game in cursor:
        totals = {entry["userId"]: entry.get("total") or 0 for entry in game.get("scoreboard", [])}
        played_at = game.get("completedAt")
        players = game["players"]
        for player in players:
            user_id = player["userId"]
            record = records.setdefault(user_id, _Record(player["displayName"]))
            # Names can change between battles; the most recent one wins.
            record.display_name = player["displayName"]
            result = _result_of(game, user_id)
            record.add(result, totals.get(user_id, 0), played_at)

            if user_id != viewer_id:
                continue
            opponent = next(one for one in players if one["userId"] != user_id)
            history.append(
                {
                    "opponent": opponent["displayName"],
                    "result": result,
                    "yourScore": round(totals.get(user_id, 0), 1),
                    "theirScore": round(totals.get(opponent["userId"], 0), 1),
                    "playedAt": played_at,
                }
            )

    return records, history


def _win_rate(record: _Record) -> float:
    return round(100 * record.wins / record.battles, 1) if record.battles else 0.0


def _entry(record: _Record, *, is_you: bool) -> dict[str, Any]:
    return {
        "displayName": record.display_name,
        "isYou": is_you,
        "battles": record.battles,
        "wins": record.wins,
        "losses": record.losses,
        "draws": record.draws,
        "winRate": _win_rate(record),
        "averageScore": round(record.score_total / record.battles, 1) if record.battles else 0.0,
        "streak": {"result": record.streak_result, "length": record.streak_length},
        "currentStreak": record.streak_length if record.streak_result == "win" else 0,
        "bestStreak": record.best_streak,
        "lastPlayedAt": record.last_played_at,
    }


async def standings(viewer_id: str, limit: int) -> dict[str, Any]:
    """The leaderboard plus, for the viewer, the battles they have played, newest first.

    Player ids stay on the server: a player is published by display name only.
    """
    records, history = await _records(viewer_id)

    # Names break any remaining tie so the same battles always produce the same order.
    by_name = sorted(records.items(), key=lambda pair: pair[1].display_name.lower())
    ranked = sorted(
        by_name,
        key=lambda pair: (
            pair[1].wins,
            _win_rate(pair[1]),
            pair[1].score_total / pair[1].battles if pair[1].battles else 0,
        ),
        reverse=True,
    )
    ranks = {user_id: rank for rank, (user_id, _) in enumerate(ranked, start=1)}
    leaderboard = [
        {"rank": ranks[user_id], **_entry(record, is_you=user_id == viewer_id)}
        for user_id, record in ranked[:limit]
    ]

    you = records.get(viewer_id)

    return {
        "leaderboard": leaderboard,
        # Carries the viewer's rank even when they sit below the published cut.
        "you": {"rank": ranks[viewer_id], **_entry(you, is_you=True)} if you else None,
        "matches": list(reversed(history))[:limit],
    }
