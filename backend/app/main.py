"""FastAPI application entrypoint. Fails fast when configuration is incomplete."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import ConfigError, get_config
from app.db import close_client, ensure_indexes
from app.routes import auth, challenges, games, images, learning, library, standings

try:
    config = get_config()
except ConfigError as error:
    print(f"Configuration error: {error}", file=sys.stderr)
    raise SystemExit(1) from error


@asynccontextmanager
async def lifespan(_: FastAPI):
    await ensure_indexes()
    yield
    await close_client()


app = FastAPI(title="PromptForward", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.cors_allow_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(challenges.router)
app.include_router(learning.router)
app.include_router(games.router)
app.include_router(library.router)
app.include_router(images.router)
app.include_router(standings.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "env": config.app_env}
