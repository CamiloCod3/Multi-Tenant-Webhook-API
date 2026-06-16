import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from typing import cast
from ..core.db import get_db
from ..core.logging import correlation_id_ctx
from ..core.rate_limit import limiter
from ..core.webhook_security import verify_webhook_signature
from ..models.tenant import Tenant as TenantModel
from ..schemas.common import APIMessage
from ..schemas.webhooks import LeadWebhookEvent, LeadWebhookIngestResult, IngestStatus
from ..services.webhook_ingest import ingest_with_dead_letter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/lead-event", response_model=APIMessage)
@limiter.limit("60/minute")
async def ingest_lead_event(
    request: Request,
    body: LeadWebhookEvent,
    db: Session = Depends(get_db),
    _sig=Depends(verify_webhook_signature),
):
    corr_id = correlation_id_ctx.get()
    return ingest_with_dead_letter(db=db, body=body, corr_id=corr_id)


@router.post("/lead-event/t/{token}", response_model=LeadWebhookIngestResult)
@limiter.limit("60/minute")
async def ingest_lead_event_token(
    token: str,
    request: Request,
    body: LeadWebhookEvent,
    db: Session = Depends(get_db),
):
    corr_id = correlation_id_ctx.get()

    tenant = db.scalar(select(TenantModel).where(TenantModel.webhook_token == token))
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    if body.tenant_id and body.tenant_id != tenant.id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch for token")

    body.tenant_id = tenant.id

    result = ingest_with_dead_letter(db=db, body=body, corr_id=corr_id)

    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif isinstance(result, dict):
        payload = result
    else:
        payload = {"detail": str(result)}

    detail = str(payload.get("detail", ""))

    raw_status = payload.get("status")
    duplicate = bool(payload.get("duplicate", False))

    status: IngestStatus

    if raw_status in ("ingested", "duplicate", "unknown"):
        status = cast(IngestStatus, raw_status)
    elif "Duplicate event ignored" in detail:
        status = "duplicate"
        duplicate = True
    elif "Lead event ingested" in detail:
        status = "ingested"
    else:
        status = "unknown"

    return LeadWebhookIngestResult(
        detail=detail,
        status=status,
        duplicate=duplicate,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )