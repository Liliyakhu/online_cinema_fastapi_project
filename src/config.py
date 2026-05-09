import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).parent.parent
    PATH_TO_DB: str = str(BASE_DIR / "cinema.db")


class TestingSettings(Settings):
    PATH_TO_DB: str = ":memory:"


def get_settings() -> BaseSettings:
    """
    Retrieve the application settings based on the environment.

    This function checks the `ENVIRONMENT` environment variable to determine
    which settings class to use. If `ENVIRONMENT` is set to `"testing"`, it
    returns an instance of `TestingSettings`. Otherwise, it defaults to `Settings`.

    :return: An instance of the appropriate settings class.
    :rtype: BaseSettings
    """
    environment = os.getenv("ENVIRONMENT", "developing")
    if environment == "testing":
        return TestingSettings()
    return Settings()
