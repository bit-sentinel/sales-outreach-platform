"""Audit logging helper – write to audit_logs table asynchronously."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert one audit_log row.  Fire-and-forget – never raises."""
    try:
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details,
        )
        db.add(entry)
        await db.flush()
    except Exception:
        pass  # never block the main request
