"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file and environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://defectsync:defectsync_dev@localhost:5432/defectsync"
    DATABASE_URL_SYNC: str = "postgresql+psycopg://defectsync:defectsync_dev@localhost:5432/defectsync"

    # Redis
    REDIS_URL: str = "rediss://default:xxx@xxx.upstash.io:6379"

    # Storage — "local" or "s3"
    STORAGE_BACKEND: str = "local"
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
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ML
    ML_MODEL_PATH: str = "ml/models/defect_detector.pt"
    ML_CONFIDENCE_THRESHOLD: float = 0.25
    ML_DEVICE: str = "cpu"

    # App
    APP_NAME: str = "DefectSync"
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }

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
