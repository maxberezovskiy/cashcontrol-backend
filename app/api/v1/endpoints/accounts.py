from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.crud.account import crud_account
from app.db.session import get_db
from app.models.user import User
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate

router = APIRouter()


@router.get("/", response_model=List[AccountRead])
async def list_accounts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud_account.get_by_user(db, user_id=current_user.id)


@router.post("/", response_model=AccountRead, status_code=201)
async def create_account(
    account_in: AccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud_account.create_for_user(db, obj_in=account_in, user_id=current_user.id)


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    account = await crud_account.get(db, id=account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: int,
    account_in: AccountUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    account = await crud_account.get(db, id=account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    return await crud_account.update(db, db_obj=account, obj_in=account_in)


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    account = await crud_account.get(db, id=account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    await crud_account.delete(db, id=account_id)
