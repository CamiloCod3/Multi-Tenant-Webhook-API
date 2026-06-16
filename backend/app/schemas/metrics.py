# backend/app/schemas/metrics.py
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

from .base import ORMBaseModel


class CampaignStatsOut(ORMBaseModel):
    id: int
    tenant_id: str
    campaign_id: str = Field(max_length=100)
    campaign_name: Optional[str] = Field(default=None, max_length=200)

    total_leads: int
    contacted_leads: int
    engaged_leads: int
    converted_leads: int

    last_lead_at: Optional[datetime] = None
    updated_at: datetime


class WorkflowStatsOut(ORMBaseModel):
    id: int
    tenant_id: str
    workflow_id: str = Field(max_length=100)
    workflow_name: Optional[str] = Field(default=None, max_length=200)

    processed_leads: int
    success_leads: int
    failed_leads: int

    last_run_at: Optional[datetime] = None
    updated_at: datetime


class LeadEventOut(ORMBaseModel):
    id: int
    tenant_id: str
    lead_id: str = Field(max_length=100)
    event_type: str = Field(max_length=50)
    source: Optional[str] = Field(default=None, max_length=50)
    event_id: str = Field(max_length=255)

    payload: dict
    occurred_at: datetime


class RevenueSnapshotOut(ORMBaseModel):
    id: int
    tenant_id: str

    period_start: date
    period_end: date

    total_revenue: Decimal
    attributed_revenue: Decimal
    currency: str = Field(max_length=10)

    created_at: datetime


class ContactStatusBreakdown(BaseModel):
    """Antal kontakter per status."""

    new: int = 0
    contacted: int = 0
    engaged: int = 0
    converted: int = 0
    other: int = 0


class MetricsOverviewOut(BaseModel):
    tenant_id: Optional[str] = None

    # Leads & campaigns
    total_campaigns: int
    total_workflows: int
    total_lead_events: int

    # Revenue
    total_revenue: Decimal
    currency: Optional[str] = None

    # Contacts
    total_contacts: int = 0
    contact_status_breakdown: ContactStatusBreakdown = Field(
        default_factory=ContactStatusBreakdown,
    )

    # Opt-outs
    total_opted_out_sms: int = 0
    total_opted_out_email: int = 0

    # Messages
    total_messages: int = 0
    total_messages_sent: int = 0
    total_messages_delivered: int = 0
    total_messages_failed: int = 0

    # Failed events (dead letter)
    total_failed_events: int = 0

    # Timestamps
    last_event_at: Optional[datetime] = None
    last_revenue_snapshot_at: Optional[datetime] = None