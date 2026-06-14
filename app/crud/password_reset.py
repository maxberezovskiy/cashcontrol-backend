import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset import PasswordResetToken


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class CRUDPasswordReset:
    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        created_by: int | None,
        ttl_minutes: int,
    ) -> str:
        """Создать токен сброса, инвалидировав прежние неиспользованные. Возвращает сырой токен."""
        now = datetime.now(timezone.utc)
        await db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw = secrets.token_urlsafe(32)
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=_hash_token(raw),
            expires_at=now + timedelta(minutes=ttl_minutes),
            created_by=created_by,
        )
        db.add(token)
        await db.flush()
        return raw

    async def get_valid(self, db: AsyncSession, *, raw: str) -> PasswordResetToken | None:
        """Вернуть токен, если он существует, не использован и не истёк; иначе None."""
        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == _hash_token(raw)
            )
        )
        token = result.scalar_one_or_none()
        if token is None or token.used_at is not None:
            return None
        if token.expires_at <= datetime.now(timezone.utc):
            return None
        return token

    async def mark_used(self, db: AsyncSession, *, token: PasswordResetToken) -> None:
        token.used_at = datetime.now(timezone.utc)
        db.add(token)
        await db.flush()


crud_password_reset = CRUDPasswordReset()
