# backend/alembic/versions/0011_add_tenant_dashboard_token.py
import secrets

from alembic import op
import sqlalchemy as sa

revision = "0011_add_tenant_dashboard_token"
down_revision = "0010_auto_updated_at_trigger"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenants",
        sa.Column("dashboard_token", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "tenants_dashboard_token_uq",
        "tenants",
        ["dashboard_token"],
        unique=True,
    )

    # Backfill existing tenants
    op.execute(
        "UPDATE tenants "
        "SET dashboard_token = md5(random()::text || clock_timestamp()::text || 'dash') "
        "WHERE dashboard_token IS NULL;"
    )

    op.alter_column("tenants", "dashboard_token", nullable=False)


def downgrade():
    op.drop_index("tenants_dashboard_token_uq", table_name="tenants")
    op.drop_column("tenants", "dashboard_token")