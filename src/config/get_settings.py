import os
from src.config.settings import TestingSettings, Settings, BaseAppSettings


def get_settings() -> BaseAppSettings:
    environment = os.getenv("ENVIRONMENT", "developing")
    if environment == "testing":
        return TestingSettings()
    return Settings()
