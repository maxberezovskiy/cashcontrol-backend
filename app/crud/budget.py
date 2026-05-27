from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.budget import Budget
from app.schemas.budget import BudgetCreate, BudgetUpdate


class CRUDBudget(CRUDBase[Budget, BudgetCreate, BudgetUpdate]):
    async def get_by_user(self, db: AsyncSession, *, user_id: int) -> Sequence[Budget]:
        result = await db.execute(
            select(Budget).where(Budget.user_id == user_id, Budget.is_active == True)
        )
        return result.scalars().all()

    async def create_for_user(
        self, db: AsyncSession, *, obj_in: BudgetCreate, user_id: int
    ) -> Budget:
        db_obj = Budget(**obj_in.model_dump(), user_id=user_id)
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj


crud_budget = CRUDBudget(Budget)
