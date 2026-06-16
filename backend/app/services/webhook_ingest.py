# backend/app/services/webhook_ingest.py
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..core.dead_letter import store_failed_event
from ..models.contact_opt_out_event import ContactOptOutEvent
from ..models.contacts import Contact
from ..models.message_log import MessageLog
from ..models.metrics import (
    CampaignStats,
    LeadEvent,
    RevenueSnapshot,
    WorkflowStats,
)
from ..schemas.common import APIMessage
from ..schemas.webhooks import LeadWebhookEvent

logger = logging.getLogger(__name__)


# ── Event type classification sets ──

CONTACT_STATUS_CONVERTED = {"converted", "deal_won", "sale"}
CONTACT_STATUS_ENGAGED = {"engaged", "email_opened", "clicked", "replied"}
CONTACT_STATUS_CONTACTED = {"contacted", "email_sent", "sms_sent"}
CONTACT_STATUS_NEW = {"lead_created", "lead_imported"}

CAMPAIGN_TOTAL_EVENTS = {"lead_created", "lead_imported"}
CAMPAIGN_CONTACTED_EVENTS = {"contacted", "email_sent", "sms_sent"}
CAMPAIGN_ENGAGED_EVENTS = {"engaged", "email_opened", "clicked"}
CAMPAIGN_CONVERTED_EVENTS = {"converted", "deal_won", "sale"}

WORKFLOW_PROCESSED_EVENTS = {"workflow_processed", "lead_processed", "step_completed"}
WORKFLOW_SUCCESS_EVENTS = {"workflow_success", "converted", "deal_won"}
WORKFLOW_FAILED_EVENTS = {"workflow_failed", "failed", "error"}

REVENUE_EVENTS = {"deal_won", "converted", "sale"}

MESSAGE_SEND_EVENTS = {"sms_sent", "email_sent"}
MESSAGE_DELIVERY_EVENTS = {"sms_delivered", "email_delivered"}
MESSAGE_ENGAGEMENT_EVENTS = {"email_opened", "clicked", "replied"}
MESSAGE_FAILURE_EVENTS = {"sms_failed", "email_failed", "email_bounced"}

MESSAGE_RELATED_EVENTS = (
    MESSAGE_SEND_EVENTS
    | MESSAGE_DELIVERY_EVENTS
    | MESSAGE_ENGAGEMENT_EVENTS
    | MESSAGE_FAILURE_EVENTS
)

OPT_OUT_SMS_EVENTS = {"opt_out_sms", "opt_out_all"}
OPT_OUT_EMAIL_EVENTS = {"opt_out_email", "opt_out_all"}
OPT_OUT_ALL_EVENTS = {"opt_out_sms", "opt_out_email", "opt_out_all"}

# Status progression: hogre nummer = langre i funneln. Status gar aldrig bakat.
_STATUS_RANK: dict[str, int] = {
    "new": 0,
    "contacted": 1,
    "engaged": 2,
    "converted": 3,
}


# ── Utility helpers ──

def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def _normalize_email(value: Any) -> Optional[str]:
    cleaned = _clean_str(value)
    return cleaned.lower() if cleaned else None


def _normalize_phone(value: Any) -> Optional[str]:
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    cleaned = (
        cleaned.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    return cleaned


def _pick_first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return None


def _coalesce(existing: Any, incoming: Any) -> Any:
    return incoming if incoming not in (None, "") else existing


# ── Contact helpers ──

def _derive_contact_status(event_type: str, current_status: Optional[str]) -> str:
    """
    Haerled kontaktstatus fran event type.

    Status gar ALDRIG bakat i funneln:
      new -> contacted -> engaged -> converted

    Om ett email_sent-event kommer in for en redan converted kontakt,
    behalls converted. Okanda event types andrar inte status.
    """
    if event_type in CONTACT_STATUS_CONVERTED:
        candidate = "converted"
    elif event_type in CONTACT_STATUS_ENGAGED:
        candidate = "engaged"
    elif event_type in CONTACT_STATUS_CONTACTED:
        candidate = "contacted"
    elif event_type in CONTACT_STATUS_NEW:
        candidate = current_status or "new"
    else:
        # Okand event type (workflow events, opt-outs, etc) -- behall nuvarande
        return current_status or "new"

    # Progression guard: gar aldrig bakat
    current_rank = _STATUS_RANK.get(current_status or "new", -1)
    candidate_rank = _STATUS_RANK.get(candidate, -1)

    if candidate_rank >= current_rank:
        return candidate
    return current_status or "new"


def _extract_contact_fields(body: LeadWebhookEvent) -> dict[str, Any]:
    data = body.data or {}

    first_name = _clean_str(_pick_first(data, "first_name", "firstname", "given_name"))
    last_name = _clean_str(_pick_first(data, "last_name", "lastname", "family_name"))
    email = _normalize_email(_pick_first(data, "email", "email_address"))
    phone = _clean_str(_pick_first(data, "phone", "phone_number", "mobile"))
    normalized_phone = _normalize_phone(phone)
    registration_number = _clean_str(
        _pick_first(data, "registration_number", "org_number", "organization_number")
    )
    source = _clean_str(body.source or _pick_first(data, "source", "crm_source"))

    external_contact_id = _clean_str(
        _pick_first(data, "external_contact_id", "contact_external_id", "contact_id")
    )
    if not external_contact_id:
        external_contact_id = _clean_str(body.lead_id)

    return {
        "external_contact_id": external_contact_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "normalized_phone": normalized_phone,
        "registration_number": registration_number,
        "source": source,
    }


def _find_existing_contact(
    db: Session,
    tenant_id: str,
    external_contact_id: Optional[str],
    email: Optional[str],
    normalized_phone: Optional[str],
) -> Optional[Contact]:
    contact: Optional[Contact] = None

    if external_contact_id:
        contact = db.scalar(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.external_contact_id == external_contact_id,
            )
        )
    if not contact and email:
        contact = db.scalar(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.email == email,
            )
        )
    if not contact and normalized_phone:
        contact = db.scalar(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.normalized_phone == normalized_phone,
            )
        )
    return contact


def _upsert_contact_from_event(
    db: Session,
    tenant_id: str,
    body: LeadWebhookEvent,
    now_ts: datetime,
) -> Optional[str]:
    """
    Multi-tenant contact upsert. Returnerar contact.id.
    """
    incoming = _extract_contact_fields(body)
    external_contact_id = incoming["external_contact_id"]
    email = incoming["email"]
    normalized_phone = incoming["normalized_phone"]

    contact = _find_existing_contact(
        db=db,
        tenant_id=tenant_id,
        external_contact_id=external_contact_id,
        email=email,
        normalized_phone=normalized_phone,
    )

    derived_status = _derive_contact_status(
        body.event_type,
        contact.status if contact else None,
    )

    should_set_last_message_sent = body.event_type in CONTACT_STATUS_CONTACTED
    should_set_last_engagement = body.event_type in (
        CONTACT_STATUS_ENGAGED | CONTACT_STATUS_CONVERTED
    )

    if contact:
        contact.external_contact_id = _coalesce(contact.external_contact_id, external_contact_id)
        contact.first_name = _coalesce(contact.first_name, incoming["first_name"])
        contact.last_name = _coalesce(contact.last_name, incoming["last_name"])
        contact.email = _coalesce(contact.email, email)
        contact.phone = _coalesce(contact.phone, incoming["phone"])
        contact.normalized_phone = _coalesce(contact.normalized_phone, normalized_phone)
        contact.registration_number = _coalesce(
            contact.registration_number, incoming["registration_number"]
        )
        contact.source = _coalesce(contact.source, incoming["source"])
        contact.status = derived_status
        contact.last_seen_at = now_ts
        if should_set_last_message_sent:
            contact.last_message_sent_at = now_ts
        if should_set_last_engagement:
            contact.last_engagement_at = now_ts
        contact.updated_at = now_ts
        return contact.id

    metadata_json = {
        "last_event_type": body.event_type,
        "last_event_id": body.event_id,
    }

    contact = Contact(
        tenant_id=tenant_id,
        external_contact_id=external_contact_id,
        first_name=incoming["first_name"],
        last_name=incoming["last_name"],
        email=email,
        phone=incoming["phone"],
        normalized_phone=normalized_phone,
        registration_number=incoming["registration_number"],
        source=incoming["source"],
        status=derived_status,
        last_seen_at=now_ts,
        last_message_sent_at=now_ts if should_set_last_message_sent else None,
        last_engagement_at=now_ts if should_set_last_engagement else None,
        metadata_json=metadata_json,
    )

    try:
        with db.begin_nested():
            db.add(contact)
            db.flush()
        return contact.id
    except IntegrityError:
        contact = _find_existing_contact(
            db=db,
            tenant_id=tenant_id,
            external_contact_id=external_contact_id,
            email=email,
            normalized_phone=normalized_phone,
        )
        if not contact:
            raise
        contact.external_contact_id = _coalesce(contact.external_contact_id, external_contact_id)
        contact.first_name = _coalesce(contact.first_name, incoming["first_name"])
        contact.last_name = _coalesce(contact.last_name, incoming["last_name"])
        contact.email = _coalesce(contact.email, email)
        contact.phone = _coalesce(contact.phone, incoming["phone"])
        contact.normalized_phone = _coalesce(contact.normalized_phone, normalized_phone)
        contact.registration_number = _coalesce(
            contact.registration_number, incoming["registration_number"]
        )
        contact.source = _coalesce(contact.source, incoming["source"])
        contact.status = derived_status
        contact.last_seen_at = now_ts
        if should_set_last_message_sent:
            contact.last_message_sent_at = now_ts
        if should_set_last_engagement:
            contact.last_engagement_at = now_ts
        contact.updated_at = now_ts
        return contact.id


# ── Aggregation upserts ──

def _upsert_campaign_stats(
    db: Session,
    tenant_id: str,
    campaign_id: str,
    campaign_name: Optional[str],
    event_type: str,
    now_ts: datetime,
) -> None:
    total_inc = 1 if event_type in CAMPAIGN_TOTAL_EVENTS else 0
    contacted_inc = 1 if event_type in CAMPAIGN_CONTACTED_EVENTS else 0
    engaged_inc = 1 if event_type in CAMPAIGN_ENGAGED_EVENTS else 0
    converted_inc = 1 if event_type in CAMPAIGN_CONVERTED_EVENTS else 0

    stmt = pg_insert(CampaignStats).values(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        total_leads=total_inc,
        contacted_leads=contacted_inc,
        engaged_leads=engaged_inc,
        converted_leads=converted_inc,
        last_lead_at=now_ts if total_inc else None,
        updated_at=now_ts,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "campaign_id"],
        set_={
            "campaign_name": stmt.excluded.campaign_name,
            "total_leads": CampaignStats.total_leads + total_inc,
            "contacted_leads": CampaignStats.contacted_leads + contacted_inc,
            "engaged_leads": CampaignStats.engaged_leads + engaged_inc,
            "converted_leads": CampaignStats.converted_leads + converted_inc,
            "last_lead_at": now_ts if total_inc else CampaignStats.last_lead_at,
            "updated_at": now_ts,
        },
    )
    db.execute(stmt)


def _upsert_workflow_stats(
    db: Session,
    tenant_id: str,
    workflow_id: str,
    workflow_name: Optional[str],
    event_type: str,
    now_ts: datetime,
) -> None:
    processed_inc = 1 if event_type in WORKFLOW_PROCESSED_EVENTS else 0
    success_inc = 1 if event_type in WORKFLOW_SUCCESS_EVENTS else 0
    failed_inc = 1 if event_type in WORKFLOW_FAILED_EVENTS else 0

    stmt = pg_insert(WorkflowStats).values(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        processed_leads=processed_inc,
        success_leads=success_inc,
        failed_leads=failed_inc,
        last_run_at=now_ts if (processed_inc or success_inc or failed_inc) else None,
        updated_at=now_ts,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "workflow_id"],
        set_={
            "workflow_name": stmt.excluded.workflow_name,
            "processed_leads": WorkflowStats.processed_leads + processed_inc,
            "success_leads": WorkflowStats.success_leads + success_inc,
            "failed_leads": WorkflowStats.failed_leads + failed_inc,
            "last_run_at": now_ts,
            "updated_at": now_ts,
        },
    )
    db.execute(stmt)


def _upsert_revenue_snapshot(
    db: Session,
    tenant_id: str,
    day: date,
    currency: str,
    amount: Decimal,
) -> None:
    stmt = pg_insert(RevenueSnapshot).values(
        tenant_id=tenant_id,
        period_start=day,
        period_end=day,
        total_revenue=amount,
        attributed_revenue=amount,
        currency=currency,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="revenue_snapshots_tenant_period_currency_uq",
        set_={
            "total_revenue": RevenueSnapshot.total_revenue + amount,
            "attributed_revenue": RevenueSnapshot.attributed_revenue + amount,
        },
    )
    db.execute(stmt)


# ── Message log creation from events ──

def _derive_channel(event_type: str, data: dict[str, Any]) -> str:
    explicit = _clean_str(data.get("channel"))
    if explicit and explicit in ("sms", "email"):
        return explicit
    if "sms" in event_type:
        return "sms"
    if "email" in event_type:
        return "email"
    return data.get("channel", "unknown")


def _derive_message_status(event_type: str) -> str:
    if event_type in MESSAGE_SEND_EVENTS:
        return "sent"
    if event_type in MESSAGE_DELIVERY_EVENTS:
        return "delivered"
    if event_type in {"email_opened"}:
        return "opened"
    if event_type in {"clicked"}:
        return "clicked"
    if event_type in {"replied"}:
        return "replied"
    if event_type in MESSAGE_FAILURE_EVENTS:
        return "failed"
    return "sent"


def _create_message_log_from_event(
    db: Session,
    tenant_id: str,
    contact_id: Optional[str],
    body: LeadWebhookEvent,
    event_id: str,
    now_ts: datetime,
) -> None:
    if not contact_id:
        logger.warning(f"Skipping message_log for event {event_id}: no contact_id")
        return

    data = body.data or {}
    event_type = body.event_type

    channel = _derive_channel(event_type, data)
    status = _derive_message_status(event_type)

    provider_message_id = _clean_str(
        _pick_first(data, "provider_message_id", "message_id", "external_message_id")
    )

    if provider_message_id:
        existing = db.scalar(
            select(MessageLog).where(
                MessageLog.tenant_id == tenant_id,
                MessageLog.provider_message_id == provider_message_id,
            )
        )
        if existing:
            existing.status = status
            if status == "delivered" and not existing.delivered_at:
                existing.delivered_at = now_ts
            elif status == "opened" and not existing.opened_at:
                existing.opened_at = now_ts
            elif status == "clicked" and not existing.clicked_at:
                existing.clicked_at = now_ts
            elif status == "replied" and not existing.replied_at:
                existing.replied_at = now_ts
            elif status == "failed":
                existing.failure_reason = _clean_str(
                    _pick_first(data, "failure_reason", "error_message", "error")
                )
            return

    direction = _clean_str(data.get("direction")) or "outbound"
    if direction not in ("outbound", "inbound"):
        direction = "outbound"

    msg = MessageLog(
        tenant_id=tenant_id,
        contact_id=contact_id,
        campaign_id=_clean_str(data.get("campaign_id")),
        workflow_id=_clean_str(data.get("workflow_id")),
        event_id=event_id,
        channel=channel,
        direction=direction,
        provider=_clean_str(_pick_first(data, "provider", "sms_provider", "email_provider")),
        provider_message_id=provider_message_id,
        template_key=_clean_str(data.get("template_key")),
        subject=_clean_str(data.get("subject")),
        body=_clean_str(_pick_first(data, "body", "message_body", "message", "text")),
        status=status,
        failure_reason=_clean_str(
            _pick_first(data, "failure_reason", "error_message", "error")
        ) if status == "failed" else None,
        metadata_json={
            "source_event_type": event_type,
            "source_event_id": event_id,
        },
        sent_at=now_ts if status == "sent" else None,
        delivered_at=now_ts if status == "delivered" else None,
        opened_at=now_ts if status == "opened" else None,
        clicked_at=now_ts if status == "clicked" else None,
        replied_at=now_ts if status == "replied" else None,
    )

    db.add(msg)


# ── Opt-out handling from events ──

def _handle_opt_out_event(
    db: Session,
    tenant_id: str,
    contact_id: Optional[str],
    body: LeadWebhookEvent,
    now_ts: datetime,
) -> None:
    if not contact_id:
        logger.warning(f"Skipping opt-out for event {body.event_id}: no contact_id")
        return

    event_type = body.event_type
    data = body.data or {}

    contact = db.scalar(
        select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
    )
    if not contact:
        logger.warning(f"Opt-out: contact {contact_id} not found")
        return

    reason = _clean_str(_pick_first(data, "reason", "opt_out_reason", "unsubscribe_reason"))
    source = _clean_str(body.source or _pick_first(data, "opt_out_source")) or "webhook"

    if event_type == "opt_out_sms":
        channel = "sms"
    elif event_type == "opt_out_email":
        channel = "email"
    else:
        channel = "all"

    if event_type in OPT_OUT_SMS_EVENTS:
        contact.opted_out_sms = True
    if event_type in OPT_OUT_EMAIL_EVENTS:
        contact.opted_out_email = True

    if not contact.opted_out_at:
        contact.opted_out_at = now_ts
    contact.opt_out_reason = reason or contact.opt_out_reason
    contact.updated_at = now_ts

    opt_out_event = ContactOptOutEvent(
        tenant_id=tenant_id,
        contact_id=contact_id,
        channel=channel,
        source=source,
        reason=reason,
        metadata_json={
            "event_type": event_type,
            "event_id": body.event_id,
            "data": {k: v for k, v in data.items() if k not in ("reason", "opt_out_reason")},
        },
        occurred_at=now_ts,
    )
    db.add(opt_out_event)


# ── Core processing ──

def process_lead_event_core(
    db: Session,
    body: LeadWebhookEvent,
    event_id: str,
) -> bool:
    tenant_id = body.tenant_id
    if not tenant_id:
        raise ValueError("tenant_id is required for lead event ingestion")

    insert_stmt = (
        pg_insert(LeadEvent)
        .values(
            tenant_id=tenant_id,
            event_id=event_id,
            lead_id=body.lead_id,
            event_type=body.event_type,
            source=body.source,
            payload=body.data,
            occurred_at=body.timestamp,
        )
        .on_conflict_do_nothing(constraint="lead_events_tenant_event_uq")
        .returning(LeadEvent.id)
    )
    res = db.execute(insert_stmt)
    inserted_row = res.first()

    if not inserted_row:
        return False

    # Servertid för all statistik och alla statusfält — klientens timestamp
    # sparas enbart som occurred_at på själva eventet.
    now_ts = datetime.now(timezone.utc)
    event_type = body.event_type

    contact_id = _upsert_contact_from_event(
        db=db, tenant_id=tenant_id, body=body, now_ts=now_ts,
    )

    campaign_id = body.data.get("campaign_id")
    if campaign_id:
        _upsert_campaign_stats(
            db=db, tenant_id=tenant_id, campaign_id=campaign_id,
            campaign_name=body.data.get("campaign_name"),
            event_type=event_type, now_ts=now_ts,
        )

    workflow_id = body.data.get("workflow_id")
    if workflow_id:
        _upsert_workflow_stats(
            db=db, tenant_id=tenant_id, workflow_id=workflow_id,
            workflow_name=body.data.get("workflow_name"),
            event_type=event_type, now_ts=now_ts,
        )

    if event_type in REVENUE_EVENTS:
        amount = body.data.get("amount")
        if amount is not None:
            try:
                amount_dec = Decimal(str(amount))
                currency = body.data.get("currency", "USD")
                _upsert_revenue_snapshot(
                    db=db, tenant_id=tenant_id, day=now_ts.date(),
                    currency=currency, amount=amount_dec,
                )
            except (ValueError, TypeError):
                logger.warning(f"Invalid revenue amount: {amount}")

    if event_type in MESSAGE_RELATED_EVENTS:
        _create_message_log_from_event(
            db=db, tenant_id=tenant_id, contact_id=contact_id,
            body=body, event_id=event_id, now_ts=now_ts,
        )

    if event_type in OPT_OUT_ALL_EVENTS:
        _handle_opt_out_event(
            db=db, tenant_id=tenant_id, contact_id=contact_id,
            body=body, now_ts=now_ts,
        )

    return True


def ingest_with_dead_letter(
    db: Session,
    body: LeadWebhookEvent,
    corr_id: Optional[str],
) -> APIMessage:
    tenant_id = body.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")

    event_id = body.event_id or (
        f"{tenant_id}:{body.lead_id}:{body.event_type}:"
        f"{body.timestamp.isoformat()}"
    )

    try:
        inserted = process_lead_event_core(db=db, body=body, event_id=event_id)

        if not inserted:
            db.commit()
            return APIMessage(
                detail=f"Duplicate event ignored (event_id={event_id}, corr={corr_id or '-'})"
            )

        db.commit()
        return APIMessage(detail=f"Lead event ingested (corr={corr_id or '-'})")

    except Exception as e:
        db.rollback()

        try:
            store_failed_event(
                db=db, tenant_id=tenant_id, event_id=event_id,
                raw_payload=body.model_dump(mode="json"),
                error_message=str(e),
            )
            logger.error(f"Event {event_id} failed and stored in dead letter: {e}")
        except Exception as dl_error:
            logger.error(f"Failed to store dead letter for {event_id}: {dl_error}")

        raise HTTPException(status_code=500, detail=f"Failed to ingest event: {e}")