from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, verify_bot_secret
from app.core.security import create_access_token, create_refresh_token
from app.crud.telegram import crud_telegram_link_code
from app.crud.user import crud_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.telegram import (
    BotLinkRequest,
    BotTokenRequest,
    BotTokenResponse,
    BotUserRead,
    LinkCodeRead,
    TelegramStatusRead,
)

router = APIRouter()


# --- Endpoint-ы веб-приложения (авторизация по JWT пользователя) ---


@router.post("/link-code", response_model=LinkCodeRead)
async def create_link_code(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Сгенерировать одноразовый код для привязки Telegram-аккаунта."""
    link_code = await crud_telegram_link_code.create_for_user(db, user_id=current_user.id)
    return LinkCodeRead(code=link_code.code, expires_at=link_code.expires_at)


@router.get("/status", response_model=TelegramStatusRead)
async def telegram_status(
    current_user: User = Depends(get_current_active_user),
):
    return TelegramStatusRead(
        linked=current_user.telegram_id is not None,
        telegram_id=current_user.telegram_id,
    )


@router.post("/unlink", response_model=TelegramStatusRead)
async def telegram_unlink(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await crud_user.update(db, db_obj=current_user, obj_in={"telegram_id": None})
    return TelegramStatusRead(linked=False, telegram_id=None)


# --- Сервисные endpoint-ы бота (авторизация по BOT_API_SECRET) ---


@router.post("/link", response_model=BotUserRead, dependencies=[Depends(verify_bot_secret)])
async def bot_link(body: BotLinkRequest, db: AsyncSession = Depends(get_db)):
    """Погасить код и привязать telegram_id к пользователю."""
    link_code = await crud_telegram_link_code.consume(db, code=body.code)
    if link_code is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Если этот telegram_id уже привязан к другому пользователю — отвязываем
    existing = await crud_user.get_by_telegram_id(db, telegram_id=body.telegram_id)
    if existing and existing.id != link_code.user_id:
        await crud_user.update(db, db_obj=existing, obj_in={"telegram_id": None})

    user = await crud_user.get(db, id=link_code.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")
    await crud_user.update(db, db_obj=user, obj_in={"telegram_id": body.telegram_id})
    return user


@router.post("/token", response_model=BotTokenResponse, dependencies=[Depends(verify_bot_secret)])
async def bot_token(body: BotTokenRequest, db: AsyncSession = Depends(get_db)):
    """Выдать JWT-токены пользователя по его telegram_id (для вызовов от имени пользователя)."""
    user = await crud_user.get_by_telegram_id(db, telegram_id=body.telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Telegram account not linked")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return BotTokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
