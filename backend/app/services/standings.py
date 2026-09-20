"""Battle standings: the leaderboard, head-to-head records, and win streaks.

Everything here is derived from completed battles rather than kept in a running tally, so a
battle that is finished, replayed, or removed never leaves the records disagreeing with the
games they are counted from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    current_streak: int = 0
    best_streak: int = 0
    last_played_at: datetime | None = None
    # Keyed by opponent id: the same walk builds the head-to-head records.
    opponents: dict[str, _Head] = field(default_factory=dict)

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
        # A draw or a loss both end a streak: only wins in a row count.
        self.current_streak = self.current_streak + 1 if result == "win" else 0
        self.best_streak = max(self.best_streak, self.current_streak)
        self.last_played_at = played_at or self.last_played_at


@dataclass
class _Head:
    display_name: str
    wins: int = 0
    losses: int = 0
    draws: int = 0
    last_result: Result | None = None
    last_played_at: datetime | None = None

    def add(self, result: Result, played_at: datetime | None) -> None:
        if result == "win":
            self.wins += 1
        elif result == "loss":
            self.losses += 1
        else:
            self.draws += 1
        self.last_result = result
        self.last_played_at = played_at or self.last_played_at


def _result_of(game: dict[str, Any], user_id: str) -> Result:
    winner = game.get("winnerUserId")
    if winner is None:
        return "draw"
    return "win" if winner == user_id else "loss"


async def _records() -> dict[str, _Record]:
    """Walk every completed battle oldest first, tallying both players as it goes."""
    records: dict[str, _Record] = {}
    cursor = (
        db.games()
        .find(
            {"status": "completed", "players.1": {"$exists": True}},
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

            for other in players:
                if other["userId"] == user_id:
                    continue
                head = record.opponents.setdefault(other["userId"], _Head(other["displayName"]))
                head.display_name = other["displayName"]
                head.add(result, played_at)

    return records


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
        "currentStreak": record.current_streak,
        "bestStreak": record.best_streak,
        "lastPlayedAt": record.last_played_at,
    }


async def standings(viewer_id: str, limit: int) -> dict[str, Any]:
    """The leaderboard plus, for the viewer, their record against everyone they have played.

    Player ids stay on the server: a player is published by display name only.
    """
    records = await _records()

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
    head_to_head = sorted(
        (
            {
                "opponent": head.display_name,
                "wins": head.wins,
                "losses": head.losses,
                "draws": head.draws,
                "lastResult": head.last_result,
                "lastPlayedAt": head.last_played_at,
            }
            for head in (you.opponents.values() if you else ())
        ),
        key=lambda one: (-(one["wins"] + one["losses"] + one["draws"]), one["opponent"].lower()),
    )

    return {
        "leaderboard": leaderboard,
        # Carries the viewer's rank even when they sit below the published cut.
        "you": {"rank": ranks[viewer_id], **_entry(you, is_you=True)} if you else None,
        "headToHead": head_to_head,
    }
