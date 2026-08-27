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

    # EP-024 M2: secret backend selection.
    # local/test: "memory" or "environment" permitted
    # staging/production: "oci" required (fail-closed via validator below)
    secret_backend: Literal["memory", "environment", "oci"] = "environment"
    oci_region: str = "eu-frankfurt-1"

    # EP-026 M1 (SECURITY.md §201): auth cookies MUST be Secure=True outside
    # local development. Fail-closed via model_validator below.
    cookie_secure: bool = False

    @model_validator(mode="after")
    def _enforce_secure_cookie_posture(self) -> "Settings":
        if self.environment in ("staging", "production") and not self.cookie_secure:
            raise ValueError(
                f"environment={self.environment} requires cookie_secure=True "
                "(SECURITY.md §201 secure-cookie hard gate)"
            )
        return self

    @model_validator(mode="after")
    def _enforce_secret_backend_for_managed_environments(self) -> "Settings":
        if self.environment in ("staging", "production"):
            if self.secret_backend != "oci":
                raise ValueError(
                    f"environment={self.environment} requires secret_backend=oci; "
                    "environment/memory backends are not permitted in managed environments"
                )
        return self

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

    browser_navigation_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    browser_stabilization_ms: int = Field(default=1_000, ge=0, le=10_000)
    browser_consent_discovery_timeout_ms: int = Field(default=2_000, ge=100, le=10_000)
    browser_consent_action_timeout_ms: int = Field(default=3_000, ge=100, le=15_000)
    browser_post_consent_stabilization_ms: int = Field(default=500, ge=0, le=10_000)
    browser_overall_timeout_seconds: int = Field(default=60, ge=5, le=300)
    browser_max_requests: int = Field(default=500, ge=10, le=5_000)
    browser_viewport_width: int = Field(default=1440, ge=320, le=3840)
    browser_viewport_height: int = Field(default=900, ge=320, le=2160)
    browser_locale: str = "en-US"
    browser_timezone: str = "UTC"
    browser_allow_private_networks: bool = False
    browser_schedule_stagger_seconds: int = Field(default=30, ge=0, le=900)

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
        if self.browser_allow_private_networks:
            local_fields.append("browser_allow_private_networks")
        if local_fields:
            fields = ", ".join(local_fields)
            raise ValueError(f"production configuration requires explicit values for: {fields}")
        return self

    def safe_summary(self) -> dict[str, str | bool | int | float]:
        return {
            "environment": self.environment,
            "secret_backend": self.secret_backend,
            "oci_region": self.oci_region,
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
            "browser_navigation_timeout_ms": self.browser_navigation_timeout_ms,
            "browser_stabilization_ms": self.browser_stabilization_ms,
            "browser_consent_discovery_timeout_ms": self.browser_consent_discovery_timeout_ms,
            "browser_consent_action_timeout_ms": self.browser_consent_action_timeout_ms,
            "browser_post_consent_stabilization_ms": (self.browser_post_consent_stabilization_ms),
            "browser_overall_timeout_seconds": self.browser_overall_timeout_seconds,
            "browser_max_requests": self.browser_max_requests,
            "browser_viewport_width": self.browser_viewport_width,
            "browser_viewport_height": self.browser_viewport_height,
            "browser_locale": self.browser_locale,
            "browser_timezone": self.browser_timezone,
            "browser_allow_private_networks": self.browser_allow_private_networks,
            "browser_schedule_stagger_seconds": self.browser_schedule_stagger_seconds,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
