from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.crud.account import crud_account
from app.crud.transaction import crud_transaction
from app.db.session import get_db
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate

router = APIRouter()


@router.get("/", response_model=List[TransactionRead])
async def list_transactions(
    account_id: int | None = Query(None),
    category_id: int | None = Query(None),
    transaction_type: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud_transaction.get_by_user(
        db,
        user_id=current_user.id,
        account_id=account_id,
        category_id=category_id,
        transaction_type=transaction_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.post("/", response_model=TransactionRead, status_code=201)
async def create_transaction(
    transaction_in: TransactionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    account = await crud_account.get(db, id=transaction_in.account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    return await crud_transaction.create(db, obj_in=transaction_in)


@router.get("/{transaction_id}", response_model=TransactionRead)
async def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    transaction = await crud_transaction.get(db, id=transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    account = await crud_account.get(db, id=transaction.account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int,
    transaction_in: TransactionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    transaction = await crud_transaction.get(db, id=transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    account = await crud_account.get(db, id=transaction.account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return await crud_transaction.update(db, db_obj=transaction, obj_in=transaction_in)


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    transaction = await crud_transaction.get(db, id=transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    account = await crud_account.get(db, id=transaction.account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    await crud_transaction.delete(db, id=transaction_id)
