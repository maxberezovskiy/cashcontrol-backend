from datetime import datetime

from pydantic import BaseModel


class CategoryBase(BaseModel):
    name: str
    category_type: str  # income / expense
    color: str | None = None
    icon: str | None = None
    parent_id: int | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    icon: str | None = None


class CategoryRead(CategoryBase):
    id: int
    user_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
