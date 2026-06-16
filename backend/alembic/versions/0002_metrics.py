from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Anpassa om du vill, men se till att filnamn och revision matchar
revision = "0002_leads_and_metrics"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade():
    # --- Campaign stats per tenant & campaign ---
    op.create_table(
        "campaign_stats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.String(length=100), nullable=False),
        sa.Column("campaign_name", sa.String(length=200), nullable=True),

        sa.Column("total_leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacted_leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engaged_leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("converted_leads", sa.Integer(), nullable=False, server_default="0"),

        sa.Column("last_lead_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "campaign_stats_tenant_campaign_uq",
        "campaign_stats",
        ["tenant_id", "campaign_id"],
        unique=True,
    )
    op.create_index(
        "campaign_stats_tenant_id_idx",
        "campaign_stats",
        ["tenant_id"],
    )

    # --- Workflow stats per tenant & workflow ---
    op.create_table(
        "workflow_stats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_id", sa.String(length=100), nullable=False),
        sa.Column("workflow_name", sa.String(length=200), nullable=True),

        sa.Column("processed_leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_leads", sa.Integer(), nullable=False, server_default="0"),

        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "workflow_stats_tenant_workflow_uq",
        "workflow_stats",
        ["tenant_id", "workflow_id"],
        unique=True,
    )
    op.create_index(
        "workflow_stats_tenant_id_idx",
        "workflow_stats",
        ["tenant_id"],
    )

        # --- Lead events (event-stream från workflows / n8n) ---
    op.create_table(
        "lead_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 🔑 Idempotency key – unik per logisk event
        sa.Column("event_id", sa.String(length=100), nullable=False),

        sa.Column("lead_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Index & unique constraints
    op.create_index(
        "lead_events_event_id_uq",
        "lead_events",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "lead_events_tenant_lead_idx",
        "lead_events",
        ["tenant_id", "lead_id"],
    )
    op.create_index(
        "lead_events_tenant_event_type_idx",
        "lead_events",
        ["tenant_id", "event_type"],
    )
    op.create_index(
        "lead_events_occurred_at_idx",
        "lead_events",
        ["occurred_at"],
    )


    # --- Revenue snapshots (periodvisa intäkter per tenant) ---
    op.create_table(
        "revenue_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DATE(), nullable=False),
        sa.Column("period_end", sa.DATE(), nullable=False),

        sa.Column(
            "total_revenue",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "attributed_revenue",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("currency", sa.String(length=10), nullable=False),

        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # unique: en rad per (tenant, period, currency)
    op.create_unique_constraint(
        "revenue_snapshots_tenant_period_currency_uq",
        "revenue_snapshots",
        ["tenant_id", "period_start", "period_end", "currency"],
    )
    op.create_index(
        "revenue_snapshots_tenant_id_idx",
        "revenue_snapshots",
        ["tenant_id"],
    )


def downgrade():
    # Revenue snapshots
    op.drop_index("revenue_snapshots_tenant_id_idx", table_name="revenue_snapshots")
    op.drop_constraint(
        "revenue_snapshots_tenant_period_currency_uq",
        "revenue_snapshots",
        type_="unique",
    )
    op.drop_table("revenue_snapshots")

    
    # Lead events
    op.drop_index("lead_events_occurred_at_idx", table_name="lead_events")
    op.drop_index("lead_events_tenant_event_type_idx", table_name="lead_events")
    op.drop_index("lead_events_tenant_lead_idx", table_name="lead_events")
    op.drop_index("lead_events_event_id_uq", table_name="lead_events")
    op.drop_table("lead_events")

    # Workflow stats
    op.drop_index("workflow_stats_tenant_id_idx", table_name="workflow_stats")
    op.drop_index("workflow_stats_tenant_workflow_uq", table_name="workflow_stats")
    op.drop_table("workflow_stats")

    # Campaign stats
    op.drop_index("campaign_stats_tenant_id_idx", table_name="campaign_stats")
    op.drop_index("campaign_stats_tenant_campaign_uq", table_name="campaign_stats")
    op.drop_table("campaign_stats")
