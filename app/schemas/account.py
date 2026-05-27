from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class AccountBase(BaseModel):
    name: str
    account_type: str
    currency: str = "RUB"
    color: str | None = None
    icon: str | None = None


class AccountCreate(AccountBase):
    balance: Decimal = Decimal("0")


class AccountUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    icon: str | None = None
    is_active: bool | None = None


class AccountRead(AccountBase):
    id: int
    user_id: int
    balance: Decimal
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
