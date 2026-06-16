# backend/app/schemas/webhooks.py
from datetime import datetime
from typing import Any, Dict, Optional, Literal

from pydantic import BaseModel, Field, model_validator


_EVENT_TYPE_ALIASES: dict[str, str] = {
    # ── lead lifecycle ──
    "lead.created": "lead_created",
    "lead_create": "lead_created",
    "lead_created": "lead_created",
    "created": "lead_created",

    "lead.imported": "lead_imported",
    "lead_imported": "lead_imported",
    "imported": "lead_imported",

    # ── contact / outbound ──
    "contacted": "contacted",

    "email.sent": "email_sent",
    "email_sent": "email_sent",

    "sms.sent": "sms_sent",
    "sms_sent": "sms_sent",

    # ── delivery ──
    "email.delivered": "email_delivered",
    "email_delivered": "email_delivered",
    "delivered": "email_delivered",

    "sms.delivered": "sms_delivered",
    "sms_delivered": "sms_delivered",

    # ── engagement ──
    "engaged": "engaged",

    "email.opened": "email_opened",
    "email_opened": "email_opened",
    "opened": "email_opened",
    "open": "email_opened",

    "clicked": "clicked",
    "click": "clicked",
    "link.clicked": "clicked",
    "link_clicked": "clicked",

    "replied": "replied",
    "reply": "replied",
    "email.replied": "replied",
    "email_replied": "replied",

    # ── bounced / failed ──
    "email.bounced": "email_bounced",
    "email_bounced": "email_bounced",
    "bounced": "email_bounced",
    "bounce": "email_bounced",

    "sms.failed": "sms_failed",
    "sms_failed": "sms_failed",

    "email.failed": "email_failed",
    "email_failed": "email_failed",

    # ── conversion / revenue ──
    "converted": "converted",
    "convert": "converted",

    "deal.won": "deal_won",
    "deal_won": "deal_won",
    "won": "deal_won",

    "sale": "sale",

    # ── workflow ──
    "workflow.processed": "workflow_processed",
    "workflow_processed": "workflow_processed",

    "lead.processed": "lead_processed",
    "lead_processed": "lead_processed",

    "step.completed": "step_completed",
    "step_completed": "step_completed",

    "workflow.success": "workflow_success",
    "workflow_success": "workflow_success",
    "success": "workflow_success",

    "workflow.failed": "workflow_failed",
    "workflow_failed": "workflow_failed",

    "failed": "failed",
    "error": "error",

    # ── opt-out / unsubscribe ──
    "opt_out": "opt_out_all",
    "opt.out": "opt_out_all",
    "optout": "opt_out_all",
    "unsubscribe": "opt_out_all",
    "unsubscribe.all": "opt_out_all",
    "opt_out_all": "opt_out_all",

    "opt_out_sms": "opt_out_sms",
    "opt.out.sms": "opt_out_sms",
    "unsubscribe_sms": "opt_out_sms",
    "unsubscribe.sms": "opt_out_sms",
    "sms.opt_out": "opt_out_sms",
    "sms_opt_out": "opt_out_sms",
    "stop": "opt_out_sms",

    "opt_out_email": "opt_out_email",
    "opt.out.email": "opt_out_email",
    "unsubscribe_email": "opt_out_email",
    "unsubscribe.email": "opt_out_email",
    "email.opt_out": "opt_out_email",
    "email_opt_out": "opt_out_email",
    "email.unsubscribe": "opt_out_email",
}


def _normalize_event_type(value: Any) -> Any:
    if value is None:
        return value

    if not isinstance(value, str):
        value = str(value)

    normalized = value.strip().lower()
    if not normalized:
        return normalized

    normalized = normalized.replace("-", "_").replace(" ", "_")
    canonical = _EVENT_TYPE_ALIASES.get(normalized)
    if canonical:
        return canonical

    return normalized.replace(".", "_")

IngestStatus = Literal["ingested", "duplicate", "unknown"]

class LeadWebhookIngestResult(BaseModel):
    detail: str
    status: IngestStatus = "unknown"
    duplicate: bool = False
    tenant_id: str
    tenant_name: str | None = None

class LeadWebhookEvent(BaseModel):
    """
    Generisk payloadmodell for lead-relaterade webhooks.

    Intern canonical representation for event_type ar snake_case.
    Externa system kan skicka t.ex.:
    - lead.created
    - sms.sent
    - opt.out.sms
    - unsubscribe
    Dessa normaliseras innan ingest-logiken kors.
    """

    tenant_id: Optional[str] = Field(default=None, min_length=1)

    lead_id: str = Field(min_length=1, max_length=100)

    event_id: Optional[str] = Field(
        default=None,
        max_length=255,
        description=(
            "Idempotency key for eventet. Om samma event skickas flera ganger, "
            "ateranvand detta varde."
        ),
    )

    event_type: str = Field(
        min_length=1,
        max_length=50,
        description=(
            "Canonical lagras internt som snake_case, t.ex. "
            "lead_created, email_sent, deal_won, opt_out_sms. "
            "Inkommande dotted names och vanliga alias normaliseras automatiskt."
        ),
    )

    source: Optional[str] = Field(default=None, max_length=50)

    timestamp: datetime

    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Ra payload fran CRM/n8n (mappas till LeadEvent.payload)",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_and_pack_payload(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        # 1) timestamp alias -> timestamp
        if "timestamp" not in values:
            for k in ("occurred_at", "created_at"):
                if k in values and values[k] is not None:
                    values["timestamp"] = values[k]
                    break

        # 2) event_type -> canonical snake_case
        if "event_type" in values and values["event_type"] is not None:
            values["event_type"] = _normalize_event_type(values["event_type"])

        # 3) Packa "allt annat" in i data om data saknas/ar tom
        incoming_data = values.get("data")
        if not incoming_data:
            top_fields = {
                "tenant_id",
                "lead_id",
                "event_id",
                "event_type",
                "source",
                "timestamp",
                "occurred_at",
                "created_at",
                "data",
            }
            packed = {k: v for k, v in values.items() if k not in top_fields}
            values["data"] = packed

        return values