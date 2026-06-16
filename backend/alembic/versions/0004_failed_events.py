# backend/alembic/versions/0004_failed_events.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_failed_events"
down_revision = "0003_sync_revenue_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "failed_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(length=100), nullable=True),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_retry_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_index("failed_events_tenant_idx", "failed_events", ["tenant_id"])
    op.create_index("failed_events_created_at_idx", "failed_events", ["created_at"])


def downgrade():
    op.drop_index("failed_events_created_at_idx", table_name="failed_events")
    op.drop_index("failed_events_tenant_idx", table_name="failed_events")
    op.drop_table("failed_events")