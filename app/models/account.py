from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)  # cash, card, deposit, credit
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    color: Mapped[str | None] = mapped_column(String(7))  # hex color
    icon: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="accounts")
    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        foreign_keys="[Transaction.account_id]",
    )
