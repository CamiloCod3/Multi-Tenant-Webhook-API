# backend/app/routers/contacts.py
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.audit import write_audit_log
from ..core.db import get_db
from ..core.deps import require_admin_token
from ..core.rate_limit import limiter

from ..models.contact_opt_out_event import ContactOptOutEvent
from ..models.contacts import Contact
from ..models.message_log import MessageLog
from ..schemas.contacts import (
    ContactCreate,
    ContactOut,
    ContactSummary,
    ContactUpdate,
)
from ..schemas.opt_out import (
    ContactOptOutEventOut,
    OptInRequest,
    OptOutRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/contacts", tags=["contacts"])


def _normalize_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    return cleaned or None


@router.get("", response_model=List[ContactSummary])
@limiter.limit("60/minute")
def list_contacts(
    request: Request,
    tenant_id: str,
    status: Optional[str] = Query(default=None, max_length=50),
    source: Optional[str] = Query(default=None, max_length=100),
    is_member: Optional[bool] = Query(default=None),
    opted_out: Optional[bool] = Query(
        default=None,
        description="True = only opt-outs, False = only active contacts",
    ),
    search: Optional[str] = Query(
        default=None,
        max_length=200,
        description="Free-text search by name, email, or phone",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    stmt = (
        select(Contact)
        .where(Contact.tenant_id == tenant_id)
        .order_by(Contact.created_at.desc())
    )

    if status:
        stmt = stmt.where(Contact.status == status)
    if source:
        stmt = stmt.where(Contact.source == source)
    if is_member is not None:
        stmt = stmt.where(Contact.is_member == is_member)
    if opted_out is True:
        stmt = stmt.where(
            (Contact.opted_out_sms == True) | (Contact.opted_out_email == True)  # noqa: E712
        )
    elif opted_out is False:
        stmt = stmt.where(
            Contact.opted_out_sms == False,  # noqa: E712
            Contact.opted_out_email == False,  # noqa: E712
        )

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (Contact.first_name.ilike(pattern))
            | (Contact.last_name.ilike(pattern))
            | (Contact.email.ilike(pattern))
            | (Contact.normalized_phone.ilike(pattern))
        )

    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [ContactSummary.model_validate(r) for r in rows]


@router.get("/count")
@limiter.limit("60/minute")
def count_contacts(
    request: Request,
    tenant_id: str,
    status: Optional[str] = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    stmt = select(func.count()).select_from(Contact).where(Contact.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Contact.status == status)
    total = db.scalar(stmt) or 0
    return {"tenant_id": tenant_id, "total": total, "status_filter": status}


@router.get("/{contact_id}", response_model=ContactOut)
@limiter.limit("60/minute")
def get_contact(
    request: Request,
    tenant_id: str,
    contact_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    c = db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
    )
    if not c:
        raise HTTPException(404, "Contact not found")
    return ContactOut.model_validate(c)


@router.post("", response_model=ContactOut, status_code=201)
@limiter.limit("30/minute")
def create_contact(
    request: Request,
    tenant_id: str,
    body: ContactCreate,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    normalized_phone = _normalize_phone(body.phone)

    c = Contact(
        tenant_id=tenant_id,
        external_contact_id=body.external_contact_id or None,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email.strip().lower() if body.email else None,
        phone=body.phone,
        normalized_phone=normalized_phone,
        registration_number=body.registration_number,
        source=body.source,
        status=body.status,
        member_status=body.member_status,
        is_member=body.is_member,
        consent_sms=body.consent_sms,
        consent_email=body.consent_email,
        tags=body.tags,
        metadata_json=body.metadata_json,
    )

    try:
        db.add(c)
        db.commit()
        db.refresh(c)
        return ContactOut.model_validate(c)
    except Exception as e:
        db.rollback()
        detail = str(e)
        if "contacts_tenant_external_contact_uq" in detail:
            raise HTTPException(409, "Contact with this external_contact_id already exists")
        if "contacts_tenant_email_uq" in detail:
            raise HTTPException(409, "Contact with this email already exists for tenant")
        if "contacts_tenant_normalized_phone_uq" in detail:
            raise HTTPException(409, "Contact with this phone already exists for tenant")
        logger.exception("Failed to create contact")
        raise HTTPException(500, "Failed to create contact")


@router.patch("/{contact_id}", response_model=ContactOut)
@limiter.limit("30/minute")
def update_contact(
    request: Request,
    tenant_id: str,
    contact_id: str,
    body: ContactUpdate,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    c = db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
    )
    if not c:
        raise HTTPException(404, "Contact not found")

    update_data = body.model_dump(exclude_unset=True)

    if "phone" in update_data:
        c.phone = update_data["phone"]
        c.normalized_phone = _normalize_phone(update_data["phone"])
        del update_data["phone"]

    if "email" in update_data and update_data["email"]:
        update_data["email"] = update_data["email"].strip().lower()

    now = datetime.now(timezone.utc)
    if update_data.get("opted_out_sms") is True or update_data.get("opted_out_email") is True:
        if not c.opted_out_at:
            c.opted_out_at = now
    elif update_data.get("opted_out_sms") is False and update_data.get("opted_out_email") is False:
        c.opted_out_at = None
        c.opt_out_reason = None

    for key, value in update_data.items():
        setattr(c, key, value)

    try:
        db.add(c)
        db.commit()
        db.refresh(c)
        return ContactOut.model_validate(c)
    except Exception as e:
        db.rollback()
        detail = str(e)
        if "contacts_tenant_email_uq" in detail:
            raise HTTPException(409, "Contact with this email already exists for tenant")
        if "contacts_tenant_normalized_phone_uq" in detail:
            raise HTTPException(409, "Contact with this phone already exists for tenant")
        logger.exception("Failed to update contact")
        raise HTTPException(500, "Failed to update contact")


@router.post("/{contact_id}/opt-out", response_model=ContactOut)
@limiter.limit("30/minute")
def opt_out_contact(
    request: Request,
    tenant_id: str,
    contact_id: str,
    body: OptOutRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Opt a contact out of one or more communication channels."""
    c = db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
    )
    if not c:
        raise HTTPException(404, "Contact not found")

    channel = body.channel.lower()
    if channel not in ("sms", "email", "all"):
        raise HTTPException(422, "channel must be sms, email, or all")

    now = datetime.now(timezone.utc)

    if channel in ("sms", "all"):
        c.opted_out_sms = True
    if channel in ("email", "all"):
        c.opted_out_email = True

    if not c.opted_out_at:
        c.opted_out_at = now
    if body.reason:
        c.opt_out_reason = body.reason
    c.updated_at = now

    opt_event = ContactOptOutEvent(
        tenant_id=tenant_id,
        contact_id=contact_id,
        channel=channel,
        source=body.source,
        reason=body.reason,
        metadata_json={"via": "api"},
        occurred_at=now,
    )

    try:
        db.add(c)
        db.add(opt_event)
        db.commit()
        db.refresh(c)
        return ContactOut.model_validate(c)
    except Exception:
        db.rollback()
        logger.exception("Failed to opt out contact")
        raise HTTPException(500, "Failed to opt out contact")


@router.post("/{contact_id}/opt-in", response_model=ContactOut)
@limiter.limit("30/minute")
def opt_in_contact(
    request: Request,
    tenant_id: str,
    contact_id: str,
    body: OptInRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Reverse a contact opt-out for one or more channels."""
    c = db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
    )
    if not c:
        raise HTTPException(404, "Contact not found")

    channel = body.channel.lower()
    if channel not in ("sms", "email", "all"):
        raise HTTPException(422, "channel must be sms, email, or all")

    now = datetime.now(timezone.utc)

    if channel in ("sms", "all"):
        c.opted_out_sms = False
    if channel in ("email", "all"):
        c.opted_out_email = False

    if not c.opted_out_sms and not c.opted_out_email:
        c.opted_out_at = None
        c.opt_out_reason = None

    c.updated_at = now

    try:
        db.add(c)
        db.commit()
        db.refresh(c)
        return ContactOut.model_validate(c)
    except Exception:
        db.rollback()
        logger.exception("Failed to opt in contact")
        raise HTTPException(500, "Failed to opt in contact")


@router.post("/{contact_id}/anonymize", response_model=ContactOut)
@limiter.limit("10/minute")
def anonymize_contact(
    request: Request,
    tenant_id: str,
    contact_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """
    Apply a right-to-erasure style anonymization for a contact.

    The contact record is kept for aggregate reporting, but direct PII is removed
    from the contact and related message logs.
    """
    c = db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
    )
    if not c:
        raise HTTPException(404, "Contact not found")

    now = datetime.now(timezone.utc)

    c.first_name = None
    c.last_name = None
    c.email = None
    c.phone = None
    c.normalized_phone = None
    c.registration_number = None
    c.external_contact_id = None
    c.tags = []
    c.metadata_json = {"anonymized_at": now.isoformat()}

    c.opted_out_sms = True
    c.opted_out_email = True
    if not c.opted_out_at:
        c.opted_out_at = now
    c.opt_out_reason = "contact_anonymized"
    c.updated_at = now

    message_logs = db.scalars(
        select(MessageLog).where(
            MessageLog.tenant_id == tenant_id,
            MessageLog.contact_id == contact_id,
        )
    ).all()
    for message_log in message_logs:
        message_log.body = None
        message_log.subject = None
        message_log.metadata_json = {"anonymized_at": now.isoformat()}

    write_audit_log(
        db,
        tenant_id=tenant_id,
        action="contact.anonymize",
        actor="admin",
        meta={
            "contact_id": contact_id,
            "message_logs_scrubbed": len(message_logs),
        },
    )

    try:
        db.commit()
        db.refresh(c)
        return ContactOut.model_validate(c)
    except Exception:
        db.rollback()
        logger.exception("Failed to anonymize contact %s", contact_id)
        raise HTTPException(500, "Failed to anonymize contact")


@router.get(
    "/{contact_id}/opt-out-events",
    response_model=List[ContactOptOutEventOut],
)
@limiter.limit("60/minute")
def list_opt_out_events(
    request: Request,
    tenant_id: str,
    contact_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """Return opt-out history for a contact."""
    rows = db.scalars(
        select(ContactOptOutEvent)
        .where(
            ContactOptOutEvent.tenant_id == tenant_id,
            ContactOptOutEvent.contact_id == contact_id,
        )
        .order_by(ContactOptOutEvent.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [ContactOptOutEventOut.model_validate(r) for r in rows]
