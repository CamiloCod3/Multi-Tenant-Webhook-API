# backend/app/models/audit_log.py
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    __table_args__ = (
        sa.Index("audit_logs_tenant_id_idx", "tenant_id"),
        sa.Index("audit_logs_created_at_idx", "created_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)

    tenant_id: Mapped[str] = mapped_column(
        sa.String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    actor: Mapped[str | None] = mapped_column(sa.String(320), nullable=True)
    action: Mapped[str] = mapped_column(sa.String(100), nullable=False)

    meta: Mapped[dict] = mapped_column(
        sa.JSON,
        nullable=True,
        server_default=sa.text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )