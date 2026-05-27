from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountUpdate


class CRUDAccount(CRUDBase[Account, AccountCreate, AccountUpdate]):
    async def get_by_user(self, db: AsyncSession, *, user_id: int) -> Sequence[Account]:
        result = await db.execute(
            select(Account).where(Account.user_id == user_id, Account.is_active == True)
        )
        return result.scalars().all()

    async def create_for_user(
        self, db: AsyncSession, *, obj_in: AccountCreate, user_id: int
    ) -> Account:
        db_obj = Account(**obj_in.model_dump(), user_id=user_id)
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj


crud_account = CRUDAccount(Account)
