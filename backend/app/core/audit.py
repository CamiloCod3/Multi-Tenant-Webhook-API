# backend/app/core/audit.py
from typing import Any, Optional

from sqlalchemy.orm import Session

from .logging import correlation_id_ctx
from ..models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    tenant_id: str,
    action: str,
    actor: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
    *,
    auto_commit: bool = False,
) -> None:
    """
    Centraliserad audit-loggning via ORM.

    Args:
        db: Database session
        tenant_id: Tenant som ager denna logg
        action: Typ av handelse (t.ex. "user.register", "tenant.create")
        actor: Vem som utforde handlingen (email, "system", etc)
        meta: Extra metadata (dict som blir JSONB)
        auto_commit: Om True, committar direkt (default False)
    """
    meta = meta or {}
    meta["correlation_id"] = correlation_id_ctx.get()

    log = AuditLog(
        tenant_id=tenant_id,
        actor=actor or "system",
        action=action,
        meta=meta,
    )
    db.add(log)

    if auto_commit:
        db.commit()