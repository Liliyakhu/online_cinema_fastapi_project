import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BASE_DIR: Path = Path(__file__).parent.parent
    PATH_TO_DB: str = str(BASE_DIR.parent / "cinema.db")
    SECRET_KEY_ACCESS: str = os.getenv("SECRET_KEY_ACCESS", "change-me-in-production")
    SECRET_KEY_REFRESH: str = os.getenv("SECRET_KEY_REFRESH", "change-me-in-production")
    JWT_SIGNING_ALGORITHM: str = "HS256"
    LOGIN_TIME_DAYS: int = 7
    EMAIL_HOST: str = "localhost"
    EMAIL_PORT: int = 1025
    EMAIL_HOST_USER: str = "noreply@cinema.com"
    EMAIL_HOST_PASSWORD: str = ""
    EMAIL_USE_TLS: bool = False
    PATH_TO_EMAIL_TEMPLATES_DIR: str = str(BASE_DIR / "notifications" / "templates")
    ACTIVATION_EMAIL_TEMPLATE_NAME: str = "activation_request.html"
    ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME: str = "activation_complete.html"
    PASSWORD_RESET_TEMPLATE_NAME: str = "password_reset_request.html"
    PASSWORD_RESET_COMPLETE_TEMPLATE_NAME: str = "password_reset_complete.html"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    ORDER_CONFIRMATION_EMAIL_TEMPLATE_NAME: str = "order_confirmation.html"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", 5432))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "cinema")
    MINIO_HOST: str = os.getenv("MINIO_HOST", "localhost")
    MINIO_PORT: int = int(os.getenv("MINIO_PORT", 9000))
    MINIO_ROOT_USER: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_ROOT_PASSWORD: str = os.getenv("MINIO_ROOT_PASSWORD", "some_password")
    MINIO_STORAGE: str = os.getenv("MINIO_STORAGE", "cinema-storage")

    @property
    def S3_STORAGE_ENDPOINT(self) -> str:
        return f"http://{self.MINIO_HOST}:{self.MINIO_PORT}"

    @property
    def CELERY_BROKER_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


class TestingSettings(Settings):
    PATH_TO_DB: str = ":memory:"
    SECRET_KEY_ACCESS: str = "test-access-key"
    SECRET_KEY_REFRESH: str = "test-refresh-key"
