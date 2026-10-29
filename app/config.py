from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./taskhub.db"
    redis_url: str = "redis://localhost:6379/0"
    ai_provider: Literal["demo", "remote"] = "demo"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"


@lru_cache
def settings():
    return Settings()
