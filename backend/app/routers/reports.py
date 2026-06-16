# backend/app/routers/reports.py
"""
Tenant-scoped usage reporting endpoints.

These endpoints summarize message, event, contact, and revenue activity for a
selected time period. They are kept generic so the project remains usable as a
portfolio-ready multi-tenant backend example.
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, and_
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.deps import require_admin_token
from ..core.rate_limit import limiter

from ..models.message_log import MessageLog
from ..models.contacts import Contact
from ..models.metrics import LeadEvent, RevenueSnapshot
from ..models.tenant import Tenant

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/reports", tags=["reports"])


@router.get("/usage")
@limiter.limit("30/minute")
def usage_report(
    request: Request,
    tenant_id: str,
    date_from: date = Query(description="Start date (YYYY-MM-DD)"),
    date_to: date = Query(description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """
    Returns a tenant usage report for a selected date range.

    The report includes message volume, event volume, contact creation, and
    revenue/conversion totals so it can be used for operational dashboards,
    usage reviews, or billing-style summaries.
    """
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    msg_filter = and_(
        MessageLog.tenant_id == tenant_id,
        MessageLog.created_at >= dt_from,
        MessageLog.created_at <= dt_to,
    )

    evt_filter = and_(
        LeadEvent.tenant_id == tenant_id,
        LeadEvent.occurred_at >= dt_from,
        LeadEvent.occurred_at <= dt_to,
    )

    message_breakdown = db.execute(
        select(
            MessageLog.channel,
            MessageLog.direction,
            func.count().label("cnt"),
        )
        .where(msg_filter)
        .group_by(MessageLog.channel, MessageLog.direction)
    ).all()

    sms_out = 0
    sms_in = 0
    email_out = 0
    email_in = 0
    for channel, direction, count in message_breakdown:
        if channel == "sms" and direction == "outbound":
            sms_out = count
        elif channel == "sms" and direction == "inbound":
            sms_in = count
        elif channel == "email" and direction == "outbound":
            email_out = count
        elif channel == "email" and direction == "inbound":
            email_in = count

    total_messages = sms_out + sms_in + email_out + email_in

    sms_status_rows = db.execute(
        select(MessageLog.status, func.count().label("cnt"))
        .where(msg_filter, MessageLog.channel == "sms", MessageLog.direction == "outbound")
        .group_by(MessageLog.status)
    ).all()
    sms_status_breakdown = {row[0]: row[1] for row in sms_status_rows}

    daily_sms = db.execute(
        select(
            func.date_trunc("day", MessageLog.created_at).label("day"),
            func.count().label("cnt"),
        )
        .where(msg_filter, MessageLog.channel == "sms", MessageLog.direction == "outbound")
        .group_by("day").order_by("day")
    ).all()
    daily_sms_breakdown = [{"date": row[0].strftime("%Y-%m-%d"), "count": row[1]} for row in daily_sms]

    daily_email = db.execute(
        select(
            func.date_trunc("day", MessageLog.created_at).label("day"),
            func.count().label("cnt"),
        )
        .where(msg_filter, MessageLog.channel == "email", MessageLog.direction == "outbound")
        .group_by("day").order_by("day")
    ).all()
    daily_email_breakdown = [{"date": row[0].strftime("%Y-%m-%d"), "count": row[1]} for row in daily_email]

    unique_sms = db.scalar(
        select(func.count(func.distinct(MessageLog.contact_id)))
        .where(msg_filter, MessageLog.channel == "sms", MessageLog.direction == "outbound")
    ) or 0

    unique_email = db.scalar(
        select(func.count(func.distinct(MessageLog.contact_id)))
        .where(msg_filter, MessageLog.channel == "email", MessageLog.direction == "outbound")
    ) or 0

    total_events = db.scalar(
        select(func.count()).select_from(LeadEvent).where(evt_filter)
    ) or 0

    new_leads = db.scalar(
        select(func.count()).select_from(LeadEvent)
        .where(evt_filter, LeadEvent.event_type == "lead_created")
    ) or 0

    rev_filter = and_(
        RevenueSnapshot.tenant_id == tenant_id,
        RevenueSnapshot.created_at >= dt_from,
        RevenueSnapshot.created_at <= dt_to,
    )
    total_revenue = float(db.scalar(
        select(func.coalesce(func.sum(RevenueSnapshot.attributed_revenue), 0))
        .where(rev_filter)
    ) or 0)

    new_contacts = db.scalar(
        select(func.count()).select_from(Contact)
        .where(
            Contact.tenant_id == tenant_id,
            Contact.created_at >= dt_from,
            Contact.created_at <= dt_to,
        )
    ) or 0

    sms_messages = db.execute(
        select(
            MessageLog.id,
            MessageLog.contact_id,
            MessageLog.status,
            MessageLog.provider,
            MessageLog.provider_message_id,
            MessageLog.body,
            MessageLog.created_at,
        )
        .where(msg_filter, MessageLog.channel == "sms", MessageLog.direction == "outbound")
        .order_by(MessageLog.created_at.asc())
        .limit(1000)
    ).all()

    sms_message_list = [{
        "id": row[0],
        "contact_id": row[1],
        "status": row[2],
        "provider": row[3],
        "provider_message_id": row[4],
        "body_preview": (row[5] or "")[:80],
        "sent_at": row[6].isoformat() if row[6] else None,
    } for row in sms_messages]

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "period_from": date_from.isoformat(),
        "period_to": date_to.isoformat(),
        "total_messages": total_messages,
        "total_events": total_events,
        "new_leads": new_leads,
        "new_contacts": new_contacts,
        "total_revenue": total_revenue,
        "sms_outbound": sms_out,
        "sms_inbound": sms_in,
        "sms_unique_contacts": unique_sms,
        "sms_status_breakdown": sms_status_breakdown,
        "sms_daily": daily_sms_breakdown,
        "sms_messages": sms_message_list,
        "email_outbound": email_out,
        "email_inbound": email_in,
        "email_unique_contacts": unique_email,
        "email_daily": daily_email_breakdown,
    }
