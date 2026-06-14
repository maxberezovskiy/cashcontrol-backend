from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class CRUDAuditLog:
    async def log(
        self,
        db: AsyncSession,
        *,
        actor_user_id: int | None,
        action: str,
        target_user_id: int | None = None,
        meta: dict[str, Any] | None = None,
        ip: str | None = None,
    ) -> AuditLog:
        """Записать событие аудита. Вызывается в той же транзакции, что и действие."""
        entry = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_user_id=target_user_id,
            meta=meta,
            ip=ip,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def search(
        self,
        db: AsyncSession,
        *,
        actor_id: int | None = None,
        target_id: int | None = None,
        action: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[AuditLog], int]:
        conditions = []
        if actor_id is not None:
            conditions.append(AuditLog.actor_user_id == actor_id)
        if target_id is not None:
            conditions.append(AuditLog.target_user_id == target_id)
        if action is not None:
            conditions.append(AuditLog.action == action)
        if date_from is not None:
            conditions.append(AuditLog.created_at >= date_from)
        if date_to is not None:
            conditions.append(AuditLog.created_at <= date_to)

        base_q = select(AuditLog)
        count_q = select(func.count()).select_from(AuditLog)
        for cond in conditions:
            base_q = base_q.where(cond)
            count_q = count_q.where(cond)

        total = (await db.execute(count_q)).scalar_one()
        result = await db.execute(
            base_q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
        return result.scalars().all(), total


crud_audit_log = CRUDAuditLog()
