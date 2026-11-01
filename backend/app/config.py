from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-6-luna"
    openai_reasoning_effort: Literal[
        "none", "low", "medium", "high"
    ] = "low"
    openai_max_output_tokens: int = Field(
        default=6000,
        ge=1000,
        le=16000,
    )
    openai_timeout_seconds: float = Field(
        default=90,
        ge=10,
        le=180,
    )
    desired_retention: float = Field(
        default=0.9,
        ge=0.7,
        le=0.99,
    )


settings = Settings()