# backend/app/models/tenant.py
from datetime import datetime
import uuid
import secrets

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, text, DateTime

from ..core.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def gen_webhook_token() -> str:
    return secrets.token_hex(32)


def gen_dashboard_token() -> str:
    return secrets.token_hex(32)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="basic")

    webhook_token: Mapped[str] = mapped_column(
        String(128), unique=True, default=gen_webhook_token,
    )
    dashboard_token: Mapped[str] = mapped_column(
        String(128), unique=True, default=gen_dashboard_token,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
