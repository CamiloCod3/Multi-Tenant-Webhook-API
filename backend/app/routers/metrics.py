# app/routers/metrics.py
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, select, func
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.rate_limit import limiter
from ..core.deps import require_admin_token

from ..models.contacts import Contact
from ..models.message_log import MessageLog
from ..models.metrics import (
    CampaignStats,
    FailedEvent,
    LeadEvent,
    RevenueSnapshot,
    WorkflowStats,
)
from ..schemas.metrics import (
    CampaignStatsOut,
    ContactStatusBreakdown,
    LeadEventOut,
    MetricsOverviewOut,
    RevenueSnapshotOut,
    WorkflowStatsOut,
)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


# ---- Campaign stats ----

@router.get("/campaigns", response_model=List[CampaignStatsOut])
@limiter.limit("60/minute")
def get_campaign_stats(
    request: Request,
    tenant_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    stmt = select(CampaignStats).order_by(CampaignStats.updated_at.desc())
    if tenant_id:
        stmt = stmt.where(CampaignStats.tenant_id == tenant_id)
    stmt = stmt.limit(limit).offset(offset)
    return db.scalars(stmt).all()


# ---- Workflow stats ----

@router.get("/workflows", response_model=List[WorkflowStatsOut])
@limiter.limit("60/minute")
def get_workflow_stats(
    request: Request,
    tenant_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    stmt = select(WorkflowStats).order_by(WorkflowStats.updated_at.desc())
    if tenant_id:
        stmt = stmt.where(WorkflowStats.tenant_id == tenant_id)
    stmt = stmt.limit(limit).offset(offset)
    return db.scalars(stmt).all()


# ---- Lead events ----

@router.get("/lead-events", response_model=List[LeadEventOut])
@limiter.limit("60/minute")
def get_lead_events(
    request: Request,
    tenant_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    stmt = select(LeadEvent).order_by(LeadEvent.occurred_at.desc())
    if tenant_id:
        stmt = stmt.where(LeadEvent.tenant_id == tenant_id)
    if event_type:
        stmt = stmt.where(LeadEvent.event_type == event_type)
    stmt = stmt.limit(limit).offset(offset)
    return db.scalars(stmt).all()


# ---- Revenue snapshots ----

@router.get("/revenue", response_model=List[RevenueSnapshotOut])
@limiter.limit("60/minute")
def get_revenue_snapshots(
    request: Request,
    tenant_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    stmt = select(RevenueSnapshot).order_by(RevenueSnapshot.period_start.desc())
    if tenant_id:
        stmt = stmt.where(RevenueSnapshot.tenant_id == tenant_id)
    stmt = stmt.limit(limit).offset(offset)
    return db.scalars(stmt).all()


# ---- Helper: tenant filter ----

def _tenant_where(stmt, model, tenant_id: Optional[str]):
    """Lagger till tenant_id filter om det ar satt."""
    if tenant_id:
        return stmt.where(model.tenant_id == tenant_id)
    return stmt


# ---- Overview / dashboard ----

@router.get("/overview", response_model=MetricsOverviewOut)
@limiter.limit("30/minute")
def get_metrics_overview(
    request: Request,
    tenant_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """
    Utokad sammanfattning for dashboard.
    Om tenant_id satt -> overview for en tenant, annars global.
    """

    # --- Campaigns ---
    q = _tenant_where(
        select(func.count()).select_from(CampaignStats),
        CampaignStats,
        tenant_id,
    )
    total_campaigns = db.scalar(q) or 0

    # --- Workflows ---
    q = _tenant_where(
        select(func.count()).select_from(WorkflowStats),
        WorkflowStats,
        tenant_id,
    )
    total_workflows = db.scalar(q) or 0

    # --- Lead events ---
    q = _tenant_where(
        select(func.count()).select_from(LeadEvent),
        LeadEvent,
        tenant_id,
    )
    total_lead_events = db.scalar(q) or 0

    # --- Revenue ---
    q = _tenant_where(
        select(func.coalesce(func.sum(RevenueSnapshot.attributed_revenue), 0)),
        RevenueSnapshot,
        tenant_id,
    )
    total_revenue = Decimal(db.scalar(q) or 0)

    q_last_rev = select(RevenueSnapshot).order_by(RevenueSnapshot.created_at.desc()).limit(1)
    if tenant_id:
        q_last_rev = q_last_rev.where(RevenueSnapshot.tenant_id == tenant_id)
    last_rev_row = db.scalars(q_last_rev).first()

    currency = last_rev_row.currency if last_rev_row else None
    last_revenue_snapshot_at = last_rev_row.created_at if last_rev_row else None

    # --- Latest event ---
    q = _tenant_where(
        select(func.max(LeadEvent.occurred_at)),
        LeadEvent,
        tenant_id,
    )
    last_event_at = db.scalar(q)

    # --- Contacts: total + status breakdown ---
    q = _tenant_where(
        select(func.count()).select_from(Contact),
        Contact,
        tenant_id,
    )
    total_contacts = db.scalar(q) or 0

    known_statuses = ("new", "contacted", "engaged", "converted")
    status_counts = {}
    if total_contacts > 0:
        status_q = select(
            Contact.status,
            func.count().label("cnt"),
        ).group_by(Contact.status)
        if tenant_id:
            status_q = status_q.where(Contact.tenant_id == tenant_id)

        for row in db.execute(status_q).all():
            s, cnt = row
            if s in known_statuses:
                status_counts[s] = cnt
            else:
                status_counts["other"] = status_counts.get("other", 0) + cnt

    contact_status_breakdown = ContactStatusBreakdown(
        new=status_counts.get("new", 0),
        contacted=status_counts.get("contacted", 0),
        engaged=status_counts.get("engaged", 0),
        converted=status_counts.get("converted", 0),
        other=status_counts.get("other", 0),
    )

    # --- Contacts: opt-outs ---
    q = _tenant_where(
        select(func.count()).select_from(Contact).where(Contact.opted_out_sms == True),  # noqa: E712
        Contact,
        tenant_id,
    )
    total_opted_out_sms = db.scalar(q) or 0

    q = _tenant_where(
        select(func.count()).select_from(Contact).where(Contact.opted_out_email == True),  # noqa: E712
        Contact,
        tenant_id,
    )
    total_opted_out_email = db.scalar(q) or 0

    # --- Messages ---
    q = _tenant_where(
        select(func.count()).select_from(MessageLog),
        MessageLog,
        tenant_id,
    )
    total_messages = db.scalar(q) or 0

    msg_status_counts = {}
    if total_messages > 0:
        msg_q = select(
            MessageLog.status,
            func.count().label("cnt"),
        ).group_by(MessageLog.status)
        if tenant_id:
            msg_q = msg_q.where(MessageLog.tenant_id == tenant_id)

        for row in db.execute(msg_q).all():
            msg_status_counts[row[0]] = row[1]

    total_messages_sent = msg_status_counts.get("sent", 0)
    total_messages_delivered = msg_status_counts.get("delivered", 0)
    total_messages_failed = msg_status_counts.get("failed", 0)

    # --- Failed events ---
    q = _tenant_where(
        select(func.count()).select_from(FailedEvent),
        FailedEvent,
        tenant_id,
    )
    total_failed_events = db.scalar(q) or 0

    return MetricsOverviewOut(
        tenant_id=tenant_id,
        total_campaigns=total_campaigns,
        total_workflows=total_workflows,
        total_lead_events=total_lead_events,
        total_revenue=total_revenue,
        currency=currency,
        total_contacts=total_contacts,
        contact_status_breakdown=contact_status_breakdown,
        total_opted_out_sms=total_opted_out_sms,
        total_opted_out_email=total_opted_out_email,
        total_messages=total_messages,
        total_messages_sent=total_messages_sent,
        total_messages_delivered=total_messages_delivered,
        total_messages_failed=total_messages_failed,
        total_failed_events=total_failed_events,
        last_event_at=last_event_at,
        last_revenue_snapshot_at=last_revenue_snapshot_at,
    )