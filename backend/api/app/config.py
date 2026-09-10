from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.auth import UserStore

# The `backend/` directory, i.e. the parent of this package.
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Any port on the loopback interface, in the three spellings a browser can
# send. Applied in development only, because the Next dev server moves to
# 3001+ whenever 3000 is taken and each move is a new origin.
#
# Starlette matches this with `re.fullmatch`, so it cannot be widened by a
# lookalike host such as `http://localhost:3000.example.com`.
LOOPBACK_ORIGIN_REGEX = r"http://(?:localhost|127\.0\.0\.1|\[::1\]):\d{1,5}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "resume-parser"
    environment: str = "development"

    # Comma-separated; read through `cors_origin_list`. Kept as a plain string
    # because pydantic-settings tries to JSON-decode list-typed fields.
    #
    # Both loopback spellings are listed: a browser treats
    # http://localhost:3000 and http://127.0.0.1:3000 as different origins, so
    # allowing only one turns the other into a CORS failure.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Escape hatch for origins that cannot be enumerated (preview deployments,
    # a wildcard subdomain). Empty by default; see `cors_origin_regex_or_none`,
    # which falls back to the loopback pattern in development.
    cors_origin_regex: str = ""

    # The project's .env points at OpenRouter's OpenAI-compatible endpoint,
    # so the OpenAI client is pointed there rather than at api.openai.com.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openai_model: str = "gpt-4.1-mini"

    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 90.0
    llm_max_retries: int = 2
    # Left unset by default: the ranking call has to emit one entry per
    # candidate, and a fixed cap silently truncates the JSON on large batches.
    llm_max_tokens: int | None = None

    # Placeholder auth (see app/auth.py). The default secret is a development
    # convenience: set AUTH_SECRET before deploying anywhere, or every install
    # will accept every other install's tokens.
    auth_secret: str = "development-only-change-me"
    auth_store_path: str = ".data/users.json"
    auth_token_ttl_hours: int = 12

    # Upload limits
    max_resume_files: int = 25
    max_file_size_mb: float = 10.0
    max_pdf_pages: int = 30
    max_resume_chars: int = 20_000
    max_job_description_chars: int = 20_000

    # How many resumes are screened concurrently.
    screening_concurrency: int = 4
    # Spacing between screening calls, for provider rate limits.
    screening_delay_seconds: float = 0.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def cors_origin_regex_or_none(self) -> str | None:
        """The regex handed to `CORSMiddleware(allow_origin_regex=...)`.

        An explicit `CORS_ORIGIN_REGEX` always wins. Otherwise development
        accepts any loopback port and every other environment gets `None`, so
        production is limited to the enumerated `CORS_ORIGINS`.
        """

        if self.cors_origin_regex:
            return self.cors_origin_regex

        return LOOPBACK_ORIGIN_REGEX if self.environment == "development" else None

    @property
    def max_file_size_bytes(self) -> int:
        return int(self.max_file_size_mb * 1024 * 1024)

    @property
    def auth_token_ttl_seconds(self) -> int:
        return int(self.auth_token_ttl_hours * 3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_user_store(path: str) -> UserStore:
    """One store per path, so tests pointing at a tmp file get their own.

    A relative `path` is anchored to `backend/` rather than the working
    directory, so `uv run main.py` and `uvicorn app.main:app` from the
    repo root read the same accounts.
    """

    # VERCEL_ENV is automatically injected by Vercel in production
    if os.getenv("VERCEL_ENV"):
        # Serverless runtime: write to the shared container temporary path
        storage_path = Path("/tmp/users.json")
        return UserStore(path=storage_path)

    resolved = Path(path)

    return UserStore(resolved if resolved.is_absolute() else BACKEND_ROOT / resolved)


class LLMNotConfiguredError(RuntimeError):
    """Raised when no API key is available to talk to the model provider."""


def build_chat_model(settings: Settings) -> ChatOpenAI:
    """Construct the chat model shared by the screening and ranking steps."""

    if not settings.openrouter_api_key:
        raise LLMNotConfiguredError(
            "OPENROUTER_API_KEY is not set. Add it to .env before running a screening."
        )

    return ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.llm_temperature,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_tokens=settings.llm_max_tokens,
    )
