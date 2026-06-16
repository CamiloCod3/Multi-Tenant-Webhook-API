# backend/app/models/message_log.py
from datetime import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class MessageLog(Base):
    __tablename__ = "message_logs"

    __table_args__ = (
        sa.Index("message_logs_tenant_contact_idx", "tenant_id", "contact_id"),
        sa.Index("message_logs_tenant_channel_idx", "tenant_id", "channel"),
        sa.Index("message_logs_tenant_status_idx", "tenant_id", "status"),
        sa.Index("message_logs_tenant_created_at_idx", "tenant_id", "created_at"),
        sa.Index(
            "message_logs_tenant_provider_message_idx",
            "tenant_id",
            "provider_message_id",
        ),
    )

    id: Mapped[str] = mapped_column(sa.String, primary_key=True, default=gen_uuid)

    # Composite indexes i __table_args__ tacker tenant_id- och contact_id-queries.
    tenant_id: Mapped[str] = mapped_column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    contact_id: Mapped[str] = mapped_column(
        sa.String,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )

    campaign_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    event_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    channel: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    direction: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default="outbound",
    )

    provider: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    template_key: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    subject: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    status: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        server_default="queued",
    )

    failure_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )