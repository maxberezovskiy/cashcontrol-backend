from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.crud.category import crud_category
from app.db.session import get_db
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter()


@router.get("/", response_model=List[CategoryRead])
async def list_categories(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud_category.get_for_user(db, user_id=current_user.id)


@router.post("/", response_model=CategoryRead, status_code=201)
async def create_category(
    category_in: CategoryCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud_category.create_for_user(db, obj_in=category_in, user_id=current_user.id)


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    category_in: CategoryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    category = await crud_category.get(db, id=category_id)
    if not category or category.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Category not found")
    return await crud_category.update(db, db_obj=category, obj_in=category_in)


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    category = await crud_category.get(db, id=category_id)
    if not category or category.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Category not found")
    await crud_category.delete(db, id=category_id)
