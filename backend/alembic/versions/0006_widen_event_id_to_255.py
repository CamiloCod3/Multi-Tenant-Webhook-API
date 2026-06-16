"""widen event_id columns to 255 chars

Revision ID: 0006_widen_event_id_to_255
Revises: 0005_add_tenant_webhook_token
Create Date: 2026-01-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_widen_event_id_to_255"
down_revision = "0005_add_tenant_webhook_token"
branch_labels = None
depends_on = None


def upgrade():
    # lead_events.event_id: 100 -> 255
    op.alter_column(
        "lead_events",
        "event_id",
        existing_type=sa.String(length=100),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    # failed_events.event_id: 100 -> 255
    op.alter_column(
        "failed_events",
        "event_id",
        existing_type=sa.String(length=100),
        type_=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade():
    # ⚠️ Downgrade kan FAILA om det finns data > 100 chars
    # Kör endast om du vet vad du gör

    op.alter_column(
        "lead_events",
        "event_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=100),
        existing_nullable=False,
    )

    op.alter_column(
        "failed_events",
        "event_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
