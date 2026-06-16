from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.models.smtp_settings import SmtpSettings

# Поля, обновляемые напрямую (секреты password/api_key шифруются отдельно ниже).
_PLAIN_FIELDS = (
    "host", "port", "username", "use_tls", "from_email", "enabled",
    "transport", "api_provider",
)


class CRUDSmtpSettings:
    async def get(self, db: AsyncSession) -> SmtpSettings | None:
        result = await db.execute(select(SmtpSettings).where(SmtpSettings.id == 1))
        return result.scalar_one_or_none()

    async def upsert(
        self, db: AsyncSession, *, data: dict[str, Any], updated_by: int
    ) -> SmtpSettings:
        cfg = await self.get(db)
        if cfg is None:
            cfg = SmtpSettings(id=1)
            db.add(cfg)
        for field in _PLAIN_FIELDS:
            if field in data and data[field] is not None:
                setattr(cfg, field, data[field])
        # Секреты меняем только если переданы непустыми — иначе сохраняем прежние (write-only).
        if data.get("password"):
            cfg.password_encrypted = encrypt(data["password"])
        if data.get("api_key"):
            cfg.api_key_encrypted = encrypt(data["api_key"])
        cfg.updated_by = updated_by
        await db.flush()
        await db.refresh(cfg)
        return cfg

    def get_decrypted_password(self, cfg: SmtpSettings) -> str | None:
        if not cfg.password_encrypted:
            return None
        return decrypt(cfg.password_encrypted)

    def get_decrypted_api_key(self, cfg: SmtpSettings) -> str | None:
        if not cfg.api_key_encrypted:
            return None
        return decrypt(cfg.api_key_encrypted)


crud_smtp_settings = CRUDSmtpSettings()
