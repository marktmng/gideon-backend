"""Application configuration management using Pydantic Settings."""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Gideon"
    app_env: str = "development"
    debug: bool = True
    database_url: str = "sqlite:///./gideon.db"
    ai_provider: str = "demo"
    ai_model: Optional[str] = ""
    ai_api_key: Optional[str] = ""
    frontend_origin: str = "http://localhost:3000"
    api_v1_prefix: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
