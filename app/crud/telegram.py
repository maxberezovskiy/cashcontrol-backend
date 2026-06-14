import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.telegram_link_code import TelegramLinkCode

# Без похожих символов (0/O, 1/I), чтобы код легко вводился вручную
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_code(length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


class CRUDTelegramLinkCode:
    async def create_for_user(self, db: AsyncSession, *, user_id: int) -> TelegramLinkCode:
        # Удаляем прежние неиспользованные коды пользователя — активным остаётся один
        existing = await db.execute(
            select(TelegramLinkCode).where(
                TelegramLinkCode.user_id == user_id,
                TelegramLinkCode.used == False,  # noqa: E712
            )
        )
        for old in existing.scalars().all():
            await db.delete(old)

        # На случай коллизии генерируем код в цикле
        code = _generate_code()
        while await self._get_by_code(db, code=code) is not None:
            code = _generate_code()

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.TELEGRAM_LINK_CODE_TTL_MINUTES
        )
        db_obj = TelegramLinkCode(code=code, user_id=user_id, expires_at=expires_at)
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def _get_by_code(self, db: AsyncSession, *, code: str) -> TelegramLinkCode | None:
        result = await db.execute(
            select(TelegramLinkCode).where(TelegramLinkCode.code == code)
        )
        return result.scalar_one_or_none()

    async def consume(self, db: AsyncSession, *, code: str) -> TelegramLinkCode | None:
        """Атомарно возвращает валидный код и помечает использованным, либо None.

        Берём блокировку строки (FOR UPDATE), чтобы два параллельных /link с одним
        кодом не прошли оба (TOCTOU): второй дождётся коммита первого и увидит used=True.
        """
        result = await db.execute(
            select(TelegramLinkCode)
            .where(TelegramLinkCode.code == code.strip().upper())
            .with_for_update()
        )
        link_code = result.scalar_one_or_none()
        if link_code is None or link_code.used:
            return None
        expires_at = link_code.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return None
        link_code.used = True
        db.add(link_code)
        await db.flush()
        return link_code


crud_telegram_link_code = CRUDTelegramLinkCode()
