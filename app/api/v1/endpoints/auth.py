from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import email as email_service
from app.core.config import settings
from app.core.ratelimit import login_limiter, password_reset_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
)
from app.crud.audit_log import crud_audit_log
from app.crud.password_reset import crud_password_reset
from app.crud.user import crud_user
from app.db.session import get_db
from app.schemas.user import (
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    TokenRefresh,
    UserCreate,
    UserRead,
)

router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await crud_user.get_by_email(db, email=user_in.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await crud_user.create(db, obj_in=user_in)
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # Анти-брутфорс: лимит попыток входа на e-mail
    if not login_limiter.allow(form_data.username.strip().lower()):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте через минуту.",
        )
    user = await crud_user.authenticate(db, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/password-reset/request")
async def password_reset_request(
    body: PasswordResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Self-service «забыли пароль». Анти-энумерация: всегда 200."""
    ip = request.client.host if request.client else None
    # Лимит на IP (не на email — иначе атакующий узнаёт существование аккаунта по 429).
    if password_reset_limiter.allow(ip or "unknown"):
        user = await crud_user.get_by_email(db, email=body.email.strip().lower())
        if user and user.is_active:
            raw_token = await crud_password_reset.create(
                db,
                user_id=user.id,
                created_by=user.id,
                ttl_minutes=settings.PASSWORD_RESET_TTL_MINUTES,
            )
            await crud_audit_log.log(
                db,
                actor_user_id=user.id,
                action="auth.password_reset_self_requested",
                target_user_id=user.id,
                ip=ip,
            )
            background.add_task(
                email_service.send_password_reset_email, user.email, raw_token
            )
    return {"detail": "Если аккаунт существует, на почту отправлена ссылка для сброса пароля"}


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    body: PasswordResetConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else None
    if not password_reset_limiter.allow(ip or "unknown"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток. Попробуйте позже.",
        )
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")
    token = await crud_password_reset.get_valid(db, raw=body.token)
    if token is None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или истекла")
    user = await crud_user.get(db, id=token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или истекла")
    user.hashed_password = get_password_hash(body.new_password)
    db.add(user)
    await crud_password_reset.mark_used(db, token=token)
    await crud_audit_log.log(
        db,
        actor_user_id=user.id,
        action="auth.password_reset_completed",
        target_user_id=user.id,
        ip=ip,
    )
    return {"detail": "Пароль обновлён"}


@router.post("/refresh", response_model=Token)
async def refresh_token(body: TokenRefresh, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await crud_user.get(db, id=user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
