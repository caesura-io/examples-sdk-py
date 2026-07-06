"""Application settings loaded from environment variables.

Uses pydantic-settings to validate and type env vars at startup.
Copy ``.env.example`` to ``.env`` and fill in your keys before running.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-based configuration for the FastAPI server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── OpenAI ────────────────────────────────────────────────────────────
    # Sent ONLY to OpenAI. Never forwarded to the Caesura backend.
    openai_api_key: str

    # ── Caesura ────────────────────────────────────────────────────────────
    # Sent ONLY to the Caesura backend. Never forwarded to OpenAI.
    caesura_api_key: str

    # Base URL including the subdomain (environment).  Available features
    # may differ between environments (e.g. dev.caesura.io vs beta.caesura.io).
    # Never hardcode — always read from config.
    caesura_base_url: str = "https://dev.caesura.io"

    # Caesura observation mode:
    #   "sync" (default in this example) — analysis runs inline; recommendations are injected
    #       into the *current* turn.
    #   "async" — analysis runs in the background; recommendations
    #       appear on the *next* turn (no added latency).
    #
    # NOTE: This is independent of Python's AsyncOpenAI client.  "async" here
    # refers to the Caesura observation mode, not the Python concurrency model.
    caesura_mode: Literal["async", "sync"] = "sync"


settings = Settings()  # type: ignore[call-arg]
