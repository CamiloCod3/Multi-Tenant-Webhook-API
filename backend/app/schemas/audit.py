from datetime import datetime
from typing import Optional, Dict, Any

from .base import ORMBaseModel


class AuditLogOut(ORMBaseModel):
    id: int
    tenant_id: str
    actor: Optional[str]
    action: str
    meta: Dict[str, Any]
    created_at: datetime