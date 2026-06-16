from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SmtpSettings(Base):
    """Single-row конфиг внешнего SMTP (id=1). Источник истины для отправки писем.

    Пароль хранится зашифрованным (Fernet, см. app.core.crypto) и наружу в API не отдаётся.
    """

    __tablename__ = "smtp_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # всегда 1
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    use_tls: Mapped[str] = mapped_column(String(16), default="starttls", nullable=False)
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Транспорт писем: "smtp" (по умолчанию) или "api" (HTTPS-API провайдера, когда
    # исходящий SMTP закрыт сетью). api_key шифруется тем же Fernet, что и SMTP-пароль.
    transport: Mapped[str] = mapped_column(String(16), default="smtp", nullable=False)
    api_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
