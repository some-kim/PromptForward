"""Account sign-up, login, and the per-account progress stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.accounts import (
    AccountError,
    end_session,
    log_in,
    record_attempt,
    sign_up,
    user_for_token,
    user_view,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignUpRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)
    displayName: str | None = Field(default=None, max_length=64)


class LogInRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class ProgressRequest(BaseModel):
    attemptId: str = Field(max_length=64)
    score: float = Field(ge=0, le=100)
    generations: int = Field(ge=1, le=10)


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return token


async def optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    """The signed-in account if a valid bearer token was sent, else None."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return await user_for_token(token)


async def current_user(token: str = Depends(bearer_token)) -> dict:
    user = await user_for_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired, sign in again")
    return user


@router.post("/signup", status_code=201)
async def signup(body: SignUpRequest) -> dict:
    try:
        user, token = await sign_up(body.username, body.password, body.displayName)
    except AccountError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"token": token, "user": user_view(user)}


@router.post("/login")
async def login(body: LogInRequest) -> dict:
    try:
        user, token = await log_in(body.username, body.password)
    except AccountError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    return {"token": token, "user": user_view(user)}


@router.post("/logout", status_code=204)
async def logout(token: str = Depends(bearer_token)) -> None:
    await end_session(token)


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return user_view(user)


@router.post("/progress")
async def add_progress(body: ProgressRequest, user: dict = Depends(current_user)) -> dict:
    return await record_attempt(user, body.attemptId, body.score, body.generations)
