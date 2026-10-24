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
    ai_model: Optional[str] = "gemini-2.5-flash"
    ai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ai_request_timeout_seconds: int = 60
    ai_max_context_messages: int = 20
    ai_max_output_tokens: int = 1024
    ai_temperature: float = 0.7
    memory_max_retrieval_count: int = 5
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

    @property
    def effective_gemini_api_key(self) -> Optional[str]:
        return self.gemini_api_key or self.ai_api_key


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
