from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class BudgetBase(BaseModel):
    name: str
    amount: Decimal
    period: str  # monthly / weekly / yearly
    start_date: date
    end_date: date | None = None
    category_id: int | None = None


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    name: str | None = None
    amount: Decimal | None = None
    is_active: bool | None = None
    end_date: date | None = None


class BudgetRead(BudgetBase):
    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    spent: Decimal = Decimal("0")  # вычисляется динамически

    model_config = {"from_attributes": True}
