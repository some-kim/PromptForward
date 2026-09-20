"""Battle standings routes: leaderboard, match history, and win streaks."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.standings import standings

router = APIRouter(prefix="/api/standings", tags=["standings"])

MAX_IDENTITY_CHARS = 120
DEFAULT_LIMIT = 10
MAX_LIMIT = 50


@router.get("")
async def get_standings(
    userId: str = Query(..., max_length=MAX_IDENTITY_CHARS),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict:
    return await standings(userId, limit)
