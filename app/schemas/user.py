from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = None


class UserRead(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserAdminRead(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    telegram_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserAdminUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None


class RoleUpdate(BaseModel):
    role: Literal["admin", "user"]


class PaginatedUsers(BaseModel):
    items: list[UserAdminRead]
    total: int


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str
