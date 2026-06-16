# backend/app/routers/message_logs.py
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.deps import require_admin_token
from ..core.rate_limit import limiter

from ..models.contacts import Contact
from ..models.message_log import MessageLog
from ..schemas.messages import MessageLogCreate, MessageLogOut

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/message-logs", tags=["message-logs"])


# ---------- Create ----------

@router.post("", response_model=MessageLogOut, status_code=201)
@limiter.limit("120/minute")
def create_message_log(
    request: Request,
    tenant_id: str,
    body: MessageLogCreate,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """
    Loggar ett skickat/mottaget meddelande manuellt.

    Anvands av n8n for att registrera SMS/email som skickats via
    externa providers. Contact maste redan finnas.
    """
    contact = db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == body.contact_id,
        )
    )
    if not contact:
        raise HTTPException(
            404,
            f"Contact {body.contact_id} not found for tenant {tenant_id}",
        )

    now = datetime.now(timezone.utc)

    msg = MessageLog(
        tenant_id=tenant_id,
        contact_id=body.contact_id,
        campaign_id=body.campaign_id,
        workflow_id=body.workflow_id,
        event_id=body.event_id,
        channel=body.channel,
        direction=body.direction,
        provider=body.provider,
        provider_message_id=body.provider_message_id,
        template_key=body.template_key,
        subject=body.subject,
        body=body.body,
        status=body.status,
        failure_reason=body.failure_reason,
        metadata_json=body.metadata_json,
        sent_at=body.sent_at or (now if body.status == "sent" else None),
    )

    try:
        db.add(msg)

        if body.direction == "outbound" and body.status in ("sent", "queued"):
            contact.last_message_sent_at = now
            contact.updated_at = now

        db.commit()
        db.refresh(msg)
        return MessageLogOut.model_validate(msg)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to create message log: {str(e)}")


# ---------- List ----------

@router.get("", response_model=List[MessageLogOut])
@limiter.limit("60/minute")
def list_message_logs(
    request: Request,
    tenant_id: str,
    contact_id: Optional[str] = Query(default=None),
    campaign_id: Optional[str] = Query(default=None, max_length=100),
    workflow_id: Optional[str] = Query(default=None, max_length=100),
    channel: Optional[str] = Query(default=None, max_length=20),
    direction: Optional[str] = Query(default=None, max_length=20),
    status: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """
    Listar meddelanden for en tenant med filter.

    For meddelandehistorik per kontakt, anvand ?contact_id=<id>.
    """
    stmt = (
        select(MessageLog)
        .where(MessageLog.tenant_id == tenant_id)
        .order_by(MessageLog.created_at.desc())
    )

    if contact_id:
        stmt = stmt.where(MessageLog.contact_id == contact_id)
    if campaign_id:
        stmt = stmt.where(MessageLog.campaign_id == campaign_id)
    if workflow_id:
        stmt = stmt.where(MessageLog.workflow_id == workflow_id)
    if channel:
        stmt = stmt.where(MessageLog.channel == channel)
    if direction:
        stmt = stmt.where(MessageLog.direction == direction)
    if status:
        stmt = stmt.where(MessageLog.status == status)

    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [MessageLogOut.model_validate(r) for r in rows]


# ---------- Get single ----------

@router.get("/{message_id}", response_model=MessageLogOut)
@limiter.limit("60/minute")
def get_message_log(
    request: Request,
    tenant_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Hamtar ett enskilt meddelande."""
    m = db.scalar(
        select(MessageLog).where(
            MessageLog.tenant_id == tenant_id,
            MessageLog.id == message_id,
        )
    )
    if not m:
        raise HTTPException(404, "Message log not found")
    return MessageLogOut.model_validate(m)