from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow"
    )

    PROJECT_NAME: str = "HR Management with AI"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # PostgreSQL config
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "hr_user"
    POSTGRES_PASSWORD: str = "hr_secret_password"
    POSTGRES_DB: str = "hr_management_db"

    # Database URLs
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://hr_user:hr_secret_password@localhost:5432/hr_management_db"
    )
    SYNC_DATABASE_URL: str = Field(
        default="postgresql+psycopg2://hr_user:hr_secret_password@localhost:5432/hr_management_db"
    )

    # JWT Security
    SECRET_KEY: str = "super_secret_jwt_key_should_be_changed_in_production_env_32_bytes_min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Kiosk Web authorization token
    KIOSK_API_SECRET_KEY: str = "kiosk_secret_device_authorization_token_hr_group3"

    # AI Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_NAME: str = "gemini-1.5-flash"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]


settings = Settings()
