# backend/alembic/versions/0005_add_tenant_webhook_token.py
from alembic import op
import sqlalchemy as sa

revision = "0005_add_tenant_webhook_token"
down_revision = "0004_failed_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenants",
        sa.Column("webhook_token", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "tenants_webhook_token_uq",
        "tenants",
        ["webhook_token"],
        unique=True,
    )

    # Backfill för befintliga tenants
    op.execute(
        "UPDATE tenants "
        "SET webhook_token = md5(random()::text || clock_timestamp()::text) "
        "WHERE webhook_token IS NULL;"
    )

    op.alter_column("tenants", "webhook_token", nullable=False)


def downgrade():
    op.drop_index("tenants_webhook_token_uq", table_name="tenants")
    op.drop_column("tenants", "webhook_token")
