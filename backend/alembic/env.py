# backend/alembic/env.py
from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app.core.config import settings
from app.core.db import Base

from app.models.audit_log import AuditLog  # noqa: F401
from app.models.contacts import Contact  # noqa: F401
from app.models.contact_opt_out_event import ContactOptOutEvent  # noqa: F401
from app.models.message_log import MessageLog  # noqa: F401
from app.models.metrics import (  # noqa: F401
    CampaignStats,
    FailedEvent,
    LeadEvent,
    RevenueSnapshot,
    WorkflowStats,
)
from app.models.tenant import Tenant  # noqa: F401
from app.models.user import User  # noqa: F401

target_metadata = Base.metadata


def get_url() -> str:
    return settings.database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
