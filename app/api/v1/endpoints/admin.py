from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import email as email_service
from app.core.config import settings
from app.core.dependencies import get_current_superuser
from app.crud.account import crud_account
from app.crud.audit_log import crud_audit_log
from app.crud.password_reset import crud_password_reset
from app.crud.smtp_settings import crud_smtp_settings
from app.crud.transaction import crud_transaction
from app.crud.user import crud_user
from app.db.session import get_db
from app.models.smtp_settings import SmtpSettings
from app.models.user import User
from app.schemas.account import AccountRead
from app.schemas.audit import PaginatedAuditLogs
from app.schemas.settings import SmtpSettingsRead, SmtpSettingsUpdate, SmtpTestRequest
from app.schemas.transaction import TransactionRead
from app.schemas.user import (
    PaginatedUsers,
    RoleUpdate,
    UserAdminRead,
    UserAdminUpdate,
)

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


async def _guard_last_admin(db: AsyncSession, user: User) -> None:
    """Защита последнего активного администратора (§2.3)."""
    if user.is_superuser and user.is_active and await crud_user.count_active_admins(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя выполнить действие над последним активным администратором",
        )


# ---- Пользователи ----

@router.get("/users", response_model=PaginatedUsers)
async def list_users(
    q: str | None = None,
    is_active: bool | None = None,
    role: str | None = Query(default=None, pattern="^(admin|user)$"),
    offset: int = 0,
    limit: int = Query(default=50, le=200),
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud_user.search(
        db, q=q, is_active=is_active, role=role, offset=offset, limit=limit
    )
    return PaginatedUsers(items=items, total=total)


@router.get("/users/{user_id}", response_model=UserAdminRead)
async def get_user(
    user_id: int,
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await _get_user_or_404(db, user_id)


@router.patch("/users/{user_id}", response_model=UserAdminRead)
async def update_user(
    user_id: int,
    user_in: UserAdminUpdate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    if user_in.email and user_in.email != user.email:
        existing = await crud_user.get_by_email(db, email=user_in.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
    changes = user_in.model_dump(exclude_unset=True)
    updated = await crud_user.update(db, db_obj=user, obj_in=user_in)
    await crud_audit_log.log(
        db,
        actor_user_id=admin.id,
        action="user.update",
        target_user_id=user.id,
        meta={"changes": list(changes.keys())},
        ip=_client_ip(request),
    )
    return updated


@router.post("/users/{user_id}/activate", response_model=UserAdminRead)
async def activate_user(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    updated = await crud_user.set_active(db, user=user, is_active=True)
    await crud_audit_log.log(
        db,
        actor_user_id=admin.id,
        action="user.activate",
        target_user_id=user.id,
        ip=_client_ip(request),
    )
    return updated


@router.post("/users/{user_id}/deactivate", response_model=UserAdminRead)
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Нельзя деактивировать самого себя"
        )
    await _guard_last_admin(db, user)
    updated = await crud_user.set_active(db, user=user, is_active=False)
    await crud_audit_log.log(
        db,
        actor_user_id=admin.id,
        action="user.deactivate",
        target_user_id=user.id,
        ip=_client_ip(request),
    )
    return updated


@router.post("/users/{user_id}/role", response_model=UserAdminRead)
async def change_role(
    user_id: int,
    body: RoleUpdate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    make_admin = body.role == "admin"
    if not make_admin:  # снятие роли admin
        if user.id == admin.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя снять роль администратора с самого себя",
            )
        await _guard_last_admin(db, user)
    updated = await crud_user.set_role(db, user=user, is_superuser=make_admin)
    await crud_audit_log.log(
        db,
        actor_user_id=admin.id,
        action="user.role_change",
        target_user_id=user.id,
        meta={"role": body.role},
        ip=_client_ip(request),
    )
    return updated


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Нельзя удалить самого себя"
        )
    await _guard_last_admin(db, user)
    # Аудит пишем до удаления; target_user_id обнулится каскадом (ON DELETE SET NULL),
    # поэтому идентификаторы дублируем в meta.
    await crud_audit_log.log(
        db,
        actor_user_id=admin.id,
        action="user.delete",
        target_user_id=user.id,
        meta={"user_id": user.id, "email": user.email},
        ip=_client_ip(request),
    )
    await crud_user.delete(db, id=user.id)


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: int,
    request: Request,
    background: BackgroundTasks,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Инициировать сброс пароля пользователя: создать токен и отправить письмо со ссылкой."""
    user = await _get_user_or_404(db, user_id)
    raw_token = await crud_password_reset.create(
        db,
        user_id=user.id,
        created_by=admin.id,
        ttl_minutes=settings.PASSWORD_RESET_TTL_MINUTES,
    )
    await crud_audit_log.log(
        db,
        actor_user_id=admin.id,
        action="user.password_reset_requested",
        target_user_id=user.id,
        ip=_client_ip(request),
    )
    background.add_task(email_service.send_password_reset_email, user.email, raw_token)
    return {"detail": "Письмо со ссылкой для сброса пароля отправлено"}


# ---- Read-only финансы пользователя ----

@router.get("/users/{user_id}/accounts", response_model=list[AccountRead])
async def list_user_accounts(
    user_id: int,
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_or_404(db, user_id)
    return await crud_account.get_by_user(db, user_id=user_id)


@router.get("/users/{user_id}/transactions", response_model=list[TransactionRead])
async def list_user_transactions(
    user_id: int,
    account_id: int | None = None,
    category_id: int | None = None,
    transaction_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    offset: int = 0,
    limit: int = Query(default=50, le=200),
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_or_404(db, user_id)
    return await crud_transaction.get_by_user(
        db,
        user_id=user_id,
        account_id=account_id,
        category_id=category_id,
        transaction_type=transaction_type,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )


# ---- Настройки SMTP ----

def _smtp_read(cfg: SmtpSettings | None) -> SmtpSettingsRead:
    if cfg is None:
        return SmtpSettingsRead()
    return SmtpSettingsRead(
        host=cfg.host,
        port=cfg.port,
        username=cfg.username,
        use_tls=cfg.use_tls,
        from_email=cfg.from_email,
        enabled=cfg.enabled,
        password_set=bool(cfg.password_encrypted),
        updated_at=cfg.updated_at,
    )


@router.get("/settings/smtp", response_model=SmtpSettingsRead)
async def get_smtp_settings(
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    return _smtp_read(await crud_smtp_settings.get(db))


@router.put("/settings/smtp", response_model=SmtpSettingsRead)
async def update_smtp_settings(
    body: SmtpSettingsUpdate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    cfg = await crud_smtp_settings.upsert(db, data=data, updated_by=admin.id)
    await crud_audit_log.log(
        db,
        actor_user_id=admin.id,
        action="settings.smtp_update",
        meta={
            "fields": [k for k in data if k != "password"],
            "password_changed": bool(data.get("password")),
        },
        ip=_client_ip(request),
    )
    return _smtp_read(cfg)


@router.post("/settings/smtp/test")
async def test_smtp_settings(
    body: SmtpTestRequest,
    _: User = Depends(get_current_superuser),
):
    """Отправить тестовое письмо по текущим настройкам (даже если enabled=false)."""
    try:
        await email_service.deliver(
            to=body.to,
            subject="CashControl — тестовое письмо",
            text="Это тестовое письмо от CashControl. SMTP настроен корректно.",
            html="<p>Это тестовое письмо от <strong>CashControl</strong>. "
            "SMTP настроен корректно.</p>",
            require_enabled=False,
        )
    except email_service.EmailNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — наружу отдаём текст ошибки SMTP
        raise HTTPException(status_code=502, detail=f"Ошибка SMTP: {exc}")
    return {"detail": f"Тестовое письмо отправлено на {body.to}"}


# ---- Журнал аудита ----

@router.get("/audit-logs", response_model=PaginatedAuditLogs)
async def list_audit_logs(
    actor_id: int | None = None,
    target_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    offset: int = 0,
    limit: int = Query(default=50, le=200),
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud_audit_log.search(
        db,
        actor_id=actor_id,
        target_id=target_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )
    return PaginatedAuditLogs(items=items, total=total)
