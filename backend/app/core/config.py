"""Centralized application configuration.

All environment-driven configuration is read exactly once here and exposed
as a singleton `settings` object (Singleton pattern) so the rest of the
codebase never touches `os.environ` directly.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Personal Assistant Platform"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # --- Security / Auth ---
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h
    ADMIN_REGISTRATION_CODE: str = "change-me-admin-code"

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Database (app data: users, conversations, messages, session logs) ---
    DATABASE_URL: str = "postgresql+psycopg://assistant:assistant@postgres:5432/assistant_db"

    # --- LangGraph checkpointer DB (persists interrupt/resume state) ---
    CHECKPOINTER_DATABASE_URL: str = "postgresql://assistant:assistant@postgres:5432/assistant_db"

    # --- LLM provider ---
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.1-flash-lite"
    EMBEDDING_MODEL: str = "models/text-embedding-004"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
