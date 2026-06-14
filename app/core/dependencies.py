import secrets

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.crud.user import crud_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await crud_user.get(db, id=int(user_id))
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user=Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_superuser(current_user=Depends(get_current_active_user)):
    """Доступ только для суперпользователя (роль admin).

    Роль перепроверяется по БД (через get_current_user), а не из JWT-claim,
    чтобы снятие прав действовало немедленно для следующего запроса.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав"
        )
    return current_user


# Плейсхолдер из config/.env.example — с ним сервисные endpoint-ы должны быть закрыты
_PLACEHOLDER_BOT_SECRET = "change-me-bot-secret"


async def verify_bot_secret(x_bot_secret: str = Header(default="")):
    """Сервисная авторизация бота по общему секрету (заголовок X-Bot-Secret)."""
    configured = settings.BOT_API_SECRET
    if not configured or configured == _PLACEHOLDER_BOT_SECRET:
        # Без явно заданного секрета endpoint выдачи токенов не должен работать
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot API secret is not configured",
        )
    if not secrets.compare_digest(x_bot_secret, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bot secret"
        )
