from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = Field(min_length=32)
    access_token_ttl_minutes: int = Field(default=15, ge=5, le=60)
    refresh_token_ttl_days: int = Field(default=14, ge=1, le=90)
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:5173"])
    database_url: str
    redis_url: str
    storage_provider: str = "local_filesystem"
    storage_root: Path = Path("/var/lib/transcriber/storage")
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str | None = None
    s3_use_ssl: bool = True
    model_root: Path = Path("/var/lib/transcriber/models")
    ffprobe_path: str = "ffprobe"
    ffmpeg_path: str = "ffmpeg"
    max_upload_bytes: int = Field(default=2_147_483_648, ge=1)
    malware_scanner_mode: str = "placeholder"
    default_transcription_provider: str = "faster_whisper"
    default_transcription_model: str = "base"
    transcription_device: str = "auto"
    transcription_compute_type: str = "int8"
    external_apis_allowed: bool = False
    local_only_enforced: bool = True
    credential_encryption_key: str = Field(min_length=32)
    credential_key_version: int = Field(default=1, ge=1)
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_organisation_name: str = "Local Organisation"
    # Phase 6/7 settings
    post_processing_provider: str = "stub"
    multimodal_provider: str = "stub"
    default_report_template_kind: str = "presentation"
    log_format: str = Field(default="json", pattern="^(json|text)$")
    # Rate limiting (per IP, per minute)
    rate_limit_storage: str = Field(default="redis", pattern="^(redis|memory)$")
    rate_limit_namespace: str = "transcriber:rate-limit"
    rate_limit_login: str = "10/minute"
    rate_limit_upload: str = "30/minute"
    rate_limit_export: str = "30/minute"
    rate_limit_provider_test: str = "20/minute"
    rate_limit_ai_run: str = "20/minute"
    # Malware scanning
    clamav_host: str = "clamav"
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    # Operational health checks
    worker_health_timeout_seconds: float = Field(default=0.5, gt=0, le=10)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @model_validator(mode="after")
    def reject_placeholder_secrets_in_production(self) -> "Settings":
        if self.is_production and (
            self.app_secret_key.startswith("replace-with-")
            or self.credential_encryption_key.startswith("replace-with-")
        ):
            raise ValueError("Placeholder secrets are not permitted in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
