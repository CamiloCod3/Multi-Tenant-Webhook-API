# backend/app/models/contacts.py
from datetime import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Contact(Base):
    __tablename__ = "contacts"

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "external_contact_id",
            name="contacts_tenant_external_contact_uq",
        ),
        sa.Index(
            "contacts_tenant_email_uq",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=sa.text("email IS NOT NULL"),
        ),
        sa.Index(
            "contacts_tenant_normalized_phone_uq",
            "tenant_id",
            "normalized_phone",
            unique=True,
            postgresql_where=sa.text("normalized_phone IS NOT NULL"),
        ),
        sa.Index("contacts_tenant_status_idx", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(sa.String, primary_key=True, default=gen_uuid)

    # Composite indexes i __table_args__ tacker tenant_id-only queries.
    tenant_id: Mapped[str] = mapped_column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    external_contact_id: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)

    first_name: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)

    email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)

    registration_number: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)

    source: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        server_default="new",
    )

    member_status: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        server_default="non_member",
    )
    is_member: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )

    opted_out_sms: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    opted_out_email: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    opt_out_reason: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    consent_sms: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    consent_email: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )

    tags: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    last_message_sent_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    last_engagement_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )