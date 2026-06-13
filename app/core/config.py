from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "CashControl"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/cashcontrol"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Telegram bot
    # Общий секрет между backend и ботом для сервисных endpoint-ов /telegram/link и /telegram/token
    BOT_API_SECRET: str = "change-me-bot-secret"
    # Время жизни одноразового кода привязки Telegram (в минутах)
    TELEGRAM_LINK_CODE_TTL_MINUTES: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True
        # В общем .env живут и переменные бота (BOT_TOKEN, BOT_USERNAME) — backend их не знает
        extra = "ignore"


settings = Settings()
