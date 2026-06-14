from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    actor_user_id: int | None
    action: str
    target_user_id: int | None
    meta: dict[str, Any] | None
    ip: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAuditLogs(BaseModel):
    items: list[AuditLogRead]
    total: int
