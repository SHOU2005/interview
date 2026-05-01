"""Application settings via environment variables."""

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/interviewiq"
    JWT_SECRET: str = "change-me"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7
    ALLOWED_EMAIL_DOMAIN: str = "@iilm.edu"
    OTP_EXPIRE_SECONDS: int = 600
    DEBUG: bool = False
    CORS_ORIGINS: str = "http://localhost:5173"
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@iilm.edu"
    BOOTSTRAP_ADMIN_PASSWORD: str = "admin123"
    ML_USE_SENTENCE_TRANSFORMERS: bool = True
    UPLOAD_DIR: str = "uploads"
    PROCTORING_STORE_SNAPSHOTS: bool = False
    INTEGRITY_WEIGHT_DEFAULT: float = 0.15
    ANSWER_QUALITY_WEIGHT_DEFAULT: float = 0.85

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
