"""REPAIR engine configuration (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
ENGINE_ROOT = Path(__file__).resolve().parents[2]

# Prefer local gitignored .env over a stale process environment (common in IDE shells).
load_dotenv(REPO_ROOT / ".env", override=True)
load_dotenv(ENGINE_ROOT / ".env", override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ENGINE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    repair_support_model: str = "gpt-4.1-mini"
    repair_flow_model: str = "gpt-4.1"

    one_secret: str | None = None
    one_stripe_connection_key: str | None = None
    one_linear_connection_key: str | None = None
    one_api_base: str = "https://api.withone.ai"

    ydc_api_key: str | None = None
    daytona_api_key: str | None = None
    daytona_api_url: str = "https://app.daytona.io/api"
    daytona_target: str | None = None

    linear_team_key: str | None = None
    repair_fault_mode: str = "CommitThenDisconnect"
    repair_engine_port: int = 8000
    repair_web_origin: str = "http://localhost:3000"

    fixtures_dir: Path = Field(default=REPO_ROOT / "fixtures")
    policies_dir: Path = Field(default=REPO_ROOT / "policies")
    runs_dir: Path = Field(default=REPO_ROOT / "runs")

    def require_one(self) -> None:
        if not self.one_secret:
            raise RuntimeError("Missing required credentials: ONE_SECRET")
        # Connection keys may be resolved dynamically via `one --agent list`.
        # Only fail hard later if discovery also fails.

    def missing_credentials(self) -> dict[str, bool]:
        return {
            "ONE_SECRET": bool(self.one_secret),
            "ONE_STRIPE_CONNECTION_KEY": bool(self.one_stripe_connection_key),
            "ONE_LINEAR_CONNECTION_KEY": bool(self.one_linear_connection_key),
            "OPENAI_API_KEY": bool(self.openai_api_key),
            "YDC_API_KEY": bool(self.ydc_api_key),
            "DAYTONA_API_KEY": bool(self.daytona_api_key),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
