# backend/app/schemas/failed_events.py
from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from .base import ORMBaseModel


class FailedEventOut(ORMBaseModel):
    id: int
    tenant_id: str
    event_id: Optional[str] = Field(default=None, max_length=255)
    raw_payload: dict[str, Any]
    error_message: str
    retry_count: int
    created_at: datetime
    last_retry_at: Optional[datetime] = None