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
    EMAIL_HOST: str = "localhost"
    EMAIL_PORT: int = 1025
    EMAIL_HOST_USER: str = "noreply@cinema.com"
    EMAIL_HOST_PASSWORD: str = ""
    EMAIL_USE_TLS: bool = False
    PATH_TO_EMAIL_TEMPLATES_DIR: str = str(BASE_DIR / "src" / "notifications" / "templates")
    ACTIVATION_EMAIL_TEMPLATE_NAME: str = "activation_request.html"
    ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME: str = "activation_complete.html"
    PASSWORD_RESET_TEMPLATE_NAME: str = "password_reset_request.html"
    PASSWORD_RESET_COMPLETE_TEMPLATE_NAME: str = "password_reset_complete.html"


class TestingSettings(Settings):
    PATH_TO_DB: str = ":memory:"
    SECRET_KEY_ACCESS: str = "test-access-key"
    SECRET_KEY_REFRESH: str = "test-refresh-key"
