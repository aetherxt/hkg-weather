from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    mongodb_ingest_uri: SecretStr
    mongodb_read_uri: SecretStr
    mongodb_database: str = "hkg-weather-live"
    cron_secret: SecretStr

    model_config = SettingsConfigDict(
        env_file=(
            REPOSITORY_ROOT / ".env.local",
            REPOSITORY_ROOT / "web" / ".env.local",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("mongodb_ingest_uri", "mongodb_read_uri")
    @classmethod
    def validate_mongodb_uri(cls, value: SecretStr) -> SecretStr:
        uri = value.get_secret_value()
        if not uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("must be a MongoDB connection URI")
        return value

    @field_validator("mongodb_database")
    @classmethod
    def validate_database_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("cron_secret")
    @classmethod
    def validate_cron_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("must contain at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
