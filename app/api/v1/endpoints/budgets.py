from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.crud.budget import crud_budget
from app.crud.transaction import crud_transaction
from app.db.session import get_db
from app.models.user import User
from app.schemas.budget import BudgetCreate, BudgetRead, BudgetUpdate

router = APIRouter()


def _get_period_dates(budget) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if budget.period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=now.year + 1, month=1)
        else:
            end = start.replace(month=now.month + 1)
    elif budget.period == "weekly":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start.replace(day=start.day - start.weekday())
        end = start.replace(day=start.day + 7)
    else:  # yearly
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=now.year + 1)
    return start, end


@router.get("/", response_model=List[BudgetRead])
async def list_budgets(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    budgets = await crud_budget.get_by_user(db, user_id=current_user.id)
    result = []
    for budget in budgets:
        date_from, date_to = _get_period_dates(budget)
        spent = await crud_transaction.get_spent_for_budget(
            db,
            user_id=current_user.id,
            category_id=budget.category_id,
            date_from=date_from,
            date_to=date_to,
        )
        budget_read = BudgetRead.model_validate(budget)
        budget_read.spent = spent
        result.append(budget_read)
    return result


@router.post("/", response_model=BudgetRead, status_code=201)
async def create_budget(
    budget_in: BudgetCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud_budget.create_for_user(db, obj_in=budget_in, user_id=current_user.id)


@router.patch("/{budget_id}", response_model=BudgetRead)
async def update_budget(
    budget_id: int,
    budget_in: BudgetUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    budget = await crud_budget.get(db, id=budget_id)
    if not budget or budget.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Budget not found")
    return await crud_budget.update(db, db_obj=budget, obj_in=budget_in)


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(
    budget_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    budget = await crud_budget.get(db, id=budget_id)
    if not budget or budget.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Budget not found")
    await crud_budget.delete(db, id=budget_id)
