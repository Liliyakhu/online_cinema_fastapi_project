import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    PATH_TO_DB: str = str(BASE_DIR / "cinema.db")
    SECRET_KEY_ACCESS: str = os.getenv("SECRET_KEY_ACCESS", "change-me-in-production")
    SECRET_KEY_REFRESH: str = os.getenv("SECRET_KEY_REFRESH", "change-me-in-production")
    JWT_SIGNING_ALGORITHM: str = "HS256"
    LOGIN_TIME_DAYS: int = 7


class TestingSettings(Settings):
    PATH_TO_DB: str = ":memory:"
    SECRET_KEY_ACCESS: str = "test-access-key"
    SECRET_KEY_REFRESH: str = "test-refresh-key"
