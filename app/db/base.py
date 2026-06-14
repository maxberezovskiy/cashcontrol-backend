from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models here so Alembic can detect them
from app.models.user import User  # noqa: F401, E402
from app.models.account import Account  # noqa: F401, E402
from app.models.transaction import Transaction  # noqa: F401, E402
from app.models.category import Category  # noqa: F401, E402
from app.models.budget import Budget  # noqa: F401, E402
from app.models.telegram_link_code import TelegramLinkCode  # noqa: F401, E402
from app.models.audit_log import AuditLog  # noqa: F401, E402
from app.models.smtp_settings import SmtpSettings  # noqa: F401, E402
from app.models.password_reset import PasswordResetToken  # noqa: F401, E402
