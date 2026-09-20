"""The problem set: the curriculum as a list, with the caller's progress folded in."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routes.auth import optional_user
from app.services.problems import list_problems

router = APIRouter(prefix="/api/problems", tags=["problems"])


@router.get("")
async def get_problems(user: dict | None = Depends(optional_user)) -> dict:
    return await list_problems(user["_id"] if user else None)
