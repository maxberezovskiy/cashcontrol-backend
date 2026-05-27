from datetime import datetime, timezone
from typing import List

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # null = системная категория
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_type: Mapped[str] = mapped_column(String(10), nullable=False)  # income / expense
    color: Mapped[str | None] = mapped_column(String(7))
    icon: Mapped[str | None] = mapped_column(String(50))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User | None"] = relationship(back_populates="categories")
    children: Mapped[List["Category"]] = relationship(back_populates="parent")
    parent: Mapped["Category | None"] = relationship(back_populates="children", remote_side="Category.id")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="category")
    budgets: Mapped[List["Budget"]] = relationship(back_populates="category")
