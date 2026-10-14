"""Settings loaded from environment variables and .env."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str
    caesura_base_url: str = "https://api.caesurao.com"
    caesura_api_key: str
    caesura_persist: bool = True
    caesura_mode: Literal["async", "sync"] = "sync"
    caesura_agent_name: str = "Agent"
    caesura_calculate_similarities: bool = True
    caesura_similarity_threshold: float | None = Field(default=None, ge=0, le=1)


settings = Settings()  # type: ignore[call-arg]
