"""The problem set: the curriculum as a list, with the caller's progress folded in."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.services.accounts import user_for_token
from app.services.problems import list_problems

router = APIRouter(prefix="/api/problems", tags=["problems"])


async def optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return await user_for_token(token)


@router.get("")
async def get_problems(user: dict | None = Depends(optional_user)) -> dict:
    return await list_problems(user["_id"] if user else None)
