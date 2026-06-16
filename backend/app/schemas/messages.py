# backend/app/schemas/messages.py
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .base import ORMBaseModel


class MessageLogCreate(BaseModel):
    """
    Schema for att skapa en message_log manuellt via API.
    Anvands av n8n for att logga skickade meddelanden.
    """

    contact_id: str = Field(min_length=1, description="ID of the contact")

    campaign_id: Optional[str] = Field(default=None, max_length=100)
    workflow_id: Optional[str] = Field(default=None, max_length=100)
    event_id: Optional[str] = Field(default=None, max_length=255)

    channel: Literal["sms", "email"] = Field(
        description="Kanal: sms eller email",
    )
    direction: Literal["outbound", "inbound"] = Field(default="outbound")

    provider: Optional[str] = Field(default=None, max_length=50)
    provider_message_id: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Externt meddelande-ID fran SMS/email-provider",
    )

    template_key: Optional[str] = Field(default=None, max_length=100)
    subject: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = Field(default=None)

    status: Literal[
        "queued", "sent", "delivered", "failed",
        "opened", "clicked", "replied", "bounced",
    ] = Field(default="sent")

    failure_reason: Optional[str] = Field(default=None)

    metadata_json: dict[str, Any] = Field(default_factory=dict)

    sent_at: Optional[datetime] = Field(
        default=None,
        description="Om inte satt anvands nuvarande tid for sent-status",
    )


class MessageLogOut(ORMBaseModel):
    id: str
    tenant_id: str
    contact_id: str

    campaign_id: Optional[str] = Field(default=None, max_length=100)
    workflow_id: Optional[str] = Field(default=None, max_length=100)
    event_id: Optional[str] = Field(default=None, max_length=255)

    channel: str = Field(max_length=20)
    direction: str = Field(max_length=20)

    provider: Optional[str] = Field(default=None, max_length=50)
    provider_message_id: Optional[str] = Field(default=None, max_length=255)

    template_key: Optional[str] = Field(default=None, max_length=100)
    subject: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = None

    status: str = Field(max_length=50)
    failure_reason: Optional[str] = None

    metadata_json: dict[str, Any]

    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None

    created_at: datetime