import os

from fastapi import Depends

from config.settings import Settings, TestingSettings
from security.interfaces import JWTAuthManagerInterface
from security.token_manager import JWTAuthManager


def get_settings() -> Settings:
    environment = os.getenv("ENVIRONMENT", "developing")
    if environment == "testing":
        return TestingSettings()
    return Settings()


def get_jwt_auth_manager(
    settings: Settings = Depends(get_settings)
) -> JWTAuthManagerInterface:
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM
    )
