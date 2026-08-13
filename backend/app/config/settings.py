from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated process configuration with secret-safe representations."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://publisher:publisher-local@localhost:5432/publisher_intelligence"
    )

    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "publisher-intelligence-local"
    s3_access_key_id: SecretStr = SecretStr("publisher-local")
    s3_secret_access_key: SecretStr = SecretStr("replace-with-local-only-secret")
    s3_use_ssl: bool = False

    job_poll_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    job_lease_seconds: int = Field(default=30, gt=0, le=3600)
    job_reclaim_backoff_seconds: int = Field(default=5, ge=0, le=3600)

    def safe_summary(self) -> dict[str, str | bool | int | float]:
        return {
            "environment": self.environment,
            "log_level": self.log_level,
            "database_url": "[REDACTED]",
            "s3_endpoint_url": self.s3_endpoint_url,
            "s3_region": self.s3_region,
            "s3_bucket": self.s3_bucket,
            "s3_access_key_id": "[REDACTED]",
            "s3_secret_access_key": "[REDACTED]",
            "s3_use_ssl": self.s3_use_ssl,
            "job_poll_interval_seconds": self.job_poll_interval_seconds,
            "job_lease_seconds": self.job_lease_seconds,
            "job_reclaim_backoff_seconds": self.job_reclaim_backoff_seconds,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
