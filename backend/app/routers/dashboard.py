"""
Read-only dashboard endpoints for customers.

Authentication: dashboard_token in URL (no headers needed).
Each tenant gets a unique URL at creation.
All endpoints return tenant-scoped, read-only data.
"""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.rate_limit import limiter

from ..models.contacts import Contact
from ..models.message_log import MessageLog
from ..models.tenant import Tenant
from ..models.metrics import (
    CampaignStats,
    FailedEvent,
    LeadEvent,
    RevenueSnapshot,
    WorkflowStats,
)
from ..schemas.contacts import ContactSummary
from ..schemas.messages import MessageLogOut
from ..schemas.metrics import (
    CampaignStatsOut,
    LeadEventOut,
    RevenueSnapshotOut,
    WorkflowStatsOut,
)

router = APIRouter(prefix="/api/v1/dashboard/t/{token}", tags=["dashboard"])


# ── Token lookup ──

def _get_tenant_by_dashboard_token(token: str, db: Session) -> Tenant:
    tenant = db.scalar(
        select(Tenant).where(Tenant.dashboard_token == token)
    )
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid dashboard token")
    return tenant


# ── Overview ──

@router.get("/overview")
@limiter.limit("60/minute")
def dashboard_overview(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_by_dashboard_token(token, db)
    tid = tenant.id

    total_campaigns = db.scalar(
        select(func.count()).select_from(CampaignStats)
        .where(CampaignStats.tenant_id == tid)
    ) or 0

    total_workflows = db.scalar(
        select(func.count()).select_from(WorkflowStats)
        .where(WorkflowStats.tenant_id == tid)
    ) or 0

    total_lead_events = db.scalar(
        select(func.count()).select_from(LeadEvent)
        .where(LeadEvent.tenant_id == tid)
    ) or 0

    total_revenue = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(RevenueSnapshot.attributed_revenue), 0))
            .where(RevenueSnapshot.tenant_id == tid)
        ) or 0
    )

    last_rev = db.scalars(
        select(RevenueSnapshot)
        .where(RevenueSnapshot.tenant_id == tid)
        .order_by(RevenueSnapshot.created_at.desc())
        .limit(1)
    ).first()

    last_event_at = db.scalar(
        select(func.max(LeadEvent.occurred_at)).where(LeadEvent.tenant_id == tid)
    )

    total_contacts = db.scalar(
        select(func.count()).select_from(Contact).where(Contact.tenant_id == tid)
    ) or 0

    status_counts = {}
    if total_contacts > 0:
        for row in db.execute(
            select(Contact.status, func.count().label("cnt"))
            .where(Contact.tenant_id == tid)
            .group_by(Contact.status)
        ).all():
            status, cnt = row
            if status in ("new", "contacted", "engaged", "converted"):
                status_counts[status] = cnt
            else:
                status_counts["other"] = status_counts.get("other", 0) + cnt

    total_opted_out_sms = db.scalar(
        select(func.count()).select_from(Contact)
        .where(Contact.tenant_id == tid, Contact.opted_out_sms == True)  # noqa: E712
    ) or 0

    total_opted_out_email = db.scalar(
        select(func.count()).select_from(Contact)
        .where(Contact.tenant_id == tid, Contact.opted_out_email == True)  # noqa: E712
    ) or 0

    total_messages = db.scalar(
        select(func.count()).select_from(MessageLog)
        .where(MessageLog.tenant_id == tid)
    ) or 0

    msg_status_counts = {}
    if total_messages > 0:
        for row in db.execute(
            select(MessageLog.status, func.count().label("cnt"))
            .where(MessageLog.tenant_id == tid)
            .group_by(MessageLog.status)
        ).all():
            msg_status_counts[row[0]] = row[1]

    total_failed = db.scalar(
        select(func.count()).select_from(FailedEvent)
        .where(FailedEvent.tenant_id == tid)
    ) or 0

    return {
        "tenant_id": tid,
        "total_campaigns": total_campaigns,
        "total_workflows": total_workflows,
        "total_lead_events": total_lead_events,
        "total_revenue": float(total_revenue),
        "currency": last_rev.currency if last_rev else None,
        "total_contacts": total_contacts,
        "contact_status_breakdown": {
            "new": status_counts.get("new", 0),
            "contacted": status_counts.get("contacted", 0),
            "engaged": status_counts.get("engaged", 0),
            "converted": status_counts.get("converted", 0),
            "other": status_counts.get("other", 0),
        },
        "total_opted_out_sms": total_opted_out_sms,
        "total_opted_out_email": total_opted_out_email,
        "total_messages": total_messages,
        "total_messages_sent": msg_status_counts.get("sent", 0),
        "total_messages_delivered": msg_status_counts.get("delivered", 0),
        "total_messages_failed": msg_status_counts.get("failed", 0),
        "total_failed_events": total_failed,
        "last_event_at": last_event_at,
        "last_revenue_snapshot_at": last_rev.created_at if last_rev else None,
    }


# ── Contacts ──

@router.get("/contacts", response_model=List[ContactSummary])
@limiter.limit("60/minute")
def dashboard_contacts(
    request: Request,
    token: str,
    status: Optional[str] = Query(default=None, max_length=50),
    search: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_by_dashboard_token(token, db)
    stmt = (
        select(Contact)
        .where(Contact.tenant_id == tenant.id)
        .order_by(Contact.created_at.desc())
    )
    if status:
        stmt = stmt.where(Contact.status == status)
    if search:
        p = f"%{search}%"
        stmt = stmt.where(
            (Contact.first_name.ilike(p))
            | (Contact.last_name.ilike(p))
            | (Contact.email.ilike(p))
            | (Contact.normalized_phone.ilike(p))
        )
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [ContactSummary.model_validate(r) for r in rows]


# ── Messages ──

@router.get("/messages", response_model=List[MessageLogOut])
@limiter.limit("60/minute")
def dashboard_messages(
    request: Request,
    token: str,
    channel: Optional[str] = Query(default=None, max_length=20),
    status: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_by_dashboard_token(token, db)
    stmt = (
        select(MessageLog)
        .where(MessageLog.tenant_id == tenant.id)
        .order_by(MessageLog.created_at.desc())
    )
    if channel:
        stmt = stmt.where(MessageLog.channel == channel)
    if status:
        stmt = stmt.where(MessageLog.status == status)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [MessageLogOut.model_validate(r) for r in rows]


# ── Campaigns ──

@router.get("/campaigns", response_model=List[CampaignStatsOut])
@limiter.limit("60/minute")
def dashboard_campaigns(
    request: Request,
    token: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_by_dashboard_token(token, db)
    rows = db.scalars(
        select(CampaignStats)
        .where(CampaignStats.tenant_id == tenant.id)
        .order_by(CampaignStats.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [CampaignStatsOut.model_validate(r) for r in rows]


# ── Workflows ──

@router.get("/workflows", response_model=List[WorkflowStatsOut])
@limiter.limit("60/minute")
def dashboard_workflows(
    request: Request,
    token: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_by_dashboard_token(token, db)
    rows = db.scalars(
        select(WorkflowStats)
        .where(WorkflowStats.tenant_id == tenant.id)
        .order_by(WorkflowStats.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [WorkflowStatsOut.model_validate(r) for r in rows]


# ── Events ──

@router.get("/events", response_model=List[LeadEventOut])
@limiter.limit("60/minute")
def dashboard_events(
    request: Request,
    token: str,
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_by_dashboard_token(token, db)
    stmt = (
        select(LeadEvent)
        .where(LeadEvent.tenant_id == tenant.id)
        .order_by(LeadEvent.occurred_at.desc())
    )
    if event_type:
        stmt = stmt.where(LeadEvent.event_type == event_type)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [LeadEventOut.model_validate(r) for r in rows]


# ── Revenue ──

@router.get("/revenue", response_model=List[RevenueSnapshotOut])
@limiter.limit("60/minute")
def dashboard_revenue(
    request: Request,
    token: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_by_dashboard_token(token, db)
    rows = db.scalars(
        select(RevenueSnapshot)
        .where(RevenueSnapshot.tenant_id == tenant.id)
        .order_by(RevenueSnapshot.period_start.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [RevenueSnapshotOut.model_validate(r) for r in rows]