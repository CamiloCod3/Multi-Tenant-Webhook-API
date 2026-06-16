# backend/app/routers/failed_events.py
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.deps import require_admin_token
from ..core.rate_limit import limiter

from ..models.metrics import FailedEvent
from ..schemas.failed_events import FailedEventOut
from ..schemas.common import APIMessage
from ..schemas.webhooks import LeadWebhookEvent
from ..services.webhook_ingest import process_lead_event_core

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/tenants/{tenant_id}/failed-events",
    tags=["failed-events"],
)


@router.get("", response_model=List[FailedEventOut])
@limiter.limit("60/minute")
def list_failed_events(
    request: Request,
    tenant_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Listar misslyckade events for en tenant, senaste forst."""
    rows = db.scalars(
        select(FailedEvent)
        .where(FailedEvent.tenant_id == tenant_id)
        .order_by(FailedEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [FailedEventOut.model_validate(r) for r in rows]


@router.get("/count")
@limiter.limit("60/minute")
def count_failed_events(
    request: Request,
    tenant_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Returnerar antal misslyckade events for en tenant."""
    total = (
        db.scalar(
            select(func.count())
            .select_from(FailedEvent)
            .where(FailedEvent.tenant_id == tenant_id)
        )
        or 0
    )
    return {"tenant_id": tenant_id, "total": total}


@router.get("/{failed_event_id}", response_model=FailedEventOut)
@limiter.limit("60/minute")
def get_failed_event(
    request: Request,
    tenant_id: str,
    failed_event_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Hamtar ett enskilt misslyckat event."""
    fe = db.scalar(
        select(FailedEvent).where(
            FailedEvent.tenant_id == tenant_id,
            FailedEvent.id == failed_event_id,
        )
    )
    if not fe:
        raise HTTPException(404, "Failed event not found")
    return FailedEventOut.model_validate(fe)


@router.post("/{failed_event_id}/retry", response_model=APIMessage)
@limiter.limit("10/minute")
def retry_failed_event(
    request: Request,
    tenant_id: str,
    failed_event_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """
    Forsoker re-processa ett misslyckat event.

    Om det lyckas tas det bort fran failed_events.
    Om det failar igen uppdateras retry_count och last_retry_at.
    """
    fe = db.scalar(
        select(FailedEvent).where(
            FailedEvent.tenant_id == tenant_id,
            FailedEvent.id == failed_event_id,
        )
    )
    if not fe:
        raise HTTPException(404, "Failed event not found")

    payload = fe.raw_payload
    if not payload:
        raise HTTPException(
            422,
            "Cannot retry: raw_payload is empty",
        )

    # Forsok bygga ett LeadWebhookEvent fran den sparade payloaden
    try:
        body = LeadWebhookEvent.model_validate(payload)
    except Exception as e:
        raise HTTPException(
            422,
            f"Cannot retry: payload does not match expected format: {e}",
        )

    # Sakerstall att tenant_id ar korrekt
    body.tenant_id = tenant_id

    event_id = fe.event_id or body.event_id or (
        f"{tenant_id}:{body.lead_id}:{body.event_type}:"
        f"{body.timestamp.isoformat()}"
    )

    try:
        inserted = process_lead_event_core(db=db, body=body, event_id=event_id)

        if not inserted:
            # Event var redan processad (duplicate). Ta bort fran dead letter.
            db.delete(fe)
            db.commit()
            return APIMessage(
                detail=f"Event already processed (duplicate). Removed from failed queue."
            )

        # Lyckades! Ta bort fran dead letter.
        db.delete(fe)
        db.commit()

        logger.info(f"Retry succeeded for failed_event {failed_event_id}, event_id={event_id}")
        return APIMessage(detail=f"Retry succeeded. Event {event_id} processed.")

    except Exception as e:
        db.rollback()

        # Uppdatera retry-metadata
        try:
            fe.retry_count = (fe.retry_count or 0) + 1
            fe.last_retry_at = datetime.now(timezone.utc)
            fe.error_message = f"Retry #{fe.retry_count} failed: {str(e)[:1500]}"
            db.add(fe)
            db.commit()
        except Exception:
            db.rollback()

        logger.warning(
            f"Retry failed for failed_event {failed_event_id}: {e}"
        )
        raise HTTPException(
            500,
            f"Retry failed: {e}",
        )


@router.delete("/{failed_event_id}", response_model=APIMessage)
@limiter.limit("10/minute")
def delete_failed_event(
    request: Request,
    tenant_id: str,
    failed_event_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Tar bort ett misslyckat event permanent (acknowledge/discard)."""
    fe = db.scalar(
        select(FailedEvent).where(
            FailedEvent.tenant_id == tenant_id,
            FailedEvent.id == failed_event_id,
        )
    )
    if not fe:
        raise HTTPException(404, "Failed event not found")

    db.delete(fe)
    db.commit()
    return APIMessage(detail="Failed event deleted")