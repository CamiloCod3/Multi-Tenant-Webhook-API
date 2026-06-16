from alembic import op
import sqlalchemy as sa

# Anpassa namnet om du vill, men behåll kopplingen
revision = "0003_sync_revenue_snapshots"
down_revision = "0002_leads_and_metrics"
branch_labels = None
depends_on = None


def upgrade():
    # Ändra precision på belopp från Numeric(12,2) → Numeric(18,2)
    op.alter_column(
        "revenue_snapshots",
        "total_revenue",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(18, 2),
        existing_nullable=False,
        server_default="0",
    )
    op.alter_column(
        "revenue_snapshots",
        "attributed_revenue",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(18, 2),
        existing_nullable=False,
        server_default="0",
    )

    # Sätt server_default på currency till "USD" så det matchar modellen
    op.alter_column(
        "revenue_snapshots",
        "currency",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        server_default="USD",
    )


def downgrade():
    # Backa precisionen till Numeric(12,2) och ta bort server_defaults
    op.alter_column(
        "revenue_snapshots",
        "currency",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "revenue_snapshots",
        "attributed_revenue",
        existing_type=sa.Numeric(18, 2),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "revenue_snapshots",
        "total_revenue",
        existing_type=sa.Numeric(18, 2),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
        server_default=None,
    )
