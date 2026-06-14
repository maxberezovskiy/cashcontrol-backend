from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, db: AsyncSession, *, telegram_id: int) -> User | None:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, *, obj_in: UserCreate) -> User:
        db_obj = User(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            full_name=obj_in.full_name,
        )
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def authenticate(self, db: AsyncSession, *, email: str, password: str) -> User | None:
        user = await self.get_by_email(db, email=email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def search(
        self,
        db: AsyncSession,
        *,
        q: str | None = None,
        is_active: bool | None = None,
        role: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[User], int]:
        conditions = []
        if q:
            like = f"%{q}%"
            conditions.append(or_(User.email.ilike(like), User.full_name.ilike(like)))
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if role is not None:
            conditions.append(User.is_superuser.is_(role == "admin"))

        base_q = select(User)
        count_q = select(func.count()).select_from(User)
        for cond in conditions:
            base_q = base_q.where(cond)
            count_q = count_q.where(cond)

        total = (await db.execute(count_q)).scalar_one()
        result = await db.execute(base_q.order_by(User.id).offset(offset).limit(limit))
        return result.scalars().all(), total

    async def set_active(self, db: AsyncSession, *, user: User, is_active: bool) -> User:
        user.is_active = is_active
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    async def set_role(self, db: AsyncSession, *, user: User, is_superuser: bool) -> User:
        user.is_superuser = is_superuser
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    async def count_active_admins(self, db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.is_superuser.is_(True), User.is_active.is_(True))
        )
        return result.scalar_one()


crud_user = CRUDUser(User)
