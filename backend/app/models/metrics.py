# app/models/metrics.py
from datetime import datetime, date

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from ..core.db import Base


class CampaignStats(Base):
    __tablename__ = "campaign_stats"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)

    # Inget index=True har: composite unique (tenant_id, campaign_id) tacker
    # tenant_id-only queries via leading column.
    tenant_id = sa.Column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    campaign_id = sa.Column(sa.String(100), nullable=False)
    campaign_name = sa.Column(sa.String(200), nullable=True)

    total_leads = sa.Column(sa.Integer, nullable=False, server_default="0")
    contacted_leads = sa.Column(sa.Integer, nullable=False, server_default="0")
    engaged_leads = sa.Column(sa.Integer, nullable=False, server_default="0")
    converted_leads = sa.Column(sa.Integer, nullable=False, server_default="0")

    last_lead_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    updated_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "campaign_id",
            name="campaign_stats_tenant_campaign_uq",
        ),
    )


class WorkflowStats(Base):
    __tablename__ = "workflow_stats"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)
    tenant_id = sa.Column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    workflow_id = sa.Column(sa.String(100), nullable=False)
    workflow_name = sa.Column(sa.String(200), nullable=True)

    processed_leads = sa.Column(sa.Integer, nullable=False, server_default="0")
    success_leads = sa.Column(sa.Integer, nullable=False, server_default="0")
    failed_leads = sa.Column(sa.Integer, nullable=False, server_default="0")

    last_run_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    updated_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "workflow_id",
            name="workflow_stats_tenant_workflow_uq",
        ),
    )


class LeadEvent(Base):
    __tablename__ = "lead_events"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)
    tenant_id = sa.Column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_id = sa.Column(sa.String(255), nullable=False)

    lead_id = sa.Column(sa.String(100), nullable=False)
    event_type = sa.Column(sa.String(50), nullable=False)
    source = sa.Column(sa.String(50), nullable=True)

    payload = sa.Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    occurred_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "event_id",
            name="lead_events_tenant_event_uq",
        ),
        sa.Index("lead_events_tenant_lead_idx", "tenant_id", "lead_id"),
        sa.Index("lead_events_tenant_event_type_idx", "tenant_id", "event_type"),
        sa.Index("lead_events_occurred_at_idx", "occurred_at"),
    )


class RevenueSnapshot(Base):
    __tablename__ = "revenue_snapshots"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)
    tenant_id = sa.Column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    period_start = sa.Column(sa.Date, nullable=False)
    period_end = sa.Column(sa.Date, nullable=False)

    total_revenue = sa.Column(sa.Numeric(18, 2), nullable=False, server_default="0")
    attributed_revenue = sa.Column(sa.Numeric(18, 2), nullable=False, server_default="0")
    currency = sa.Column(sa.String(10), nullable=False, server_default="USD")

    created_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "period_start",
            "period_end",
            "currency",
            name="revenue_snapshots_tenant_period_currency_uq",
        ),
    )


class FailedEvent(Base):
    __tablename__ = "failed_events"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)

    # Standalone index definieras i __table_args__, inte via index=True.
    tenant_id = sa.Column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id = sa.Column(sa.String(255), nullable=True)
    raw_payload = sa.Column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    error_message = sa.Column(sa.Text, nullable=False)
    retry_count = sa.Column(sa.Integer, nullable=False, server_default="0")
    created_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    last_retry_at = sa.Column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.Index("failed_events_tenant_idx", "tenant_id"),
        sa.Index("failed_events_created_at_idx", "created_at"),
    )