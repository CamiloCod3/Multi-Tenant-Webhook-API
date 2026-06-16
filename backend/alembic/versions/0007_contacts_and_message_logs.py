from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import CITEXT

revision = "0007_contacts_and_message_logs"
down_revision = "0006_widen_event_id_to_255"
branch_labels = None
depends_on = None


def upgrade():
    # Säkerställ CITEXT innan contacts.email skapas
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # ---------------------------
    # contacts
    # ---------------------------
    op.create_table(
        "contacts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_contact_id", sa.String(length=120), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=True),
        sa.Column("last_name", sa.String(length=120), nullable=True),
        sa.Column("email", CITEXT(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("normalized_phone", sa.String(length=50), nullable=True),
        sa.Column("registration_number", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "member_status",
            sa.String(length=50),
            nullable=False,
            server_default="non_member",
        ),
        sa.Column(
            "is_member",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "opted_out_sms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "opted_out_email",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("opt_out_reason", sa.String(length=255), nullable=True),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consent_sms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "consent_email",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_message_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_engagement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_unique_constraint(
        "contacts_tenant_external_contact_uq",
        "contacts",
        ["tenant_id", "external_contact_id"],
    )
    op.create_index("contacts_tenant_id_idx", "contacts", ["tenant_id"])
    op.create_index("contacts_tenant_email_idx", "contacts", ["tenant_id", "email"])
    op.create_index(
        "contacts_tenant_phone_idx",
        "contacts",
        ["tenant_id", "normalized_phone"],
    )
    op.create_index("contacts_tenant_status_idx", "contacts", ["tenant_id", "status"])

    # ---------------------------
    # message_logs
    # ---------------------------
    op.create_table(
        "message_logs",
        sa.Column("id", sa.String(), primary_key=True),
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
        sa.Column("campaign_id", sa.String(length=100), nullable=True),
        sa.Column("workflow_id", sa.String(length=100), nullable=True),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column(
            "direction",
            sa.String(length=20),
            nullable=False,
            server_default="outbound",
        ),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("template_key", sa.String(length=100), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("message_logs_tenant_id_idx", "message_logs", ["tenant_id"])
    op.create_index("message_logs_contact_id_idx", "message_logs", ["contact_id"])
    op.create_index(
        "message_logs_tenant_contact_idx",
        "message_logs",
        ["tenant_id", "contact_id"],
    )
    op.create_index(
        "message_logs_tenant_channel_idx",
        "message_logs",
        ["tenant_id", "channel"],
    )
    op.create_index(
        "message_logs_tenant_status_idx",
        "message_logs",
        ["tenant_id", "status"],
    )
    op.create_index(
        "message_logs_tenant_created_at_idx",
        "message_logs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "message_logs_tenant_provider_message_idx",
        "message_logs",
        ["tenant_id", "provider_message_id"],
    )

    # ---------------------------
    # lead_events unique fix
    # ---------------------------
    op.drop_index("lead_events_event_id_uq", table_name="lead_events")
    op.create_unique_constraint(
        "lead_events_tenant_event_uq",
        "lead_events",
        ["tenant_id", "event_id"],
    )


def downgrade():
    op.drop_constraint("lead_events_tenant_event_uq", "lead_events", type_="unique")
    op.create_index("lead_events_event_id_uq", "lead_events", ["event_id"], unique=True)

    op.drop_index("message_logs_tenant_provider_message_idx", table_name="message_logs")
    op.drop_index("message_logs_tenant_created_at_idx", table_name="message_logs")
    op.drop_index("message_logs_tenant_status_idx", table_name="message_logs")
    op.drop_index("message_logs_tenant_channel_idx", table_name="message_logs")
    op.drop_index("message_logs_tenant_contact_idx", table_name="message_logs")
    op.drop_index("message_logs_contact_id_idx", table_name="message_logs")
    op.drop_index("message_logs_tenant_id_idx", table_name="message_logs")
    op.drop_table("message_logs")

    op.drop_index("contacts_tenant_status_idx", table_name="contacts")
    op.drop_index("contacts_tenant_phone_idx", table_name="contacts")
    op.drop_index("contacts_tenant_email_idx", table_name="contacts")
    op.drop_index("contacts_tenant_id_idx", table_name="contacts")
    op.drop_constraint(
        "contacts_tenant_external_contact_uq",
        "contacts",
        type_="unique",
    )
    op.drop_table("contacts")