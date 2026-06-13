from datetime import datetime

from pydantic import BaseModel


class LinkCodeRead(BaseModel):
    """Ответ веб-приложению при генерации кода привязки."""

    code: str
    expires_at: datetime


class TelegramStatusRead(BaseModel):
    """Статус привязки Telegram для текущего пользователя."""

    linked: bool
    telegram_id: int | None = None


# --- Сервисные схемы (вызывает бот, авторизация по BOT_API_SECRET) ---


class BotLinkRequest(BaseModel):
    code: str
    telegram_id: int


class BotTokenRequest(BaseModel):
    telegram_id: int


class BotTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class BotUserRead(BaseModel):
    id: int
    email: str
    full_name: str | None = None

    model_config = {"from_attributes": True}
