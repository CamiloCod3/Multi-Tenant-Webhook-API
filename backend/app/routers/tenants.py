# backend/app/routers/tenants.py
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..core.config import settings
from ..core.db import get_db
from ..core.rate_limit import limiter
from ..core.deps import require_admin_token
from ..core.audit import write_audit_log

from ..models.tenant import Tenant
from ..models.metrics import (
    CampaignStats,
    WorkflowStats,
    LeadEvent,
    RevenueSnapshot,
)

from ..schemas.tenants import TenantCreate, TenantUpdate, TenantOut
from ..schemas.metrics import (
    CampaignStatsOut,
    WorkflowStatsOut,
    LeadEventOut,
    RevenueSnapshotOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


def _tenant_out_dict(t: Tenant) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "plan": t.plan,
        "created_at": t.created_at,
        "webhook_url": f"{settings.public_base_url}/api/v1/webhooks/lead-event/t/{t.webhook_token}",
        "dashboard_url": f"{settings.dashboard_base_url}/t/{t.dashboard_token}",
    }


@router.post("", response_model=TenantOut)
@limiter.limit("10/minute")
def create_tenant(
    request: Request,
    body: TenantCreate,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Create a new tenant."""
    try:
        t = Tenant(
            name=body.name,
            plan=body.plan,
        )
        db.add(t)
        db.flush()

        write_audit_log(
            db=db,
            tenant_id=t.id,
            action="tenant.create",
            meta={"name": t.name, "plan": t.plan},
            auto_commit=False,
        )

        db.commit()
        db.refresh(t)

        return _tenant_out_dict(t)

    except Exception:
        db.rollback()
        logger.exception("Failed to create tenant")
        raise HTTPException(500, "Failed to create tenant")


@router.get("", response_model=List[TenantOut])
@limiter.limit("30/minute")
def list_tenants(
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """List all tenants."""
    tenants = db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
    return [_tenant_out_dict(t) for t in tenants]


@router.get("/{tenant_id}", response_model=TenantOut)
@limiter.limit("30/minute")
def get_tenant(
    request: Request,
    tenant_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Return a single tenant."""
    t = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not t:
        raise HTTPException(404, "Tenant not found")
    return _tenant_out_dict(t)


@router.patch("/{tenant_id}", response_model=TenantOut)
@limiter.limit("10/minute")
def update_tenant(
    request: Request,
    tenant_id: str,
    body: TenantUpdate,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Update tenant metadata."""
    t = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not t:
        raise HTTPException(404, "Tenant not found")

    if body.name is not None:
        t.name = body.name
    if body.plan is not None:
        t.plan = body.plan

    try:
        db.add(t)

        write_audit_log(
            db=db,
            tenant_id=t.id,
            action="tenant.update",
            meta={"name": t.name, "plan": t.plan},
            auto_commit=False,
        )

        db.commit()
        db.refresh(t)

        return _tenant_out_dict(t)

    except Exception:
        db.rollback()
        logger.exception("Failed to update tenant")
        raise HTTPException(500, "Failed to update tenant")


@router.delete("/{tenant_id}")
@limiter.limit("5/minute")
def delete_tenant(
    request: Request,
    tenant_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Delete a tenant."""
    t = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not t:
        raise HTTPException(404, "Tenant not found")

    try:
        write_audit_log(
            db=db,
            tenant_id=tenant_id,
            action="tenant.delete",
            auto_commit=False,
        )

        db.delete(t)
        db.commit()

        return {"detail": "Tenant deleted"}
    except Exception:
        db.rollback()
        logger.exception("Failed to delete tenant")
        raise HTTPException(500, "Failed to delete tenant")


@router.get("/{tenant_id}/campaign-stats", response_model=List[CampaignStatsOut])
@limiter.limit("60/minute")
def get_campaign_stats_for_tenant(
    request: Request,
    tenant_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Return campaign-style statistics for a tenant."""
    rows = db.scalars(
        select(CampaignStats)
        .where(CampaignStats.tenant_id == tenant_id)
        .order_by(CampaignStats.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [CampaignStatsOut.model_validate(r) for r in rows]


@router.get("/{tenant_id}/workflow-stats", response_model=List[WorkflowStatsOut])
@limiter.limit("60/minute")
def get_workflow_stats_for_tenant(
    request: Request,
    tenant_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Return workflow statistics for a tenant."""
    rows = db.scalars(
        select(WorkflowStats)
        .where(WorkflowStats.tenant_id == tenant_id)
        .order_by(WorkflowStats.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [WorkflowStatsOut.model_validate(r) for r in rows]


@router.get("/{tenant_id}/lead-events", response_model=List[LeadEventOut])
@limiter.limit("60/minute")
def get_lead_events_for_tenant(
    request: Request,
    tenant_id: str,
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Return raw ingested events for a tenant."""
    stmt = (
        select(LeadEvent)
        .where(LeadEvent.tenant_id == tenant_id)
        .order_by(LeadEvent.occurred_at.desc())
    )
    if event_type:
        stmt = stmt.where(LeadEvent.event_type == event_type)

    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [LeadEventOut.model_validate(r) for r in rows]


@router.get("/{tenant_id}/revenue-snapshots", response_model=List[RevenueSnapshotOut])
@limiter.limit("30/minute")
def get_revenue_snapshots_for_tenant(
    request: Request,
    tenant_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Return revenue snapshots for a tenant."""
    rows = db.scalars(
        select(RevenueSnapshot)
        .where(RevenueSnapshot.tenant_id == tenant_id)
        .order_by(RevenueSnapshot.period_start.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [RevenueSnapshotOut.model_validate(r) for r in rows]
