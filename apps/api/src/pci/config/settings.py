from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str = "postgresql+psycopg://pci:pci_dev@localhost:5432/pci_dev"
    gemini_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
