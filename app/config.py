"""Application configuration management."""
from __future__ import annotations

from functools import lru_cache
from typing import Any
import os

from pydantic import BaseModel, Field, validator


class Settings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "dev"))
    jwt_secret: str = Field(default_factory=lambda: os.getenv("JWT_SECRET", "devsecret"))
    jwt_audience: str = Field(default_factory=lambda: os.getenv("JWT_AUDIENCE", "invoice.sieve"))
    jwt_issuer: str = Field(default_factory=lambda: os.getenv("JWT_ISSUER", "local.sieve"))
    db_dsn: str = Field(
        default_factory=lambda: os.getenv(
            "DB_DSN", "postgresql+psycopg://postgres:postgres@localhost:5432/sieve"
        )
    )
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    s3_endpoint: str | None = Field(default_factory=lambda: os.getenv("S3_ENDPOINT"))
    s3_key: str | None = Field(default_factory=lambda: os.getenv("S3_ACCESS_KEY"))
    s3_secret: str | None = Field(default_factory=lambda: os.getenv("S3_SECRET_KEY"))
    s3_bucket: str = Field(default_factory=lambda: os.getenv("S3_BUCKET", "invoice-blobs"))
    os_host: str = Field(default_factory=lambda: os.getenv("OS_HOST", "http://localhost:9200"))
    mlflow_tracking_uri: str | None = Field(
        default_factory=lambda: os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
    )
    tenant_id: str = Field(default_factory=lambda: os.getenv("TENANT_ID", "tenant_demo"))
    hold_threshold_default: float = 80.0
    review_threshold_default: float = 50.0

    class Config:
        frozen = True

    @validator("hold_threshold_default", "review_threshold_default")
    def _validate_threshold(cls, value: float) -> float:  # noqa: D401
        """Ensure thresholds are within the 0-100 risk score range."""

        if not 0 <= value <= 100:
            raise ValueError("thresholds must be between 0 and 100")
        return value

    def decision_thresholds(self) -> dict[str, Any]:
        """Return default decision thresholds."""

        return {
            "hold": self.hold_threshold_default,
            "review": self.review_threshold_default,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()


settings = get_settings()
"""Module-level settings singleton used across the application."""
