from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RealityCheck"
    app_version: str = "0.1.0"
    app_description: str = "AI-powered evidence reconciliation"
    environment: str = "development"

    max_upload_size_mb: int = Field(default=50, gt=0)
    max_concurrent_uploads: int = Field(default=4, gt=0)
    max_concurrent_llm_calls: int = Field(default=8, gt=0)
    max_concurrent_extractions: int = Field(default=2, gt=0)
    max_pending_extraction_jobs: int = Field(default=20, gt=0)
    job_retention_days: int = Field(default=30, gt=0)
    job_cleanup_interval_seconds: int = Field(default=3600, gt=0)
    orphan_artifact_grace_seconds: int = Field(default=3600, ge=0)
    llm_timeout_seconds: int = Field(default=60, gt=0)
    max_extraction_duration_seconds: float = Field(default=300.0, gt=0)
    max_analysis_input_chars: int = Field(default=60000, gt=1000)
    analysis_provider: Literal["auto", "nebius", "offline"] = "auto"
    nebius_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    nebius_claim_model: str = "nvidia/nemotron-3-nano-30b-a3b"
    nebius_reasoning_model: str = "nvidia/nemotron-3-super-120b-a12b"
    data_dir: Path = Path("data")
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
