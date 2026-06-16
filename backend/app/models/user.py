# backend/app/models/user.py
from datetime import datetime
import uuid

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Boolean, text, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT

from ..core.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="users_tenant_email_uq"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)

    # Unique constraint pa (tenant_id, email) tacker tenant_id-only queries.
    # Email-only lookup behovs inte i multi-tenant context.
    tenant_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        CITEXT(),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(20), default="admin")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )