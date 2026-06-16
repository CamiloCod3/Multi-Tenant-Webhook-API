# backend/app/schemas/opt_out.py
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import ORMBaseModel


class OptOutRequest(BaseModel):
    """
    Begaran om att opt-outa en kontakt fran en eller flera kanaler.
    Anvands av n8n, webhooks, eller admin-verktyg.
    """

    channel: str = Field(
        min_length=1,
        max_length=20,
        description="Kanal att opt-outa fran: sms, email, eller all",
    )
    source: str = Field(
        default="api",
        max_length=50,
        description=(
            "Vad som triggade opt-out: "
            "sms_reply, unsubscribe_link, admin_action, crm_sync, api"
        ),
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Frivillig anledning",
    )


class OptInRequest(BaseModel):
    """Aterställer opt-out for en kanal."""

    channel: str = Field(
        min_length=1,
        max_length=20,
        description="Kanal att opt-ina tillbaka: sms, email, eller all",
    )
    source: str = Field(default="api", max_length=50)


class ContactOptOutEventOut(ORMBaseModel):
    id: int
    tenant_id: str
    contact_id: str
    channel: str
    source: str
    reason: Optional[str] = None
    metadata_json: dict[str, Any]
    occurred_at: datetime
    created_at: datetime