from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionUpdate


class CRUDTransaction(CRUDBase[Transaction, TransactionCreate, TransactionUpdate]):
    async def create(self, db: AsyncSession, *, obj_in: TransactionCreate) -> Transaction:
        db_obj = Transaction(**obj_in.model_dump())
        db.add(db_obj)

        # Update account balance
        account = await db.get(Account, obj_in.account_id)
        if account:
            if obj_in.transaction_type == "income":
                account.balance += obj_in.amount
            elif obj_in.transaction_type == "expense":
                account.balance -= obj_in.amount
            elif obj_in.transaction_type == "transfer" and obj_in.to_account_id:
                account.balance -= obj_in.amount
                to_account = await db.get(Account, obj_in.to_account_id)
                if to_account:
                    to_account.balance += obj_in.amount

        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: Transaction,
        obj_in: TransactionUpdate | dict,
    ) -> Transaction:
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)

        new_amount = update_data.get("amount")
        if new_amount is not None:
            new_amount = Decimal(str(new_amount))
            old_amount = db_obj.amount
            diff = new_amount - old_amount  # positive means increase

            account = await db.get(Account, db_obj.account_id)
            if account:
                if db_obj.transaction_type == "income":
                    account.balance += diff
                elif db_obj.transaction_type == "expense":
                    account.balance -= diff
                elif db_obj.transaction_type == "transfer":
                    account.balance -= diff
                    if db_obj.to_account_id:
                        to_account = await db.get(Account, db_obj.to_account_id)
                        if to_account:
                            to_account.balance += diff

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def get_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        account_id: int | None = None,
        category_id: int | None = None,
        transaction_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Transaction]:
        stmt = (
            select(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .where(Account.user_id == user_id)
        )
        if account_id:
            stmt = stmt.where(Transaction.account_id == account_id)
        if category_id:
            stmt = stmt.where(Transaction.category_id == category_id)
        if transaction_type:
            stmt = stmt.where(Transaction.transaction_type == transaction_type)
        if date_from:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to:
            stmt = stmt.where(Transaction.date <= date_to)

        stmt = stmt.order_by(Transaction.date.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_spent_for_budget(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        category_id: int | None,
        date_from: datetime,
        date_to: datetime,
    ) -> Decimal:
        stmt = (
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .join(Account, Transaction.account_id == Account.id)
            .where(
                and_(
                    Account.user_id == user_id,
                    Transaction.transaction_type == "expense",
                    Transaction.date >= date_from,
                    Transaction.date <= date_to,
                )
            )
        )
        if category_id:
            stmt = stmt.where(Transaction.category_id == category_id)
        result = await db.execute(stmt)
        return result.scalar() or Decimal("0")


crud_transaction = CRUDTransaction(Transaction)
