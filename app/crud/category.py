from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


class CRUDCategory(CRUDBase[Category, CategoryCreate, CategoryUpdate]):
    async def get_for_user(self, db: AsyncSession, *, user_id: int) -> Sequence[Category]:
        """Return system categories + user's own categories."""
        result = await db.execute(
            select(Category).where(
                or_(Category.user_id == user_id, Category.user_id.is_(None))
            )
        )
        return result.scalars().all()

    async def create_for_user(
        self, db: AsyncSession, *, obj_in: CategoryCreate, user_id: int
    ) -> Category:
        db_obj = Category(**obj_in.model_dump(), user_id=user_id)
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj


crud_category = CRUDCategory(Category)
