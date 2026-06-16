# backend/app/schemas/contacts.py
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import ORMBaseModel


class ContactCreate(BaseModel):
    """Skapar en ny kontakt manuellt (inte via webhook)."""

    external_contact_id: Optional[str] = Field(default=None, max_length=120)

    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)

    email: Optional[str] = Field(default=None, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=50)

    registration_number: Optional[str] = Field(default=None, max_length=32)

    source: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="new", max_length=50)

    member_status: str = Field(default="non_member", max_length=50)
    is_member: bool = False

    consent_sms: bool = False
    consent_email: bool = False

    tags: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ContactUpdate(BaseModel):
    """Partiell uppdatering av en kontakt."""

    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)

    email: Optional[str] = Field(default=None, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=50)

    registration_number: Optional[str] = Field(default=None, max_length=32)

    source: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = Field(default=None, max_length=50)

    member_status: Optional[str] = Field(default=None, max_length=50)
    is_member: Optional[bool] = None

    opted_out_sms: Optional[bool] = None
    opted_out_email: Optional[bool] = None
    opt_out_reason: Optional[str] = Field(default=None, max_length=255)

    consent_sms: Optional[bool] = None
    consent_email: Optional[bool] = None

    tags: Optional[list[str]] = None
    metadata_json: Optional[dict[str, Any]] = None


class ContactOut(ORMBaseModel):
    id: str
    tenant_id: str

    external_contact_id: Optional[str] = Field(default=None, max_length=120)

    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)

    email: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    normalized_phone: Optional[str] = Field(default=None, max_length=50)

    registration_number: Optional[str] = Field(default=None, max_length=32)

    source: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(max_length=50)

    member_status: str = Field(max_length=50)
    is_member: bool

    opted_out_sms: bool
    opted_out_email: bool
    opt_out_reason: Optional[str] = Field(default=None, max_length=255)
    opted_out_at: Optional[datetime] = None

    consent_sms: bool
    consent_email: bool

    tags: list[Any]
    metadata_json: dict[str, Any]

    last_message_sent_at: Optional[datetime] = None
    last_engagement_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime


class ContactSummary(ORMBaseModel):
    """Kompakt version for listningar."""

    id: str
    tenant_id: str
    external_contact_id: Optional[str] = None

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    normalized_phone: Optional[str] = None

    source: Optional[str] = None
    status: str
    is_member: bool

    opted_out_sms: bool
    opted_out_email: bool

    last_seen_at: Optional[datetime] = None
    created_at: datetime