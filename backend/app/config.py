"""Environment loading and validation. All model names live here, nowhere else."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

ANALYSIS_VERSION = 1


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    base_url: str
    challenge_analyzer_model: str
    prompt_evaluator_model: str
    result_evaluator_model: str


@dataclass(frozen=True)
class MetaConfig:
    api_key: str
    base_url: str
    image_model: str
    timeout_ms: int


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    db_name: str


@dataclass(frozen=True)
class DropboxConfig:
    app_key: str
    app_secret: str
    refresh_token: str
    access_token: str
    challenges_folder: str
    generated_folder: str


@dataclass(frozen=True)
class Config:
    openai: OpenAIConfig
    meta: MetaConfig
    mongo: MongoConfig
    dropbox: DropboxConfig
    app_env: str
    port: int
    cors_allow_origins: tuple[str, ...]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


REQUIRED_VARS = (
    "OPENAI_API_KEY",
    "OPENAI_CHALLENGE_ANALYZER_MODEL",
    "OPENAI_PROMPT_EVALUATOR_MODEL",
    "OPENAI_RESULT_EVALUATOR_MODEL",
    "META_API_KEY",
    "META_API_BASE_URL",
    "META_IMAGE_MODEL",
    "MONGODB_URI",
    "MONGODB_DB_NAME",
    "DROPBOX_APP_KEY",
    "DROPBOX_APP_SECRET",
    "DROPBOX_CHALLENGES_FOLDER",
    "DROPBOX_GENERATED_FOLDER",
)


def load_config(env: dict[str, str] | None = None) -> Config:
    if env is None:
        load_dotenv()
        env = dict(os.environ)

    missing = [name for name in REQUIRED_VARS if not (env.get(name) or "").strip()]
    if not any(
        (env.get(name) or "").strip() for name in ("DROPBOX_REFRESH_TOKEN", "DROPBOX_ACCESS_TOKEN")
    ):
        missing.append("DROPBOX_REFRESH_TOKEN or DROPBOX_ACCESS_TOKEN")
    if missing:
        raise ConfigError(
            "Missing required environment variables: " + ", ".join(missing) + ". "
            "Copy backend/.env.example to backend/.env and fill them in."
        )

    return Config(
        openai=OpenAIConfig(
            api_key=env["OPENAI_API_KEY"],
            base_url=(env.get("OPENAI_BASE_URL") or "").strip().rstrip("/"),
            challenge_analyzer_model=env["OPENAI_CHALLENGE_ANALYZER_MODEL"],
            prompt_evaluator_model=env["OPENAI_PROMPT_EVALUATOR_MODEL"],
            result_evaluator_model=env["OPENAI_RESULT_EVALUATOR_MODEL"],
        ),
        meta=MetaConfig(
            api_key=env["META_API_KEY"],
            base_url=env["META_API_BASE_URL"].rstrip("/"),
            image_model=env["META_IMAGE_MODEL"],
            timeout_ms=int(env.get("META_IMAGE_TIMEOUT_MS") or 120000),
        ),
        mongo=MongoConfig(uri=env["MONGODB_URI"], db_name=env["MONGODB_DB_NAME"]),
        dropbox=DropboxConfig(
            app_key=env["DROPBOX_APP_KEY"],
            app_secret=env["DROPBOX_APP_SECRET"],
            refresh_token=env.get("DROPBOX_REFRESH_TOKEN", ""),
            access_token=env.get("DROPBOX_ACCESS_TOKEN", ""),
            challenges_folder=env["DROPBOX_CHALLENGES_FOLDER"].rstrip("/"),
            generated_folder=env["DROPBOX_GENERATED_FOLDER"].rstrip("/"),
        ),
        app_env=env.get("APP_ENV") or "development",
        port=int(env.get("PORT") or 8000),
        cors_allow_origins=tuple(
            origin.strip()
            for origin in (env.get("CORS_ALLOW_ORIGINS") or "http://localhost:5173").split(",")
            if origin.strip() and origin.strip() != "*"
        ),
    )


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config
