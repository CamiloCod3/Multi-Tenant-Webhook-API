# backend/alembic/versions/0012_feedback_system.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_feedback_system"
down_revision = "0011_add_tenant_dashboard_token"
branch_labels = None
depends_on = None


def upgrade():
    # ── Add google_review_url to tenants ──
    op.add_column(
        "tenants",
        sa.Column("google_review_url", sa.Text(), nullable=True),
    )

    # ── feedback_requests ──
    op.create_table(
        "feedback_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id", sa.String(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("google_review_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="sms"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("issue_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("issue_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("google_review_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("google_review_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json", postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
    )

    op.create_index("feedback_requests_token_uq", "feedback_requests", ["token"], unique=True)
    op.create_index("feedback_requests_tenant_idx", "feedback_requests", ["tenant_id"])
    op.create_index("feedback_requests_tenant_contact_idx", "feedback_requests", ["tenant_id", "contact_id"])
    op.create_index("feedback_requests_tenant_status_idx", "feedback_requests", ["tenant_id", "status"])
    op.create_index(
        "feedback_requests_pending_review_idx",
        "feedback_requests",
        ["google_review_due_at"],
        postgresql_where=sa.text("google_review_sent_at IS NULL AND score IS NOT NULL AND score <= 2"),
    )


def downgrade():
    op.drop_index("feedback_requests_pending_review_idx", table_name="feedback_requests")
    op.drop_index("feedback_requests_tenant_status_idx", table_name="feedback_requests")
    op.drop_index("feedback_requests_tenant_contact_idx", table_name="feedback_requests")
    op.drop_index("feedback_requests_tenant_idx", table_name="feedback_requests")
    op.drop_index("feedback_requests_token_uq", table_name="feedback_requests")
    op.drop_table("feedback_requests")
    op.drop_column("tenants", "google_review_url")