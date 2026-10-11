"""Базовые настройки приложения (читаются из .env / переменных окружения)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Приложение ---
    app_name: str = "IT-служба колледжа — REST API"
    app_description: str = (
        "Центральный бэкенд системы автоматизации IT-службы колледжа. "
        "API для будущего бота MAX и веб-панели."
    )
    app_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # --- База данных ---
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/it_support"
    )
    db_echo: bool = False

    # --- JWT (веб-панель) ---
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 120

    # --- Внутренние сервисы (бот MAX как REST-клиент) ---
    # Примечание: токены/URL MAX API здесь НЕ хранятся. Core API не общается
    # с мессенджером напрямую; доставка уведомлений в MAX — ответственность
    # отдельного приложения (Бота), которое ходит в API как обычный клиент.
    service_api_key: str = "CHANGE_ME_SERVICE_KEY"

    # --- CORS ---
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
