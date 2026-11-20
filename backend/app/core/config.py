"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from typing import Literal

_ROOT_DIR = Path(__file__).resolve().parents[3]
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from .env file and environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://defectsync:defectsync_dev@localhost:5432/defectsync"
    DATABASE_URL_SYNC: str = "postgresql+psycopg://defectsync:defectsync_dev@localhost:5432/defectsync"

    # Redis
    REDIS_URL: str = "rediss://default:xxx@xxx.upstash.io:6379"

    # Storage — "local" or "s3"
    STORAGE_BACKEND: Literal["local"] = "local"
    LOCAL_UPLOAD_DIR: str = "uploads"

    # MinIO / S3 (only used when STORAGE_BACKEND=s3)
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_IMAGES: str = "images"
    S3_BUCKET_IFC: str = "ifc-models"
    S3_BUCKET_FRAGMENTS: str = "fragments"
    S3_BUCKET_REPORTS: str = "reports"

    # JWT Auth
    JWT_SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ML
    ML_MODEL_PATH: str = "ml/models/defect_detector.pt"
    ML_CONFIDENCE_THRESHOLD: float = Field(default=0.25, ge=0.01, le=1.0)
    ML_DEVICE: str = "cpu"

    CAMERA_ALLOWED_HOSTS: str = ""
    STREAM_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    STREAM_MAX_SECONDS: int = Field(default=120, ge=10, le=600)
    SCHEDULER_ENABLED: bool = False
    MAX_IMAGE_PIXELS: int = 25_000_000

    # App
    APP_NAME: str = "DefectSync"
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"

    model_config = {
        "env_file": (
            str(_ROOT_DIR / ".env"),
            str(_BACKEND_DIR / ".env"),
            ".env",
        ),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def production_settings(self):
        if self.APP_ENV == "production":
            if len(self.JWT_SECRET_KEY) < 32 or self.JWT_SECRET_KEY.startswith(("change-me", "REPLACE_")):
                raise ValueError("Production requires a random JWT_SECRET_KEY of at least 32 characters")
            if any(not origin.startswith("https://") for origin in self.cors_origins_list):
                raise ValueError("Production CORS origins must use HTTPS")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS comma-separated string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def is_local_storage(self) -> bool:
        """Check if using local filesystem storage."""
        return self.STORAGE_BACKEND == "local"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
