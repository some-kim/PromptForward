"""Accounts: password hashing, sessions, and the per-account progress stats."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

import bcrypt
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app import db

USERNAME_MIN = 3
USERNAME_MAX = 32
PASSWORD_MIN = 8
# bcrypt hashes at most 72 bytes and rejects anything longer.
PASSWORD_MAX_BYTES = 72

EMPTY_PROGRESS = {
    "xp": 0,
    "attempts": 0,
    "generations": 0,
    "streak": 0,
    "lastPlayedDay": None,
}


class AccountError(Exception):
    """Sign-up or login could not be completed."""


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _normalize_username(username: str) -> str:
    cleaned = username.strip().lower()
    if not USERNAME_MIN <= len(cleaned) <= USERNAME_MAX:
        raise AccountError(f"Username must be {USERNAME_MIN}-{USERNAME_MAX} characters")
    if not all(character.isalnum() or character in "._-" for character in cleaned):
        raise AccountError("Username may only contain letters, numbers, dot, dash, underscore")
    return cleaned


async def sign_up(username: str, password: str, display_name: str | None) -> tuple[dict, str]:
    cleaned = _normalize_username(username)
    if len(password) < PASSWORD_MIN:
        raise AccountError(f"Password must be at least {PASSWORD_MIN} characters")
    if len(password.encode()) > PASSWORD_MAX_BYTES:
        raise AccountError("Password is too long")

    user = {
        "username": cleaned,
        "displayName": (display_name or username).strip() or cleaned,
        "passwordHash": _hash_password(password),
        "progress": dict(EMPTY_PROGRESS),
        "createdAt": datetime.now(timezone.utc),
    }
    try:
        result = await db.users().insert_one(user)
    except DuplicateKeyError as error:
        raise AccountError("That username is taken") from error

    user["_id"] = result.inserted_id
    return user, await create_session(user["_id"])


async def log_in(username: str, password: str) -> tuple[dict, str]:
    user = await db.users().find_one({"username": username.strip().lower()})
    if (
        user is None
        or len(password.encode()) > PASSWORD_MAX_BYTES
        or not _check_password(password, user["passwordHash"])
    ):
        raise AccountError("Wrong username or password")
    return user, await create_session(user["_id"])


async def create_session(user_id: ObjectId) -> str:
    token = secrets.token_urlsafe(32)
    await db.sessions().insert_one(
        {
            "_id": _hash_token(token),
            "userId": user_id,
            "createdAt": datetime.now(timezone.utc),
        }
    )
    return token


async def user_for_token(token: str) -> dict | None:
    session = await db.sessions().find_one({"_id": _hash_token(token)})
    if session is None:
        return None
    return await db.users().find_one({"_id": session["userId"]})


async def end_session(token: str) -> None:
    await db.sessions().delete_one({"_id": _hash_token(token)})


def _next_streak(previous: dict, today: str) -> int:
    last = previous.get("lastPlayedDay")
    if last == today:
        return max(int(previous.get("streak", 0)), 1)
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    return int(previous.get("streak", 0)) + 1 if last == yesterday else 1


async def record_attempt(user: dict, attempt_id: str, score: float, generations: int) -> dict:
    """Applies one attempt to the account's stats and returns the new totals.

    Keyed by attempt so the client can report as soon as an attempt is scored and report again
    after a retry: the account gains the difference, never a second attempt.
    """
    xp = max(0, round(score))
    used = max(1, int(generations))
    event = {
        "_id": f"{user['_id']}:{attempt_id}",
        "userId": user["_id"],
        "xp": xp,
        "generations": used,
    }

    try:
        await db.progress_events().insert_one(event)
        deltas = {"progress.xp": xp, "progress.attempts": 1, "progress.generations": used}
    except DuplicateKeyError:
        applied = await db.progress_events().find_one_and_update(
            {"_id": event["_id"]},
            {"$set": {"xp": xp, "generations": used}},
        )
        deltas = {
            "progress.xp": xp - int(applied["xp"]),
            "progress.attempts": 0,
            "progress.generations": used - int(applied["generations"]),
        }

    updated = await db.users().find_one_and_update(
        {"_id": user["_id"]},
        {"$inc": deltas},
        return_document=ReturnDocument.AFTER,
    )
    return await _touch_streak(user["_id"], {**EMPTY_PROGRESS, **(updated.get("progress") or {})})


async def _touch_streak(user_id: ObjectId, progress: dict) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    streak = _next_streak(progress, today)
    if (progress["lastPlayedDay"], progress["streak"]) == (today, streak):
        return progress

    await db.users().update_one(
        {"_id": user_id, "progress.lastPlayedDay": progress["lastPlayedDay"]},
        {"$set": {"progress.streak": streak, "progress.lastPlayedDay": today}},
    )
    return {**progress, "streak": streak, "lastPlayedDay": today}


def user_view(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "displayName": user.get("displayName") or user["username"],
        "progress": {**EMPTY_PROGRESS, **(user.get("progress") or {})},
    }
