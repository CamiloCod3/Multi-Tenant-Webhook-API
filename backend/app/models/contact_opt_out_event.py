# backend/app/models/contact_opt_out_event.py
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class ContactOptOutEvent(Base):
    __tablename__ = "contact_opt_out_events"

    __table_args__ = (
        sa.Index("contact_opt_out_events_tenant_contact_idx", "tenant_id", "contact_id"),
        sa.Index("contact_opt_out_events_occurred_at_idx", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)

    # Composite index i __table_args__ tacker tenant_id- och contact_id-queries.
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

    channel: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )