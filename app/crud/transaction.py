from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionUpdate


class CRUDTransaction(CRUDBase[Transaction, TransactionCreate, TransactionUpdate]):
    @staticmethod
    def _balance_deltas(
        transaction_type: str,
        account_id: int,
        to_account_id: int | None,
        amount: Decimal,
    ) -> list[tuple[int, Decimal]]:
        """Effect of a transaction on account balances as (account_id, delta) pairs.

        Pass the transaction amount on create, the amount diff on update,
        and the negated amount on delete.
        """
        if transaction_type == "income":
            return [(account_id, amount)]
        if transaction_type == "expense":
            return [(account_id, -amount)]
        if transaction_type == "transfer":
            deltas = [(account_id, -amount)]
            if to_account_id:
                deltas.append((to_account_id, amount))
            return deltas
        return []

    @staticmethod
    async def _apply_balance_deltas(
        db: AsyncSession, deltas: list[tuple[int, Decimal]]
    ) -> None:
        # Atomic in-database increments: safe under concurrent edits,
        # unlike read-modify-write on a loaded Account row.
        for account_id, delta in deltas:
            await db.execute(
                sa_update(Account)
                .where(Account.id == account_id)
                .values(balance=Account.balance + delta)
            )

    async def create(self, db: AsyncSession, *, obj_in: TransactionCreate) -> Transaction:
        db_obj = Transaction(**obj_in.model_dump())
        db.add(db_obj)

        await self._apply_balance_deltas(
            db,
            self._balance_deltas(
                obj_in.transaction_type, obj_in.account_id, obj_in.to_account_id, obj_in.amount
            ),
        )

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
            update_data["amount"] = new_amount
            diff = new_amount - db_obj.amount  # positive means increase
            if diff:
                await self._apply_balance_deltas(
                    db,
                    self._balance_deltas(
                        db_obj.transaction_type, db_obj.account_id, db_obj.to_account_id, diff
                    ),
                )

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> Transaction | None:
        obj = await self.get(db, id)
        if obj:
            await self._apply_balance_deltas(
                db,
                self._balance_deltas(
                    obj.transaction_type, obj.account_id, obj.to_account_id, -obj.amount
                ),
            )
            await db.delete(obj)
            await db.flush()
        return obj

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
