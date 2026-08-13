from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = (
    "postgresql+psycopg://publisher:publisher-local@localhost:5432/publisher_intelligence"
)
LOCAL_S3_ENDPOINT_URL = "http://localhost:9000"
LOCAL_S3_ACCESS_KEY_ID = "publisher-local"
LOCAL_S3_SECRET_ACCESS_KEY = "replace-with-local-only-secret"


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
    database_url: SecretStr = SecretStr(LOCAL_DATABASE_URL)

    s3_endpoint_url: str = LOCAL_S3_ENDPOINT_URL
    s3_region: str = "us-east-1"
    s3_bucket: str = "publisher-intelligence-local"
    s3_access_key_id: SecretStr = SecretStr(LOCAL_S3_ACCESS_KEY_ID)
    s3_secret_access_key: SecretStr = SecretStr(LOCAL_S3_SECRET_ACCESS_KEY)
    s3_use_ssl: bool = False

    job_poll_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    job_lease_seconds: int = Field(default=30, gt=0, le=3600)
    job_reclaim_backoff_seconds: int = Field(default=5, ge=0, le=3600)

    @model_validator(mode="after")
    def reject_local_defaults_in_production(self) -> "Settings":
        if self.environment != "production":
            return self
        local_fields = []
        if self.database_url.get_secret_value() == LOCAL_DATABASE_URL:
            local_fields.append("database_url")
        if self.s3_endpoint_url == LOCAL_S3_ENDPOINT_URL:
            local_fields.append("s3_endpoint_url")
        if self.s3_access_key_id.get_secret_value() == LOCAL_S3_ACCESS_KEY_ID:
            local_fields.append("s3_access_key_id")
        if self.s3_secret_access_key.get_secret_value() == LOCAL_S3_SECRET_ACCESS_KEY:
            local_fields.append("s3_secret_access_key")
        if local_fields:
            fields = ", ".join(local_fields)
            raise ValueError(f"production configuration requires explicit values for: {fields}")
        return self

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
