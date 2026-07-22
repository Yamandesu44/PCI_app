from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str = "postgresql+pg8000://pci:pci_dev@localhost:5432/pci_dev"
    gemini_api_key: str | None = None
    gemini_model: str = DEFAULT_GEMINI_MODEL
    ingest_token: str | None = None  # Bearer token for /internal/ingest/* endpoints


@lru_cache
def get_settings() -> Settings:
    return Settings()
