from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class TransactionBase(BaseModel):
    transaction_type: str  # income / expense / transfer
    amount: Decimal
    currency: str = "RUB"
    description: str | None = None
    note: str | None = None
    date: datetime
    category_id: int | None = None
    to_account_id: int | None = None


class TransactionCreate(TransactionBase):
    account_id: int


class TransactionUpdate(BaseModel):
    amount: Decimal | None = None
    description: str | None = None
    note: str | None = None
    category_id: int | None = None
    date: datetime | None = None


class TransactionRead(TransactionBase):
    id: int
    account_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionListParams(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    transaction_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 50
    offset: int = 0
