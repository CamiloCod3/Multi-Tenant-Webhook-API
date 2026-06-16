# backend/alembic/versions/0009_contact_opt_out_events.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_contact_opt_out_events"
down_revision = "0008_contacts_identity_uniques"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_opt_out_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.String(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "contact_opt_out_events_tenant_contact_idx",
        "contact_opt_out_events",
        ["tenant_id", "contact_id"],
    )
    op.create_index(
        "contact_opt_out_events_occurred_at_idx",
        "contact_opt_out_events",
        ["occurred_at"],
    )


def downgrade():
    op.drop_index(
        "contact_opt_out_events_occurred_at_idx",
        table_name="contact_opt_out_events",
    )
    op.drop_index(
        "contact_opt_out_events_tenant_contact_idx",
        table_name="contact_opt_out_events",
    )
    op.drop_table("contact_opt_out_events")